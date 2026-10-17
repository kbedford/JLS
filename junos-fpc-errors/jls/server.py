"""Private ingestion endpoint. The authenticated collector is the sole writer."""
import hmac
import json
import logging
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import psycopg

LOG = logging.getLogger(__name__)
MAX_BODY = 262144


class Server(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def __init__(self, address, store, token):
        if len(token) < 32:
            raise ValueError("INGEST_TOKEN must be at least 32 characters")
        self.store, self.token = store, token
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(address, Handler)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(10)
        super().setup()

    def log_message(self, fmt, *args):
        # Do not log payloads, raw request paths, tokens or network device data.
        pass

    def reply(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/health":
            return self.reply(404, {"error": "not_found"})
        try:
            self.reply(200, self.server.store.health())
        except Exception:
            self.reply(503, {"status": "not_ready"})

    def do_POST(self):
        if self.path != "/events":
            return self.reply(404, {"error": "not_found"})
        auth = self.headers.get("Authorization", "")
        if not hmac.compare_digest(auth, "Bearer " + self.server.token):
            return self.reply(401, {"error": "unauthorized"})
        if self.headers.get("Transfer-Encoding"):
            return self.reply(400, {"error": "chunked_requests_not_supported"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.reply(400, {"error": "invalid_length"})
        if length < 1 or length > MAX_BODY:
            return self.reply(413, {"error": "invalid_body_size"})
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                return self.reply(400, {"error": "incomplete_body"})
            try:
                event = json.loads(raw)
            except (ValueError, UnicodeError):
                self.server.store.reject({"raw": raw.decode("utf-8", errors="replace").replace("\x00", "\\u0000")}, "invalid_json")
                return self.reply(200, {"status": "quarantined"})
            try:
                result = self.server.store.ingest(event)
            except (TypeError, ValueError) as exc:
                # Catalogue failure must retry, not silently quarantine a valid event.
                from .parser import parse
                try:
                    parse(event, os.environ.get("SYSLOG_TIMEZONE", "UTC"))
                except (TypeError, ValueError, AttributeError):
                    safe = json.loads(json.dumps(event).replace("\\u0000", "\\\\u0000"))
                    self.server.store.reject(safe, type(exc).__name__)
                    return self.reply(200, {"status": "quarantined"})
                raise
            self.reply(200, result)
        except (socket.timeout, TimeoutError):
            self.reply(503, {"error": "retry"})
        except Exception as exc:
            LOG.warning("Ingestion failed: %s", type(exc).__name__)
            self.reply(503, {"error": "retry"})
