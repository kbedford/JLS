# Junos Log Scanner

JLS receives Junos syslog, matches a versioned error catalogue, and stores events and troubleshooting guidance in PostgreSQL for Grafana. Matches are advisory: JLS never executes router commands or automatically decides to restart, disable, or replace hardware.

## Architecture

```mermaid
flowchart TD
    R["Junos devices"] -->|"UDP / TCP syslog"| L["Logstash persistent queue"]
    L -->|"Authenticated HTTP delivery"| S["Python parser and rule matcher"]
    C["98-rule JSON catalogue"] -->|"Validated import"| P[("PostgreSQL")]
    P -->|"Load matching rules"| S
    S -->|"Store events and matches atomically"| P
    P -->|"Read-only queries"| G["Grafana dashboards"]
```

Routers send UDP or newline-delimited TCP syslog to Logstash. Logstash persists incoming events in a bounded disk queue and retries delivery to an authenticated internal Python endpoint. The endpoint records the event and all matching rule snapshots in one PostgreSQL transaction before acknowledging delivery. Grafana connects using a read-only database role.

There is no periodic whole-file scan, three-hour cutoff, Supervisor, duplicate scanner process, or test-results HTTP server. PostgreSQL and the ingestion API have no published host ports. Grafana binds to localhost by default.

## Install

Requires Docker Engine with Compose v2 and Python 3 for credential generation. The scanner image runs on Python 3.12; Logstash is a separate official image rather than a bundled x86-only download.

```sh
git clone https://github.com/kbedford/JLS.git
cd JLS
python3 tools/setup.py
```

The repository includes all **98 error rules** from Health Check FPC Errors v1.3 in [`catalogue/catalogue.json`](catalogue/catalogue.json). The default configuration mounts this catalogue and imports it into PostgreSQL automatically. No separate catalogue download is required. Keep the directory readable by container UID 10001. Source notices and provenance are retained; publication does not change the source licensing terms. Word source files and local private overrides remain excluded from Git.

Edit `.env` to set `SYSLOG_BIND` to the collector's management IP and `SYSLOG_TIMEZONE` to the timezone used by devices without explicit timestamp offsets. Restrict incoming ports to the intended device network. The default bind is localhost for initial testing. Credentials are independently generated; inspect `.env` locally for the Grafana admin password.

```sh
docker compose config --quiet
docker compose up --build -d --wait
docker compose ps
```

Visit http://localhost:3003 and open **JLS / JLS Error Monitoring**. On a remote host, use an SSH tunnel or your authenticated HTTPS proxy. There are no default passwords. Do not expose Grafana directly without HTTPS and your required authentication controls.

On first start the application validates the entire catalogue, creates the `jls` schema tables, and imports the rules transactionally. An absent, invalid, or empty active catalogue fails readiness rather than silently monitoring nothing. On later starts an unchanged catalogue is a no-op; a changed catalogue replaces only its own rules. Events retain their original rule snapshots.

For a synthetic-only demonstration, create `private-catalogue/`, copy `examples/catalogue.json` into `private-catalogue/catalogue.json` and set `CATALOGUE_DIR=./private-catalogue` and `CATALOGUE_ID=synthetic-example` in `.env`. This demo contains no Juniper fault catalogue.

## Ports and delivery

| Host port | Protocol | Purpose |
|---|---|---|
| 514 | UDP | Mapped to the actual Logstash 5514 listener |
| 5514 | UDP / TCP | Direct syslog; TCP uses newline-delimited messages |
| 6514 | TCP with mutual TLS | Optional TLS overlay |
| 3003 on localhost | HTTP | Grafana |

UDP can lose messages before they reach the queue. TCP provides backpressure but not an application-level durable acknowledgement to a router. The 1 GiB Logstash queue protects accepted events across process restarts and database outages, subject to available disk and storage durability. UDP can drop when the queue fills. Monitor queue utilisation, disk, container health, ingestion freshness, and quarantine counts. Size and performance must be validated against the intended traffic rate.

Retries of the **same collector envelope** are idempotent using its receipt timestamp, source IP, and message. A later recurrence with a different receipt timestamp is a separate event. Two byte-identical messages from the same source with identical receipt timestamps collapse; upstream retransmissions that acquire a new receipt timestamp remain separate. This is not a universal exactly-once transport guarantee.

The collector retains its original `@timestamp`. Device timestamps are parsed separately. Missing years are inferred relative to receipt time and missing timezones use `SYSLOG_TIMEZONE`; the interpretation is recorded. Unknown formats retain the full message and use receipt time. Historical events are accepted regardless of age. For replay, preserve the original receipt timestamp and source to preserve identity. Syslog priority and CM alarm severity are separate fields. ASIC instance numbers are not assumed to be PFE IDs.

Messages are limited to 64 KiB in the matcher. Malformed envelopes are stored in `jls.rejected_events`; individual regex timeouts retain the event with `evaluation_errors` for investigation and replay. Logstash retries database or validation failures instead of acknowledging them. A configuration/authentication error can intentionally block delivery until corrected.

## Catalogue maintenance

