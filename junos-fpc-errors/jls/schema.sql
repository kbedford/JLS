CREATE TABLE IF NOT EXISTS jls.schema_version (version integer PRIMARY KEY, installed_at timestamptz NOT NULL DEFAULT now());
INSERT INTO jls.schema_version(version) VALUES (1) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS jls.catalogues (
  catalogue_id text PRIMARY KEY, version text NOT NULL, digest text NOT NULL,
  source jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS jls.error_patterns (
  catalogue_id text NOT NULL REFERENCES jls.catalogues, id text NOT NULL,
  title text NOT NULL, pattern text NOT NULL, enabled boolean NOT NULL,
  metadata jsonb NOT NULL, PRIMARY KEY(catalogue_id,id)
);
CREATE TABLE IF NOT EXISTS jls.events (
  event_id text PRIMARY KEY, received_at timestamptz NOT NULL, event_time timestamptz NOT NULL,
  stored_at timestamptz NOT NULL DEFAULT now(), device text NOT NULL, source_ip text NOT NULL,
  fpc integer, pfe integer, asic text, routing_engine text, cm_severity text,
  syslog_severity smallint, error_code text, stream text, timestamp_source text NOT NULL,
  message text NOT NULL, parse_warnings jsonb NOT NULL, evaluation_errors jsonb NOT NULL,
  catalogue_digest text NOT NULL
);
CREATE INDEX IF NOT EXISTS events_time_idx ON jls.events(event_time DESC);
CREATE INDEX IF NOT EXISTS events_stored_idx ON jls.events(stored_at);
CREATE INDEX IF NOT EXISTS events_component_idx ON jls.events(device,fpc,pfe,event_time DESC);
CREATE TABLE IF NOT EXISTS jls.syslog_hits (
  event_id text NOT NULL REFERENCES jls.events ON DELETE CASCADE,
  catalogue_id text NOT NULL, pattern_id text NOT NULL, catalogue_version text NOT NULL,
  rule_snapshot jsonb NOT NULL, PRIMARY KEY(event_id,catalogue_id,pattern_id)
);
CREATE TABLE IF NOT EXISTS jls.rejected_events (
  id bigserial PRIMARY KEY, received_at timestamptz NOT NULL DEFAULT now(),
  reason text NOT NULL, payload jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS rejected_time_idx ON jls.rejected_events(received_at);
CREATE OR REPLACE VIEW jls.hit_details AS
SELECT e.*, h.catalogue_id, h.pattern_id, h.catalogue_version,
 h.rule_snapshot->>'title' AS title,
 h.rule_snapshot->'kb_references' AS kb_references,
 h.rule_snapshot->'pr_references' AS pr_references,
 h.rule_snapshot->'sources' AS guidance,
 h.rule_snapshot->'version_notes' AS version_notes
FROM jls.events e JOIN jls.syslog_hits h USING(event_id);
-- Occurrence groups aid triage; first_seen is NOT a root-cause assertion.
CREATE OR REPLACE VIEW jls.occurrence_groups AS
SELECT date_bin('15 minutes',event_time,'2000-01-01'::timestamptz) AS time_bucket,
 device, source_ip, fpc, pfe, asic, catalogue_id, pattern_id, title,
 count(*) AS occurrences, min(event_time) AS first_seen, max(event_time) AS last_seen
FROM jls.hit_details GROUP BY 1,2,3,4,5,6,7,8,9;
