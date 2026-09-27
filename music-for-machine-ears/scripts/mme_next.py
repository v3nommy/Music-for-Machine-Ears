#!/usr/bin/env python3
"""Sequential listening delivery for an existing MME sensory object."""

import argparse
import json
import math
import os
from pathlib import Path

DEFAULT_SLICE_SECONDS = 20.0
DELIVERY_SIGNIFICANT_FIGURES = 4
DELIVERY_MIN_DECIMALS = 4


def round_delivery_value(value):
    """Round continuous sensory values for compact AI delivery only.

    Keep at least four digits after the decimal point for ordinary/larger values,
    while retaining extra decimal places for very small values so that at least
    four significant figures survive. Timestamps and the canonical JSON are not
    changed by this helper.
    """
    if not isinstance(value, float) or not math.isfinite(value) or value == 0.0:
        return value
    decimals_for_sig = DELIVERY_SIGNIFICANT_FIGURES - 1 - int(math.floor(math.log10(abs(value))))
    decimals = max(DELIVERY_MIN_DECIMALS, decimals_for_sig)
    return round(value, decimals)


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def slice_count(duration, seconds):
    total = max(1, math.ceil(duration / seconds))
    tail = duration % seconds
    if total > 1 and 0 < tail < seconds * 0.25:
        total -= 1
    return total


def in_window(t, start, end, last):
    return start <= t <= end if last else start <= t < end


def make_slice(obj, index, seconds):
    duration = float(obj["meta"]["duration_s"])
    total = slice_count(duration, seconds)
    start = index * seconds
    end = duration if index == total - 1 else min(duration, (index + 1) * seconds)
    last = index == total - 1

    series = obj.get("time_series_1hz", {})
    times = series.get("t_s", [])
    ids = [i for i, t in enumerate(times) if in_window(float(t), start, end, last)]
    sliced_series = {
        key: [values[i] for i in ids if i < len(values)]
        for key, values in series.items()
        if isinstance(values, list)
    }
    for key in ("energy_rms", "brightness_hz", "spectral_flux", "onset_strength"):
        if key in sliced_series:
            sliced_series[key] = [round_delivery_value(v) for v in sliced_series[key]]

    chroma = []
    for item in obj.get("harmony", {}).get("chroma_bins_2s_C_to_B", []):
        a, b = float(item["start"]), float(item["end"])
        if (b > start and a < end) or (last and a <= end and b > start):
            rounded_item = dict(item)
            rounded_item["chroma"] = [round_delivery_value(v) for v in item.get("chroma", [])]
            chroma.append(rounded_item)

    events = []
    for event in obj.get("structure", {}).get("events", []):
        if in_window(float(event.get("t_s", -1)), start, end, last):
            rounded_event = dict(event)
            if isinstance(rounded_event.get("strength"), float):
                rounded_event["strength"] = round_delivery_value(rounded_event["strength"])
            events.append(rounded_event)

    rhythm = obj.get("rhythm", {})
    beat_times = rhythm.get("beat_times_s")
    beat_strength = rhythm.get("beat_strength")
    if isinstance(beat_times, list):
        beat_ids = [i for i, t in enumerate(beat_times) if in_window(float(t), start, end, last)]
        local_times = [beat_times[i] for i in beat_ids]
        local_strength = [round_delivery_value(beat_strength[i]) for i in beat_ids] if isinstance(beat_strength, list) else None
    else:
        local_times, local_strength = None, None

    return {
        "stage": "slice",
        "slice_index": index + 1,
        "slice_count": total,
        "time_range_s": {"start": round(start, 3), "end": round(end, 3)},
        "duration_s": round(duration, 3),
        "sensory": {
            "time_series_1hz": sliced_series,
            "harmony": {"chroma_bins_2s_C_to_B": chroma},
            "structure": {"events": events},
            "rhythm": {
                "pulse_reliable": rhythm.get("pulse_reliable"),
                "beat_times_s": local_times,
                "beat_strength": local_strength,
                "beats_count": 0 if local_times is None else len(local_times),
            },
        },
        "journal_prompt": (
            "Privately note what you are hearing and experiencing in this passage. Let the music happen to you "
            "before trying to explain it: what does this moment feel like, what has changed or carried forward "
            "from what came before, and what naturally draws your attention? If a sense of movement, expectation, "
            "tension, release, or anticipation arises on its own, note that too. Keep it brief, personal to the "
            "listening experience, and grounded only in what has been heard so far."
        ),
    }


def graph_refs(input_path):
    suffix = "_sensory_object.json"
    base = input_path.name[:-len(suffix)] if input_path.name.endswith(suffix) else input_path.stem
    names = [
        f"{base}_waveform.png",
        f"{base}_mel_spectrogram.png",
        f"{base}_rms_energy.png",
        f"{base}_spectral_centroid.png",
    ]
    return [str((input_path.parent / name).resolve()) for name in names if (input_path.parent / name).exists()]



