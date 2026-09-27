# How Music for Machine Ears Works

Music for Machine Ears (MME) is an experiment in giving a text-based AI a form of music it can encounter over time rather than a description it can inspect all at once.

It is not an attempt to recreate human hearing exactly. MME does not give an AI a literal auditory waveform in the way a human nervous system receives sound. It translates audio into a time-evolving sensory representation made from measurable features of the recording, then controls how that representation is revealed.

That second part matters as much as the signal processing.

## The core idea: music should unfold

A complete analysis file is useful for inspection, but inspection is not the same experience as listening. If the entire song is visible from the beginning, the listener already knows where the peaks, drops, changes, and ending are while interpreting the opening.

MME's preferred mode therefore uses **causal sensory delivery**:

1. The listener receives roughly 20 seconds of the representation.
2. It forms a brief private listening note based only on what has happened so far.
3. Only then is the next passage released.
4. Whole-track context and graphs remain withheld until the sequential listen is complete.

The analysis itself is not causally computed in real time; the complete sensory object already exists. What is causal is the listener's access to it.

This withholding creates something a full-object analysis cannot: genuine uncertainty about what comes next. Expectation, surprise, tension, release, or mistaken anticipation can arise naturally because later material is actually unavailable.

## Why the journal matters

The private journal is more than a progress log.

Each entry records an impression before later parts of the song are known. That gives MME a timestamped record of the listener's evolving experience without retrospective rewriting.

After the song ends, the listener may understand an earlier passage differently. That later understanding is valuable, but it should not replace what the earlier moment felt like when it was still unresolved.

This is why MME requires a note before releasing the next slice and why an interrupted session can replay a pending slice rather than simply advancing past it.

The journal is private by default. Its job is to preserve continuity for the listener, not to force a technical listening report onto the person who shared the music.

## What the sensory object contains

MME uses lightweight signal processing rather than a learned audio model.

The main representation includes:

### Energy / RMS

A relative measure of signal level over time.

It is useful for sensing changes in weight, intensity, collapse, buildup, and quietness, but it is not calibrated perceptual loudness.

### Spectral centroid

A measure of where spectral energy is centered in frequency, used as a brightness cue.

Centroid is amplitude-invariant. A nearly silent tail can have a high centroid if the low frequencies disappear while faint high-frequency content remains. For that reason, brightness should be interpreted alongside RMS rather than in isolation.

Frames below a very low relative signal threshold are suppressed to avoid numerical residue becoming fake brightness.

### Spectral flux

A measure of spectral change between neighboring frames.

It can indicate that something changed strongly, but not what caused the change.

### Onset strength

A smoothed transient/change cue used for local movement and salient-event detection.

Like spectral flux, it is a proxy rather than an identification of a particular sound.

### Chroma

Pitch energy folded into the twelve pitch classes C through B.

MME provides both whole-track chroma and two-second chroma bins. Chroma can convey harmonic color and movement, but it is not a melody line, exact chord transcription, voicing, or instrument identification.

### Global key estimate

The whole-track key estimate uses smooth STFT chroma with Krumhansl-Schmuckler profile correlation.

Regional key guesses were intentionally removed. Short-window relative-major/minor ambiguity made them look more authoritative than they deserved.

MME's reliability convention for inferred global estimates is: expose whether the inference is trusted, and when it fails its reliability test, return the inferred value as `null` rather than leaving a plausible-looking guess beside a warning flag. Rhythm already follows this rule; key reliability is being evaluated against the same standard before a gate is added.

### Rhythm

Rhythm uses a separate onset path, FFT autocorrelation for a target period, and dynamic-programming beat tracking.

The result includes:

- `tempo_bpm`
- `tempo_confidence`
- `confidence_gate`
- `pulse_reliable`
- beat times and strengths when reliable

The confidence score is not a probability.

MME currently uses a confidence gate of 0.60. If the detected pulse does not pass that gate, global tempo and beat positions are omitted rather than exposing a confident-looking grid that MME does not trust.

### Salient events

