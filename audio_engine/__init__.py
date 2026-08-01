"""audio_engine -- procedural retro-terminal SFX for video edits.

All audio is synthesized from code (oscillators, ADSR, filtered noise,
bit-crush); nothing is sampled. Deterministic given a seed. 48 kHz stereo WAV.
"""

from .library import LIBRARY, LIBRARY_VERSION, build_sfx, list_sfx, render_library
from .mixer import Cue, render_track, ticks_every
from .synth import SAMPLE_RATE

__all__ = [
    "LIBRARY",
    "LIBRARY_VERSION",
    "SAMPLE_RATE",
    "Cue",
    "build_sfx",
    "list_sfx",
    "render_library",
    "render_track",
    "ticks_every",
]
