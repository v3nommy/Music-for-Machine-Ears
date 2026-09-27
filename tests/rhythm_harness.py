#!/usr/bin/env python3
"""Small external regression harness for Music for Machine Ears rhythm tracking.

The harness treats generate-mme.py as a black box: it generates WAV fixtures,
runs the CLI, then reads the public sensory-object JSON. Use it on current main
without --strict to record a baseline, then on the candidate with --strict.

Examples:
  python tests/rhythm_harness.py --script ./music-for-machine-ears/scripts/generate-mme.py
  python tests/rhythm_harness.py --script ./music-for-machine-ears/scripts/generate-mme.py --strict
  python tests/rhythm_harness.py --script ./music-for-machine-ears/scripts/generate-mme.py \
      --compare-script ./generate-mme-main.py --strict
"""

import argparse
import copy
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import matplotlib.image as mpimg
import numpy as np
from scipy.io import wavfile

SR = 22050
TOLERANCE_S = 0.070


def decaying_noise_burst(rng, length_s=0.03):
    n = max(16, int(round(length_s * SR)))
    envelope = np.exp(-np.arange(n) / (0.006 * SR))
    return (rng.normal(0.0, 1.0, n) * envelope).astype(np.float32)


def click_track(bpm, duration_s=60.0, jitter_s=0.0, lead_s=0.0, trail_s=0.0, seed=1):
    rng = np.random.default_rng(seed)
    total = lead_s + duration_s + trail_s
    y = np.zeros(int(math.ceil(total * SR)), dtype=np.float32)
    burst = decaying_noise_burst(rng)
    step = 60.0 / bpm
    t = lead_s
    truth = []
    while t < lead_s + duration_s:
        tj = t + (float(rng.normal(0.0, jitter_s)) if jitter_s else 0.0)
        i = int(round(tj * SR))
        if 0 <= i < len(y) - len(burst):
            y[i:i + len(burst)] += burst
            truth.append(float(tj))
        t += step
    return y, truth


def random_click_track(duration_s=20.0, rate_hz=2.0, seed=4):
    rng = np.random.default_rng(seed)
    y = np.zeros(int(duration_s * SR), dtype=np.float32)
    burst = decaying_noise_burst(rng)
    t = 0.0
    while True:
        t += float(rng.exponential(1.0 / rate_hz))
        if t >= duration_s:
            break
        i = int(round(t * SR))
        if i < len(y) - len(burst):
            y[i:i + len(burst)] += burst
    return y, []


def sustained_pad(duration_s=20.0):
    t = np.arange(int(duration_s * SR), dtype=float) / SR
    # A deliberately steady two-tone pad with no rhythmic modulation.
    return (0.14 * np.sin(2 * np.pi * 220 * t) + 0.08 * np.sin(2 * np.pi * 330 * t)).astype(np.float32), []


def white_noise(duration_s=20.0, seed=2):
    return np.random.default_rng(seed).normal(0.0, 0.1, int(duration_s * SR)).astype(np.float32), []


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
        raise RuntimeError(f"{name}: script failed\n{proc.stderr[-2000:]}")

    json_files = list(out_dir.glob("*_sensory_object.json"))
    if len(json_files) != 1:
        raise RuntimeError(f"{name}: expected one sensory JSON, found {len(json_files)}")
    with json_files[0].open("r", encoding="utf-8") as f:
        obj = json.load(f)
    return obj, out_dir


def f_measure(reference, estimated, tolerance=TOLERANCE_S):
    reference = list(reference)
    estimated = list(estimated or [])
    if not reference and not estimated:
        return 1.0
    if not reference or not estimated:
        return 0.0
    used = set()
    tp = 0
    for est in estimated:
        candidates = [(abs(est - ref), i) for i, ref in enumerate(reference) if i not in used]
        if not candidates:
            continue
        distance, idx = min(candidates)
        if distance <= tolerance:
            used.add(idx)
            tp += 1
    precision = tp / len(estimated)
    recall = tp / len(reference)
    return 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)


def tail_f_measure(reference, estimated, duration_s, tail_s=20.0):
    start = max(0.0, duration_s - tail_s)
    ref = [x for x in reference if x >= start]
    est = [x for x in (estimated or []) if x >= start]
    return f_measure(ref, est)


def tempo_error_percent(actual, reported):
    if reported is None:
        return float("inf")
    return abs(float(reported) - actual) / actual * 100.0


def rhythm_summary(obj):
    r = obj.get("rhythm", {})
    return {
        "tempo": r.get("tempo_bpm"),
        "confidence": r.get("tempo_confidence"),
        "beats": r.get("beats_count", len(r.get("beat_times_s") or [])),
        "beat_times": r.get("beat_times_s"),
        "note": r.get("note"),
    }


def normalized_non_rhythm(obj):
    obj = copy.deepcopy(obj)
    obj.pop("rhythm", None)
    meta = obj.get("meta", {})
    for key in (
        "created_utc",
        "analysis_notes",
        "tempo_bpm",
        "tempo_confidence",
        "tempo_reliable",
        "tempo_candidates_bpm",
        "beat0_s_est",
    ):
        meta.pop(key, None)
    return obj


def compare_graph_pixels(dir_a, dir_b):
    suffixes = ["waveform.png", "mel_spectrogram.png", "rms_energy.png", "spectral_centroid.png"]
    results = {}
    for suffix in suffixes:
        a = next(dir_a.glob(f"*_{suffix}"))
        b = next(dir_b.glob(f"*_{suffix}"))
        ia = mpimg.imread(a)
        ib = mpimg.imread(b)
        results[suffix] = ia.shape == ib.shape and np.array_equal(ia, ib)
    return results