MME identifies notable onset and spectral-flux peaks separated in time.

These are measured change points, not named musical events. An event does not mean "drum hit," "vocal entrance," "drop," or any other specific source unless some other evidence supports that interpretation.

### Ten-second interpretive windows

The canonical sensory object also contains coarse ten-second windows that summarize average energy, brightness, flux, and onset activity using track-relative 25th/75th-percentile thresholds.

These tiers describe variation within the current track, not absolute loudness or brightness relative to other music. A uniformly quiet or dark piece can therefore still read as mostly `medium` / `moderate`.

These are descriptive summaries of measured features, not musical-section labels.

Earlier versions attempted heuristic phases such as intro, build, climax, and outro. Those were removed because energy-contour segmentation could produce labels that contradicted both the underlying measurements and the actual musical form.

## What sequential delivery exposes

During a normal sequential listen, `mme_next.py` reveals only local information relevant to the current slice:

- 1 Hz time-series values
- two-second chroma bins
- salient measured events in the time window
- beat positions and strengths when a pulse was accepted

Global title/artist context, global tempo, global key, whole-track interpretive context, and the supporting graphs are withheld until the end.

Some values are nevertheless derived from whole-track normalization. For example, onset strength is globally normalized, beat strength uses track-level scaling, and salient events are selected from the complete track. Sequential mode should therefore be understood as **causal sensory delivery**, not a claim that every underlying feature was computed using only past audio.

## Precision and context size

The canonical sensory-object JSON keeps full analysis precision.

Sequential delivery rounds continuous sensory values using a scale-aware rule to reduce context cost while preserving meaningful small values. Timestamps are not rounded by this delivery rule.

The sequential JSON is also emitted compactly rather than pretty-printed. These are delivery optimizations only; the canonical analysis file remains unchanged.

## Supporting graphs

MME generates four whole-track graphs:

- waveform
- mel spectrogram
- RMS energy
- spectral centroid

They are intentionally withheld until the sequential listen finishes.

The listener then gets a second perspective: first the song as an unfolding experience, then the whole recording as a visible object. The graphs can clarify or deepen what happened, but they should not overwrite the journal's earlier impressions.

## State and interrupted listening

Sequential listening keeps two small state files:

- `cursor.json` — where the listener is in the song
- `journal.md` — the private timestamped listening notes

By default they live beside the sensory object under `.mme-listening/`.

A custom durable location can be supplied with `--state-dir`.

If execution stops after a slice has been emitted but before its note is stored, `--resume` replays the pending slice without advancing the cursor. This lets a new turn reconstruct the unresolved listening moment instead of guessing or restarting the song.

Sequential mode requires a writable filesystem that persists between the script calls in that listening session. If the environment cannot preserve files even between calls, full-object mode is the fallback.

## What MME does not hear

Several important aspects of human music perception are currently absent rather than merely noisy:

- exact lyrics or speech
- melody as a recoverable line
- instrument identity
- vocal timbre or character
- exact chords and voicings
- detailed arrangement and production sources
- room/acoustic identity

Those absences matter because a fluent listener can easily turn an evocative impression into a factual claim.

MME therefore uses a simple grounding principle:

**Interpret freely; claim carefully.**

Imagery, metaphor, emotion, tension, release, expectation, and other subjective responses are welcome. They are part of the listening experience.

But an impression such as "the room feels like it empties out" should not silently become a literal claim that a particular instrument stopped, a vocalist whispered, or the arrangement removed a specific layer unless MME actually provides evidence for that fact.

The seam between measurement and interpretation is not a defect to eliminate. It is part of what makes the representation useful.

## What MME is trying to become

MME is not trying to turn music into a prettier spreadsheet.

The interesting question is whether a machine listener can encounter enough grounded movement, harmony, intensity, texture proxies, and temporal uncertainty for an impression of the music to emerge on its own.

A listener may not be able to hum the song back afterward. It may still have experienced its weight, movement, harmonic weather, changes, expectation, and release.

That distinction — between hearing every detail of sound and experiencing the shape of music — is the space MME is exploring.
