#!/usr/bin/env python3
"""Lightweight, fail-open update checker for Music for Machine Ears."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_API_URL = "https://api.github.com/repos/v3nommy/Music-for-Machine-Ears/releases/latest"
CHECK_INTERVAL_SECONDS = 48 * 60 * 60
NETWORK_TIMEOUT_SECONDS = 2.5
VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?$")


def installed_version() -> str:
    return (Path(__file__).resolve().parents[1] / "VERSION").read_text(encoding="utf-8").strip()


def version_tuple(value: str) -> tuple[int, int, int]:
    match = VERSION_PATTERN.fullmatch(value.strip())
    if not match:
        raise ValueError(f"Unsupported version: {value!r}")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def default_cache_file() -> Path:
    override = os.environ.get("MME_UPDATE_CACHE_DIR")
    if override:
        return Path(override).expanduser() / "update-check.json"

    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg).expanduser() / "music-for-machine-ears" / "update-check.json"

    local_app_data = os.environ.get("LOCALAPPDATA")
    if os.name == "nt" and local_app_data:
        return Path(local_app_data).expanduser() / "MusicForMachineEars" / "update-check.json"

    return Path.home() / ".cache" / "music-for-machine-ears" / "update-check.json"


def read_cache(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        return payload
    except (OSError, ValueError, TypeError):
        return None


def cache_is_fresh(payload: dict[str, Any], now: float) -> bool:
    try:
        checked_at = float(payload["checked_at_epoch"])
    except (KeyError, TypeError, ValueError):
        return False
    age = max(0.0, now - checked_at)
    return age < CHECK_INTERVAL_SECONDS


def write_cache(path: Path, payload: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(path)
    except OSError:
        # Cache persistence is optional. Update checking must never block MME.
        pass


def checks_disabled() -> bool:
    value = os.environ.get("MME_UPDATE_CHECK", "1").strip().lower()
    return value in {"0", "false", "no", "off", "disabled"}


def fetch_latest(api_url: str) -> tuple[str, str]:
    request = urllib.request.Request(
        api_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "music-for-machine-ears-update-checker",
        },
    )
    with urllib.request.urlopen(request, timeout=NETWORK_TIMEOUT_SECONDS) as response:
        payload = json.load(response)

    latest = str(payload["tag_name"]).strip()
    release_url = str(payload.get("html_url") or "").strip()
    version_tuple(latest)
    return latest.lstrip("v"), release_url


def result(
    *,
    status: str,
    installed: str,
    latest: str | None = None,
    update_available: bool = False,
    should_notify: bool = False,
    release_url: str = "",
    cached: bool = False,
) -> dict[str, Any]:
    return {
        "status": status,
        "installed_version": installed,
        "latest_version": latest,
        "update_available": update_available,
        "should_notify": should_notify,
        "release_url": release_url,
        "cached": cached,
    }


def check_for_update(api_url: str, cache_file: Path, force: bool = False) -> dict[str, Any]:
    try:
        installed = installed_version()
        installed_parts = version_tuple(installed)
    except (OSError, ValueError):
        return result(status="unavailable", installed="unknown")

    if checks_disabled():
        return result(status="disabled", installed=installed)

    now = time.time()
    cached_payload = read_cache(cache_file)

    if not force and cached_payload and cache_is_fresh(cached_payload, now):
        latest = str(cached_payload.get("latest_version") or "").strip() or None
        release_url = str(cached_payload.get("release_url") or "")
        try:
            available = bool(latest and version_tuple(latest) > installed_parts)
        except ValueError:
            available = False
        return result(
            status="cached",
            installed=installed,
            latest=latest,
            update_available=available,
            should_notify=False,
            release_url=release_url,
            cached=True,
        )

    try:
        latest, release_url = fetch_latest(api_url)
        available = version_tuple(latest) > installed_parts
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, urllib.error.URLError):
        return result(status="unavailable", installed=installed)

    write_cache(
        cache_file,
        {
            "checked_at_epoch": now,
            "latest_version": latest,
            "release_url": release_url,
        },
    )

    return result(
        status="update_available" if available else "current",
        installed=installed,
        latest=latest,
        update_available=available,
        should_notify=available,
        release_url=release_url,
        cached=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether a newer MME release is available.")
    parser.add_argument("--force", action="store_true", help="Ignore the 48-hour cache for this check.")
    parser.add_argument("--cache-dir", help=argparse.SUPPRESS)
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help=argparse.SUPPRESS)
    args = parser.parse_args()

    cache_file = (
        Path(args.cache_dir).expanduser() / "update-check.json"
        if args.cache_dir
        else default_cache_file()
    )

    payload = check_for_update(args.api_url, cache_file, force=args.force)
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
