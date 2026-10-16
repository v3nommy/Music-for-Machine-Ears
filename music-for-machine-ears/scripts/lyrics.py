"""Parse supplied LRC timing; no audio or verification that text is sung."""
from __future__ import annotations
import re
from pathlib import Path

_TIMESTAMP = re.compile(r"\[(?:(?P<hours>\d+):)?(?P<minutes>\d{1,3}):(?P<seconds>\d{2})(?:[.,](?P<fraction>\d{1,3}))?\]")
_OFFSET = re.compile(r"^\[offset\s*:\s*([+-]?\d+)\s*\]$", re.I)
_METADATA = re.compile(r"^\[(ar|ti|al|by|re|ve|length):([^\]]*)\]$", re.I)
_CREDIT = re.compile(r"^(?:(?:lyrics?|words?|music|written|composed|arranged|produced|performed|sung|vocals?|singer|artist|title|album|lrc|作词|作曲|编曲|词|曲)\s*(?:by\b|[:：])|https?://|www\.)", re.I)


def classify_text(text, identities):
    if _CREDIT.search(text) or text.casefold() in identities:
        return "credit"
    if (text.startswith("[") and text.endswith("]")) or (text.startswith("(") and text.endswith(")")):
        return "unknown"
    if not any(c.isalpha() for c in text):
        return "unknown"
    return "lyric_candidate"


def parse_lrc(path: str | Path) -> dict:
    """Last valid offset applies globally, added in milliseconds (negative clamps to 0).

    Unmarked text is only a lyric candidate; labels cannot prove it was sung.
    Recognized credits/annotations remain in timed_text, not in lyric lines.
    """
    source = Path(path)
    raw_lines = source.read_text(encoding="utf-8-sig").splitlines()
    offset_s = 0.0
    identities = set()
    for raw in raw_lines:
        text = raw.strip()
        offset = _OFFSET.fullmatch(text)
        if offset:
            offset_s = int(offset[1]) / 1000
        meta = _METADATA.fullmatch(text)
        if meta and meta[1].lower() in {"ar", "ti", "al", "by"}:
            identities.add(meta[2].strip().casefold())
    entries = []
    seen = set()
    for raw in raw_lines:
        rest = raw.strip()
        matches = []
        while (match := _TIMESTAMP.match(rest)):
            matches.append(match)
            rest = rest[match.end():].lstrip()
        if not matches or not rest or re.match(r"\[\d", rest):
            continue
        kind = classify_text(rest, identities)
        for match in matches:
            hours = int(match["hours"] or 0)
            minutes, seconds = int(match["minutes"]), int(match["seconds"])
            if seconds >= 60 or (match["hours"] is not None and minutes >= 60):
                continue
            fraction = match["fraction"]
            time = hours * 3600 + minutes * 60 + seconds
            time += int(fraction) / 10 ** len(fraction) if fraction else 0
            time = round(max(0.0, time + offset_s), 3)
            key = (time, rest)
            if key not in seen:
                seen.add(key)
                entries.append({"time_s": time, "text": rest, "kind": kind})
    entries.sort(key=lambda item: item["time_s"])
    if not entries:
        raise ValueError("No valid timed text found in supplied LRC")
    lines = [{"time_s": e["time_s"], "text": e["text"]} for e in entries if e["kind"] == "lyric_candidate"]
    return {
        "format": "lrc", "source_file": source.name, "offset_s": offset_s,
        "lines": lines, "timed_text": entries,
        "first_timed_text_s": entries[0]["time_s"],
        "first_timed_text_kind": entries[0]["kind"],
        "first_timed_text_is_sung": None,
        "lyric_onset_s": lines[0]["time_s"] if lines else None,
        "onset_basis": "first supplied lyric candidate; unverified text classification and timing, not voice detection",
    }
