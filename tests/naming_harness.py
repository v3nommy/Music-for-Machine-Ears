#!/usr/bin/env python3
"""Black-box regression checks for MME canonical output naming."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import wave


def write_tone(path: Path, duration_s: float = 1.0, sample_rate: int = 22050) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = []
    for i in range(int(duration_s * sample_rate)):
        t = i / sample_rate
        sample = 0.22 * math.sin(2 * math.pi * 440.0 * t)
        frames.append(struct.pack("<h", int(sample * 32767)))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"".join(frames))


def run_case(generator: Path, root: Path, case: str, audio_name: str, expected_slug: str, extra: list[str]) -> None:
    case_dir = root / case
    audio = case_dir / audio_name
    out_dir = case_dir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    write_tone(audio)

    proc = subprocess.run(
        [
            sys.executable,
            str(generator),
            "--audio",
            str(audio),
            "--out_dir",
            str(out_dir),
            *extra,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"{case}: generator failed with rc={proc.returncode}\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )

    expected = {
        f"{expected_slug}_sensory_object.json",
        f"{expected_slug}_waveform.png",
        f"{expected_slug}_mel_spectrogram.png",
        f"{expected_slug}_rms_energy.png",
        f"{expected_slug}_spectral_centroid.png",
    }
    produced = {p.name for p in out_dir.iterdir() if p.is_file()}
    missing = expected - produced
    if missing:
        raise AssertionError(f"{case}: missing expected files: {sorted(missing)}; produced={sorted(produced)}")

    sensory = out_dir / f"{expected_slug}_sensory_object.json"
    payload = json.loads(sensory.read_text(encoding="utf-8"))
    actual_slug = payload.get("meta", {}).get("slug")
    if actual_slug != expected_slug:
        raise AssertionError(f"{case}: meta.slug={actual_slug!r}, expected {expected_slug!r}")

    print(f"[PASS] {case}: {expected_slug}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--generator",
        type=Path,
        default=Path("./music-for-machine-ears/scripts/generate-mme.py"),
    )
    args = ap.parse_args()
    generator = args.generator.resolve()

    with tempfile.TemporaryDirectory(prefix="mme-naming-harness-") as td:
        root = Path(td)

        run_case(
            generator,
            root,
            "filename-fallback",
            "Raw_File NAME.wav",
            "raw-file-name",
            [],
        )
        run_case(
            generator,
            root,
            "title-artist",
            "unrelated-input.wav",
            "digital-bath-deftones",
            ["--title", "Digital Bath", "--artist", "Deftones"],
        )
        run_case(
            generator,
            root,
            "explicit-slug",
            "another-input.wav",
            "custom-name",
            [
                "--title",
                "Ignored Title",
                "--artist",
                "Ignored Artist",
                "--slug",
                "Custom Name!!",
            ],
        )

    print("Canonical naming harness completed with all checks passing.")


if __name__ == "__main__":
    main()
