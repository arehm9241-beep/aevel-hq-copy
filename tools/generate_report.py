"""
Generate marketing-ready report from analytics result.
Input: .tmp/analytics_result.json. Output: .tmp/report_output.json (Report Payload schema).
Narrative from template; no LLM calculations.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

TMP_DIR = Path(__file__).resolve().parent.parent / ".tmp"
INPUT_FILE = TMP_DIR / "analytics_result.json"
OUTPUT_FILE = TMP_DIR / "report_output.json"
SCHEMA_VERSION = "1.0"


def generate_report(title: str = "", period: str = "") -> int:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    if not INPUT_FILE.is_file():
        print("analytics_result.json not found. Run analyze first.", file=sys.stderr)
        return 1
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    totals = data.get("totals", {})
    by_source = data.get("by_source", [])
    summary = data.get("summary", "")
    period_start = data.get("period_start", "")
    period_end = data.get("period_end", "")
    if not title:
        title = "Analytics Report"
    if not period:
        period = f"{period_start} to {period_end}" if period_start and period_end else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    narrative = summary or f"Visits: {totals.get('visits', 0):.0f}, Conversions: {totals.get('conversions', 0):.0f}, Revenue: ${totals.get('revenue', 0):.2f}."
    out = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "period": period,
        "metrics": dict(totals),
        "by_source": list(by_source),
        "narrative": narrative,
        "format": "json",
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    return 0


if __name__ == "__main__":
    title = ""
    period = ""
    if len(sys.argv) > 1:
        title = sys.argv[1]
    if len(sys.argv) > 2:
        period = sys.argv[2]
    sys.exit(generate_report(title=title, period=period))
