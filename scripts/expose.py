#!/usr/bin/env python3
"""Expose local API: ngrok HTTP tunnel or Tailscale serve (prints commands)."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys


def main() -> None:
    p = argparse.ArgumentParser(description="Expose localhost API (ngrok or Tailscale hints).")
    p.add_argument("--port", type=int, default=8000, help="Local port (default 8000)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--ngrok", action="store_true", help="Run `ngrok http <port>` if installed")
    g.add_argument(
        "--tailscale",
        action="store_true",
        help="Print `tailscale serve` example (does not run automatically)",
    )
    args = p.parse_args()

    if args.ngrok:
        exe = shutil.which("ngrok")
        if not exe:
            print("ngrok not found in PATH. Install from https://ngrok.com/", file=sys.stderr)
            raise SystemExit(1)
        subprocess.run([exe, "http", str(args.port)], check=True)
        return

    if args.tailscale:
        print(
            "Tailscale (v1.52+): expose HTTPS to your tailnet, proxying to the API:\n"
            f"  tailscale serve --bg {args.port}\n"
            "Or HTTP only to local:\n"
            f"  tailscale serve --bg --tcp {args.port} tcp://127.0.0.1:{args.port}\n"
            "See: https://tailscale.com/kb/1242/tailscale-serve/",
        )
        return

    print(
        "Usage:\n"
        f"  uv run python scripts/expose.py --ngrok --port {args.port}\n"
        f"  uv run python scripts/expose.py --tailscale --port {args.port}\n",
    )


if __name__ == "__main__":
    main()
