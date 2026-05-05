#!/usr/bin/env python3
"""Convenience entrypoint: forwards to `scripts/setup.py`."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    script = root / "scripts" / "setup.py"
    raise SystemExit(subprocess.call([sys.executable, str(script)]))
