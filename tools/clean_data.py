"""
Clean raw input: flatten metrics, drop invalid rows.
Input: .tmp/raw_input.json. Output: .tmp/cleaned_data.json (Cleaned Data schema).
Deterministic; atomic.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

TMP_DIR = Path(__file__).resolve().parent.parent / ".tmp"
INPUT_FILE = TMP_DIR / "raw_input.json"
OUTPUT_FILE = TMP_DIR / "cleaned_data.json"
SCHEMA_VERSION = "1.0"


def _float(val, default=0.0):
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def clean() -> int:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    if not INPUT_FILE.is_file():
        print("raw_input.json not found. Run ingest first.", file=sys.stderr)
        return 1
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)
    records_in = raw.get("records", [])
    records_out = []
    validation_errors = 0
    for r in records_in:
        if not isinstance(r, dict):
            validation_errors += 1
            continue
        metrics = r.get("metrics") if isinstance(r.get("metrics"), dict) else {}
        rec = {
            "id": str(r.get("id", "")),
            "timestamp": str(r.get("timestamp", datetime.now(timezone.utc).isoformat())),
            "source": str(r.get("source", "")),
            "visits": _float(metrics.get("visits"), 0),
            "conversions": _float(metrics.get("conversions"), 0),
            "revenue": _float(metrics.get("revenue"), 0),
        }
        records_out.append(rec)
    data = {
        "schema_version": SCHEMA_VERSION,
        "cleaned_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records_out),
        "records": records_out,
        "validation_errors_count": validation_errors,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(clean())
