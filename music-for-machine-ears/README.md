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
│   └── mme_next.py
└── references/
    └── EXPLANATION.md
```

- `SKILL.md` — authoritative instructions for the agent
- `VERSION` — installed MME package version
- `scripts/check_update.py` — lightweight cached check for newer GitHub releases
- `scripts/generate-mme.py` — generates the MME sensory object and supporting graphs
- `scripts/mme_next.py` — serves the song sequentially and manages listening state/private journaling
- `references/EXPLANATION.md` — deeper explanation of MME's design, measurements, and limitations
- `LICENSE` — Music for Machine Ears License 1.0

Keep these files together as one skill directory when installing or sharing MME. There is no universal MME install path: use your agent or harness's normal skill import/install mechanism, or place the extracted `music-for-machine-ears` directory wherever that harness loads skills from.

## Project

Original project: https://github.com/v3nommy/Music-for-Machine-Ears

MME is distributed under the terms in [`LICENSE`](LICENSE).
