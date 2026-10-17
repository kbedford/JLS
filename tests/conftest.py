import copy
import os
import pytest
import psycopg
from psycopg.rows import dict_row
from jls.database import migrate


@pytest.fixture
def catalogue():
    return {"schema_version": 1, "catalogue_id": "test-catalogue", "version": "1",
            "source": {"classification": "synthetic"}, "rules": [{
                "id": "synthetic-parity", "title": "Synthetic parity fixture",
                "pattern": r"TESTCHIP\(\d+\).*parity error", "enabled": True,
                "positive_examples": ["TESTCHIP(4): parity error"],
                "negative_examples": ["TESTCHIP(4): parity corrected"],
                "kb_references": [], "pr_references": [],
                "sources": [{"actions": "Synthetic test guidance only."}], "version_notes": []}]}


@pytest.fixture
def event():
    return {"@timestamp": "2026-10-16T12:00:00.123456Z", "source_ip": "192.0.2.5",
            "message": "Oct 16 12:00:00 router-a fpc2 TESTCHIP(4): parity error"}


@pytest.fixture
def connector():
    dsn = os.getenv("JLS_TEST_DSN")
    if not dsn:
        pytest.skip("Set JLS_TEST_DSN to an isolated disposable PostgreSQL database")
    def connect():
        return psycopg.connect(dsn, row_factory=dict_row)
    with connect() as conn:
        migrate(conn)
        conn.execute("TRUNCATE jls.syslog_hits,jls.events,jls.rejected_events,jls.error_patterns,jls.catalogues CASCADE")
    return connect
