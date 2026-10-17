"""Validated, versioned catalogue loading. No network fetches or command execution."""
import hashlib
import json
from pathlib import Path
import regex

MAX_RULES = 2000
MAX_PATTERN_LENGTH = 2048
MATCH_TIMEOUT = 0.025


def validate(data):
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported catalogue schema version")
    for key in ("catalogue_id", "version"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f"Missing {key}")
    rules = data.get("rules", [])
    if not rules or len(rules) > MAX_RULES:
        raise ValueError("Catalogue must contain 1..2000 rules")
    ids, compiled = set(), []
    for rule in rules:
        rid = rule.get("id")
        if not isinstance(rid, str) or not rid or rid in ids:
            raise ValueError("Missing or duplicate rule ID")
        ids.add(rid)
        pattern = rule.get("pattern")
        if not isinstance(pattern, str) or not pattern or len(pattern) > MAX_PATTERN_LENGTH:
            raise ValueError(f"Invalid pattern length: {rid}")
        if type(rule.get("enabled")) is not bool or not isinstance(rule.get("title"), str):
            raise ValueError(f"Invalid rule metadata: {rid}")
        try:
            rx = regex.compile(pattern, regex.I)
            if rx.search("", timeout=MATCH_TIMEOUT):
                raise ValueError(f"Pattern matches empty messages: {rid}")
            if rule["enabled"] and not rule.get("positive_examples"):
                raise ValueError(f"Enabled rule needs positive examples: {rid}")
            for example in rule.get("positive_examples", []):
                if not rx.search(normalise(example), timeout=MATCH_TIMEOUT):
                    raise ValueError(f"Positive example failed: {rid}")
            for example in rule.get("negative_examples", []):
                if rx.search(normalise(example), timeout=MATCH_TIMEOUT):
                    raise ValueError(f"Negative example matched: {rid}")
        except (regex.error, TimeoutError) as exc:
            raise ValueError(f"Invalid or excessive regex: {rid}") from exc
        if rule["enabled"]:
            compiled.append((rule, rx))
    if not compiled:
        raise ValueError("No enabled rules; refusing silent monitoring")
    return compiled


def normalise(text):
    return text.replace("\u200b", "").replace("\ufeff", "").replace("\xa0", " ")


def read_catalogue(path):
    data = json.loads(Path(path).read_text())
    validate(data)
    return data


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def match(message, compiled):
    hits, errors = [], []
    message = normalise(message)
    for rule, rx in compiled:
        try:
            if rx.search(message, timeout=MATCH_TIMEOUT):
                hits.append(rule)
        except TimeoutError:
            # Preserve the event for replay and surface this on the dashboard.
            errors.append({"rule_id": rule["id"], "error": "regex_timeout"})
    return hits, errors
