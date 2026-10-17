import copy
import pytest
from jls.database import Store, import_catalogue, migrate

pytestmark = pytest.mark.integration


def setup_store(connector, catalogue):
    with connector() as c: import_catalogue(c,catalogue)
    return Store(connector,catalogue['catalogue_id'],reload_seconds=0)


def test_retry_and_restart_are_idempotent(connector,catalogue,event):
    store = setup_store(connector,catalogue)
    assert store.ingest(event)['status'] == 'stored'
    assert store.ingest(event)['status'] == 'duplicate'
    restarted = Store(connector,catalogue['catalogue_id'])
    assert restarted.ingest(event)['status'] == 'duplicate'
    with connector() as c:
        assert c.execute('SELECT count(*) AS n FROM jls.events').fetchone()['n'] == 1
        assert c.execute('SELECT count(*) AS n FROM jls.syslog_hits').fetchone()['n'] == 1


def test_recurrence_and_old_event(connector,catalogue,event):
    store = setup_store(connector,catalogue)
    store.ingest(event)
    event['@timestamp']='2026-10-16T12:00:01Z'
    store.ingest(event)
    event['message']='2021-01-01T00:00:00Z router-a fpc2 TESTCHIP(4): parity error'
    assert store.ingest(event)['matches'] == 1
    with connector() as c:
        assert c.execute('SELECT max(occurrences) AS n FROM jls.occurrence_groups').fetchone()['n'] == 2
    store.retain(30)  # Retention uses stored_at, so a newly received old event survives.
    with connector() as c:
        assert c.execute('SELECT count(*) AS n FROM jls.events').fetchone()['n'] == 3


def test_catalogue_update_atomic_and_live(connector,catalogue,event):
    store = setup_store(connector,catalogue)
    store.ingest(event)
    broken=copy.deepcopy(catalogue)
    broken['rules'][0]['pattern']='['
    with connector() as c:
        with pytest.raises(ValueError): import_catalogue(c,broken)
    revised=copy.deepcopy(catalogue)
    revised['version']='2'
    revised['rules'][0]['sources'][0]['actions']='New synthetic advice'
    with connector() as c:
        assert import_catalogue(c,revised)
        assert not import_catalogue(c,revised)
    event['@timestamp']='2026-10-16T12:00:01Z'
    store.ingest(event)
    with connector() as c:
        versions=c.execute('SELECT catalogue_version FROM jls.syslog_hits ORDER BY catalogue_version').fetchall()
        assert [r['catalogue_version'] for r in versions]==['1','2']


def test_transaction_failure_can_retry(connector,catalogue,event):
    store=setup_store(connector,catalogue)
    with connector() as c:
        c.execute("ALTER TABLE jls.syslog_hits ADD CONSTRAINT reject_test CHECK (false)")
    try:
        with pytest.raises(Exception): store.ingest(event)
        with connector() as c:
            assert c.execute('SELECT count(*) AS n FROM jls.events').fetchone()['n']==0
    finally:
        with connector() as c: c.execute('ALTER TABLE jls.syslog_hits DROP CONSTRAINT reject_test')
    assert store.ingest(event)['status']=='stored'


def test_replay_and_retention(connector,catalogue,event):
    store=setup_store(connector,catalogue)
    store.ingest(event)
    store.ingest(event,replay=True)
    with connector() as c:
        assert c.execute('SELECT count(*) AS n FROM jls.syslog_hits').fetchone()['n']==1
        c.execute("UPDATE jls.events SET stored_at=now()-interval '40 days'")
    store.retain(30)
    with connector() as c:
        assert c.execute('SELECT count(*) AS n FROM jls.syslog_hits').fetchone()['n']==0


def test_migrations_repeat_safely(connector,catalogue):
    setup_store(connector,catalogue)
    with connector() as c:
        migrate(c)
        assert c.execute('SELECT count(*) AS n FROM jls.error_patterns').fetchone()['n']==1


def test_migrate_as_schema_owner_without_database_create(connector,catalogue):
    with connector() as c:
        c.execute('DROP SCHEMA jls CASCADE')
        c.execute('DROP ROLE IF EXISTS jls_restricted_test')
        c.execute('CREATE ROLE jls_restricted_test')
        c.execute('CREATE SCHEMA jls AUTHORIZATION jls_restricted_test')
        c.execute('SET ROLE jls_restricted_test')
        migrate(c)
        import_catalogue(c,catalogue)
        assert c.execute('SELECT count(*) AS n FROM jls.error_patterns').fetchone()['n']==1
        c.execute('RESET ROLE')
        c.execute('DROP SCHEMA jls CASCADE')
        c.execute('DROP ROLE jls_restricted_test')