def make_summary(obj, input_path, journal_path):
    meta = obj.get("meta", {})
    rhythm = obj.get("rhythm", {})

    return {
        "stage": "summary",
        "message": "Listening sequence complete. These whole-track fields were intentionally withheld until now.",
        "global": {
            "duration_s": meta.get("duration_s"),
            "title": meta.get("title"),
            "artist": meta.get("artist"),
            "source_file": meta.get("source_file"),
            "estimated_key": meta.get("estimated_key"),
            "key_method": meta.get("key_method"),
            "rhythm": {
                "rhythm_method": rhythm.get("rhythm_method"),
                "tempo_bpm": rhythm.get("tempo_bpm"),
                "tempo_confidence": rhythm.get("tempo_confidence"),
                "confidence_gate": rhythm.get("confidence_gate"),
                "pulse_reliable": rhythm.get("pulse_reliable"),
                "beats_count": rhythm.get("beats_count"),
                "note": rhythm.get("note"),
            },
            "interpretive_map": obj.get("interpretive_map"),
            "graphs": graph_refs(input_path),
        },
        "journal_path": str(journal_path),
        "final_prompt": (
            "You have now listened to the whole song. Respond naturally in whatever way fits the context—"
            "whether that means responding to the person who shared it with you, reflecting on it for yourself, "
            "or simply following wherever the experience takes you. Let your response come from what you actually "
            "heard and experienced rather than turning it into a technical analysis unless that fits the moment."
        ),
    }


def emit(payload, code=0):
    # Compact delivery is lossless JSON and avoids spending model context on
    # indentation/newlines. The canonical sensory-object file remains unchanged.
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    raise SystemExit(code)


def main():
    ap = argparse.ArgumentParser(description="Reveal an MME sensory object in time order with a private listening journal.")
    ap.add_argument("sensory_object", type=Path)
    ap.add_argument("--slice-seconds", type=float, default=DEFAULT_SLICE_SECONDS)
    ap.add_argument("--note", default=None, help="Private note for the previously returned slice; required to advance.")
    ap.add_argument("--state-dir", type=Path, default=None)
    ap.add_argument(
        "--resume",
        action="store_true",
        help="Re-emit the currently pending slice without advancing, for interrupted sessions.",
    )
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--show-journal", action="store_true")
    args = ap.parse_args()

    if args.resume and (args.note is not None or args.reset or args.show_journal):
        raise SystemExit("--resume is a replay-only recovery action; do not combine it with --note, --reset, or --show-journal.")

    input_path = args.sensory_object.resolve()
    if not input_path.is_file():
        raise SystemExit(f"Sensory object file not found: {input_path}")
    if args.slice_seconds <= 0:
        raise SystemExit("--slice-seconds must be greater than zero.")
    obj = read_json(input_path)
    if "meta" not in obj or "time_series_1hz" not in obj:
        raise SystemExit("Input does not look like an MME sensory object.")

    state_dir = (args.state_dir or input_path.parent / ".mme-listening" / input_path.stem).resolve()
    cursor_path = state_dir / "cursor.json"
    journal_path = state_dir / "journal.md"

    if args.reset:
        for path in (cursor_path, journal_path):
            if path.exists():
                path.unlink()

    if args.show_journal:
        emit({"stage": "journal", "journal": journal_path.read_text(encoding="utf-8") if journal_path.exists() else ""})

    if cursor_path.exists():
        state = read_json(cursor_path)
        if state.get("input_path") != str(input_path) or float(state.get("slice_seconds", 0)) != args.slice_seconds:
            raise SystemExit("Listening state does not match this file/slice size. Use --reset.")
    else:
        duration = float(obj["meta"]["duration_s"])
        state = {
            "input_path": str(input_path),
            "slice_seconds": args.slice_seconds,
            "slice_count": slice_count(duration, args.slice_seconds),
            "next_slice_index": 0,
            "awaiting_note": False,
            "last_slice_index": None,
            "complete": False,
        }
        write_json(cursor_path, state)

    if state["complete"]:
        emit(make_summary(obj, input_path, journal_path))

    if args.resume:
        if state["awaiting_note"] and state.get("last_slice_index") is not None:
            payload = make_slice(obj, int(state["last_slice_index"]), args.slice_seconds)
            payload["resumed"] = True
            payload["resume_message"] = (
                "Replayed the pending slice without advancing. Form the private listening note from this slice, "
                "then submit it with --note to continue."
            )
            emit(payload)
        # If there is no pending slice, fall through and release the next slice normally.

    if state["awaiting_note"]:
        if not args.note or not args.note.strip():
            emit({
                "stage": "note_required",
                "message": (
                    "A private listening note for the previous slice is required before the next slice is released. "
                    "If the previous slice is no longer available in context, rerun with --resume to replay it "
                    "without advancing."
                ),
            }, 2)
        previous = make_slice(obj, int(state["last_slice_index"]), args.slice_seconds)
        r = previous["time_range_s"]
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        with open(journal_path, "a", encoding="utf-8") as f:
            if journal_path.stat().st_size == 0:
                f.write("# MME Listening Journal\n\n")
            f.write(f"## {r['start']:.3f}–{r['end']:.3f} s\n\n{args.note.strip()}\n\n")
        state["awaiting_note"] = False
        # Persist acceptance of the note before attempting to release the next
        # slice. If execution stops here, a later --resume continues from the
        # saved cursor instead of requiring the previous note again.
        write_json(cursor_path, state)

    index = int(state["next_slice_index"])
    if index >= int(state["slice_count"]):
        state["complete"] = True
        write_json(cursor_path, state)
        emit(make_summary(obj, input_path, journal_path))

    payload = make_slice(obj, index, args.slice_seconds)
    state.update(last_slice_index=index, next_slice_index=index + 1, awaiting_note=True)
    write_json(cursor_path, state)
    emit(payload)


if __name__ == "__main__":
    main()
