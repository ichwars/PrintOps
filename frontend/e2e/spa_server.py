"""Minimal no-network SPA server used only by Playwright acceptance tests."""

from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


class SpaHandler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript",
        ".mjs": "text/javascript",
        ".css": "text/css",
    }

    def do_GET(self) -> None:
        requested = urlsplit(self.path).path.lstrip("/")
        target = Path(self.directory, requested)
        if requested and not target.is_file() and not requested.startswith("assets/"):
            self.path = "/index.html"
        super().do_GET()

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True)
    parser.add_argument("--port", type=int, default=4173)
    args = parser.parse_args()
    handler = lambda *values, **kwargs: SpaHandler(*values, directory=args.directory, **kwargs)
    ThreadingHTTPServer(("127.0.0.1", args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
