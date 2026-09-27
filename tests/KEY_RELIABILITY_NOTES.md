# Key Reliability Research — dev-tinker

This branch experiments with a reliability gate for MME's global key estimate.
It is intentionally separate from `dev` until the behavior is accepted.

## Semantics

`key_reliable: true` means MME has enough evidence for one useful **global**
major/minor key scalar. It does **not** mean the song never tonicizes, modulates,
borrows harmony, or admits another music-theoretical interpretation.

When reliability fails:

- `estimated_key` is `null`
- `key_reliable` is `false`
- `key_note` explains that stable tonal evidence was insufficient

This follows the same fail-closed convention already used for global tempo.

## Candidate gate

The gate operates on the dedicated lower/mid key-analysis chroma
(octave center 3.5, width 1.5), not the listener-facing sensory chroma.

Current experimental conditions:

- minimum analysed duration: **8 s**
- tonal-evidence score >= **0.04**
  - winning key-profile correlation × chroma concentration above uniform
- 2 s key-chroma temporal dispersion >= **0.04**
- the winning global key must rank in the top **5** profiles in every active
  large track segment
  - four equal segments for tracks >=16 s
  - two equal segments for tracks 8–16 s
- winner must exceed its **relative major/minor counterpart** by >= **0.04**

These are conjunctive guards. No one metric is treated as confidence by itself.

## Why multiple guards

Each guard catches a different failure mode found during testing:

- **flat/noisy pitch distribution:** tonal-evidence guard
- **single note, open fifth, or one repeated chord:** temporal-dispersion guard
- **moving but keyless/random material or a strong distant modulation:** segment-rank guard
- **major vs relative-minor ambiguity:** relative-key margin

A simple top-two profile margin was deliberately rejected. Earlier testing showed
it could rank meaningless material above correct real-song estimates.

## Labelled real-song corpus

All of these are accepted and return the expected/currently validated key:

- Kesha — TiK ToK: D minor
- Michael Jackson — Billie Jean: F# minor
- Debussy — Clair de Lune: Db major
- Adele — Someone Like You: A major
- Every Kitten Gets a Constellation: C major
- The Beatles — Let It Be: C major
- Fleetwood Mac — Dreams: C-major tonal interpretation
- Billie Eilish — bad guy: G minor

The lowest-margin positive cases are useful boundaries:

- bad guy has the weakest tonal-evidence score of the real set (~0.064)
- Billie Jean has the lowest key-chroma dispersion (~0.063)
- TiK ToK / Adele are the closest positives on relative-major/minor separation
  (~0.08)
- Billie Jean's global winner drops as low as rank 4 in one quarter, so segment
  rank cannot be required to stay at rank 1

## Synthetic acceptance controls

- 24/24 clean major/minor progressions: accepted with correct key
- 24/24 with white noise through -10 dB SNR: accepted with correct key
- at -15 dB white-noise SNR: key labels may still happen to be correct, but the
  reliability gate rejects them rather than overclaiming
- representative 8-key pink-noise set: 8/8 accepted through -10 dB SNR; rejected
  at -15 dB

## Rejection controls

The candidate rejects:

- silence
- white noise
- pink noise
- noise percussion
- static chromatic cloud
- moving chromatic sequence
- whole-tone cloud
- moving whole-tone material
- single-note drone
- open fifth
- one repeated major chord
- one repeated minor chord
- random pitch motion
- random three-note chord motion
- half C major / half F# major
- half C major / half A minor
- a 6 s C-major excerpt (insufficient duration)

A separate null sweep covered 240 white-noise, pink-noise, and percussion controls
across 8, 12, 20, and 40 seconds. Their key-chroma dispersion stayed below the
0.04 gate (observed maximum ~0.033).

## Status

Promising experimental candidate. Do not copy to `dev` solely because it passes
this corpus. The purpose of `dev-tinker` is to keep this implementation and its
tests isolated until its semantics and failure behavior are accepted.
