"""Best-effort Junos parsing; uncertain timestamps and identifiers stay explicit."""
import hashlib
import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from .catalogue import normalise

MONTHS = {m: i for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}
CLASSIC = re.compile(r"^(?:<\d+>)?(?P<month>[A-Z][a-z]{2})\s+(?P<day>\d{1,2})\s+(?P<time>\d\d:\d\d:\d\d(?:\.\d+)?)(?:\s+(?P<year>\d{4}))?\s+(?P<host>[^\s:]+)(?=\s|:)")
ISO = re.compile(r"^(?:<\d+>)?(?:1\s+)?(?P<date>\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)?)\s+(?P<host>\S+)")


def iso(value):
    if not isinstance(value, str):
        raise ValueError("Expected ISO timestamp string")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Receipt timestamp requires timezone")
    return dt.astimezone(timezone.utc)


def field(pattern, text):
    m = re.search(pattern, text, re.I)
    return m.group(1) if m else None


def parse(event, source_timezone="UTC"):
    if not isinstance(event, dict) or not isinstance(event.get("message"), str):
        raise ValueError("Event requires a string message")
    message = event["message"]
    if not message or len(message.encode()) > 65536 or "\x00" in message:
        raise ValueError("Message must contain 1..65536 bytes and no NUL")
    received = iso(event.get("@timestamp"))
    host = event.get("host", {})
    if isinstance(host, dict):
        source_ip = host.get("ip") or host.get("name")
    else:
        source_ip = host
    # Logstash copies TCP metadata into source_ip before serialising its output.
    source_ip = event.get("source_ip") or source_ip or "unknown"
    if not isinstance(source_ip, str):
        raise ValueError("Source IP must be a string")
    text = normalise(message)
    device, event_time, timestamp_source = source_ip, received, "receipt_fallback"
    warnings = []
    m = ISO.match(text)
    try:
        if m:
            stamp = datetime.fromisoformat(m["date"].replace("Z", "+00:00"))
            timestamp_source = "device_explicit_timezone" if stamp.tzinfo else "device_assumed_timezone"
            event_time = (stamp if stamp.tzinfo else stamp.replace(tzinfo=ZoneInfo(source_timezone))).astimezone(timezone.utc)
            device = m["host"].rstrip(":")
        else:
            m = CLASSIC.match(text)
            if m:
                device = m["host"].rstrip(":")
                local = received.astimezone(ZoneInfo(source_timezone))
                years = [int(m["year"])] if m["year"] else [local.year - 1, local.year, local.year + 1]
                candidates = []
                for year in years:
                    try:
                        candidates.append(datetime.fromisoformat(f"{year}-{MONTHS[m['month']]:02}-{int(m['day']):02}T{m['time']}").replace(tzinfo=ZoneInfo(source_timezone)))
                    except ValueError:
                        continue
                if not candidates:
                    raise ValueError("Invalid calendar date")
                event_time = min(candidates, key=lambda d: abs((d-local).total_seconds())).astimezone(timezone.utc)
                timestamp_source = "device_assumed_timezone" if m["year"] else "device_inferred_year_timezone"
            else:
                warnings.append("unparsed_syslog_header")
    except (ValueError, KeyError):
        warnings.append("invalid_device_timestamp")
        event_time, timestamp_source = received, "receipt_fallback"
    # fpc-only samples do not contain a hostname. Prefer the transport source.
    if re.fullmatch(r"(?:member\d+-)?fpc\d+", device, re.I) or device in ("-", "%PFE-3"):
        device = source_ip
        warnings.append("hostname_missing")
    fpc = field(r"/fpc/(\d+)/", text) or field(r"\bfpc\s*(\d+)\b", text)
    pfe = field(r"/pfe/(\d+)/", text) or field(r"\bPFE\s*[:#]?\s*(\d+)\b", text)
    # ASIC instance numbers are not universally PFE IDs: store them separately.
    asic = field(r"\b((?:XMCHIP|MQCHIP|LUCHIP|MQSS|XQSS)\(\d+\)|(?:EA|XL)\[\d+:\d+\])", text)
    cm = field(r"severity:\s*(minor|major|fatal|info(?:rmational)?)\b", text)
    if not cm:
        cm = field(r"\b(Major|Minor)\s+(?:alarm|Host\s+\d+|Errors)", text)
    pri = field(r"^<(\d+)>", text)
    facility_severity = field(r"%[A-Z]+-(\d)(?::|-)", text)
    severity = int(pri) % 8 if pri and int(pri) <= 191 else int(facility_severity) if facility_severity else None
    identity = json.dumps([event.get("@timestamp"), source_ip, message], ensure_ascii=False, separators=(",", ":"))
    return {"event_id": hashlib.sha256(identity.encode()).hexdigest(), "message": message,
            "source_ip": source_ip, "device": device, "received_at": received, "event_time": event_time,
            "timestamp_source": timestamp_source, "fpc": int(fpc) if fpc else None,
            "pfe": int(pfe) if pfe else None, "asic": asic,
            "routing_engine": field(r"\b(?:RE|Host)\s*([01])\b", text),
            "cm_severity": cm.lower() if cm else None, "syslog_severity": severity,
            "error_code": field(r"(?:errorno|Error code:|Error\s*\()\s*(0x[0-9a-f]+)", text),
            "stream": field(r"\bStream\s+(\d+)\b", text), "parse_warnings": warnings}
