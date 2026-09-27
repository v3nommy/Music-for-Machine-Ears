import os, json, math, datetime, re, subprocess, tempfile, shutil, unicodedata, warnings
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from scipy import signal, ndimage

# Optional (preferred) WAV reading:
try:
    import soundfile as sf
    HAS_SF = True
except Exception:
    HAS_SF = False
    from scipy.io import wavfile

# -------------------------
# CONFIG (MME standard)
# -------------------------
SR_TARGET = 22050
HOP = 512
N_FFT = 2048
WINDOW_S = 10
CHROMA_BIN_S = 2

# Sensory chroma favors the middle/upper register for a useful perceptual view.
# Global key estimation uses a separate lower/mid weighting so upper harmonics
# do not dominate the tonic/mode estimate.
SENSORY_CHROMA_OCTAVE_CENTER = 5.0
SENSORY_CHROMA_OCTAVE_WIDTH = 2.0
KEY_CHROMA_OCTAVE_CENTER = 4.0
KEY_CHROMA_OCTAVE_WIDTH = 2.0

# Native rhythm tracker defaults. These are intentionally few and centralized so
# the public skill stays lightweight; the external harness is the place to tune them.
RHYTHM_GAMMA = 100.0
RHYTHM_DETREND_S = 1.5
RHYTHM_PRIOR_CENTER_BPM = 120.0
RHYTHM_PRIOR_OCTAVES = 0.75
RHYTHM_DP_TIGHTNESS = 100.0
RHYTHM_PERIODICITY_REF = 0.40
RHYTHM_CONFIDENCE_GATE = 0.60
RHYTHM_MIN_ACTIVITY_RATIO = 5e-3

# Fallback thresholds (used only if adaptive computation fails)
ENERGY_THRESH_DEFAULT = {"low": 0.05, "high": 0.10}
BRIGHT_THRESH_DEFAULT = {"dark": 1500.0, "bright": 2200.0}
BRIGHTNESS_SILENCE_RATIO = 1e-3  # -60 dB relative to peak frame level

NOTE_NAMES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
MAJOR_KEY_NAMES = ["C","Db","D","Eb","E","F","F#","G","Ab","A","Bb","B"]
MINOR_KEY_NAMES = ["C","C#","D","Eb","E","F","F#","G","G#","A","Bb","B"]

MAJOR_PROFILE = np.array([6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88], dtype=float)
MINOR_PROFILE = np.array([6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17], dtype=float)

MAJOR_PROFILE /= MAJOR_PROFILE.sum()
MINOR_PROFILE /= MINOR_PROFILE.sum()

def compute_adaptive_thresholds(energy_1hz, bright_1hz):
    """Compute percentile-based thresholds from the track's own data."""
    e = np.array(energy_1hz, dtype=float)
    b = np.array(bright_1hz, dtype=float)
    energy_thresh = {
        "low": float(np.percentile(e, 25)),
        "high": float(np.percentile(e, 75)),
    }
    bright_thresh = {
        "dark": float(np.percentile(b, 25)),
        "bright": float(np.percentile(b, 75)),
    }
    # Guard against degenerate tracks where all values are identical
    if energy_thresh["low"] >= energy_thresh["high"]:
        energy_thresh = ENERGY_THRESH_DEFAULT
    if bright_thresh["dark"] >= bright_thresh["bright"]:
        bright_thresh = BRIGHT_THRESH_DEFAULT
    return energy_thresh, bright_thresh

def tier_energy(x, thresh):
    if x < thresh["low"]:
        return "low"
    if x <= thresh["high"]:
        return "medium"
    return "high"

def tier_brightness(hz, thresh):
    if hz < thresh["dark"]:
        return "dark"
    if hz <= thresh["bright"]:
        return "moderate"
    return "bright"

def _ffmpeg_to_temp_wav(path):
    """Convert an audio file to a conventional PCM WAV via ffmpeg."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required to repair/convert this audio file but is not installed.")
    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", path, "-ar", "44100", "-ac", "1", "-sample_fmt", "s16", tmp],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg conversion failed: {result.stderr[:500]}")
        return tmp, lambda: os.path.exists(tmp) and os.unlink(tmp)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _ensure_wav(path):
    """If path is not a WAV file, convert to a temp WAV via ffmpeg. Returns (wav_path, cleanup_fn)."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".wav", ".wave"):
        return path, lambda: None
    return _ffmpeg_to_temp_wav(path)


