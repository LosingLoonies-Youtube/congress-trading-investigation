"""Cue-based track mixing: place named SFX on a timeline and render a WAV."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from .library import build_sfx
from .synth import SAMPLE_RATE, amp_to_db, db_to_amp

CEILING_DB: float = -3.0  # hard safety ceiling on the final mix


@dataclass(frozen=True)
class Cue:
    """A named sfx placed at a time offset, with optional gain trim."""

    name: str
    time_s: float
    gain_db: float = 0.0


def ticks_every(
    name: str,
    start_s: float,
    end_s: float,
    interval_s: float,
    gain_db: float = 0.0,
) -> list[Cue]:
    """Cues for `name` at start_s, start_s+interval_s, ... up to end_s (inclusive)."""
    times = np.arange(start_s, end_s + 1e-9, interval_s)
    return [Cue(name, float(t), gain_db) for t in times]


def render_track(
    cues: list[Cue],
    duration_s: float,
    out_path: str | Path,
    seed: int = 0,
) -> Path:
    """Synthesize and sum all cues into a stereo 48 kHz buffer of exactly
    duration_s seconds, enforce the -3 dBFS ceiling, and write a 16-bit WAV."""
    n = int(round(duration_s * SAMPLE_RATE))
    mix = np.zeros((n, 2), dtype=np.float64)
    for cue in cues:
        clip = build_sfx(cue.name, seed=seed) * db_to_amp(cue.gain_db)
        start = int(round(cue.time_s * SAMPLE_RATE))
        if start >= n or start + clip.shape[0] <= 0:
            continue
        lo = max(start, 0)
        hi = min(start + clip.shape[0], n)
        mix[lo:hi] += clip[lo - start : hi - start]
    peak = float(np.max(np.abs(mix))) if n else 0.0
    ceiling = db_to_amp(CEILING_DB)
    if peak > ceiling:  # safety limiter: scale the whole mix under the ceiling
        mix *= ceiling / peak
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out, mix, SAMPLE_RATE, subtype="PCM_16")
    return out


def track_peak_db(path: str | Path) -> float:
    """Peak level of a rendered WAV in dBFS (verification helper)."""
    data, _ = sf.read(path)
    return amp_to_db(float(np.max(np.abs(data))))
