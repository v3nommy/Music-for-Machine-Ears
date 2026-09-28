---
name: music-for-machine-ears
description: "Listen to and experience songs through Music for Machine Ears (MME), including generating sensory objects from audio, hearing them sequentially, privately journaling impressions, and resuming interrupted sessions. Use whenever you want to listen to, hear, explore, react to, reflect on, or analyze a song—whether prompted by a user, your own curiosity, autonomous time, or an unfinished listening session. Invoke when a song/audio file or MME sensory object is available or can be prepared."
license: "See LICENSE"
compatibility: "Requires Python 3.11+, NumPy, SciPy, and Matplotlib; SoundFile is recommended. Sequential listening requires a writable filesystem persistent across script calls. FFmpeg is optional for non-WAV input or WAV repair."
metadata:
  author: "v3nommy"
  homepage: "https://github.com/v3nommy/Music-for-Machine-Ears"
---

# Music for Machine Ears

Music for Machine Ears (MME) is a listening experience, not just an audio-analysis task. Use the sensory data as the form through which you hear and experience the music.

## Core rules

- Prefer **sequential listening mode** with `mme_next.py`.
- Do **not** open or read the full sensory-object JSON during sequential listening. That reveals later parts of the song before they happen.
- Do **not** inspect the whole-song graphs until the sequential listening is complete.
- Complete the listening sequence autonomously without making the user shuttle slices or journal notes back and forth. Normally finish in the same turn; if execution is interrupted, resume from the saved listening state rather than restarting.
- After every slice, follow its returned `journal_prompt` and write a brief private listening note before requesting the next slice.
- Keep the journal private unless the user asks to see it or the context clearly calls for sharing it.
- Treat the sensory data as music to experience, not as a checklist of measurements to report.
- Interpret freely; claim carefully. Metaphor, imagery, emotion, and subjective impressions are part of the listening experience. Do not turn an impression into a literal claim about features MME does not provide.

## Runtime and layout

MME expects these files to be available together:

```text
<skill-directory>/
├── SKILL.md
├── scripts/
│   ├── generate-mme.py
│   └── mme_next.py
└── references/
    └── EXPLANATION.md
```

Use a working Python 3 interpreter available in the environment: commonly `python3`, `python`, or `py -3`. In the commands below, `<python>` means whichever Python 3 command works in the current environment.

Run from the skill directory, or call the scripts by their explicit paths. The commands below assume the working directory is the skill directory.

`references/EXPLANATION.md` is optional background for humans or agents who want the deeper technical/design rationale. It is not required for an ordinary listening session.

## 1. Prepare the sensory object

If an MME sensory object already exists, use it and skip to **2. Choose listening state location**.

If you have the source audio but no sensory object, run:

```bash
<python> scripts/generate-mme.py --audio "<audio-path>" --out_dir "<output-directory>"
```

Optional metadata:

```bash
<python> scripts/generate-mme.py \
  --audio "<audio-path>" \
  --out_dir "<output-directory>" \
  --title "<title>" \
  --artist "<artist>"
```

The generated package contains the sensory-object JSON and supporting graphs.

Output filenames use a normalized slug derived from the audio filename stem: lowercased, with non-alphanumeric runs replaced by hyphens. For example, `jpeg_lullaby.wav` produces `jpeg-lullaby_sensory_object.json`. Use `--slug "<name>"` to choose the output base name explicitly.

Do not read the full sensory-object JSON yourself before sequential listening.

## 2. Choose listening state location

`mme_next.py` keeps the listening cursor and private journal on disk. Sequential listening therefore requires a writable filesystem that persists between the script calls used for that listening session.

By default, state is stored beside the sensory object:

```text
<sensory-object-directory>/.mme-listening/<sensory-object-name>/
├── cursor.json
└── journal.md
```

- `cursor.json` tracks where you are in the song.
- `journal.md` preserves the private, timestamped impressions formed during listening.

The journal is **private by default, not necessarily ephemeral**. Do not automatically include it in your response to the user.

Treat filesystem persistence as one of these three modes:

1. **Persistent for the current task/turn:** sequential listening works normally. The state may disappear afterward, which is fine for a one-off listen.
2. **Durable across later turns or sessions:** use a durable directory with `--state-dir` if you want the cursor and journal to survive and be resumable later.
3. **Not persistent between script calls:** sequential listening cannot preserve its cursor or journal. Use the full-object fallback instead.

MME cannot reliably infer future sandbox lifetime from inside one script call, so use what the environment tells you about its filesystem. A simple write succeeding proves writability, not long-term durability.