def check(condition, message, failures, strict):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {message}")
    if strict and not condition:
        failures.append(message)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True, type=Path, help="MME script to evaluate")
    ap.add_argument("--compare-script", type=Path, default=None, help="Optional baseline script for non-rhythm regression comparison")
    ap.add_argument("--strict", action="store_true", help="Exit non-zero when candidate acceptance checks fail")
    args = ap.parse_args()

    failures = []
    fixtures = []
    for bpm in (97.0, 120.0, 128.5, 174.0):
        y, truth = click_track(bpm, duration_s=60.0, seed=int(bpm * 10))
        fixtures.append((f"steady-{bpm:g}", y, truth, {"kind": "steady", "bpm": bpm, "duration": 60.0}))
    y, truth = click_track(120.0, duration_s=40.0, jitter_s=0.015, seed=1201)
    fixtures.append(("jitter-120", y, truth, {"kind": "jitter", "bpm": 120.0, "duration": 40.0}))
    y, truth = click_track(120.0, duration_s=15.0, lead_s=2.3, trail_s=3.0, seed=1202)
    fixtures.append(("silent-edges", y, truth, {"kind": "edges", "lead": 2.3, "end": 17.3}))
    for duration_s in (20.0, 60.0):
        for seed in (1, 2, 3):
            fixtures.append((
                f"white-noise-{int(duration_s)}s-seed{seed}",
                *white_noise(duration_s=duration_s, seed=seed),
                {"kind": "negative"},
            ))
            fixtures.append((
                f"random-clicks-{int(duration_s)}s-seed{seed}",
                *random_click_track(duration_s=duration_s, seed=seed),
                {"kind": "negative"},
            ))
    fixtures.append(("sustained-pad-20s", *sustained_pad(duration_s=20.0), {"kind": "negative"}))
    fixtures.append(("sustained-pad-60s", *sustained_pad(duration_s=60.0), {"kind": "negative"}))
    y, truth = click_track(120.0, duration_s=5.0, seed=5)
    fixtures.append(("short-5s", y, truth, {"kind": "short"}))

    with tempfile.TemporaryDirectory(prefix="mme-rhythm-harness-") as td:
        td = Path(td)
        print(f"Evaluating: {args.script}\n")
        for name, audio, truth, spec in fixtures:
            print(name)
            try:
                obj, _ = run_mme(args.script, audio, name, td / "candidate")
            except Exception as exc:
                check(False, f"runs successfully: {exc}", failures, args.strict)
                continue
            r = rhythm_summary(obj)
            print(f"  tempo={r['tempo']} confidence={r['confidence']} beats={r['beats']}")
            kind = spec["kind"]
            if kind == "steady":
                bpm = spec["bpm"]
                # At the fast end, a coherent half/double-time level is a documented v1 limitation.
                candidates = [bpm]
                if bpm / 2 >= 40:
                    candidates.append(bpm / 2)
                if bpm * 2 <= 240:
                    candidates.append(bpm * 2)
                err = min(tempo_error_percent(c, r["tempo"]) for c in candidates)
                check(err <= 0.75, f"tempo within 0.75% of an accepted metrical level (error={err:.3f}%)", failures, args.strict)
                if bpm == 174.0 and r["tempo"] is not None and abs(r["tempo"] - bpm) / bpm > 0.05:
                    print("  [INFO] fast test resolved at half/double metrical level; accepted v1 limitation")
                else:
                    f = tail_f_measure(truth, r["beat_times"], spec["duration"], tail_s=20.0)
                    check(f >= 0.90, f"final-20s beat F >= 0.90 (F={f:.3f})", failures, args.strict)
            elif kind == "jitter":
                f = f_measure(truth, r["beat_times"])
                check(f >= 0.85, f"jittered beat F >= 0.85 (F={f:.3f})", failures, args.strict)
            elif kind == "edges":
                bt = r["beat_times"] or []
                no_early = not bt or min(bt) >= spec["lead"] - TOLERANCE_S
                no_late = not bt or max(bt) <= spec["end"] + TOLERANCE_S
                check(no_early and no_late, "does not march beats through silent edges", failures, args.strict)
            elif kind == "negative":
                check(
                    r["tempo"] is None and r["beats"] == 0 and r["beat_times"] is None,
                    "gates tempo and beat positions on no-pulse control",
                    failures,
                    args.strict,
                )
            elif kind == "short":
                check(isinstance(obj, dict) and "rhythm" in obj, "short file produces valid sensory JSON", failures, args.strict)
            print()

        if args.compare_script:
            print("Non-rhythm regression comparison")
            audio, _ = click_track(120.0, duration_s=12.0, seed=99)
            old_obj, old_dir = run_mme(args.compare_script, audio, "regression", td / "baseline")
            new_obj, new_dir = run_mme(args.script, audio, "regression", td / "candidate-regression")
            same_json = normalized_non_rhythm(old_obj) == normalized_non_rhythm(new_obj)
            check(same_json, "non-rhythm JSON is identical after allowed meta/timestamp differences", failures, args.strict)
            for name, same in compare_graph_pixels(old_dir, new_dir).items():
                check(same, f"graph pixels unchanged: {name}", failures, args.strict)

    if failures:
        print("\nFAILED CHECKS:")
        for item in failures:
            print(f"- {item}")
        raise SystemExit(1)
    print("\nHarness completed" + (" with all strict checks passing." if args.strict else "."))


if __name__ == "__main__":
    main()