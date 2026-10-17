"""Actual document rules exercised with synthetic, non-customer syslog events."""
import copy
import json
from pathlib import Path
import pytest
from jls.catalogue import read_catalogue, validate, match
from jls.parser import parse
from jls.database import Store, import_catalogue
ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / 'examples/junos-demo.json').read_text())
CATALOGUE = read_catalogue(ROOT / 'catalogue/catalogue.json')
COMPILED = validate(CATALOGUE)


@pytest.mark.parametrize('case', CASES, ids=[c['id'] for c in CASES])
def test_dummy_log_exact_matches(case):
    parsed = parse(case['event'])
    hits, errors = match(parsed['message'], COMPILED)
    assert not errors
    assert sorted(r['id'] for r in hits) == sorted(case['expected_rule_ids'])
    assert parsed['device'] == case['expected_device']
    assert parsed['fpc'] == case['expected_fpc']
    assert parsed['pfe'] is None  # Never infer PFE from chip instance.


@pytest.mark.integration
def test_demo_database_matches_retry_and_recurrence(connector):
    with connector() as conn:
        import_catalogue(conn, CATALOGUE)
    store = Store(connector, CATALOGUE['catalogue_id'])
    for case in CASES:
        result = store.ingest(case['event'])
        assert result['status'] == 'stored'
        assert result['matches'] == len(case['expected_rule_ids'])
        with connector() as conn:
            rows = conn.execute('SELECT pattern_id,rule_snapshot FROM jls.syslog_hits WHERE event_id=%s', (result['event_id'],)).fetchall()
            assert sorted(r['pattern_id'] for r in rows) == sorted(case['expected_rule_ids'])
            assert all(r['rule_snapshot']['sources'] for r in rows)
    assert store.ingest(CASES[0]['event'])['status'] == 'duplicate'
    recurrence = copy.deepcopy(CASES[0]['event'])
    recurrence['@timestamp'] = '2026-10-17T10:05:00Z'
    assert store.ingest(recurrence)['status'] == 'stored'
    with connector() as conn:
        assert conn.execute('SELECT count(*) AS n FROM jls.events').fetchone()['n'] == 19
        assert conn.execute('SELECT count(*) AS n FROM jls.syslog_hits').fetchone()['n'] == 13
        assert conn.execute('SELECT count(*) AS n FROM jls.events e WHERE NOT EXISTS (SELECT 1 FROM jls.syslog_hits h WHERE h.event_id=e.event_id)').fetchone()['n'] == 6
