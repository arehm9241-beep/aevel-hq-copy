"""
Compute deterministic aggregations over cleaned data.
Input: .tmp/cleaned_data.json. Output: .tmp/analytics_result.json (Analytics Result schema).
Python only; no LLM.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

TMP_DIR = Path(__file__).resolve().parent.parent / ".tmp"
INPUT_FILE = TMP_DIR / "cleaned_data.json"
OUTPUT_FILE = TMP_DIR / "analytics_result.json"
SCHEMA_VERSION = "1.0"


def analyze() -> int:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    if not INPUT_FILE.is_file():
        print("cleaned_data.json not found. Run clean_data first.", file=sys.stderr)
        return 1
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    records = data.get("records", [])
    totals = {"visits": 0.0, "conversions": 0.0, "revenue": 0.0}
    by_source = defaultdict(lambda: {"visits": 0.0, "conversions": 0.0, "revenue": 0.0})
    timestamps = []
    for r in records:
        v = float(r.get("visits", 0) or 0)
        c = float(r.get("conversions", 0) or 0)
        rev = float(r.get("revenue", 0) or 0)
        src = str(r.get("source", "") or "").strip() or "unknown"
        totals["visits"] += v
        totals["conversions"] += c
        totals["revenue"] += rev
        by_source[src]["visits"] += v
        by_source[src]["conversions"] += c
        by_source[src]["revenue"] += rev
        ts = r.get("timestamp")
        if ts:
            timestamps.append(ts)
    period_start = min(timestamps) if timestamps else datetime.now(timezone.utc).isoformat()
    period_end = max(timestamps) if timestamps else datetime.now(timezone.utc).isoformat()
    by_source_list = [{"source": k, "visits": v["visits"], "conversions": v["conversions"], "revenue": v["revenue"]} for k, v in sorted(by_source.items())]
    summary = f"Total visits: {totals['visits']:.0f}, conversions: {totals['conversions']:.0f}, revenue: ${totals['revenue']:.2f}"
    out = {
        "schema_version": SCHEMA_VERSION,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "period_start": period_start,
        "period_end": period_end,
        "totals": totals,
        "by_source": by_source_list,
        "summary": summary,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(analyze())