def load_audio_mono(path):
    """Load audio (any SR), convert to mono float32 in [-1,1] if possible."""
    if HAS_SF:
        y, sr = sf.read(path, always_2d=True)
        y = y.mean(axis=1).astype(np.float32)
        # If integer-like, soundfile already gives float; keep as-is
        return y, int(sr)
    else:
        sr, y = wavfile.read(path)
        y = y.astype(np.float32)
        # Normalize common integer PCM formats
        if y.dtype != np.float32:
            pass
        if y.ndim == 2:
            y = y.mean(axis=1)
        # Heuristic normalization if looks like int range
        max_abs = np.max(np.abs(y)) + 1e-9
        if max_abs > 1.5:
            y = y / max_abs
        return y.astype(np.float32), int(sr)

def load_audio_with_fallback(path):
    """Load audio robustly, repairing/converting with ffmpeg when needed."""
    wav_path, cleanup = _ensure_wav(path)
    repair_cleanup = lambda: None
    try:
        # scipy.io.wavfile can trust placeholder sizes in streamed WAV headers
        # and attempt enormous allocations. Without soundfile, normalize WAVs
        # through ffmpeg first whenever ffmpeg is available.
        if not HAS_SF and os.path.splitext(wav_path)[1].lower() in (".wav", ".wave") and shutil.which("ffmpeg"):
            repaired_path, repair_cleanup = _ffmpeg_to_temp_wav(wav_path)
            return load_audio_mono(repaired_path)

        try:
            return load_audio_mono(wav_path)
        except (Exception, MemoryError) as first_error:
            try:
                repaired_path, repair_cleanup = _ffmpeg_to_temp_wav(wav_path)
                return load_audio_mono(repaired_path)
            except Exception as repair_error:
                raise RuntimeError(
                    f"Could not load audio directly ({first_error}) or after ffmpeg repair ({repair_error})."
                ) from repair_error
    finally:
        repair_cleanup()
        cleanup()

def resample_to_22050(y, sr):
    if sr == SR_TARGET:
        return y, sr
    # polyphase resample for quality/stability
    g = math.gcd(sr, SR_TARGET)
    up = SR_TARGET // g
    down = sr // g
    y_rs = signal.resample_poly(y, up, down).astype(np.float32)
    return y_rs, SR_TARGET

def stft_mag(y, sr):
    # SciPy STFT (consistent with N_FFT/HOP)
    f, t, Zxx = signal.stft(
        y, fs=sr,
        nperseg=N_FFT,
        noverlap=N_FFT - HOP,
        nfft=N_FFT,
        boundary=None,
        padded=False
    )
    mag = np.abs(Zxx).astype(np.float32)  # shape: (freq_bins, frames)
    return f, t, mag

def frame_rms_from_mag(mag):
    # Approx RMS from magnitude spectrum energy (not exact window correction; adequate proxy)
    # Use mean magnitude squared across freq bins
    p = np.mean(mag**2, axis=0)
    return np.sqrt(p + 1e-12)

def spectral_centroid(f, mag):
    # Centroid is unstable when virtually no signal is present. Suppress frames
    # below -60 dB of the track's peak frame level instead of turning numerical
    # residue into a spurious high-brightness reading.
    num = np.sum((f[:, None] * mag), axis=0)
    den = np.sum(mag, axis=0)
    centroid = num / (den + 1e-12)
    frame_level = np.sqrt(np.mean(mag.astype(float) ** 2, axis=0))
    peak_level = float(np.max(frame_level)) if frame_level.size else 0.0
    if peak_level > 0.0:
        centroid = np.where(
            frame_level >= peak_level * BRIGHTNESS_SILENCE_RATIO,
            centroid,
            0.0,
        )
    return centroid

def spectral_flux(mag):
    # positive differences between successive frames
    d = np.diff(mag, axis=1)
    d = np.maximum(d, 0.0)
    flux = np.sum(d, axis=0)
    # pad to same length as frames
    flux = np.concatenate([[0.0], flux])
    return flux

def smooth_1d(x, win=5):
    if win <= 1:
        return x
    w = np.ones(win, dtype=float) / win
    return np.convolve(x, w, mode="same")

def onset_envelope_from_flux(flux):
    # normalize and smooth
    x = flux.astype(float)
    x = x - np.min(x)
    x = x / (np.max(x) + 1e-9)
    x = smooth_1d(x, win=7)
    return x

