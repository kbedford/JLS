import json
import os
import threading
import time
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from .catalogue import digest, match, validate
from .parser import parse


def connect():
    return psycopg.connect(host=os.getenv("DB_HOST", "postgres"), port=os.getenv("DB_PORT", "5432"),
                          dbname=os.getenv("DB_NAME", "jls"), user=os.getenv("DB_USER", "jls_app"),
                          password=os.environ["DB_PASSWORD"], connect_timeout=5,
                          options="-c statement_timeout=15000 -c lock_timeout=5000",
                          row_factory=dict_row)


def migrate(conn):
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(734812901)")
        # CREATE SCHEMA IF NOT EXISTS still requires database CREATE privilege.
        # Production bootstrap already creates this schema for the restricted app role.
        if not conn.execute("SELECT 1 FROM pg_namespace WHERE nspname='jls'").fetchone():
            conn.execute("CREATE SCHEMA jls")
        conn.execute(Path(__file__).with_name("schema.sql").read_text())


def import_catalogue(conn, data):
    validate(data)  # All-or-nothing: validate every rule before deleting or updating anything.
    checksum = digest(data)
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(734812902)")
        old = conn.execute("SELECT digest FROM jls.catalogues WHERE catalogue_id=%s", (data["catalogue_id"],)).fetchone()
        if old and old["digest"] == checksum:
            return False
        conn.execute("""INSERT INTO jls.catalogues(catalogue_id,version,digest,source)
            VALUES(%s,%s,%s,%s) ON CONFLICT(catalogue_id) DO UPDATE
            SET version=excluded.version,digest=excluded.digest,source=excluded.source,updated_at=now()""",
                     (data["catalogue_id"], data["version"], checksum, Jsonb(data.get("source", {}))))
        conn.execute("DELETE FROM jls.error_patterns WHERE catalogue_id=%s", (data["catalogue_id"],))
        for r in data["rules"]:
            conn.execute("INSERT INTO jls.error_patterns VALUES(%s,%s,%s,%s,%s,%s)",
                         (data["catalogue_id"], r["id"], r["title"], r["pattern"], r["enabled"], Jsonb(r)))
    return True


class Store:
    def __init__(self, connector=connect, catalogue_id=None, reload_seconds=30):
        self.connector = connector
        self.catalogue_id = catalogue_id or os.environ.get("CATALOGUE_ID", "health-check-fpc-errors")
        self.reload_seconds = reload_seconds
        self.lock = threading.Lock()
        self.snapshot = None
        self.loaded_at = 0

    def catalogue(self, conn, force=False):
        with self.lock:
            if self.snapshot is not None and not force and time.monotonic() - self.loaded_at < self.reload_seconds:
                return self.snapshot
            # One statement gives a consistent catalogue/version snapshot during imports.
            rows = conn.execute("""SELECT c.version,c.digest,p.metadata,p.id,p.title,p.pattern,p.enabled
                FROM jls.catalogues c JOIN jls.error_patterns p USING(catalogue_id)
                WHERE c.catalogue_id=%s ORDER BY p.id""", (self.catalogue_id,)).fetchall()
            if not rows:
                raise ValueError("No catalogue installed")
            rules = [dict(r["metadata"], id=r["id"], title=r["title"], pattern=r["pattern"], enabled=r["enabled"]) for r in rows]
            data = {"schema_version": 1, "catalogue_id": self.catalogue_id, "version": rows[0]["version"], "rules": rules}
            compiled = validate(data)
            self.snapshot = (data, compiled, digest(data))
            self.loaded_at = time.monotonic()
            return self.snapshot

    def ingest(self, event, replay=False):
        parsed = parse(event, os.environ.get("SYSLOG_TIMEZONE", "UTC"))
        with self.connector() as conn:
            data, compiled, checksum = self.catalogue(conn)
            hits, errors = match(parsed["message"], compiled)
            # Insert, hit snapshots and commit all succeed before the HTTP acknowledgement.
            row = conn.execute("""INSERT INTO jls.events
                (event_id,received_at,event_time,device,source_ip,fpc,pfe,asic,routing_engine,
                 cm_severity,syslog_severity,error_code,stream,timestamp_source,message,
                 parse_warnings,evaluation_errors,catalogue_digest)
                VALUES(%(event_id)s,%(received_at)s,%(event_time)s,%(device)s,%(source_ip)s,%(fpc)s,
                 %(pfe)s,%(asic)s,%(routing_engine)s,%(cm_severity)s,%(syslog_severity)s,%(error_code)s,
                 %(stream)s,%(timestamp_source)s,%(message)s,%(parse_warnings)s,%(evaluation_errors)s,
                 %(catalogue_digest)s) ON CONFLICT DO NOTHING RETURNING event_id""",
                dict(parsed, parse_warnings=Jsonb(parsed["parse_warnings"]), evaluation_errors=Jsonb(errors), catalogue_digest=checksum)).fetchone()
            if not row and not replay:
                return {"status": "duplicate", "event_id": parsed["event_id"]}
            if replay:
                conn.execute("SELECT event_id FROM jls.events WHERE event_id=%s FOR UPDATE", (parsed["event_id"],))
                conn.execute("DELETE FROM jls.syslog_hits WHERE event_id=%s", (parsed["event_id"],))
                conn.execute("UPDATE jls.events SET evaluation_errors=%s,catalogue_digest=%s WHERE event_id=%s",
                             (Jsonb(errors), checksum, parsed["event_id"]))
            for rule in hits:
                conn.execute("""INSERT INTO jls.syslog_hits VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                             (parsed["event_id"], self.catalogue_id, rule["id"], data["version"], Jsonb(rule)))
        return {"status": "partial" if errors else "stored", "event_id": parsed["event_id"], "matches": len(hits)}

    def reject(self, payload, reason):
        with self.connector() as conn:
            conn.execute("INSERT INTO jls.rejected_events(reason,payload) VALUES(%s,%s)", (reason, Jsonb(payload)))

    def health(self):
        with self.connector() as conn:
            data, compiled, _ = self.catalogue(conn)
            conn.execute("SELECT 1")
        return {"status": "ready", "catalogue_version": data["version"], "active_rules": len(compiled)}

    def retain(self, days):
        if days < 1:
            raise ValueError("Retention must be at least one day")
        with self.connector() as conn:
            # Bounded batches prevent a long maintenance transaction from blocking ingestion.
            conn.execute("""DELETE FROM jls.events WHERE event_id IN
                (SELECT event_id FROM jls.events WHERE stored_at < now() - %s * interval '1 day' LIMIT 10000)""", (days,))
            conn.execute("""DELETE FROM jls.rejected_events WHERE id IN
                (SELECT id FROM jls.rejected_events WHERE received_at < now() - %s * interval '1 day' LIMIT 10000)""", (days,))
