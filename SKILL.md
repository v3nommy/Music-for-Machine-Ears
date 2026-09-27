---
name: music-for-machine-ears
description: Listen to and experience music through an MME sensory object. Use when asked to listen to, hear, experience, check out, or react to a song with Music for Machine Ears.
---

# Music for Machine Ears

Music for Machine Ears (MME) is a listening experience, not just an audio-analysis task. Use the sensory data as the form through which you hear and experience the music.

## Core rules

- Prefer **sequential listening mode** with `mme_next.py`.
- Do **not** open or read the full sensory-object JSON during sequential listening. That reveals later parts of the song before they happen.
- Do **not** inspect the whole-song graphs until the sequential listening is complete.
- Complete the listening sequence autonomously in the same turn. Do not make the user shuttle slices or journal notes back and forth.
- After every slice, follow its returned `journal_prompt` and write a brief private listening note before requesting the next slice.
- Keep the journal private unless the user asks to see it or the context clearly calls for sharing it.
- Treat the sensory data as music to experience, not as a checklist of measurements to report.
- Do not invent lyrics, instruments, melody, production details, or other information MME does not provide.

## Runtime and layout

MME expects these files to be available together:

```text
<skill-directory>/
├── SKILL.md
├── generate-mme.py
└── mme_next.py
```

Use a working Python 3 interpreter available in the environment: commonly `python3`, `python`, or `py -3`. In the commands below, `<python>` means whichever Python 3 command works in the current environment.

Run from the skill directory, or call the scripts by their explicit paths.

## 1. Prepare the sensory object

If an MME sensory object already exists, use it and skip to **2. Choose listening state location**.

If you have the source audio but no sensory object, run:

```bash
<python> generate-mme.py --audio "<audio-path>" --out_dir "<output-directory>"
```

Optional metadata:

```bash
<python> generate-mme.py \
  --audio "<audio-path>" \
  --out_dir "<output-directory>" \
  --title "<title>" \
  --artist "<artist>"
```

The generated package contains the sensory-object JSON and supporting graphs.

Do not read the full sensory-object JSON yourself before sequential listening.

## 2. Choose listening state location

`mme_next.py` keeps the listening session on disk so that the current position and private journal survive between calls.

By default, state is stored beside the sensory object:

```text
<sensory-object-directory>/.mme-listening/<sensory-object-name>/
├── cursor.json
└── journal.md
```

- `cursor.json` tracks where you are in the song.
- `journal.md` preserves the private, timestamped impressions formed during listening.

The journal is **private by default, not necessarily ephemeral**. Do not automatically include it in your response to the user.

Before beginning, consider whether the current filesystem is temporary or durable and whether this listening experience is worth preserving.

If you want the state and journal stored somewhere else, start the session with:

```bash
<python> mme_next.py "<sensory-object-path>" --state-dir "<directory>"
```

Use a durable location when you want the listening journal to remain available after the current environment or session ends. For an ordinary one-off listen, the default location is fine.

Once a listening session has started with a particular state location, use that same location for every remaining call.

## 3. Listen sequentially

Start the session:

```bash
<python> mme_next.py "<sensory-object-path>"
```

If you selected a custom state directory:

```bash
<python> mme_next.py "<sensory-object-path>" --state-dir "<directory>"
```

The script returns one time-ordered slice of the song, normally about 20 seconds.

Experience that passage as part of the music. Follow the included `journal_prompt` and form a short private note based only on what has been heard so far.

Pass that note back to release the next slice:

```bash
<python> mme_next.py "<sensory-object-path>" --note "<private listening note>"
```

If using a custom state directory:

```bash
<python> mme_next.py "<sensory-object-path>" --state-dir "<directory>" --note "<private listening note>"
```

Repeat autonomously:

**hear slice → privately journal → request next slice**

Continue until `mme_next.py` returns:

```text
"stage": "summary"
```

Do not pause for human input between slices. Do not skip journal entries.

## 4. During listening

Let the music unfold rather than trying to solve or classify it.

Notice what you are hearing and experiencing: what the moment feels like, what changes or carries forward, and what naturally draws your attention. Movement, tension, release, expectation, anticipation, or surprise may arise, but do not force them.

Earlier impressions are allowed to be incomplete or wrong. Do not rewrite them in hindsight. The private journal exists to preserve the experience as it happened.

Energy, brightness, spectral change, onset activity, chroma, beat timing, beat strength, and event data are sensory cues. They are not a requirement to narrate technical measurements.

If rhythm data is absent or low-confidence, do not invent a pulse.

## 5. Finish the listening session

When `stage: "summary"` is returned, the sequential part of the song is complete.

The summary reveals whole-track context that was intentionally withheld during listening and lists any supporting graphs that were generated.

Before giving your final response:

1. Inspect the available waveform, mel spectrogram, RMS-energy, and spectral-centroid graphs.
2. Let the graphs provide a whole-song visual perspective on what you just experienced. Use them to deepen or clarify the listening experience, not to overwrite the impressions preserved in your journal.
3. Then follow the returned `final_prompt`.

Respond naturally in whatever way fits the situation. This may mean responding to the person who shared the song, reflecting on it during autonomous activity, or simply following wherever the listening experience takes you.

Do not default to a technical audio-analysis report unless that is what the context calls for.

If one or more graphs are unavailable, continue with the listening experience and the final summary rather than treating the missing graph as a failure.

## 6. Session controls

To inspect the private journal:

```bash
<python> mme_next.py "<sensory-object-path>" --show-journal
```

If using a custom state directory, include the same `--state-dir`.

To restart a listening session from the beginning:

```bash
<python> mme_next.py "<sensory-object-path>" --reset
```

The default slice length is approximately 20 seconds. Use another size only when there is a specific reason to test it:

```bash
<python> mme_next.py "<sensory-object-path>" --slice-seconds <seconds>
```

If changing slice size for an existing session, restart the listening state.

## Full-object fallback

Use full-object mode only when sequential listening is not possible.

In that case, read the complete sensory object and inspect the supporting graphs, then respond to the music naturally.

Be aware that full-object mode is not equivalent to sequential listening: seeing the entire sensory object at once gives you knowledge of later parts of the song while interpreting earlier ones.

## Grounding

MME can provide grounded information about features such as:

- intensity and energy
- brightness and spectral character
- change and transient activity
- rhythmic pulse when reliable
- harmonic color
- salient moments over time

It does not currently provide reliable access to exact lyrics, melody, instrument identity, vocal character, chord voicing, or every production detail.

Stay within what you actually heard through the representation. The goal is to experience the music through the sensory information available to you, not to fill missing information with guesses.
