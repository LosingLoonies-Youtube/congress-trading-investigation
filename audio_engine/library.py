"""Versioned registry of named SFX builders and a batch renderer."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np
import soundfile as sf

from . import sfx
from .synth import SAMPLE_RATE

LIBRARY_VERSION: str = "1.0.0"

LIBRARY: dict[str, Callable[..., np.ndarray]] = {
    "data_blip": sfx.data_blip,
    "tick": sfx.tick,
    "line_swell": sfx.line_swell,
    "keystroke": sfx.keystroke,
    "bar_grow": sfx.bar_grow,
    "error_buzz": sfx.error_buzz,
    "resolve_tone": sfx.resolve_tone,
}


def list_sfx() -> list[str]:
    """Names of all effects in the library."""
    return sorted(LIBRARY)


def build_sfx(name: str, seed: int = 0) -> np.ndarray:
    """Synthesize one named effect as an (n, 2) stereo buffer at 48 kHz."""
    if name not in LIBRARY:
        raise KeyError(f"unknown sfx {name!r}; available: {list_sfx()}")
    return LIBRARY[name](seed=seed)


def render_library(out_dir: str | Path | None = None, seed: int = 0) -> list[Path]:
    """Render every effect to <out_dir>/<name>.wav (16-bit PCM, 48 kHz stereo).

    Defaults to audio_engine/sfx/. Returns the written paths.
    """
    out = Path(out_dir) if out_dir is not None else Path(__file__).parent / "sfx"
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in list_sfx():
        path = out / f"{name}.wav"
        sf.write(path, build_sfx(name, seed=seed), SAMPLE_RATE, subtype="PCM_16")
        paths.append(path)
    return paths
