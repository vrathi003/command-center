#!/usr/bin/env python3
"""One-time Gmail OAuth2 consent flow.

Normal use (machine has a browser):
    python scripts/setup_gmail.py --credentials ~/finance/gmail_credentials.json

Headless / Tailscale server (no browser on the machine running the API):
    python scripts/setup_gmail.py --credentials ~/finance/gmail_credentials.json --console
    # Copy the URL it prints, open it on any browser, click Allow,
    # paste the code back into the terminal.

After running, set in your .env:
    GMAIL_CREDENTIALS_PATH=~/finance/gmail_credentials.json
    GMAIL_TOKEN_PATH=~/finance/gmail_token.json

See gmail_todo.md for full GCP setup instructions.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Set up Gmail OAuth2 token")
    parser.add_argument(
        "--credentials",
        default="~/finance/gmail_credentials.json",
        help="Path to GCP OAuth2 credentials JSON (default: ~/finance/gmail_credentials.json)",
    )
    parser.add_argument(
        "--token",
        default="~/finance/gmail_token.json",
        help="Where to write the token (default: ~/finance/gmail_token.json)",
    )
    parser.add_argument(
        "--console",
        action="store_true",
        help=(
            "Use copy-paste flow instead of opening a browser. "
            "Use this when running on a headless server or remote machine (e.g. via Tailscale SSH)."
        ),
    )
    args = parser.parse_args()

    creds_path = Path(args.credentials).expanduser().resolve()
    token_path = Path(args.token).expanduser().resolve()

    if not creds_path.exists():
        print(f"[ERROR] Credentials file not found: {creds_path}", file=sys.stderr)
        print("Download it from Google Cloud Console:", file=sys.stderr)
        print("  Google Auth Platform → Clients → your Desktop app → Download JSON", file=sys.stderr)
        print("See gmail_todo.md for full setup instructions.", file=sys.stderr)
        sys.exit(1)

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: PLC0415
    except ImportError:
        print("[ERROR] Google API libraries not installed.", file=sys.stderr)
        print("Run: uv sync   (or: pip install google-auth-oauthlib google-api-python-client)", file=sys.stderr)
        sys.exit(1)

    scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
    print(f"Using credentials: {creds_path}")

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), scopes)

    if args.console:
        print()
        print("── Console (copy-paste) mode ──────────────────────────────────────")
        print("1. Copy the URL below and open it in any browser")
        print("2. Sign in with the Gmail you added as a test user")
        print("3. Click Allow")
        print("4. Copy the authorization code shown in the browser")
        print("5. Paste it below")
        print()
        creds = flow.run_console()
    else:
        print("Opening browser for OAuth consent…")
        print("(Use --console if you're on a headless/remote machine)")
        creds = flow.run_local_server(port=0)

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())

    print()
    print(f"✓ Token saved to: {token_path}")
    print()
    print("Add these to your .env:")
    print(f"  GMAIL_CREDENTIALS_PATH={creds_path}")
    print(f"  GMAIL_TOKEN_PATH={token_path}")
    print()
    print("Restart the API server. Gmail will now sync every 3 hours automatically.")
    print("Visit /email-inbox on the dashboard and click 'Sync now' to test.")


if __name__ == "__main__":
    main()
