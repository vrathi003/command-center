#!/usr/bin/env python3
"""One-click local setup: `uv sync`, copy `.env.example` → `.env` if missing."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    subprocess.run(["uv", "sync"], cwd=ROOT, check=True)
    env_path = ROOT / ".env"
    example = ROOT / ".env.example"
    if not env_path.exists() and example.exists():
        shutil.copy(example, env_path)
        print("Created .env from .env.example — add secrets before production use.")
    print("Next: `uv run python start.py` (API + optional bot) or `cd dashboard && npm install && npm run dev`.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
