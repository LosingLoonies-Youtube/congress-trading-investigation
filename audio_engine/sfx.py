"""Named SFX builders, composed from synth primitives.

Every builder takes a `seed` and returns a deterministic (n, 2) float64 stereo
buffer at 48 kHz, peak-normalized quietly (about -16 dBFS) so effects act as
subtle accents, never a soundscape.
"""

from __future__ import annotations

import numpy as np

from .synth import SAMPLE_RATE, adsr, bitcrush, filt, noise, normalize_peak, osc, to_stereo

DEFAULT_PEAK_DB: float = -16.0


def _finish(x: np.ndarray, pan: float = 0.0, peak_db: float = DEFAULT_PEAK_DB) -> np.ndarray:
    """Common tail: mono -> quiet stereo."""
    return normalize_peak(to_stereo(x, pan), peak_db)


def data_blip(seed: int = 0) -> np.ndarray:
    """Short soft blip for a data reveal (~90 ms rising chirp, crushed)."""
    dur = 0.09
    n = int(dur * SAMPLE_RATE)
    f = np.linspace(880.0, 1320.0, n)
    x = osc(f, dur, "sine")
    x = bitcrush(x, bits=9, downsample=5)
    x = filt(x, "lowpass", 6000.0)
    x *= adsr(n, 0.004, 0.03, 0.4, 0.05)
    return _finish(x)


def tick(seed: int = 0) -> np.ndarray:
    """Very short counter/odometer tick (~25 ms filtered click)."""
    dur = 0.025
    n = int(dur * SAMPLE_RATE)
    click = filt(noise(dur, seed), "bandpass", (2000.0, 6500.0))
    tone = 0.5 * osc(2200.0, dur, "square")
    x = bitcrush(click + tone, bits=8, downsample=6)
    x *= adsr(n, 0.001, 0.008, 0.15, 0.012)
    return _finish(x, peak_db=-18.0)


def line_swell(seed: int = 0) -> np.ndarray:
    """Low soft swell (~2 s) for an equity line completing its draw."""
    dur = 2.0
    n = int(dur * SAMPLE_RATE)
    x = osc(110.0, dur, "sine") + 0.6 * osc(110.5, dur, "triangle") + 0.35 * osc(220.0, dur, "sine")
    air = 0.05 * filt(noise(dur, seed), "bandpass", (400.0, 1200.0))
    x = filt(x + air, "lowpass", 900.0)
    x *= adsr(n, 0.9, 0.3, 0.7, 0.7)
    return _finish(x)


def keystroke(seed: int = 0) -> np.ndarray:
    """Soft terminal keystroke: noise thock plus a hint of low body (~55 ms)."""
    dur = 0.055
    n = int(dur * SAMPLE_RATE)
    clack = filt(noise(dur, seed), "bandpass", (1200.0, 4200.0))
    body = 0.6 * osc(180.0, dur, "sine")
    x = bitcrush(clack + body, bits=8, downsample=4)
    x *= adsr(n, 0.001, 0.015, 0.2, 0.03)
    return _finish(x, peak_db=-17.0)


def bar_grow(seed: int = 0) -> np.ndarray:
    """Subtle rising tone (~0.7 s) for a bar growing to height."""
    dur = 0.7
    n = int(dur * SAMPLE_RATE)
    f = 220.0 * 2.0 ** np.linspace(0.0, 1.0, n)  # one octave glide
    x = osc(f, dur, "triangle") + 0.3 * osc(2.0 * f, dur, "sine")
    x = bitcrush(x, bits=10, downsample=3)
    x = filt(x, "lowpass", 2500.0)
    x *= adsr(n, 0.05, 0.1, 0.75, 0.25)
    return _finish(x)


def error_buzz(seed: int = 0) -> np.ndarray:
    """Soft low warning buzz (~0.45 s) for red/negative reveals."""
    dur = 0.45
    n = int(dur * SAMPLE_RATE)
    x = osc(110.0, dur, "square") + 0.5 * osc(112.0, dur, "square")
    trem = 0.6 + 0.4 * np.sign(np.sin(2.0 * np.pi * 9.0 * np.arange(n) / SAMPLE_RATE))
    x = filt(x * trem, "lowpass", 700.0)
    x = bitcrush(x, bits=8, downsample=5)
    x *= adsr(n, 0.01, 0.05, 0.8, 0.12)
    return _finish(x)


def resolve_tone(seed: int = 0) -> np.ndarray:
    """Gentle resolution/conclusion tone: soft perfect-fifth dyad (~1.3 s)."""
    dur = 1.3
    n = int(dur * SAMPLE_RATE)
    x = osc(523.25, dur, "sine") + 0.7 * osc(784.0, dur, "sine") + 0.25 * osc(261.63, dur, "triangle")
    x = filt(x, "lowpass", 3000.0)
    x *= adsr(n, 0.06, 0.25, 0.5, 0.85)
    return _finish(x)
