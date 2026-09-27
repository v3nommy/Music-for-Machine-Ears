#!/usr/bin/env python3
"""Black-box regression harness for MME sequential listening delivery."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def synthetic_object():
    duration = 45.0
    t = list(range(45))
    return {
        "meta": {
            "schema_version": "MME",
            "duration_s": duration,
            "estimated_key": "D minor",
            "key_method": "test",
            "source_file": "spoiler-title.wav",
        },
        "time_series_1hz": {
            "t_s": t,
            "energy_rms": [0.002050227 if i == 0 else round(i / 100, 3) for i in t],
            "brightness_hz": [1847.392817 if i == 0 else 1000 + i for i in t],
            "spectral_flux": [0.00003726 if i == 0 else i * 2 for i in t],
            "onset_strength": [round((i % 10) / 10, 2) for i in t],
        },
        "rhythm": {
            "rhythm_method": "native_dp_v1",
            "tempo_bpm": 120.0,
            "tempo_confidence": 0.91,
            "confidence_gate": 0.60,
            "pulse_reliable": True,
            "beats_count": 6,
            "beat_times_s": [1.0, 9.0, 19.5, 20.0, 21.0, 44.5],
            "beat_strength": [0.2, 0.4, 0.6, 0.8, 1.0, 0.5],
            "note": None,
        },
        "harmony": {
            "chroma_mean_12_C_to_B": [1 / 12] * 12,
            "chroma_bins_2s_C_to_B": [
                {"start": float(i), "end": float(min(i + 2, 45)), "chroma": [1 / 12] * 12}
                for i in range(0, 45, 2)
            ],
        },
        "structure": {
            "events": [
                {"t_s": 5.0, "kind": "onset_peak", "strength": 0.8},
                {"t_s": 22.0, "kind": "flux_peak", "strength": 1.2},
                {"t_s": 44.0, "kind": "onset_peak", "strength": 0.9},
            ],
        },
        "interpretive_map": {"window_s": 10, "summary_text": "Whole-song hindsight."},
    }


def run(reader: Path, sensory: Path, state_dir: Path, *extra: str):
    proc = subprocess.run(
        [sys.executable, str(reader), str(sensory), "--state-dir", str(state_dir), *extra],
        capture_output=True,
        text=True,
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"Reader did not emit JSON. rc={proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}") from exc
    return proc.returncode, payload, proc.stdout


def check(cond, msg, failures):
    print(("[PASS] " if cond else "[FAIL] ") + msg)
    if not cond:
        failures.append(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reader", type=Path, default=Path("./music-for-machine-ears/scripts/mme_next.py"))
    args = ap.parse_args()
    failures = []

    with tempfile.TemporaryDirectory(prefix="mme-listening-harness-") as td:
        root = Path(td)
        sensory = root / "test_sensory_object.json"
        sensory.write_text(json.dumps(synthetic_object()), encoding="utf-8")
        state = root / "state"

        rc, first, first_raw = run(args.reader, sensory, state)
        check(rc == 0 and first.get("stage") == "slice", "first call returns slice", failures)
        check(first.get("time_range_s") == {"start": 0.0, "end": 20.0}, "first slice is 0-20s", failures)
        first_text = json.dumps(first)
        check("estimated_key" not in first_text and "tempo_bpm" not in first_text and "interpretive_map" not in first_text, "hindsight fields are withheld", failures)
        check(first["sensory"]["rhythm"].get("pulse_reliable") is True, "slice exposes pulse reliability without leaking BPM", failures)
        check(first["sensory"]["time_series_1hz"]["t_s"] == list(range(20)), "1Hz series is windowed", failures)
        check(first["sensory"]["rhythm"]["beat_times_s"] == [1.0, 9.0, 19.5], "beat timestamps are windowed and strengths stay aligned", failures)
        check(first["sensory"]["time_series_1hz"]["energy_rms"][0] == 0.00205, "tiny values retain four significant figures", failures)
        check(first["sensory"]["time_series_1hz"]["brightness_hz"][0] == 1847.3928, "larger values retain at least four decimal places", failures)
        check(first["sensory"]["time_series_1hz"]["spectral_flux"][0] == 0.00003726, "very small values keep extra decimals instead of collapsing", failures)
        check("\\n" not in first_raw.strip(), "reader emits compact single-line JSON", failures)

        rc, blocked, _ = run(args.reader, sensory, state)
        check(rc == 2 and blocked.get("stage") == "note_required", "cannot advance without journal note", failures)

        rc, second, _ = run(args.reader, sensory, state, "--note", "The opening feels tentative; I expect it to gather momentum.")
        check(rc == 0 and second.get("time_range_s") == {"start": 20.0, "end": 40.0}, "note releases slice 2", failures)
        check(second["sensory"]["rhythm"]["beat_times_s"] == [20.0, 21.0], "boundary beat belongs to next slice", failures)

        rc, third, _ = run(args.reader, sensory, state, "--note", "The middle became more active than I expected.")
        check(rc == 0 and third.get("time_range_s") == {"start": 40.0, "end": 45.0}, "final partial slice is correct", failures)

        rc, summary, summary_raw = run(args.reader, sensory, state, "--note", "The ending settles after the rise.")
        check(rc == 0 and summary.get("stage") == "summary", "final note releases summary", failures)
        summary_text = json.dumps(summary)
        check('"estimated_key": "D minor"' in summary_text and '"tempo_bpm": 120.0' in summary_text, "summary reveals global key and tempo", failures)
        check("time_series_1hz" not in summary_text and "chroma_bins_2s_C_to_B" not in summary_text, "summary does not dump raw slices again", failures)
        check("Whole-song hindsight." in summary_text, "summary reveals non-phase interpretive hindsight", failures)
        check("\\n" not in summary_raw.strip(), "summary output is compact JSON", failures)

        rc, journal, _ = run(args.reader, sensory, state, "--show-journal")
        check(rc == 0 and journal.get("stage") == "journal", "journal can be surfaced on request", failures)
        jt = journal.get("journal", "")
        check("0.000–20.000 s" in jt and "20.000–40.000 s" in jt and "40.000–45.000 s" in jt, "journal preserves time-stamped impressions", failures)
        check("tentative" in jt and "more active" in jt and "ending settles" in jt, "journal preserves notes", failures)

        missing = root / "does-not-exist.json"
        proc = subprocess.run(
            [sys.executable, str(args.reader), str(missing), "--state-dir", str(root / "missing-state")],
            capture_output=True,
            text=True,
        )
        check(proc.returncode != 0 and "Sensory object file not found:" in proc.stderr, "missing file gets a clear error", failures)

        rc, restarted, _ = run(args.reader, sensory, state, "--reset")
        check(rc == 0 and restarted.get("slice_index") == 1, "reset restarts listening from slice 1", failures)
        rc, fresh_journal, _ = run(args.reader, sensory, state, "--show-journal")
        check(fresh_journal.get("journal", "") == "# MME Listening Journal\n\n", "journal exists immediately after session start", failures)

        # Pending-slice resume is replay-only and idempotent.
        rc, replay1, _ = run(args.reader, sensory, state, "--resume")
        rc2, replay2, _ = run(args.reader, sensory, state, "--resume")
        check(
            rc == 0 and rc2 == 0 and replay1.get("resumed") is True and replay1 == replay2,
            "pending slice can be replayed idempotently with --resume",
            failures,
        )

        # Complete a short independent session, then verify resume returns summary.
        completed_state = root / "completed-state"
        rc, _, _ = run(args.reader, sensory, completed_state, "--slice-seconds", "45")
        rc, completed, _ = run(args.reader, sensory, completed_state, "--slice-seconds", "45", "--note", "Complete.")
        check(rc == 0 and completed.get("stage") == "summary", "single-slice session completes", failures)
        rc, completed_resume, _ = run(args.reader, sensory, completed_state, "--slice-seconds", "45", "--resume")
        check(rc == 0 and completed_resume.get("stage") == "summary", "--resume on completed session returns summary", failures)

        # Simulate a saved incomplete cursor after note acceptance but before next slice release.
        idle_state = root / "idle-state"
        idle_state.mkdir(parents=True, exist_ok=True)
        idle_cursor = {
            "input_path": str(sensory.resolve()),
            "slice_seconds": 20.0,
            "slice_count": 3,
            "next_slice_index": 1,
            "awaiting_note": False,
            "last_slice_index": 0,
            "complete": False,
        }
        (idle_state / "cursor.json").write_text(json.dumps(idle_cursor), encoding="utf-8")
        (idle_state / "journal.md").write_text("# MME Listening Journal\n\n## 0.000–20.000 s\n\nSaved.\n\n", encoding="utf-8")
        rc, idle_resume, _ = run(args.reader, sensory, idle_state, "--resume")
        check(
            rc == 0 and idle_resume.get("stage") == "slice" and idle_resume.get("slice_index") == 2 and not idle_resume.get("resumed"),
            "--resume with no pending slice releases the next saved slice",
            failures,
        )

    if failures:
        print("\nFAILED:")
        for f in failures:
            print("-", f)
        raise SystemExit(1)
    print("\nAll listening-mode checks passed.")


if __name__ == "__main__":
    main()
