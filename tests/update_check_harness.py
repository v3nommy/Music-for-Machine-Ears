#!/usr/bin/env python3
"""Regression tests for MME's lightweight update checker."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class ReleaseHandler(BaseHTTPRequestHandler):
    tag_name = "v1.1"
    request_count = 0

    def do_GET(self):
        type(self).request_count += 1
        body = json.dumps(
            {
                "tag_name": type(self).tag_name,
                "html_url": f"https://example.invalid/releases/{type(self).tag_name}",
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def run_checker(script: Path, cache_dir: Path, api_url: str, env=None):
    command = [
        sys.executable,
        str(script),
        "--cache-dir",
        str(cache_dir),
        "--api-url",
        api_url,
    ]
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return json.loads(completed.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checker", required=True)
    args = parser.parse_args()

    checker = Path(args.checker).resolve()
    version_file = checker.parents[1] / "VERSION"
    assert version_file.read_text(encoding="utf-8").strip() == "1.0"

    ReleaseHandler.request_count = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), ReleaseHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        api_url = f"http://127.0.0.1:{server.server_port}/latest"
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)

            first = run_checker(checker, cache_dir, api_url)
            assert first["installed_version"] == "1.0", first
            assert first["latest_version"] == "1.1", first
            assert first["update_available"] is True, first
            assert first["should_notify"] is True, first
            assert first["cached"] is False, first
            assert ReleaseHandler.request_count == 1

            second = run_checker(checker, cache_dir, api_url)
            assert second["status"] == "cached", second
            assert second["update_available"] is True, second
            assert second["should_notify"] is False, second
            assert second["cached"] is True, second
            assert ReleaseHandler.request_count == 1

            env = os.environ.copy()
            env["MME_UPDATE_CHECK"] = "0"
            disabled = run_checker(checker, cache_dir, api_url, env=env)
            assert disabled["status"] == "disabled", disabled
            assert disabled["should_notify"] is False, disabled
            assert ReleaseHandler.request_count == 1

            unavailable = run_checker(
                checker,
                cache_dir / "unavailable",
                "http://127.0.0.1:1/unreachable",
            )
            assert unavailable["status"] == "unavailable", unavailable
            assert unavailable["should_notify"] is False, unavailable

        print("Update checker regression harness passed.")
        return 0
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