def rhythm_onset_envelope(mag, frame_rate, gamma=RHYTHM_GAMMA, detrend_s=RHYTHM_DETREND_S):
    """Build a rhythm-only onset envelope from log-compressed spectral change.

    This is deliberately separate from onset_envelope_from_flux(), which remains
    the source for existing non-rhythm MME outputs.
    """
    if mag.size == 0 or mag.shape[1] == 0:
        return np.zeros(0, dtype=float)

    log_mag = np.log1p(gamma * np.maximum(mag.astype(float), 0.0))
    diff = np.diff(log_mag, axis=1)
    flux = np.sum(np.maximum(diff, 0.0), axis=0)
    flux = np.concatenate([[0.0], flux])

    # Avoid amplifying numerical residue from essentially stationary signals.
    spectral_level = float(np.mean(np.sum(log_mag, axis=0)))
    activity_ratio = float(np.std(flux) / (spectral_level + 1e-12)) if spectral_level > 0 else 0.0
    if activity_ratio < RHYTHM_MIN_ACTIVITY_RATIO:
        return np.zeros_like(flux, dtype=float)

    detrend_win = max(1, int(round(detrend_s * frame_rate)))
    if detrend_win > 1:
        baseline = ndimage.uniform_filter1d(flux, size=detrend_win, mode="nearest")
        flux = np.maximum(flux - baseline, 0.0)

    sd = float(np.std(flux))
    if not np.isfinite(sd) or sd <= 1e-12:
        return np.zeros_like(flux, dtype=float)
    return flux / sd


def estimate_rhythm_period(onset_env, frame_rate, bpm_min=40.0, bpm_max=240.0):
    """Estimate a target beat period using FFT autocorrelation + a broad tempo prior."""
    x = np.asarray(onset_env, dtype=float)
    if x.size < 3 or float(np.std(x)) <= 1e-12:
        return None, None, 0.0

    x = x - np.mean(x)
    ac = signal.correlate(x, x, mode="full", method="fft")[x.size - 1:]
    if ac.size < 3 or float(ac[0]) <= 1e-12:
        return None, None, 0.0
    ac = ac / float(ac[0])

    lag_min = max(1, int(math.ceil(frame_rate * 60.0 / bpm_max)))
    lag_max = min(ac.size - 2, int(math.floor(frame_rate * 60.0 / bpm_min)))
    if lag_max < lag_min:
        return None, None, 0.0

    lags = np.arange(lag_min, lag_max + 1, dtype=float)
    center_period = frame_rate * 60.0 / RHYTHM_PRIOR_CENTER_BPM
    prior = np.exp(-0.5 * (np.log2(lags / center_period) / RHYTHM_PRIOR_OCTAVES) ** 2)
    weighted = ac[lag_min:lag_max + 1] * prior
    best_lag = lag_min + int(np.argmax(weighted))

    # Sub-frame parabolic refinement reduces integer-lag tempo quantization.
    delta = 0.0
    denom = float(ac[best_lag - 1] - 2.0 * ac[best_lag] + ac[best_lag + 1])
    if abs(denom) > 1e-12:
        delta = 0.5 * float(ac[best_lag - 1] - ac[best_lag + 1]) / denom
        delta = float(np.clip(delta, -0.5, 0.5))

    period_frames = float(best_lag + delta)
    tempo_bpm = float(60.0 * frame_rate / period_frames)

    # Periodicity measures how distinct the selected autocorrelation peak is,
    # rather than its raw height. Aperiodic/noisy signals can retain a broad
    # positive autocorrelation floor without a true rhythmic peak.
    prominence_wlen = max(3, int(round(2.0 * best_lag)))
    if prominence_wlen % 2 == 0:
        prominence_wlen += 1
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        prominence = signal.peak_prominences(ac, [best_lag], wlen=prominence_wlen)[0]
    periodicity = float(np.clip(prominence[0] if prominence.size else 0.0, 0.0, 1.0))
    return period_frames, tempo_bpm, periodicity


def _gaussian_smooth(x, sigma):
    """Small NumPy Gaussian smoother used only by the beat tracker's local score."""
    x = np.asarray(x, dtype=float)
    if x.size == 0 or sigma <= 0.25:
        return x.copy()
    radius = max(1, int(math.ceil(3.0 * sigma)))
    grid = np.arange(-radius, radius + 1, dtype=float)
    kernel = np.exp(-0.5 * (grid / sigma) ** 2)
    kernel /= np.sum(kernel)
    return np.convolve(x, kernel, mode="same")


