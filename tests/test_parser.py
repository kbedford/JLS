from datetime import datetime, timezone
import pytest
from jls.parser import parse


def test_metadata_and_separate_asic(event):
    r = parse(event)
    assert r['device'] == 'router-a'
    assert r['fpc'] == 2
    assert r['pfe'] is None
    assert r['event_time'] == datetime(2026,10,16,12,tzinfo=timezone.utc)


def test_rfc5424_cmerror(event):
    event['message'] = '<134>1 2026-10-16T13:00:00+01:00 router-b app 1 ID - Error: /fpc/5/pfe/1/cm/0/EA[2:0]/0/FAULT severity: major, module: EA[2:0]'
    r = parse(event)
    assert (r['device'],r['fpc'],r['pfe'],r['asic'],r['cm_severity'],r['syslog_severity']) == ('router-b',5,1,'EA[2:0]','major',6)
    assert r['timestamp_source'] == 'device_explicit_timezone'


def test_new_year_and_timezone(event):
    event['@timestamp'] = '2026-01-01T00:00:02Z'
    event['message'] = 'Dec 31 23:59:59 router-a fpc0 TESTCHIP(1): parity error'
    assert parse(event)['event_time'].year == 2025
    event['@timestamp'] = '2026-10-16T12:00:00Z'
    event['message'] = 'Oct 16 13:00:00 router-a fpc0 error'
    assert parse(event,'Europe/London')['event_time'].hour == 12


def test_old_events_not_discarded(event):
    event['message'] = '2021-01-01T00:00:00Z router-a fpc4 old error'
    assert parse(event)['event_time'].year == 2021


def test_unknown_header_preserved(event):
    event['message'] = 'unstructured error'
    r = parse(event)
    assert r['device'] == '192.0.2.5'
    assert r['timestamp_source'] == 'receipt_fallback'
    assert 'unparsed_syslog_header' in r['parse_warnings']


def test_event_identity_preserves_recurrence(event):
    before = parse(event)['event_id']
    assert parse(dict(event))['event_id'] == before
    event['@timestamp'] = '2026-10-16T12:00:00.123457Z'
    assert parse(event)['event_id'] != before


@pytest.mark.parametrize('change', [{'message':None},{'message':'\x00'},{'message':'x'*65537},{'@timestamp':'bad'},{'@timestamp':'2026-10-16T12:00:00'}])
def test_invalid_envelope(event, change):
    event.update(change)
    with pytest.raises(ValueError): parse(event)


def test_fpc_only_header(event):
    event['message'] = 'Oct 16 12:00:00 fpc4 XMCHIP(2): error'
    r = parse(event)
    assert r['device'] == event['source_ip']
    assert r['fpc'] == 4 and r['pfe'] is None and r['asic'] == 'XMCHIP(2)'
