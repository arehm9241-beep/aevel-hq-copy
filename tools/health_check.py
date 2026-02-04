"""
Verify environment and optional integrations. Fail fast if required setup is missing.
No calculations; deterministic.
"""

import os
import sys
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

TMP_DIR = Path(__file__).resolve().parent.parent / ".tmp"
REQUIRED_FOR_PIPELINE = []  # None required for minimal run; DATA_SOURCE_PATH or DATA_SOURCE_URL recommended
OPTIONAL = ["GEMINI_API_KEY", "DATA_SOURCE_PATH", "DATA_SOURCE_URL", "DELIVERY_WEBHOOK_URL"]


def health_check() -> int:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    errors = []
    for key in REQUIRED_FOR_PIPELINE:
        if not (os.environ.get(key) or "").strip():
            errors.append(f"Missing required env: {key}")
    path = (os.environ.get("DATA_SOURCE_PATH") or "").strip()
    url = (os.environ.get("DATA_SOURCE_URL") or "").strip()
    if not path and not url:
        pass  # Allow demo mode with no source
    if path and not Path(path).is_file():
        errors.append(f"DATA_SOURCE_PATH file not found: {path}")
    if url:
        try:
            req = Request(url, headers={"User-Agent": "BLAST-Analytics-Health/1.0"})
            with urlopen(req, timeout=5) as _:
                pass
        except (HTTPError, URLError) as e:
            errors.append(f"DATA_SOURCE_URL unreachable: {e}")
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(health_check())
