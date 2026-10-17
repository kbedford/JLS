import argparse
import json
import logging
import os
import signal
import threading
import time
from zoneinfo import ZoneInfo
from .catalogue import read_catalogue
from .database import Store, connect, import_catalogue, migrate
from .server import Server


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["serve", "validate", "import", "replay"])
    p.add_argument("path", nargs="?")
    args = p.parse_args()
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    if args.command in ("validate", "import"):
        data = read_catalogue(args.path or os.environ["CATALOGUE_PATH"])
        if args.command == "import":
            with connect() as conn:
                migrate(conn)
                import_catalogue(conn, data)
        print(json.dumps({"rules": len(data["rules"]), "version": data["version"], "valid": True}))
        return
    if args.command == "replay":
        if not args.path:
            p.error("replay requires a JSONL file containing original @timestamp, source_ip and message")
        store = Store()
        with open(args.path) as f:
            for line in f:
                print(json.dumps(store.ingest(json.loads(line), replay=True)))
        return
    ZoneInfo(os.getenv("SYSLOG_TIMEZONE", "UTC"))
    data = read_catalogue(os.environ["CATALOGUE_PATH"])
    # Bounded startup retries; Compose restarts the service if dependencies stay unavailable.
    for attempt in range(12):
        try:
            with connect() as conn:
                migrate(conn)
                import_catalogue(conn, data)
            break
        except Exception as exc:
            logging.warning("Startup attempt %s failed: %s", attempt + 1, type(exc).__name__)
            if attempt == 11:
                raise
            time.sleep(min(2 ** attempt, 10))
    store = Store(catalogue_id=data["catalogue_id"])
    store.health()
    server = Server(("0.0.0.0", 8080), store, os.environ["INGEST_TOKEN"])
    stop = threading.Event()
    def shutdown(*_):
        stop.set()
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    days = int(os.getenv("RETENTION_DAYS", "30"))
    if days < 1:
        raise ValueError("RETENTION_DAYS must be positive")
    def maintenance():
        while not stop.wait(60):
            try:
                store.retain(days)
            except Exception as exc:
                logging.warning("Retention failed: %s", type(exc).__name__)
    threading.Thread(target=maintenance, daemon=True).start()
    try:
        server.serve_forever()
    finally:
        stop.set()
        server.server_close()


if __name__ == "__main__":
    main()
