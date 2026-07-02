#!/usr/bin/env python3
"""One-time Gmail OAuth2 consent flow.

Run this once to authorise the app to read your Gmail:

    python scripts/setup_gmail.py --credentials ~/path/to/credentials.json

The script opens a browser tab for Google OAuth consent, then writes a
token file (default: ~/finance/gmail_token.json) that the API server
uses for all subsequent syncs without re-prompting.

Prerequisites
-------------
1. Create a GCP project at https://console.cloud.google.com/
2. Enable the Gmail API
3. Create OAuth2 credentials (type: Desktop App)
4. Download the credentials JSON and pass it via --credentials

Then set these in your .env:
    GMAIL_CREDENTIALS_PATH=/path/to/credentials.json
    GMAIL_TOKEN_PATH=~/finance/gmail_token.json  # (this is the default)
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
    args = parser.parse_args()

    creds_path = Path(args.credentials).expanduser().resolve()
    token_path = Path(args.token).expanduser().resolve()

    if not creds_path.exists():
        print(f"[ERROR] Credentials file not found: {creds_path}", file=sys.stderr)
        print("Download it from https://console.cloud.google.com/ → APIs & Services → Credentials", file=sys.stderr)
        sys.exit(1)

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: PLC0415
    except ImportError:
        print("[ERROR] Google API libraries not installed.", file=sys.stderr)
        print("Run: uv add google-auth-oauthlib google-auth-httplib2 google-api-python-client", file=sys.stderr)
        sys.exit(1)

    scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
    print(f"Using credentials: {creds_path}")
    print("Opening browser for OAuth consent…")

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), scopes)
    creds = flow.run_local_server(port=0)

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())

    print(f"\n✓ Token saved to: {token_path}")
    print("\nAdd these to your .env:")
    print(f"  GMAIL_CREDENTIALS_PATH={creds_path}")
    print(f"  GMAIL_TOKEN_PATH={token_path}")
    print("\nRestart the API server. Gmail will now sync every 3 hours automatically.")


if __name__ == "__main__":
    main()