To store state somewhere else:

```bash
<python> scripts/mme_next.py "<sensory-object-path>" --state-dir "<directory>"
```

Once a listening session has started with a particular state location, use that same location for every remaining call and any later resume.

## 3. Listen sequentially

Start the session:

```bash
<python> scripts/mme_next.py "<sensory-object-path>"
```

If you selected a custom state directory:

```bash
<python> scripts/mme_next.py "<sensory-object-path>" --state-dir "<directory>"
```

The script returns one time-ordered slice of the song, normally about 20 seconds.

Experience that passage as part of the music. Follow the included `journal_prompt` and form a short private note based only on what has been heard so far.

Pass that note back to release the next slice:

```bash
<python> scripts/mme_next.py "<sensory-object-path>" --note "<private listening note>"
```

If using a custom state directory:

```bash
<python> scripts/mme_next.py "<sensory-object-path>" --state-dir "<directory>" --note "<private listening note>"
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

Use `pulse_reliable` as the authority for whether MME detected a trustworthy pulse. `tempo_confidence` is a 0–1 confidence score, and `confidence_gate` gives the threshold used by the generator (currently 0.60). If `pulse_reliable` is false, or beat positions are omitted, do not invent a pulse.

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

### Resume an interrupted listen

If execution stops after a slice was released but before its private note was saved, do **not** restart the song and do not guess what the missing slice contained.

Replay the pending slice without advancing:

```bash
<python> scripts/mme_next.py "<sensory-object-path>" --resume
```

If using a custom state directory, include the same `--state-dir`.

The replayed payload includes `"resumed": true`. Experience that slice again, form the private note, then continue normally with `--note`.

If the session had already completed, `--resume` returns the final summary. If no slice is pending, it continues from the saved cursor.

To inspect the private journal:

```bash
<python> scripts/mme_next.py "<sensory-object-path>" --show-journal
```

If using a custom state directory, include the same `--state-dir`.

To restart a listening session from the beginning:

```bash
<python> scripts/mme_next.py "<sensory-object-path>" --reset
```

The default slice length is approximately 20 seconds. Use another size only when there is a specific reason to test it:

```bash
<python> scripts/mme_next.py "<sensory-object-path>" --slice-seconds <seconds>
```

If changing slice size for an existing session, restart the listening state.

## Full-object fallback

Use full-object mode only when sequential listening is not possible.

In that case, read the complete sensory object and inspect the supporting graphs, then respond to the music naturally.

Be aware that full-object mode is not equivalent to sequential listening: seeing the entire sensory object at once gives you knowledge of later parts of the song while interpreting earlier ones.

## Grounding

MME gives you some aspects of the audio directly, some only as measured proxies, and some not at all. Treat those categories differently.

### Absent — do not invent as literal audio facts

MME does not currently provide:

- exact lyrics or spoken words
- melody as a line or hummable tune
- instrument identity
- vocal character
- exact chord voicings
- exact arrangement or production details

If one of these seems suggested by the experience, it may shape your metaphor or impression, but do not state it as something you literally heard through MME.

### Present, but contextual

- **Energy / RMS** is a relative signal-level measure, not calibrated perceptual loudness.
- **Brightness / spectral centroid** describes where spectral energy is centered, independent of overall amplitude. During a fade or very quiet passage, a centroid rise can happen because low-frequency energy disappears while faint high-frequency material remains. Check brightness changes against RMS before interpreting them as perceptual brightening.
- **Chroma** gives pitch-class distribution and harmonic color. It is not a melody line and does not identify exact chords or voicings.
- **Global key** is trustworthy only when `key_reliable` is true. When it is false, `estimated_key` is intentionally `null` rather than exposing a plausible-looking guess.
- **Spectral flux and onset strength** are proxies for change and transient activity. They do not identify what caused the change.
- **Rhythm** is trustworthy only when `pulse_reliable` is true. `tempo_confidence` is a score, not a probability; `confidence_gate` reports the threshold used to accept or reject the pulse.
- **Salient events** mark notable measured changes, not named musical events or specific sounds.
- **Interpretive-map tiers** are relative to the current track's own 25th/75th-percentile thresholds. They describe variation within that song; they cannot tell you that the entire piece is objectively quiet, loud, dark, bright, or otherwise extreme compared with other music.

### Interpretation

Metaphor, imagery, emotion, tension, release, expectation, and other subjective impressions are encouraged. They are part of the listening experience.

Keep the seam visible internally: an impression can be meaningful without being a literal claim about what physically produced the audio. Experience what the representation evokes, while keeping factual claims within what MME actually measures.