def track_beats_dp(onset_env, target_period, tightness=RHYTHM_DP_TIGHTNESS):
    """Ellis-style dynamic-programming beat tracker (Ellis, 2007)."""
    onset_env = np.asarray(onset_env, dtype=float)
    if onset_env.size < 2 or target_period is None or target_period <= 1.0:
        return [], onset_env.copy()

    local = _gaussian_smooth(onset_env, max(target_period / 32.0, 0.25))
    if local.size == 0 or float(np.max(local)) <= 1e-12:
        return [], local

    interval_min = max(1, int(math.floor(target_period / 2.0)))
    interval_max = max(interval_min, int(math.ceil(target_period * 2.0)))
    intervals = np.arange(interval_min, interval_max + 1, dtype=int)
    penalties = tightness * (np.log(intervals.astype(float) / target_period) ** 2)

    score = np.zeros(local.size, dtype=float)
    backlink = np.full(local.size, -1, dtype=int)

    for t in range(local.size):
        mask = intervals <= t
        if np.any(mask):
            valid_intervals = intervals[mask]
            candidates = score[t - valid_intervals] - penalties[mask]
            best = int(np.argmax(candidates))
            if float(candidates[best]) > 0.0:
                score[t] = local[t] + float(candidates[best])
                backlink[t] = t - int(valid_intervals[best])
            else:
                score[t] = local[t]
        else:
            score[t] = local[t]

    peaks, _ = signal.find_peaks(score)
    if peaks.size:
        median_peak = float(np.median(score[peaks]))
        eligible = peaks[score[peaks] >= 0.5 * median_peak]
        end = int(eligible[-1] if eligible.size else peaks[-1])
    else:
        end = int(np.argmax(score))

    beat_frames = []
    current = end
    while current >= 0:
        beat_frames.append(int(current))
        previous = int(backlink[current])
        if previous < 0 or previous >= current:
            break
        current = previous
    beat_frames.reverse()

    # Trim only weak edges; weak interior beats remain useful sensory data.
    edge_threshold = 0.5 * float(np.sqrt(np.mean(local ** 2)))
    while beat_frames and local[beat_frames[0]] < edge_threshold:
        beat_frames.pop(0)
    while beat_frames and local[beat_frames[-1]] < edge_threshold:
        beat_frames.pop()

    return beat_frames, local


def _beat_onset_maxima(onset_env, beat_frames, radius=2):
    onset_env = np.asarray(onset_env, dtype=float)
    values = []
    for frame in beat_frames:
        start = max(0, int(frame) - radius)
        end = min(onset_env.size, int(frame) + radius + 1)
        values.append(float(np.max(onset_env[start:end])) if end > start else 0.0)
    return values


def rhythm_confidence(onset_env, beat_frames, periodicity):
    """Return a bounded confidence score; it is a score, not a probability."""
    if len(beat_frames) < 2:
        return 0.0, []

    beat_maxima = _beat_onset_maxima(onset_env, beat_frames, radius=2)
    m_on = float(np.mean(beat_maxima)) if beat_maxima else 0.0
    first, last = int(beat_frames[0]), int(beat_frames[-1])
    m_all = float(np.mean(onset_env[first:last + 1])) if last >= first else 0.0

    salience = float(np.clip((m_on - m_all) / (m_on + m_all + 1e-12), 0.0, 1.0))
    periodicity_score = float(np.clip(periodicity / RHYTHM_PERIODICITY_REF, 0.0, 1.0))
    confidence = float(math.sqrt(periodicity_score * salience))

    scale = float(np.percentile(beat_maxima, 95)) if beat_maxima else 0.0
    if scale <= 1e-12:
        strengths = [0.0 for _ in beat_maxima]
    else:
        strengths = [float(round(np.clip(v / scale, 0.0, 1.0), 2)) for v in beat_maxima]
    return confidence, strengths


def tempo_from_tracked_beats(beat_times_s):
    """Estimate global BPM from the tracked sequence while averaging frame quantization."""
    if beat_times_s is None or len(beat_times_s) < 2:
        return None
    span = float(beat_times_s[-1] - beat_times_s[0])
    if span <= 0.0:
        return None
    return float(60.0 * (len(beat_times_s) - 1) / span)


def analyze_rhythm(mag, t_frames, frame_rate):
    """Run MME's self-contained rhythm path without changing other sensory channels."""
    rhythm_env = rhythm_onset_envelope(mag, frame_rate)
    period, estimated_bpm, periodicity = estimate_rhythm_period(rhythm_env, frame_rate)
    beat_frames, _ = track_beats_dp(rhythm_env, period)
    confidence, strengths = rhythm_confidence(rhythm_env, beat_frames, periodicity)

    candidate_times = [float(t_frames[i]) for i in beat_frames if 0 <= i < len(t_frames)]
    reliable = confidence >= RHYTHM_CONFIDENCE_GATE and len(candidate_times) >= 2

    if reliable:
        beat_times = candidate_times
        beat_strength = strengths[:len(beat_times)]
        tracked_bpm = tempo_from_tracked_beats(beat_times)
        tempo_bpm = tracked_bpm if tracked_bpm is not None else estimated_bpm
        note = None
    else:
        beat_times = None
        beat_strength = None
        tempo_bpm = None
        note = "No reliable pulse detected; tempo and beat positions omitted."

    return {
        "rhythm_method": "native_dp_v1",
        "tempo_bpm": None if tempo_bpm is None else float(round(tempo_bpm, 3)),
        "tempo_confidence": float(round(confidence, 3)),
        "confidence_gate": float(RHYTHM_CONFIDENCE_GATE),
        "pulse_reliable": bool(reliable),
        "beats_count": 0 if beat_times is None else int(len(beat_times)),
        "beat_times_s": None if beat_times is None else [float(round(x, 3)) for x in beat_times],
        "beat_strength": beat_strength,
        "note": note,
    }

