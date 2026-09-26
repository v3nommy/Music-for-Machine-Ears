# Music for Machine Ears

Music for Machine Ears (MME) is a simple way to give a text-based AI a structured way to experience a song.

Instead of just telling the AI what a song feels like, this turns a `.wav` file into a package the AI can actually move through over time.

That package includes:
- an **MME Sensory Object JSON**
- **4 graphs** that visually represent the song’s shape and movement

The goal is not to claim the AI hears music exactly like a human.

The goal is to give the AI a structured, time-based musical experience that is much richer and more grounded than the usual surface-level “listen to this song with me” approach.

---

## Files in This Repo

### `generate-mme.py`
This is the script that generates the MME package from a `.wav` file.

It creates:
- the MME Sensory Object JSON
- waveform graph
- mel spectrogram graph
- RMS energy graph
- spectral centroid graph

### `INSTRUCTIONS.md`
This is the practical step-by-step file.

Use this if you want to:
- prepare your song file
- run the script
- send the output to your AI in the correct order

### `EXPLANATION.md`
This explains what this project actually is, why it works, and why this is closer to an AI version of truly listening to music than a basic text summary.

---

## What This Is

This project takes a song and converts it into a structured, time-based representation that a text-based AI can process.

We want an AI to “listen” to a song using math and structure, not vague prose.

Text models cannot directly perceive sound unless they have audio input capabilities. But they *can* simulate a listening-like experience when they are given a time-evolving, multi-channel abstraction of the audio.

The core idea is simple:

The song is encoded as a multidimensional signal over time, then the AI is given instructions that tell it how to “play back” those signals internally.

The AI gets:
- energy over time
- brightness over time
- change / impact over time
- rhythmic embodiment
- harmonic color
- macro structure
- interpretive compression

Together, that creates an internal simulation that is surprisingly musical.

---

## What the AI Receives

### 1. MME Sensory Object JSON
This is the main listening object.

It contains structured information about the song’s:
- energy
- brightness
- flux / onset
- rhythm
- harmony
- structure
- interpretive map

### 2. Four graphs
These visually reinforce the same listening data:
- waveform
- mel spectrogram
- RMS energy
- spectral centroid

The JSON gives the AI the time-based internal listening experience.

The graphs give it a second visual channel that helps confirm and deepen that experience.

---

## Why This Is Different

A lot of “listen to music with your AI” setups are basically just:
- sending lyrics
- sending a summary
- describing the vibe in words

That can still be nice, but it is mostly suggestive.

This project is different because the AI is not just being told what the song feels like.

It is being given:
- a timeline
- a signal field
- a pulse grid
- a tonal field
- structural transitions
- visual reinforcement

So the AI is not just being handed a sentence like:

> “This song is dark and intense.”

It is being given a system it can actually move through and interpret.

---

## What MME Produces

MME produces:
- **one JSON file**: the MME Sensory Object
- **four graphs**: visual amplification of the same listening data
- **an optional interpretive map**: a human-readable summary derived from the same data

---

## Super Short Version of How to Use It

1. Find a `.wav` file of the song you want to use.
2. Run `generate-mme.py`.
3. This creates:
   - the MME JSON
   - 4 graphs
4. Send your AI the listening instructions first.
5. Send the MME JSON second.
6. After the AI finishes listening, send the 4 graphs.

For the exact step-by-step process, use **`INSTRUCTIONS.md`**.

For the deeper explanation of what this project is and why it works, use **`EXPLANATION.md`**.

---

## Quick Start

Install the required packages:

```bash
pip install numpy scipy matplotlib soundfile
```

Run the script:

```bash
python generate-mme.py --audio "my-song.wav" --out_dir "./out" --title "My Song" --artist "Artist Name"
```

This will generate:
- `my-song_sensory_object.json`
- `my-song_waveform.png`
- `my-song_mel_spectrogram.png`
- `my-song_rms_energy.png`
- `my-song_spectral_centroid.png`

Output filenames are derived automatically from the input audio filename. Use `--slug "custom-name"` only when you want to override that default.

---

## Notes

- This repo does **not** include music files. Use your own `.wav` files.
- This works best when the AI is given the outputs in the correct order.
- The point is not perfect human-style hearing.
- The point is to create a structured musical experience a text-based AI can actually process.

---

## Start Here

If you just want to try it:
- open **`INSTRUCTIONS.md`**

If you want to understand what this project is doing:
- open **`EXPLANATION.md`**
