# Music for Machine Ears

Music for Machine Ears (MME) is a portable AI skill for letting text-based agents experience music as it unfolds. It turns audio into a time-evolving sensory representation, then supports sequential listening so the song can arrive piece by piece rather than all at once.

## Start here

- **Agents:** read and follow [`SKILL.md`](SKILL.md). It is the authoritative execution workflow.
- **Humans:** this README gives the package overview. For the deeper design and technical rationale, see [`references/EXPLANATION.md`](references/EXPLANATION.md).

## Requirements

MME requires:

- Python 3.11+
- NumPy
- SciPy
- Matplotlib

SoundFile is recommended for robust and broader audio loading, but it is optional for ordinary compatible WAV input because MME has a built-in WAV fallback. FFmpeg is optional and is used for non-WAV input or WAV repair when needed.

Install the Python dependencies with:

```bash
python -m pip install numpy scipy matplotlib soundfile
```

Use the Python 3 command appropriate to your environment, such as `python3`, `python`, or `py -3`.

Sequential listening also requires a writable filesystem that persists across the script calls in a listening session.

## Update awareness

MME includes a small standard-library update checker. When the skill is invoked, the agent can run `scripts/check_update.py`; it contacts the project's latest GitHub release at most once every 48 hours and otherwise uses a local cache. If a newer version is found, the agent can let the user know and ask whether they want to update.

The checker is advisory and fail-open: lack of internet access, a timeout, or an unwritable cache never prevents MME from working. Set `MME_UPDATE_CHECK=0` to disable outbound update checks.

## Generated files

MME gives each song one canonical filesystem-safe slug, stored as `meta.slug`, and uses it for the sensory object and all four graph filenames. An explicit `--slug` takes priority; otherwise MME uses normalized `title + artist` when a title is provided, then falls back to the audio filename stem.

For example, `--title "Digital Bath" --artist "Deftones"` produces files beginning with `digital-bath-deftones_`.

After sequential listening finishes, the summary exposes the absolute graph paths in `global.graphs`; the agent should open those listed files before its final response.

Timed lyrics can be attached without changing the default blind-listening mode:

```bash
python music-for-machine-ears/scripts/generate-mme.py --audio "my-song.wav" --lyrics "my-song.lrc" --out_dir "./out"
```

The optional `lyrics` object includes `lyric_onset_s`: the first supplied timed
**lyric candidate**, not detected singing. Credits recognized by labels or exact
LRC title/artist/album/by metadata are excluded from `lines`; all timed text and
its classification remain in `timed_text`. Bracketed/parenthesized annotations
are `unknown`. Unmarked credits can still be mistaken for lyrics, and sung
parentheticals can be excluded. `first_timed_text_kind` makes the distinction
explicit; `first_timed_text_is_sung` is always null because text alone cannot
verify singing. Credit-only/annotation-only files return null onset. Files with
no valid timed text fail clearly; an omitted `--lyrics` adds no lyric object.

The last valid `[offset:milliseconds]` applies to the entire file, even at the
end, and is **added** to timestamps; negative results clamp to zero. Fractions
`.5`, `.50`, `.500` all mean half a second. Seconds must be below 60; hours-form
minutes must also be below 60. Plain minute counts may exceed 59. Only leading
timestamp tags are parsed; enhanced inline word timing is not supported. No
alignment with audio, duration correction, translation, or transcription occurs.

`mme_next.py` seals full lyrics, onset metadata, classifications and source
identity until summary. `--reveal-lyrics` reveals only candidate lines in the
current window, never the LRC filename or global onset. Windows are `[start,end)`;
the last includes the endpoint. Choose disclosure mode on the first call; it is
saved and inherited by subsequent calls and `--resume`. Changing a blind session
to reveal mode requires `--reset` or a separate state directory. Resume also
rejects a modified sensory object (legacy cursors acquire a hash on first use).

The user supplies the LRC file; no LRCLIB/web fetching, transcription, extra
model, or extra dependency is implemented here. Lyrics do not alter the audio
measurements. Keep supplied music and lyrics outside the repository; tests use
synthetic text and audio only. Sealing is a reader disclosure convention, not
encryption: the full lyrics remain in the sensory-object JSON.

For passage-local delivery, start with:

```bash
python music-for-machine-ears/scripts/mme_next.py "./out/my-song_sensory_object.json" --reveal-lyrics
```

Continue with the normal `--note` workflow; the saved disclosure mode persists.

## Package contents

```text
music-for-machine-ears/
├── README.md
├── SKILL.md
├── LICENSE
├── VERSION
├── scripts/
│   ├── check_update.py
│   ├── generate-mme.py
│   ├── lyrics.py
│   └── mme_next.py
└── references/
    └── EXPLANATION.md
```

- `SKILL.md` — authoritative instructions for the agent
- `VERSION` — installed MME package version
- `scripts/check_update.py` — lightweight cached check for newer GitHub releases
- `scripts/generate-mme.py` — generates the MME sensory object and supporting graphs
- `scripts/mme_next.py` — serves the song sequentially and manages listening state/private journaling
- `scripts/lyrics.py` — parses timed LRC lyrics without external dependencies
- `references/EXPLANATION.md` — deeper explanation of MME's design, measurements, and limitations
- `LICENSE` — Music for Machine Ears License 1.0

Keep these files together as one skill directory when installing or sharing MME. There is no universal MME install path: use your agent or harness's normal skill import/install mechanism, or place the extracted `music-for-machine-ears` directory wherever that harness loads skills from.

## Project

Original project: https://github.com/v3nommy/Music-for-Machine-Ears

MME is distributed under the terms in [`LICENSE`](LICENSE).
