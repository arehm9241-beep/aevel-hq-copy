"""
Ingest raw data from DATA_SOURCE_PATH or DATA_SOURCE_URL.
Output: .tmp/raw_input.json (Raw Input schema).
Deterministic; no calculations.
"""

import os
import sys
import json
import csv
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

TMP_DIR = Path(__file__).resolve().parent.parent / ".tmp"
OUTPUT_FILE = TMP_DIR / "raw_input.json"
SCHEMA_VERSION = "1.0"


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_csv(path: Path) -> dict:
    records = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        headers = [h.strip().lower() for h in (reader.fieldnames or [])]
        for row in reader:
            r = {}
            for k, v in row.items():
                key = k.strip().lower().replace(" ", "_")
                r[key] = v.strip() if isinstance(v, str) else v
            records.append(r)
    return _csv_rows_to_raw(records)


def _csv_rows_to_raw(rows: list) -> dict:
    records = []
    for i, row in enumerate(rows):
        rec = {
            "id": str(row.get("id", str(i))),
            "timestamp": str(row.get("timestamp", datetime.now(timezone.utc).isoformat())),
            "source": str(row.get("source", row.get("source", ""))),
            "metrics": {
                "visits": float(row.get("visits", row.get("visits", 0)) or 0),
                "conversions": float(row.get("conversions", row.get("conversions", 0)) or 0),
                "revenue": float(row.get("revenue", row.get("revenue", 0)) or 0),
            },
            "meta": {},
        }
        records.append(rec)
    return {
        "schema_version": SCHEMA_VERSION,
        "records": records,
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_label": "csv",
        },
    }


def _fetch_url(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "BLAST-Analytics/1.0"})
    with urlopen(req, timeout=30) as resp:
        return resp.read()


def ingest() -> int:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    path = os.environ.get("DATA_SOURCE_PATH", "").strip()
    url = os.environ.get("DATA_SOURCE_URL", "").strip()
    fmt = (os.environ.get("DATA_SOURCE_FORMAT", "json") or "json").strip().lower()

    if path:
        p = Path(path)
        if not p.is_file():
            print("DATA_SOURCE_PATH file not found.", file=sys.stderr)
            return 1
        if fmt == "csv":
            data = _load_csv(p)
        else:
            raw = _load_json(p)
            data = raw if "records" in raw else {"schema_version": SCHEMA_VERSION, "records": raw.get("records", []), "metadata": raw.get("metadata", {})}
    elif url:
        try:
            body = _fetch_url(url)
        except (HTTPError, URLError) as e:
            print(f"DATA_SOURCE_URL unreachable: {e}", file=sys.stderr)
            return 1
        raw = json.loads(body.decode("utf-8"))
        if isinstance(raw, list):
            raw = {"schema_version": SCHEMA_VERSION, "records": raw, "metadata": {}}
        elif isinstance(raw, dict) and "records" not in raw:
            raw = {"schema_version": SCHEMA_VERSION, "records": [], "metadata": raw.get("metadata", {})}
        data = raw
    else:
        data = {
            "schema_version": SCHEMA_VERSION,
            "records": [],
            "metadata": {"generated_at": datetime.now(timezone.utc).isoformat(), "source_label": "none"},
        }

    if "metadata" not in data:
        data["metadata"] = {"generated_at": datetime.now(timezone.utc).isoformat(), "source_label": "unknown"}
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(ingest())
