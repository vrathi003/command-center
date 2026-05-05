"""Start API (uvicorn) and optionally the Discord bot as child processes."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv


def main() -> None:
    root = Path(__file__).resolve().parent
    os.chdir(root)
    # Match finance_common.config: BotSettings reads .env, but this process must load it too
    # so DISCORD_BOT_TOKEN is visible for the spawn decision and inherited by child processes.
    load_dotenv(root / ".env")

    api_host = os.environ.get("API_HOST", "127.0.0.1")
    api_port = os.environ.get("API_PORT", "8000")

    procs: list[subprocess.Popen[bytes]] = []

    def shutdown(_sig: int | None = None, _frame: object | None = None) -> None:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    procs.append(
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "finance_api.main:app",
                "--host",
                api_host,
                "--port",
                api_port,
            ],
            cwd=root,
        ),
    )

    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if token and token != "your_bot_token_here":
        procs.append(
            subprocess.Popen(
                [sys.executable, "-m", "finance_bot.main"],
                cwd=root,
            ),
        )
    else:
        print(
            "Skipping Discord bot (set DISCORD_BOT_TOKEN in .env). "
            f"API is running at http://{api_host}:{api_port}",
            file=sys.stderr,
        )

    # First process to exit takes the whole group down
    while procs:
        for p in list(procs):
            code = p.poll()
            if code is not None:
                procs.remove(p)
                shutdown()
                sys.exit(code if code is not None else 0)
        import time

        time.sleep(0.2)


if __name__ == "__main__":
    main()
