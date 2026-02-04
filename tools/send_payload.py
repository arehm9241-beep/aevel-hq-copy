"""
Deliver report to webhook and/or write .tmp/report_summary.txt.
Input: .tmp/report_output.json. Environment: DELIVERY_WEBHOOK_URL, DELIVERY_TIMEOUT_SEC.
Deterministic; no calculations.
"""

import os
import sys
import json
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

TMP_DIR = Path(__file__).resolve().parent.parent / ".tmp"
INPUT_FILE = TMP_DIR / "report_output.json"
SUMMARY_FILE = TMP_DIR / "report_summary.txt"


def send_payload() -> int:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    if not INPUT_FILE.is_file():
        print("report_output.json not found. Run generate_report first.", file=sys.stderr)
        return 1
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)
    timeout = int(os.environ.get("DELIVERY_TIMEOUT_SEC", "10") or "10")
    webhook = (os.environ.get("DELIVERY_WEBHOOK_URL") or "").strip()
    if webhook:
        try:
            body = json.dumps(payload).encode("utf-8")
            req = Request(
                webhook,
                data=body,
                headers={"Content-Type": "application/json", "User-Agent": "BLAST-Analytics/1.0"},
                method="POST",
            )
            with urlopen(req, timeout=timeout) as resp:
                if resp.status >= 400:
                    print(f"Webhook returned {resp.status}", file=sys.stderr)
                    return 1
        except (HTTPError, URLError) as e:
            print(f"Webhook delivery failed: {e}", file=sys.stderr)
            return 1
    lines = [
        payload.get("title", "Report"),
        "Period: " + payload.get("period", ""),
        "Metrics: " + json.dumps(payload.get("metrics", {})),
        "Narrative: " + payload.get("narrative", ""),
    ]
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(send_payload())
