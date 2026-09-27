#!/usr/bin/env python3
"""Research harness for MME key-estimate reliability.

This harness does NOT define a production reliability gate. It treats
generate-mme.py as a black box, creates tonal, non-tonal, and ambiguous WAV
fixtures, then measures candidate reliability signals from the public
chroma_mean_12_C_to_B output.

Use the resulting separation between fixture classes to choose a reliability
metric/gate before changing production key output.

Example:
  python tests/key_harness.py \
      --script ./music-for-machine-ears/scripts/generate-mme.py
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
from scipy.io import wavfile


SR = 22050
MAJOR_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88],
    dtype=float,
)
MINOR_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17],
    dtype=float,
)
MAJOR_PROFILE /= MAJOR_PROFILE.sum()
MINOR_PROFILE /= MINOR_PROFILE.sum()


def midi_hz(note):
    return 440.0 * (2.0 ** ((note - 69.0) / 12.0))


def soft_clip(y):
    peak = float(np.max(np.abs(y))) if len(y) else 0.0
    if peak > 0.9:
        y = y * (0.9 / peak)
    return y.astype(np.float32)


def chord_segment(root_pc, quality="major", duration_s=2.0, octave=4):
    intervals = {
        "major": [0, 4, 7],
        "minor": [0, 3, 7],
    }[quality]
    n = int(round(duration_s * SR))
    t = np.arange(n, dtype=float) / SR
    # C4 is MIDI 60; root_pc is C=0..B=11.
    root_midi = 60 + root_pc + 12 * (octave - 4)
    y = np.zeros(n, dtype=float)
    for interval in intervals:
        f = midi_hz(root_midi + interval)
        # Fundamental + mild second harmonic make the fixture less toy-like
        # while retaining a clear pitch-class distribution.
        y += 0.16 * np.sin(2 * np.pi * f * t)
        y += 0.035 * np.sin(2 * np.pi * 2 * f * t)
    fade = max(1, int(0.02 * SR))
    ramp = np.linspace(0.0, 1.0, fade)
    y[:fade] *= ramp
    y[-fade:] *= ramp[::-1]
    return y


def progression(root_pc, mode, duration_s=24.0):
    if mode == "major":
        # Tonic-weighted I-IV-V-I.
        specs = [(0, "major", 4), (5, "major", 2), (7, "major", 2), (0, "major", 4)]
    else:
        # Tonic-weighted i-iv-V-i. Major V helps establish minor-mode function.
        specs = [(0, "minor", 4), (5, "minor", 2), (7, "major", 2), (0, "minor", 4)]
    one_cycle = []
    for offset, quality, beats in specs:
        one_cycle.append(chord_segment((root_pc + offset) % 12, quality, duration_s=0.5 * beats))
    cycle = np.concatenate(one_cycle)
    repeats = max(1, int(math.ceil(duration_s * SR / len(cycle))))
    return soft_clip(np.tile(cycle, repeats)[: int(duration_s * SR)])


def white_noise(duration_s=20.0, seed=1):
    rng = np.random.default_rng(seed)
    return rng.normal(0.0, 0.12, int(duration_s * SR)).astype(np.float32)


def pinkish_noise(duration_s=20.0, seed=2):
    # Lightweight colored-noise control: shape white noise ~1/sqrt(f) in FFT.
    rng = np.random.default_rng(seed)
    n = int(duration_s * SR)
    x = rng.normal(0.0, 1.0, n)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1.0 / SR)
    scale = np.ones_like(f)
    scale[1:] = 1.0 / np.sqrt(f[1:])
    y = np.fft.irfft(X * scale, n=n)
    y /= np.std(y) + 1e-12
    return (0.12 * y).astype(np.float32)


def chromatic_cloud(duration_s=20.0):
    n = int(duration_s * SR)
    t = np.arange(n, dtype=float) / SR
    y = np.zeros(n, dtype=float)
    for pc in range(12):
        f = midi_hz(60 + pc)
        y += 0.035 * np.sin(2 * np.pi * f * t)
    return soft_clip(y)


def whole_tone_cloud(duration_s=20.0):
    n = int(duration_s * SR)
    t = np.arange(n, dtype=float) / SR
    y = np.zeros(n, dtype=float)
    for pc in (0, 2, 4, 6, 8, 10):
        y += 0.055 * np.sin(2 * np.pi * midi_hz(60 + pc) * t)
    return soft_clip(y)


def single_note_drone(pc=0, duration_s=20.0):
    n = int(duration_s * SR)
    t = np.arange(n, dtype=float) / SR
    f = midi_hz(60 + pc)
    return soft_clip(0.25 * np.sin(2 * np.pi * f * t) + 0.06 * np.sin(2 * np.pi * 2 * f * t))


def open_fifth(root_pc=0, duration_s=20.0):
    n = int(duration_s * SR)
    t = np.arange(n, dtype=float) / SR
    y = (
        0.20 * np.sin(2 * np.pi * midi_hz(60 + root_pc) * t)
        + 0.16 * np.sin(2 * np.pi * midi_hz(67 + root_pc) * t)
    )
    return soft_clip(y)


def noise_percussion(duration_s=20.0, seed=5):
    rng = np.random.default_rng(seed)
    y = np.zeros(int(duration_s * SR), dtype=float)
    burst_n = int(0.045 * SR)
    envelope = np.exp(-np.arange(burst_n) / (0.008 * SR))
    for t_s in np.arange(0.25, duration_s, 0.5):
        i = int(t_s * SR)
        if i + burst_n <= len(y):
            y[i : i + burst_n] += 0.35 * rng.normal(0.0, 1.0, burst_n) * envelope
    return soft_clip(y)


def silence(duration_s=20.0):
    return np.zeros(int(duration_s * SR), dtype=np.float32)


def profile_correlation(chroma_vec, profile):
    a = np.asarray(chroma_vec, dtype=float)
    b = np.asarray(profile, dtype=float)
    a = a - np.mean(a)
    b = b - np.mean(b)
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom <= 1e-12:
        return -1.0
    return float(np.dot(a, b) / denom)


def profile_scores(chroma):
    p = np.asarray(chroma, dtype=float)
    scores = []
    for i in range(12):
        scores.append(profile_correlation(p, np.roll(MAJOR_PROFILE, i)))
    for i in range(12):
        scores.append(profile_correlation(p, np.roll(MINOR_PROFILE, i)))
    return np.asarray(scores, dtype=float)


def candidate_metrics(chroma):
    p = np.asarray(chroma, dtype=float)
    total = float(np.sum(p))
    if total > 0:
        p = p / total
    mean = float(np.mean(p)) if p.size else 0.0
    maximum = float(np.max(p)) if p.size else 0.0
    minimum = float(np.min(p)) if p.size else 0.0

    positive = p[p > 0]
    if positive.size:
        entropy = float(-np.sum(positive * np.log(positive)) / np.log(12.0))
        geometric = float(np.exp(np.mean(np.log(positive))))
        flatness = float(geometric / mean) if mean > 0 and positive.size == 12 else 0.0
    else:
        entropy = 1.0
        flatness = 1.0

    scores = profile_scores(p)
    order = np.sort(scores)[::-1]
    best = float(order[0])
    second = float(order[1])
    margin = best - second
    score_mean = float(np.mean(scores))
    score_sd = float(np.std(scores))
    profile_z = (best - score_mean) / score_sd if score_sd > 1e-12 else 0.0

    uniform = np.full(12, 1.0 / 12.0)
    l2_uniform = float(np.linalg.norm(p - uniform))

    return {
        "max_min": float("inf") if minimum <= 1e-12 and maximum > 0 else (maximum / minimum if minimum > 0 else 1.0),
        "peak_mean": maximum / mean if mean > 0 else 1.0,
        "entropy": entropy,
        "entropy_concentration": 1.0 - entropy,
        "flatness": flatness,
        "l2_uniform": l2_uniform,
        "best_profile_corr": best,
        "profile_margin": margin,
        "profile_z": profile_z,
    }


def run_mme(script, audio, name, root):
    fixture_dir = Path(root) / name
    fixture_dir.mkdir(parents=True, exist_ok=True)
    wav_path = fixture_dir / f"{name}.wav"
    out_dir = fixture_dir / "out"
    out_dir.mkdir(exist_ok=True)
    wavfile.write(wav_path, SR, np.asarray(audio, dtype=np.float32))

    proc = subprocess.run(
        [sys.executable, str(script), "--audio", str(wav_path), "--out_dir", str(out_dir)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{name}: generator failed\n{proc.stderr[-2000:]}")

    json_files = list(out_dir.glob("*_sensory_object.json"))
    if len(json_files) != 1:
        raise RuntimeError(f"{name}: expected one sensory JSON, found {len(json_files)}")
    return json.loads(json_files[0].read_text(encoding="utf-8"))


def fmt(value):
    if isinstance(value, float):
        if math.isinf(value):
            return "inf"
        return f"{value:.4f}"
    return str(value)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--script",
        required=True,
        type=Path,
        help="MME generate-mme.py to evaluate",
    )
    ap.add_argument("--json", action="store_true", help="Also print machine-readable result JSON")
    args = ap.parse_args()

    fixtures = [
        ("C-major-progression", progression(0, "major"), "tonal", "C major"),
        ("G-major-progression", progression(7, "major"), "tonal", "G major"),
        ("D-major-progression", progression(2, "major"), "tonal", "D major"),
        ("A-minor-progression", progression(9, "minor"), "tonal", "A minor"),
        ("D-minor-progression", progression(2, "minor"), "tonal", "D minor"),
        ("white-noise", white_noise(), "non-tonal", None),
        ("pinkish-noise", pinkish_noise(), "non-tonal", None),
        ("chromatic-cloud", chromatic_cloud(), "non-tonal", None),
        ("noise-percussion", noise_percussion(), "non-tonal", None),
        ("silence", silence(), "non-tonal", None),
        ("C-drone", single_note_drone(0), "ambiguous", None),
        ("C-open-fifth", open_fifth(0), "ambiguous", None),
        ("whole-tone-cloud", whole_tone_cloud(), "ambiguous", None),
    ]

    results = []
    with tempfile.TemporaryDirectory(prefix="mme-key-harness-") as td:
        for name, audio, kind, expected in fixtures:
            obj = run_mme(args.script.resolve(), audio, name, td)
            chroma = obj.get("harmony", {}).get("chroma_mean_12_C_to_B", [])
            row = {
                "fixture": name,
                "kind": kind,
                "expected_key": expected,
                "estimated_key": obj.get("meta", {}).get("estimated_key"),
                **candidate_metrics(chroma),
            }
            row["correct"] = expected is None or row["estimated_key"] == expected
            results.append(row)

    columns = [
        "fixture",
        "kind",
        "expected_key",
        "estimated_key",
        "max_min",
        "peak_mean",
        "entropy_concentration",
        "flatness",
        "l2_uniform",
        "best_profile_corr",
        "profile_margin",
        "profile_z",
    ]
    widths = {c: max(len(c), *(len(fmt(r[c])) for r in results)) for c in columns}
    print("  ".join(c.ljust(widths[c]) for c in columns))
    print("  ".join("-" * widths[c] for c in columns))
    for row in results:
        print("  ".join(fmt(row[c]).ljust(widths[c]) for c in columns))

    tonal = [r for r in results if r["kind"] == "tonal"]
    non_tonal = [r for r in results if r["kind"] == "non-tonal"]
    ambiguous = [r for r in results if r["kind"] == "ambiguous"]
    print()
    print(f"Tonal key accuracy: {sum(r['correct'] for r in tonal)}/{len(tonal)}")
    for metric in (
        "max_min",
        "peak_mean",
        "entropy_concentration",
        "flatness",
        "l2_uniform",
        "best_profile_corr",
        "profile_margin",
        "profile_z",
    ):
        def span(rows):
            vals = [r[metric] for r in rows if math.isfinite(r[metric])]
            return (min(vals), max(vals)) if vals else (float("nan"), float("nan"))
        print(
            f"{metric:22s} tonal={span(tonal)} "
            f"non-tonal={span(non_tonal)} ambiguous={span(ambiguous)}"
        )

    if args.json:
        print("\nJSON")
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
