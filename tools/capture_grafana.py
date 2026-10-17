"""Capture real Grafana screens from an isolated Docker Compose demo stack.
Requires playwright; never run the seeding step against a production stack.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/grafana'
OUT.mkdir(parents=True, exist_ok=True)

def sql(query):
    return subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','jls','-Atc',query],text=True,cwd=ROOT).strip()

# Refuse to mix a demo into an existing deployment's log data.
assert sql('SELECT count(*) FROM jls.events') == '0', 'Demo requires an empty, isolated stack'
cases = json.loads((ROOT/'examples/junos-demo.json').read_text())
start = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=8)
lines=[]
for i, case in enumerate(cases):
    body=case['event']['message'].split('lab-mx01 ',1)[1]
    host='lab-mx01' if case['expected_rule_ids'] else 'lab-clean01'
    if i in (1,5): body += ', severity: major'
    lines.append(f'{(start+timedelta(seconds=i*10)).isoformat()} {host} {body}')
for i in range(5):
    body=cases[0]['event']['message'].split('lab-mx01 ',1)[1]
    lines.append(f'{(start+timedelta(minutes=4,seconds=i*20)).isoformat()} lab-mx01 {body}')
with socket.create_connection(('127.0.0.1',5514),timeout=10) as sock:
    sock.sendall(('\n'.join(lines)+'\n').encode())
for _ in range(60):
    if sql('SELECT count(*) FROM jls.events')=='23': break
    time.sleep(1)
counts={
    'events':int(sql('SELECT count(*) FROM jls.events')),
    'hits':int(sql('SELECT count(*) FROM jls.syslog_hits')),
    'unmatched':int(sql('SELECT count(*) FROM jls.events e WHERE NOT EXISTS (SELECT 1 FROM jls.syslog_hits h WHERE h.event_id=e.event_id)')),
    'major_alarms':int(sql("SELECT count(*) FROM jls.events WHERE cm_severity='major'")),
    'active_rules':int(sql('SELECT count(*) FROM jls.error_patterns WHERE enabled')),
}
assert counts == dict(events=23,hits=17,unmatched=6,major_alarms=2,active_rules=98),counts
# Grouping is aligned to 15-minute wall-clock windows; repeats may span two groups.
assert int(sql("SELECT sum(occurrences) FROM jls.occurrence_groups WHERE title LIKE '%DMEM allocation memory parity error%'"))==6
(OUT/'dummy-junos.log').write_text('\n'.join(lines)+'\n')
values=dict(line.split('=',1) for line in (ROOT/'.env').read_text().splitlines() if '=' in line and not line.startswith('#'))
from_ms=int((start-timedelta(minutes=1)).timestamp()*1000)
to_ms=int((datetime.now(timezone.utc)+timedelta(minutes=1)).timestamp()*1000)
base='http://127.0.0.1:3003'
common=f'from={from_ms}&to={to_ms}&timezone=utc&theme=dark&refresh='
errors=[]
queries=[]
with sync_playwright() as p:
    browser=p.chromium.launch()
    context=browser.new_context(viewport={'width':1600,'height':1050},device_scale_factor=1,locale='en-GB',timezone_id='UTC')
    response=context.request.post(base+'/login',data={'user':'admin','password':values['GRAFANA_ADMIN_PASSWORD']})
    assert response.ok, f'Grafana login failed: {response.status}'
    page=context.new_page()
    page.on('console', lambda message: print('Browser console:', message.type, message.text, flush=True) if message.type=='error' else None)
    page.on('requestfailed', lambda request: print('Failed request:', request.url, request.failure, flush=True))
    page.on('response', lambda response: print('HTTP error:',response.status,response.url,flush=True) if response.status>=400 else None)
    page.on('pageerror', lambda error: print('Browser error:', str(error), flush=True))
    def check_response(response):
        if '/api/ds/query' in response.url:
            if response.status!=200: errors.append(f'datasource HTTP {response.status}')
            else:
                payload=response.json()
                for ref,result in payload.get('results',{}).items():
                    queries.append(ref)
                    if result.get('error'): errors.append(result['error'])
    page.on('response',check_response)
    def capture(filename,path,text):
        page.set_viewport_size({'width':1600,'height':1050 if filename.startswith('01') else 780})
        page.goto(base+path,wait_until='domcontentloaded')
        try:
            page.get_by_text(text,exact=False).first.wait_for(state='visible',timeout=45000)
        except Exception:
            print('Capture failed at',page.url,flush=True)
            print('Visible page:',page.locator('body').inner_text()[:6000],flush=True)
            print('Query errors:',errors,flush=True)
            page.screenshot(path=str(OUT/'diagnostic.png'))
            raise
        page.wait_for_timeout(2000)  # Allow charts/fonts to finish painting after data appears.
        assert not errors, errors
        page.screenshot(path=str(OUT/filename),animations='disabled')
    capture('01-overview.png',f'/d/jls-operations/jls-error-monitoring?{common}&var-device=lab-mx01','DMEM allocation memory parity error')
    capture('02-matched-errors.png',f'/d-solo/jls-operations/jls-error-monitoring?{common}&panelId=5&var-device=lab-mx01','DMEM allocation memory parity error')
    capture('03-repeated-errors.png',f'/d-solo/jls-operations/jls-error-monitoring?{common}&panelId=6&var-device=lab-mx01','DMEM allocation memory parity error')
    capture('04-unmatched-logs.png',f'/d-solo/jls-operations/jls-error-monitoring?{common}&panelId=7&var-device=lab-clean01','UNKNOWNCHIP')
    assert queries, 'No Grafana datasource queries observed'
    browser.close()
run=os.getenv('GITHUB_RUN_ID','local')
sha=os.getenv('GITHUB_SHA','local')
report={'captured_at':datetime.now(timezone.utc).isoformat(),'source_commit':sha,'run_id':run,'counts':counts,'grafana_query_errors':errors,'observed_query_responses':len(queries),'synthetic_data':True}
(OUT/'results.json').write_text(json.dumps(report,indent=2)+'\n')
(OUT/'README.md').write_text(f'''# Grafana demonstration

These are actual browser screenshots of Grafana running with JLS, PostgreSQL and Logstash in an isolated Docker Compose stack. All device names, log events and alarms are synthetic. No screenshots are mockups.

Captured: {report['captured_at']}. [Workflow run](https://github.com/kbedford/JLS/actions/runs/{run}). Source commit: `{sha}`.

## Verified results

| Check | Observed |
| --- | ---: |
| Stored log events | 23 |
| Matched events / rule hits | 17 |
| Unmatched logs retained | 6 |
| Explicit major CM alarms | 2 |
| Active catalogue rules | 98 |
| Grafana datasource query errors | 0 |

The 18 base cases contain 12 matching errors and 6 negative cases. Five additional DMEM parity occurrences demonstrate repetition (six total DMEM occurrences). Two dummy messages explicitly carry `severity: major`; severity is not inferred from the matched rule. Repetition groups use fixed 15-minute windows and can split across a boundary. Overview summary counters are global; device selection filters the detailed tables.

## Overview

Matched faults, CM alarm counts and recent matching messages.

![JLS overview](01-overview.png)

## Matched errors

Real Junos-style dummy messages matched against the bundled catalogue. Additional guidance, KB/PR references and raw message columns are available by horizontally scrolling the live table.

![Matched error records](02-matched-errors.png)

## Repeated errors

The occurrence view groups repeated fault signatures by device and component.

![Repeated fault signatures](03-repeated-errors.png)

## Negative cases: retained without fault matches

The `lab-clean01` timeline contains six unmatched logs, including normal BGP/interface messages and an unknown diagnostic fault. No match means no catalogue pattern matched; it does not prove device health.

![Unmatched log timeline](04-unmatched-logs.png)

## Reproduce

Use **Actions → Grafana demo captures → Run workflow**. The workflow starts a fresh stack, sends the [dummy logs](dummy-junos.log) over TCP, verifies database counts, captures Chromium screenshots and commits only this demo folder. It also saves a downloadable artifact. The stack is removed afterwards.

For a local reproduction, create a separate checkout and empty Docker volumes, run `python3 tools/setup.py` and `docker compose up --build -d --wait`, install `playwright==1.56.0`, run `playwright install --with-deps chromium`, then `python tools/capture_grafana.py`. The script refuses a non-empty event table. Never run it on a production stack. Log timestamps are regenerated relative to capture time so dashboard time filters show the test data.

[Machine-readable evidence](results.json) · [Detailed matching tests](../DEMONSTRATION.md)
''')
print(json.dumps(report))