The bundled JSON contains the 98 extracted rules. The separately supplied extraction package also includes review overrides, audit and PostgreSQL seed SQL. The canonical application import is JSON, with validation before writes. Full technical text, conditional actions, cited KB/PR identifiers, version/platform notes, source paragraph locations, original document checksum, and regression examples are retained. KB/PR references are citations, not a claim that each entry has an independently verified primary KB.

```sh
# Validate a replacement without changing PostgreSQL:
docker compose exec scanner python -m jls validate /catalogue/catalogue.json
# Atomically import it; the running matcher refreshes database rules within 30 seconds:
docker compose exec scanner python -m jls import /catalogue/catalogue.json
```

Mount the directory, so atomically replacing its catalogue file is visible to containers. Restart the service if changing the catalogue ID. Direct SQL changes to patterns are validated on refresh; invalid changes stop readiness and trigger retries. Update the configured JSON file as well, since subsequent changed-file imports are authoritative.

Occurrence groups show repeated signatures per device/FPC/PFE/ASIC in 15-minute windows. The timeline helps inspect preceding and concurrent events. These are triage aids, not automatic root-cause or service-impact determinations. Source guidance containing version-specific, conditional, or contradictory statements must be evaluated by the operator. Platform/version notes are context; the matcher does not enforce applicability without reliable inventory.

## TLS

Provision `secrets/tls/server.crt`, `server.pkcs8.key`, and `ca.crt` with appropriate hostnames, trust and container-read permissions. The additional listener requires client certificates:

```sh
docker compose -f docker-compose.yml -f compose.tls.yml up --build -d --wait
```

The overlay **adds** mutual TLS; existing plaintext ports remain enabled. Remove their host port mappings when deploying TLS-only. This listener supports newline framing, not RFC6587 octet-counted framing; use a compatible relay if the sender uses octet counting. Database/API traffic is internal to the Docker host; use transport TLS if moving those components across hosts.

## Retention, recovery and upgrades

`RETENTION_DAYS` defaults to 30. Every minute the service deletes up to 10,000 old events and rejected records, using database storage time so newly arrived historical events are not immediately deleted. Cascading removal includes match snapshots. Keep backups as required; idempotency does not extend beyond deleted event records. Queue capacity is separate from database retention.

```sh
# Contains collected logs and catalogue data; keep access restricted.
docker compose exec -T postgres pg_dump -U postgres -d jls > jls-backup.sql
# Readiness and operational logs:
docker compose ps
docker compose logs --tail=100 scanner logstash
```

The old application used `public.error_patterns`, `public.syslog_hits`, host bind mounts, and an embedded Grafana database. This version uses a separate `jls` schema and named volumes. **Do not point a new PostgreSQL major version at an existing data directory.** Back up the original deployment with its matching PostgreSQL tools before switching. Keep historical data in the old database or restore a dump into an isolated database for analysis. Legacy records lack reliable collector IDs and parsed fields; automatic historical migration is deliberately not attempted. Do not run `docker compose down -v` on data you need to keep.

The committed Grafana SQLite database is removed from the new tree, not rewritten out of Git history. If old committed credentials or deployed default passwords were used, rotate them. Dashboards and the datasource are provisioned from reviewed configuration instead.

Images and direct Python dependencies are pinned to explicit versions. Validate patch upgrades and scan images/dependencies in your release process; pinning does not mean vulnerability-free.

## Development and tests

JLS now uses **pytest** for parser, matcher, HTTP and database regression tests, plus **GitHub Actions** for native PostgreSQL and Docker/TCP integration checks. The original Robot Framework suite and test-results web server have been retired; Robot Framework is not required to install or test this project. This is a change in JLS tooling, not a claim that Robot Framework itself is obsolete.

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
# Use only an isolated, disposable test database: integration fixtures truncate jls tables.
JLS_TEST_DSN=postgresql://postgres:password@localhost/jls_test pytest -q
JLS_CATALOGUE_TEST_PATH=catalogue/catalogue.json pytest -q
```

Tests cover matching, timestamp parsing, regex validation/timeouts, authentication, quarantine, event replay, database transactions, catalogue updates, retention and deployment contracts. CI additionally validates Logstash configuration and starts the Docker stack with the bundled catalogue and 18 dummy Junos messages to test TCP-to-database ingestion. CI also validates every bundled rule against its regression examples.

To regenerate a private catalogue after revising its Word source:

```sh
python tools/extract_catalogue.py /private/source.docx \
  --overrides /private/overrides.json --output private-catalogue/catalogue.json
PYTHONPATH=junos-fpc-errors python -m jls validate private-catalogue/catalogue.json
```

Heading styles and paragraph locations can change between document versions: review every extraction audit and update overrides. Extraction includes text and hyperlinks, not diagrams or screenshots. No remediation commands are executed.

## Worked Junos log demonstration

See [positive and negative test results](docs/DEMONSTRATION.md) for 18 dummy Junos messages, expected matches, observed results, database behavior and replay instructions. Run `python tools/demo.py` for an offline demonstration.

## Grafana demo screenshots

[View the captured Grafana demo and verified results](docs/grafana/README.md): overview, matched errors, recurring faults and unmatched logs, using synthetic Junos events.

![Grafana JLS overview](docs/grafana/01-overview.png)
