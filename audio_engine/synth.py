"""Low-level synthesis primitives: oscillators, envelopes, noise, bit-crush.

All functions operate on mono float64 arrays at SAMPLE_RATE unless noted.
Everything is pure numpy/scipy -- no sampled audio anywhere.
"""

from __future__ import annotations

import numpy as np
from scipy import signal

SAMPLE_RATE: int = 48_000


def db_to_amp(db: float) -> float:
    """Convert dBFS to linear amplitude."""
    return float(10.0 ** (db / 20.0))


def amp_to_db(amp: float) -> float:
    """Convert linear amplitude to dBFS (returns -inf for silence)."""
    return float(20.0 * np.log10(amp)) if amp > 0 else float("-inf")


def osc(
    freq: float | np.ndarray,
    dur_s: float,
    wave: str = "sine",
    sr: int = SAMPLE_RATE,
    phase: float = 0.0,
) -> np.ndarray:
    """Band-limited-enough oscillator. `freq` may be a scalar or a per-sample array
    (for sweeps). wave: 'sine' | 'square' | 'triangle' | 'saw'."""
    n = int(round(dur_s * sr))
    f = np.broadcast_to(np.asarray(freq, dtype=np.float64), (n,))
    ph = phase + 2.0 * np.pi * np.cumsum(f) / sr
    if wave == "sine":
        return np.sin(ph)
    t = (ph / (2.0 * np.pi)) % 1.0  # normalized phase 0..1
    if wave == "square":
        return np.where(t < 0.5, 1.0, -1.0)
    if wave == "triangle":
        return 4.0 * np.abs(t - 0.5) - 1.0
    if wave == "saw":
        return 2.0 * t - 1.0
    raise ValueError(f"unknown wave: {wave!r}")


def adsr(
    n: int,
    attack_s: float,
    decay_s: float,
    sustain: float,
    release_s: float,
    sr: int = SAMPLE_RATE,
) -> np.ndarray:
    """Linear ADSR envelope of exactly n samples. Sustain fills the remainder."""
    a = int(round(attack_s * sr))
    d = int(round(decay_s * sr))
    r = int(round(release_s * sr))
    a, d, r = (max(seg, 1) for seg in (a, d, r))
    s = max(n - a - d - r, 0)
    env = np.concatenate([
        np.linspace(0.0, 1.0, a, endpoint=False),
        np.linspace(1.0, sustain, d, endpoint=False),
        np.full(s, sustain),
        np.linspace(sustain, 0.0, r),
    ])
    return env[:n] if env.size >= n else np.pad(env, (0, n - env.size))


def noise(dur_s: float, seed: int = 0, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Deterministic white noise in [-1, 1]."""
    rng = np.random.default_rng(seed)
    return rng.uniform(-1.0, 1.0, int(round(dur_s * sr)))


def filt(
    x: np.ndarray,
    kind: str,
    cutoff_hz: float | tuple[float, float],
    order: int = 4,
    sr: int = SAMPLE_RATE,
) -> np.ndarray:
    """Butterworth filter. kind: 'lowpass' | 'highpass' | 'bandpass'."""
    sos = signal.butter(order, cutoff_hz, btype=kind, fs=sr, output="sos")
    return signal.sosfilt(sos, x)


def bitcrush(x: np.ndarray, bits: int = 8, downsample: int = 4) -> np.ndarray:
    """Retro character: quantize amplitude to `bits` and hold every
    `downsample`-th sample (sample-rate reduction without interpolation)."""
    y = x
    if downsample > 1:
        idx = (np.arange(y.size) // downsample) * downsample
        y = y[idx]
    levels = float(2 ** (bits - 1))
    return np.round(y * levels) / levels


def to_stereo(x: np.ndarray, pan: float = 0.0) -> np.ndarray:
    """Mono -> (n, 2) stereo with constant-power pan, pan in [-1, 1]."""
    theta = (pan + 1.0) * np.pi / 4.0
    return np.stack([x * np.cos(theta), x * np.sin(theta)], axis=1)


def normalize_peak(x: np.ndarray, peak_db: float) -> np.ndarray:
    """Scale so the absolute peak sits exactly at peak_db dBFS."""
    peak = float(np.max(np.abs(x)))
    if peak == 0.0:
        return x
    return x * (db_to_amp(peak_db) / peak)
