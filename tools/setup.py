"""Create local credentials without printing secrets or overwriting existing setup."""
import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / ".env"
keys = ["POSTGRES_PASSWORD", "DB_PASSWORD", "GRAFANA_DB_PASSWORD", "GRAFANA_ADMIN_PASSWORD", "INGEST_TOKEN"]
content = "\n".join(f"{k}={secrets.token_hex(32)}" for k in keys)
content += "\nCATALOGUE_DIR=./catalogue\nCATALOGUE_ID=health-check-fpc-errors\nSYSLOG_BIND=127.0.0.1\nSYSLOG_TIMEZONE=UTC\nRETENTION_DAYS=30\n"
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as f:
    f.write(content)
print("Created .env using the bundled catalogue. Set SYSLOG_BIND and SYSLOG_TIMEZONE for your network.")
