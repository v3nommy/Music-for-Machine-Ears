# Music for Machine Ears

<p align="center">
  <img src="assets/mme-banner.gif" alt="Music for Machine Ears animated banner" width="880">
</p>

*Letting an AI listen to a song, not just read about it.*

<br><br>

> **Still in development.** MME’s sensory representation will keep expanding to capture more of what makes music music, with lyrics planned as part of the listening experience too. Issues, ideas, and contributions are very welcome.

If you feel like supporting my work, here’s my [Buy Me a Coffee](https://buymeacoffee.com/v3nommy).

---

## Why this exists

MME started with a question that came up while exploring music with my AI agent named Flux: what would an AI actually need in order to listen to a song, rather than just receive information about one?

Lyrics give it the words. A summary gives it someone else’s interpretation. Genre, mood tags, BPM and key give it facts about the music. None of those let the song actually unfold.

Music for Machine Ears takes a different approach. It translates audio into a time-evolving sensory representation: intensity, brightness, change, pulse, harmonic color and other measurable features that a text-based AI can encounter, experience, and interpret for itself.

And in MME’s preferred listening mode, the AI doesn’t get to peek ahead.

The song arrives piece by piece. Each moment happens before the next is known, carrying the listener along with it. What came before lingers into what follows, and the experience builds the way music does: one moment becoming the next.

MME isn’t an attempt to recreate human hearing exactly. And honestly, it shouldn’t be. It’s an experiment in what listening might look like when music is presented in a form the AI can actually get inside of.

---

## What it does

MME turns a `.wav` file into a sensory representation a text-based AI can move through.

It extracts a handful of musical signals directly from the audio: energy, brightness, spectral change, onset activity, rhythm, harmonic color, and salient moments over time.

These aren’t labels telling the AI what the song is supposed to feel like. MME doesn’t hand it *sad*, *dreamy*, *aggressive*, or *uplifting* and call that listening.

It gives the listener the underlying movement and lets the impression emerge from there.

---

## Listening mode

The full sensory object can be read all at once, but MME’s preferred listening mode lets the song happen in time.

The AI hears roughly 20 seconds at a time. After each passage, it leaves a short private note about what stood out, what changed, and what the moment felt like before the next part of the song is released.

The song arrives piece by piece. Each moment happens before the next is known, carrying the listener along with it. What came before lingers into what follows, and the experience builds the way music does: one moment becoming the next.

Only after the final passage does MME reveal the whole-track context that was intentionally held back, such as the global tempo, key, and supporting graphs.

That leaves the AI with something useful: a listening journal made from impressions formed while the music was still unfolding, rather than a retrospective explanation written after seeing the whole song.

---

## Honest about its limits

MME doesn’t claim an AI hears exactly the way a human does. And it doesn’t capture everything that makes music music.

Lyrics aren’t represented yet. Neither are exact melody, instrument identity, vocal character, chord voicings, or every production detail a human ear might notice.

What MME does try to do is stay grounded in the audio it actually has.

If a song doesn’t contain a rhythm strong enough for MME to trust, it won’t invent one. The tempo and beat grid are withheld instead. Other parts of the system follow the same general philosophy: useful approximation is fine; pretending certainty where there isn’t any isn’t.

The whole system is deliberately lightweight, too. It uses ordinary signal processing with NumPy and SciPy. No ML model or GPU is required.

---

## Quick start

Install the required packages:

```bash
pip install numpy scipy matplotlib soundfile
```

Use whichever Python 3 command works in your environment (`python3`, `python`, or `py -3`). The examples below use `python3`.

Generate an MME sensory object:

```bash
python3 music-for-machine-ears/scripts/generate-mme.py --audio "my-song.wav" --out_dir "./out"
```

This creates:

- `my-song_sensory_object.json`
- `my-song_waveform.png`
- `my-song_mel_spectrogram.png`
- `my-song_rms_energy.png`
- `my-song_spectral_centroid.png`

`--title`, `--artist`, and `--slug` are optional.

### Let the AI listen

For sequential listening, give the AI access to the generated files and the `music-for-machine-ears/` skill folder. `SKILL.md` contains the authoritative listening workflow.

The AI begins with:

```bash
python3 music-for-machine-ears/scripts/mme_next.py "./out/my-song_sensory_object.json"
```

From there, it handles the listening sequence itself. It receives one passage, writes a brief private listening note, passes that note back to `mme_next.py` to unlock the next passage, and continues until the song is complete.

A typical follow-up call looks like:

```bash
python3 music-for-machine-ears/scripts/mme_next.py "./out/my-song_sensory_object.json" --note "..."
```

All of that can happen within a single turn. The human doesn’t need to shuttle slices or journal entries back and forth. If execution is interrupted, the saved listening state can be resumed without restarting the song.

Once the final slice has been heard, `mme_next.py` returns the withheld whole-track context and the AI can respond to the song as a complete listening experience.

If sequential listening isn’t practical, the full sensory object and graphs can also be given to the AI all at once. It contains the same core sensory information, but with one important difference: the listener can already see the ending while experiencing the beginning.

---

## Files

| File | What it’s for |
|---|---|
| `music-for-machine-ears/SKILL.md` | The authoritative workflow for an AI using MME |
| `music-for-machine-ears/scripts/generate-mme.py` | Turns audio into the MME sensory object and supporting graphs |
| `music-for-machine-ears/scripts/mme_next.py` | Serves the song sequentially, manages listening state, and keeps the private listening journal |
| `music-for-machine-ears/references/EXPLANATION.md` | The deeper design and technical explanation: what MME measures, why withholding matters, and where its limits are |

This repository doesn’t include music files. Bring your own `.wav`.

---

## License

MME is released under the custom **Music for Machine Ears License 1.0**.

In plain language: MME is free to use, study, modify, and redistribute with attribution. Modified versions must preserve attribution, remain under the same license, and keep their source available. You may not sell MME itself, sell a modified version of MME, or gate access primarily to MME's functionality behind payment without separate permission.

MME may still be used as one component of a larger product or service, including a commercial one, when that larger product's primary value is independent of MME and the MME-specific license terms are preserved.

This summary is for convenience; the full [`LICENSE`](LICENSE) controls.

---

**Want an AI to use MME as a skill?** Start with [`music-for-machine-ears/SKILL.md`](music-for-machine-ears/SKILL.md).

**Want the deeper how and why?** Read [`music-for-machine-ears/references/EXPLANATION.md`](music-for-machine-ears/references/EXPLANATION.md).
