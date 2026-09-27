#!/usr/bin/env python3
"""Targeted regression checks for MME audio-loading fallbacks."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile

from scipy.io import wavfile


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("mme_generate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--generator", type=Path, default=Path("./music-for-machine-ears/scripts/generate-mme.py"))
    args = ap.parse_args()

    if not shutil.which("ffmpeg"):
        print("[SKIP] ffmpeg not installed; streamed-WAV fallback test skipped.")
        return

    mme = load_module(args.generator.resolve())

    with tempfile.TemporaryDirectory(prefix="mme-audio-harness-") as td:
        streamed = Path(td) / "streamed.wav"
        with open(streamed, "wb") as out:
            proc = subprocess.run(
                [
                    "ffmpeg", "-v", "error",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
                    "-ac", "1", "-ar", "44100",
                    "-f", "wav", "pipe:1",
                ],
                stdout=out,
                stderr=subprocess.PIPE,
            )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.decode("utf-8", errors="replace"))

        header = streamed.read_bytes()[:4096]
        data_pos = header.find(b"data")
        placeholder = (
            header[4:8] == b"\xff\xff\xff\xff"
            or (data_pos >= 0 and header[data_pos + 4:data_pos + 8] == b"\xff\xff\xff\xff")
        )
        if not placeholder:
            raise AssertionError("Fixture did not contain a streamed-WAV placeholder size.")

        # Force the exact fallback path Claude found: no soundfile, scipy loader available.
        mme.HAS_SF = False
        mme.wavfile = wavfile

        y, sr = mme.load_audio_with_fallback(str(streamed))
        if sr != 44100:
            raise AssertionError(f"Expected repaired WAV at 44100 Hz, got {sr}.")
        if len(y) < 1000:
            raise AssertionError("Repaired streamed WAV returned too little audio.")
        if getattr(y, "ndim", None) != 1:
            raise AssertionError("Repaired audio was not mono.")

    print("[PASS] streamed WAV loads safely when soundfile is unavailable.")


if __name__ == "__main__":
    main()
