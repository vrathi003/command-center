"""Serve Sphinx HTML under /guide/ so MagicDNS subpath + local preview share one URL shape."""

from __future__ import annotations

import argparse
import functools
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote


PREFIX = "/guide"


class DocsHandler(SimpleHTTPRequestHandler):
    """Serve ``directory`` at ``/`` and ``/guide/``; redirect bare ``/guide`` → ``/guide/``."""

    def _normalize_path(self) -> bool:
        """Rewrite /guide/* → /*. Return True if a redirect was sent."""
        path_only, sep, query = self.path.partition("?")
        path = unquote(path_only)
        if path == PREFIX:
            self.send_response(301)
            self.send_header("Location", PREFIX + "/")
            self.end_headers()
            return True
        if path == "/":
            self.send_response(302)
            self.send_header("Location", PREFIX + "/")
            self.end_headers()
            return True
        if path.startswith(PREFIX + "/"):
            stripped = path[len(PREFIX) :] or "/"
            self.path = stripped + (sep + query if sep else "")
        return False

    def do_GET(self) -> None:  # noqa: N802
        if self._normalize_path():
            return
        return super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802
        if self._normalize_path():
            return
        return super().do_HEAD()

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory",
        default=str(Path(__file__).resolve().parents[1] / "docs" / "site"),
        help="Sphinx HTML output directory",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    root = Path(args.directory).resolve()
    if not root.is_dir():
        raise SystemExit(f"docs directory not found: {root} (run: make docs)")

    handler = functools.partial(DocsHandler, directory=str(root))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving {root} at http://{args.host}:{args.port}{PREFIX}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)


if __name__ == "__main__":
    main()
