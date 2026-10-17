# JLS dummy Junos log demonstration

Run date: 17 October 2026. These are synthetic lab messages using documentation-only address `192.0.2.10` and hostname `lab-mx01`; they are not customer logs or evidence of real hardware faults.

## Results

- 18/18 parser and matcher scenarios passed: 12 positive and 6 negative.
- Full local suite: 57 passed, including database integration using embedded PostgreSQL (PGlite).
- Database demonstration: all 18 events persisted, with exactly 12 rule hits and 6 unmatched events. A retry of the same collector event created no duplicate. A new receipt of the first fault created a new occurrence: 19 events and 13 hits in total.
- Every positive event matched exactly the expected rule, with no additional rule hits; every hit retained source guidance. Single-bit and double-bit MQ ECC matched different rules.
- All messages parsed as device `lab-mx01`, FPC 2. PFE remained unknown rather than being inferred from the ASIC number. Classic syslog timestamps explicitly record inferred year/timezone.
- Catalogue v1.3: 98 active rules. The full catalogue's existing regression examples are also validated when loaded.

The GitHub Actions workflow runs the same suite against native PostgreSQL and sends these 18 log lines over TCP through the complete Docker stack. Its TCP gate requires exactly 18 stored events, 12 hits and 6 unmatched events. **PASS:** [GitHub Actions run 39026651203](https://github.com/kbedford/JLS/actions/runs/39026651203) completed successfully, including native PostgreSQL tests, Logstash configuration validation, full Docker stack startup, and the exact TCP ingestion counts above. Tested code commit: `04c66fd968ca2cc87894a1a11707a085e14c1820`.

| Case | Dummy scenario | Expected / observed | Result |
| --- | --- | --- | --- |
| D01 | XM DMEM parity | jls-48edb71c0ff63672 | PASS |
| D02 | XM packet CRC | jls-40272ff646193bc0 | PASS |
| D03 | XM queue underrun corrected spelling | jls-0f807aafcc486a1b | PASS |
| D04 | XM queue underrun source spelling | jls-0f807aafcc486a1b | PASS |
| D05 | MQ single-bit ECC | jls-256d4bf373ac9c0c | PASS |
| D06 | MQ double-bit ECC | jls-6bc147e936977595 | PASS |
| D07 | EA corrected ECC | jls-483b5d6511b3d2ea | PASS |
| D08 | EA primary timeout | jls-9e12ab8365519759 | PASS |
| D09 | EA secondary timeout | jls-9e12ab8365519759 | PASS |
| D10 | XL KMA parity | jls-d70fda8737709869 | PASS |
| D11 | MQ DDR checksum | jls-83846d37a71140d8 | PASS |
| D12 | MQSS child drop | jls-78027541f607557e | PASS |
| D13 | Healthy chip status | No catalogue match | PASS |
| D14 | Different chip family | No catalogue match | PASS |
| D15 | ECC status only | No catalogue match | PASS |
| D16 | BGP established | No catalogue match | PASS |
| D17 | Interface up | No catalogue match | PASS |
| D18 | Unknown hardware error | No catalogue match | PASS |

## How the app behaves

For example, this dummy event matches the DMEM parity rule:

```text
Oct 17 10:00:00 lab-mx01 fpc2 XMCHIP(1): MALLOC: DMEM allocation memory parity error
```

JLS stores the original message, device, FPC, ASIC and timestamp information in `jls.events`. It writes the matched rule ID, catalogue version and guidance snapshot to `jls.syslog_hits` in the same transaction. Grafana reads these records to show the fault and its documented guidance. JLS does not execute remediation commands.

This status message produces no rule hit:

```text
Oct 17 10:00:12 lab-mx01 fpc2 XMCHIP(1): MALLOC: DMEM allocation memory status OK
```

It is still stored as an event. Likewise, the unknown diagnostic fault in D18 is retained without a hit: **no catalogue match does not prove a device is healthy**. Matching is text-pattern based; these examples do not establish universal false-positive/false-negative rates or performance at production volume.

## Reproduce offline

From the repository root, in a Python virtual environment:

```bash
pip install -r requirements-dev.txt
python tools/demo.py --output demo-results.json
pytest -q tests/test_junos_demo.py -m 'not integration'
```

The offline demonstration sends no traffic and needs no database. Expected summary: `18/18 passed; 98 active rules`.

For database integration, set `JLS_TEST_DSN` to a **disposable test database**, then run `pytest -q tests/test_junos_demo.py`. The test fixture clears JLS tables; never point it at a production database.

## Demonstrate the complete stack

Start a separate test stack using the README instructions. Send the supplied messages to its local TCP listener:

```bash
python -c "import socket,pathlib; s=socket.create_connection(('127.0.0.1',5514)); s.sendall(pathlib.Path('examples/junos-demo.log').read_bytes()); s.close()"
```

Open Grafana at `http://localhost:3003`, select `lab-mx01`, and use a time range covering **17 October 2026 10:00 UTC** (the demo's device timestamps, assuming `SYSLOG_TIMEZONE=UTC`). The stored receipt timestamps reflect when you sent the logs. Positive cases show matched guidance; negative cases contribute incoming events but no matched fault. Re-sending over TCP is a new collector receipt and therefore creates new occurrences; it is different from retrying the same saved collector event.

## Files

- [Raw dummy log lines](../examples/junos-demo.log)
- [Fixtures with explicit expected rule IDs](../examples/junos-demo.json)
- [Machine-readable observed results](demo-results.json)
- [Executable demonstration](../tools/demo.py)
- [Parser/matcher and database regression tests](../tests/test_junos_demo.py)
