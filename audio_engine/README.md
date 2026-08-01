# audio_engine

Procedural "computerized" SFX engine: retro-terminal / CRT / VCR accents for
video edits. Every sound is synthesized from code (oscillators, ADSR envelopes,
scipy-filtered noise, bit-crush) — **no sampled or downloaded audio**. All
generators are deterministic: the same call with the same `seed` produces
byte-identical output. Output is 48 kHz stereo 16-bit WAV, tuned quiet
(per-effect peaks around -16 dBFS) with a hard -3 dBFS ceiling on final mixes.

Standalone by design — knows nothing about any particular video project.

## Regenerate the SFX library

```python
from audio_engine import render_library, list_sfx, LIBRARY_VERSION

print(LIBRARY_VERSION, list_sfx())
render_library()  # writes audio_engine/sfx/<name>.wav for every effect
```

Effects: `data_blip`, `tick`, `line_swell`, `keystroke`, `bar_grow`,
`error_buzz`, `resolve_tone`.

## Build a track

```python
from audio_engine import Cue, render_track, ticks_every

cues = [
    Cue("data_blip", 1.0),
    *ticks_every("tick", 3.0, 6.0, 0.25),
    Cue("line_swell", 11.5, gain_db=-2.0),
]
render_track(cues, duration_s=14.0, out_path="sfx_track.wav")
```

`render_track` places each cue at its offset in a stereo buffer of exactly
`duration_s` seconds, sums, applies the -3 dBFS safety limiter, and writes WAV.
