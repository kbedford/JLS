# JLS matching service

See the repository root README for deployment, private catalogue loading, security, retention and testing. Build this directory as part of Docker Compose so PostgreSQL and the collector are configured consistently.

The previous Supervisor/file-scanning entrypoint is retired. Run the application with `python -m jls serve`. `python -m jls validate PATH` validates a catalogue offline; `python -m jls import PATH` imports it transactionally. `python -m jls replay PATH` re-evaluates newline-delimited JSON envelopes, explicitly replacing their stored matches. Replay requires original receipt timestamps and source IPs to address existing events.