def chroma_from_mag(f, mag, octave_center=SENSORY_CHROMA_OCTAVE_CENTER, octave_width=SENSORY_CHROMA_OCTAVE_WIDTH):
    # Smooth STFT-to-chroma projection. Hard-assigning each FFT bin to one pitch
    # class lets harmonics dominate pitch-class evidence; a smooth filterbank is
    # substantially more stable while keeping the implementation dependency-free.
    # The sensory representation and global key estimator intentionally use
    # different octave weightings.
    if mag.size == 0 or mag.shape[1] == 0:
        return np.zeros((12, mag.shape[1] if mag.ndim == 2 else 0), dtype=np.float32)

    freqs = np.asarray(f, dtype=float)
    if freqs.size < 2:
        return np.zeros((12, mag.shape[1]), dtype=np.float32)

    positive = np.maximum(freqs[1:], 1e-9)
    semitone_bins = 12.0 * np.log2(positive / (440.0 / 16.0))
    semitone_bins = np.concatenate([[semitone_bins[0] - 18.0], semitone_bins])
    bin_width = np.concatenate([np.maximum(np.diff(semitone_bins), 1.0), [1.0]])

    distance = semitone_bins[None, :] - np.arange(12, dtype=float)[:, None]
    distance = np.remainder(distance + 6.0 + 120.0, 12.0) - 6.0
    weights = np.exp(-0.5 * (2.0 * distance / bin_width[None, :]) ** 2)

    col_norm = np.sqrt(np.sum(weights ** 2, axis=0, keepdims=True)) + 1e-12
    weights /= col_norm

    # Favor the requested register while retaining neighboring bass/upper
    # harmonics. Octave numbers are referenced so A440 is octave 4.
    octave_position = semitone_bins / 12.0
    weights *= np.exp(-0.5 * ((octave_position - octave_center) / octave_width) ** 2)[None, :]
    weights = np.roll(weights, -3, axis=0)  # C..B ordering

    raw = weights @ (mag.astype(float) ** 2)
    frame_level = np.sqrt(np.mean(mag.astype(float) ** 2, axis=0))
    peak_level = float(np.max(frame_level)) if frame_level.size else 0.0
    active = (
        frame_level >= peak_level * BRIGHTNESS_SILENCE_RATIO
        if peak_level > 0.0
        else np.zeros_like(frame_level, dtype=bool)
    )

    chroma = np.zeros_like(raw, dtype=float)
    frame_max = np.max(raw, axis=0)
    valid = active & (frame_max > 1e-12)
    chroma[:, valid] = raw[:, valid] / frame_max[valid]
    return chroma.astype(np.float32)

def normalize_chroma(v):
    s = float(np.sum(v))
    if s <= 0:
        return v
    return v / s

def chroma_bins(chroma, t_frames, duration_s, bin_s=2):
    n_bins = int(math.ceil(duration_s / bin_s))
    out = []
    for b in range(n_bins):
        start = b * bin_s
        end = min((b + 1) * bin_s, duration_s)
        mask = (t_frames >= start) & (t_frames < end)
        if np.any(mask):
            v = np.mean(chroma[:, mask], axis=1)
        else:
            v = out[-1]["chroma"] if out else np.zeros(12, dtype=float)
        v = normalize_chroma(np.array(v, dtype=float))
        out.append({"start": float(round(start, 3)), "end": float(round(end, 3)), "chroma": [float(x) for x in v]})
    return out

def _profile_correlation(chroma_vec, profile):
    a = np.asarray(chroma_vec, dtype=float)
    b = np.asarray(profile, dtype=float)
    a = a - np.mean(a)
    b = b - np.mean(b)
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom <= 1e-12:
        return -1.0
    return float(np.dot(a, b) / denom)


def estimate_key_from_chroma(chroma_mean):
    cm = normalize_chroma(np.array(chroma_mean, dtype=float))
    best = (-2.0, None, None)
    for i in range(12):
        score = _profile_correlation(cm, np.roll(MAJOR_PROFILE, i))
        if score > best[0]:
            best = (score, i, "major")
    for i in range(12):
        score = _profile_correlation(cm, np.roll(MINOR_PROFILE, i))
        if score > best[0]:
            best = (score, i, "minor")
    idx, mode = best[1], best[2]
    key_names = MAJOR_KEY_NAMES if mode == "major" else MINOR_KEY_NAMES
    return f"{key_names[idx]} {mode}", "Krumhansl-Schmuckler correlation on smooth STFT chroma"

