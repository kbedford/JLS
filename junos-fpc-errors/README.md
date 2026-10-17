# JLS matching service

See the [repository README](../README.md) for deployment, bundled catalogue loading, security, retention and testing. The default setup imports the 98 rules in `catalogue/catalogue.json`; no separate catalogue download is required. Build this directory as part of Docker Compose so PostgreSQL and the collector are configured consistently.

The previous Supervisor/file-scanning entrypoint is retired. Run the application with `python -m jls serve`. `python -m jls validate PATH` validates a catalogue offline; `python -m jls import PATH` imports it transactionally. `python -m jls replay PATH` re-evaluates newline-delimited JSON envelopes, explicitly replacing their stored matches. Replay requires original receipt timestamps and source IPs to address existing events.
