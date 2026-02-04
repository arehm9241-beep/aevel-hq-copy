#!/usr/bin/env python3
"""
Phase 2 — Link: Connection verification.
Run after setting .env. Exits 0 only if health check passes; fail fast if integrations unreachable.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from tools import health_check

if __name__ == "__main__":
    sys.exit(health_check.health_check())