def agg_to_1hz(values, times, duration_s):
    n = int(math.ceil(duration_s))
    out = np.zeros(n, dtype=float)
    for i in range(n):
        start = i
        end = i + 1
        mask = (times >= start) & (times < end)
        if np.any(mask):
            out[i] = float(np.mean(values[mask]))
        else:
            out[i] = float(out[i-1] if i > 0 else float(values[0] if len(values) else 0.0))
    return out.tolist()

def peak_events(t_frames, values, kind, min_gap_s=12.0, top_k=12):
    vals = np.array(values, dtype=float)
    peaks = []
    for i in range(1, len(vals)-1):
        if vals[i] > vals[i-1] and vals[i] >= vals[i+1]:
            peaks.append(i)
    peaks = sorted(peaks, key=lambda i: vals[i], reverse=True)
    selected = []
    for i in peaks:
        t = float(t_frames[i])
        if all(abs(t - e["t_s"]) >= min_gap_s for e in selected):
            selected.append({"t_s": float(round(t, 3)), "kind": kind, "strength": float(round(float(vals[i]), 6))})
        if len(selected) >= top_k:
            break
    selected.sort(key=lambda e: e["t_s"])
    return selected

def build_interpretive_map(energy_1hz, bright_1hz, flux_1hz, onset_1hz, energy_thresh, bright_thresh, window_s=10):
    N = len(energy_1hz)
    windows = []
    for start in range(0, N, window_s):
        end = min(start + window_s, N)
        e = float(np.mean(energy_1hz[start:end]))
        b = float(np.mean(bright_1hz[start:end]))
        f = float(np.mean(flux_1hz[start:end]))
        o = float(np.mean(onset_1hz[start:end])) if onset_1hz is not None else None

        w = {
            "start": int(start),
            "end": int(end),
            "energy_avg": float(round(e, 6)),
            "energy_tier": tier_energy(e, energy_thresh),
            "brightness_avg_hz": float(round(b, 3)),
            "brightness_tier": tier_brightness(b, bright_thresh),
            "flux_avg": float(round(f, 6)),
        }
        if o is not None:
            w["onset_avg"] = float(round(o, 6))
        windows.append(w)

    # --- Build narrative summary ---
    e_arr = np.array(energy_1hz, dtype=float)
    b_arr = np.array(bright_1hz, dtype=float)
    peak_e_idx = int(np.argmax(e_arr))
    peak_b_idx = int(np.argmax(b_arr))
    # Overall arc: compare first quarter vs peak vs last quarter
    q1 = max(1, N // 4)
    q3 = max(q1 + 1, 3 * N // 4)
    e_start = float(np.mean(e_arr[:q1]))
    e_end = float(np.mean(e_arr[q3:]))
    e_peak = float(e_arr[peak_e_idx])

    narrative = []

    # Opening character
    intro_tier = tier_energy(float(np.mean(e_arr[:min(30, N)])), energy_thresh)
    intro_bright = tier_brightness(float(np.mean(b_arr[:min(30, N)])), bright_thresh)
    narrative.append(f"Opens {intro_tier} and {intro_bright}.")

    # Build/peak description
    if e_peak > e_start * 1.5 and peak_e_idx > q1:
        narrative.append(f"Energy builds to peak at {peak_e_idx}s ({e_peak:.6f} RMS), a {e_peak/max(e_start, 1e-9):.1f}x increase from the opening.")
    elif e_peak > e_start:
        narrative.append(f"Energy peaks at {peak_e_idx}s.")

    # Brightness peak if distinct from energy peak
    if abs(peak_b_idx - peak_e_idx) > 15:
        narrative.append(f"Brightness peaks separately at {peak_b_idx}s ({b_arr[peak_b_idx]:.0f} Hz).")

    # Closing character
    if e_end < e_start * 0.5:
        narrative.append("Fades to a quieter close than the opening.")
    elif e_end > e_start * 1.5:
        narrative.append("Closes with more energy than it started.")
    else:
        narrative.append("Returns to roughly opening energy levels.")

    return {
        "window_s": int(window_s),
        "thresholds": {
            "energy_rms": {"low_lt": energy_thresh["low"], "medium_le": energy_thresh["high"], "high_gt": energy_thresh["high"]},
            "brightness_hz": {"dark_lt": bright_thresh["dark"], "moderate_le": bright_thresh["bright"], "bright_gt": bright_thresh["bright"]},
        },
        "thresholds_method": "percentile-adaptive (25th/75th of track)",
        "windows": windows,
        "summary_text": " ".join(narrative),
    }


# --- Mel filterbank (for mel spectrogram graph) ---
def hz_to_mel(hz): return 2595.0 * np.log10(1.0 + hz/700.0)
def mel_to_hz(m): return 700.0 * (10.0**(m/2595.0) - 1.0)

def mel_filterbank(sr, n_fft, n_mels=128, fmin=0.0, fmax=8000.0):
    n_freqs = n_fft//2 + 1
    freqs = np.linspace(0, sr/2, n_freqs)
    mels = np.linspace(hz_to_mel(fmin), hz_to_mel(fmax), n_mels+2)
    hz = mel_to_hz(mels)

    fb = np.zeros((n_mels, n_freqs), dtype=float)
    for i in range(n_mels):
        f_left, f_center, f_right = hz[i], hz[i+1], hz[i+2]
        left = (freqs - f_left) / (f_center - f_left + 1e-9)
        right = (f_right - freqs) / (f_right - f_center + 1e-9)
        fb[i, :] = np.maximum(0, np.minimum(left, right))
    return fb

def power_to_db(S, ref=1.0, amin=1e-10):
    S = np.maximum(S, amin)
    return 10.0 * np.log10(S / ref)

def filename_slug(value):
    """Convert a filename or explicit slug into a stable, filesystem-safe base name."""
    normalized = unicodedata.normalize("NFKD", str(value))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value).strip("-").lower()
    return slug or "song"

def output_base_name(audio_path, slug=None):
    """Use an explicit slug when supplied; otherwise derive one from the audio filename."""
    if slug is not None and str(slug).strip():
        return filename_slug(slug)
    audio_stem = os.path.splitext(os.path.basename(audio_path))[0]
    return filename_slug(audio_stem)

def generate_mme(audio_path, out_dir, title="", artist="", slug=None):
    os.makedirs(out_dir, exist_ok=True)
    output_base = output_base_name(audio_path, slug)

    # Convert/repair as needed, then load + resample.
    y, sr = load_audio_with_fallback(audio_path)
    y, sr = resample_to_22050(y, sr)
    duration_s = float(len(y) / sr)
    frame_dt_s = float(HOP / sr)

    # STFT magnitude
    f, t_frames, mag = stft_mag(y, sr)

    # Frame features
    rms_f = frame_rms_from_mag(mag)
    cent_f = spectral_centroid(f, mag)
    flux_f = spectral_flux(mag)
    onset_env = onset_envelope_from_flux(flux_f)

    # Rhythm analysis uses its own improved onset envelope. The existing onset_env
    # above remains unchanged for events, 1Hz onset strength, and interpretation.
    frame_rate = sr / HOP
    rhythm = analyze_rhythm(mag, t_frames, frame_rate)

    # Harmony: sensory chroma remains middle/upper weighted for the listener.
    chroma = chroma_from_mag(
        f,
        mag,
        octave_center=SENSORY_CHROMA_OCTAVE_CENTER,
        octave_width=SENSORY_CHROMA_OCTAVE_WIDTH,
    )
    chroma_mean = np.mean(chroma, axis=1)
    chroma_mean = normalize_chroma(chroma_mean)
    chroma_bins_2s = chroma_bins(chroma, t_frames, duration_s, bin_s=CHROMA_BIN_S)

    # Global key estimation uses a separate lower/mid-weighted chroma path.
    # This keeps the sensory representation unchanged while reducing cases where
    # upper harmonics overpower the track's tonic/mode evidence.
    key_chroma = chroma_from_mag(
        f,
        mag,
        octave_center=KEY_CHROMA_OCTAVE_CENTER,
        octave_width=KEY_CHROMA_OCTAVE_WIDTH,
    )
    key_chroma_mean = np.mean(key_chroma, axis=1)
    key_chroma_mean = normalize_chroma(key_chroma_mean)
    est_key, key_method = estimate_key_from_chroma(key_chroma_mean)
    key_method = (
        f"{key_method}; lower/mid key-analysis weighting "
        f"(octave center {KEY_CHROMA_OCTAVE_CENTER:.1f}, width {KEY_CHROMA_OCTAVE_WIDTH:.1f})"
    )

    # 1Hz aggregation
    energy_1hz = agg_to_1hz(rms_f, t_frames, duration_s)
    bright_1hz = agg_to_1hz(cent_f, t_frames, duration_s)
    flux_1hz = agg_to_1hz(flux_f, t_frames, duration_s)
    onset_1hz = agg_to_1hz(onset_env, t_frames, duration_s)

    t_s = list(range(len(energy_1hz)))

    # Events
    events = []
    events += peak_events(t_frames, onset_env, "onset_peak", min_gap_s=12.0, top_k=12)
    events += peak_events(t_frames, flux_f, "flux_peak", min_gap_s=12.0, top_k=12)

    # Adaptive thresholds from this track's data
    energy_thresh, bright_thresh = compute_adaptive_thresholds(energy_1hz, bright_1hz)

    interpretive = build_interpretive_map(
        energy_1hz,
        bright_1hz,
        flux_1hz,
        onset_1hz,
        energy_thresh,
        bright_thresh,
        window_s=WINDOW_S,
    )

    # ---- Graphs ----
    # 1) Waveform
    plt.figure(figsize=(12,3))
    x = np.arange(len(y)) / sr
    plt.plot(x, y)
    plt.title("Waveform")
    plt.xlabel("Time (s)")
    plt.tight_layout()
    wf_path = os.path.join(out_dir, f"{output_base}_waveform.png")
    plt.savefig(wf_path, dpi=200); plt.close()

    # 2) Mel spectrogram (from STFT power + mel filterbank)
    power = (mag**2).astype(float)
    fb = mel_filterbank(sr, N_FFT, n_mels=128, fmin=0.0, fmax=8000.0)
    mel = fb @ power
    mel_db = power_to_db(mel, ref=np.max(mel) + 1e-9)

    plt.figure(figsize=(12,4))
    plt.imshow(
        mel_db,
        aspect="auto",
        origin="lower",
        extent=[float(t_frames[0]), float(t_frames[-1]) if len(t_frames) else 0.0, 0, 128]
    )
    plt.title("Mel Spectrogram (dB) — STFT + mel filterbank")
    plt.xlabel("Time (s)")
    plt.ylabel("Mel bands")
    plt.colorbar(label="dB")
    plt.tight_layout()
    ms_path = os.path.join(out_dir, f"{output_base}_mel_spectrogram.png")
    plt.savefig(ms_path, dpi=200); plt.close()

    # 3) RMS 1Hz
    plt.figure(figsize=(12,3))
    plt.plot(t_s, energy_1hz)
    plt.title("Energy (RMS) — 1Hz")
    plt.xlabel("Time (s)")
    plt.ylabel("RMS")
    plt.tight_layout()
    rms_path = os.path.join(out_dir, f"{output_base}_rms_energy.png")
    plt.savefig(rms_path, dpi=200); plt.close()

    # 4) Centroid 1Hz
    plt.figure(figsize=(12,3))
    plt.plot(t_s, bright_1hz)
    plt.title("Brightness (Spectral Centroid) — 1Hz")
    plt.xlabel("Time (s)")
    plt.ylabel("Hz")
    plt.tight_layout()
    sc_path = os.path.join(out_dir, f"{output_base}_spectral_centroid.png")
    plt.savefig(sc_path, dpi=200); plt.close()

    # ---- JSON ----
    obj = {
        "meta": {
            "schema_version": "MME",
            "title": title,
            "artist": artist,
            "source_file": os.path.basename(audio_path),
            "duration_s": float(round(duration_s, 3)),
            "sr_hz": int(sr),
            "hop": int(HOP),
            "n_fft": int(N_FFT),
            "frame_dt_s": float(frame_dt_s),
            "created_utc": datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "analysis_notes": (
                "MME fallback pipeline: soundfile/scipy load+resample, scipy.signal.stft, "
                "RMS/centroid/flux/onset proxy, native rhythm onset + FFT autocorr + DP beat tracking, "
                "smooth STFT sensory chroma + separate lower/mid key-analysis chroma + key-profile correlation, "
                "1Hz aggregation, events, 10s interpretive map."
            ),
            "estimated_key": est_key,
            "key_method": key_method,
        },
        "time_series_1hz": {
            "t_s": t_s,
            "energy_rms": [float(x) for x in energy_1hz],
            "brightness_hz": [float(x) for x in bright_1hz],
            "spectral_flux": [float(x) for x in flux_1hz],
            "onset_strength": [float(x) for x in onset_1hz],
        },
        "rhythm": rhythm,
        "harmony": {
            "chroma_mean_12_C_to_B": [float(x) for x in chroma_mean],
            "chroma_bins_2s_C_to_B": chroma_bins_2s,
            "chroma_method": "smooth STFT chroma filterbank",
        },
        "structure": {
            "events": events,
        },
        "interpretive_map": interpretive,
    }

    json_path = os.path.join(out_dir, f"{output_base}_sensory_object.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

    return {
        "json": json_path,
        "waveform": wf_path,
        "mel": ms_path,
        "rms": rms_path,
        "centroid": sc_path,
    }

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--out_dir", default=".")
    ap.add_argument("--title", default="")
    ap.add_argument("--artist", default="")
    ap.add_argument(
        "--slug",
        default=None,
        help="Optional output filename override; defaults to the input audio filename",
    )
    args = ap.parse_args()

    out = generate_mme(args.audio, args.out_dir, args.title, args.artist, args.slug)
    print("Wrote:", out)