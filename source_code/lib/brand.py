"""LosingLoonies brand constants + matplotlib theme (STYLE.md is binding)."""
import matplotlib as mpl
from matplotlib import font_manager
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# ── Brand Colors (STYLE.md) ───────────────────────────────────────────────────
BG        = '#000000'   # Black — all plot backgrounds (per Devin, 2026-07-03; STYLE.md v1.2 had #141212)
GREEN     = '#00f600'   # Terminal Green — strategy / key data (use sparingly)
OFF_WHITE = '#f9fbef'   # Off-White — text, axes, SPY/benchmark line
RED       = '#FF0000'   # Red — comparison / warning
OLIVE     = '#34411e'   # Deep Olive — secondary branding elements
NAVY      = '#0f1a28'   # Dark Navy — alternate background
GRID      = '#3a3838'   # Grid / spine (gray at ~25% opacity)

# ── Typography (STYLE.md) ─────────────────────────────────────────────────────
FONT_PATH = REPO_ROOT / 'style' / 'VCR_OSD_MONO_1.001.ttf'
try:
    font_manager.fontManager.addfont(str(FONT_PATH))
    VCR = 'VCR OSD Mono'
except Exception:
    VCR = 'monospace'  # legibility fallback only

# ── Video Output Specs (STYLE.md) ─────────────────────────────────────────────
FIG_W, FIG_H, FIG_DPI = 16, 9, 160    # 16×160=2560, 9×160=1440
VIDEO_FPS   = 60
VIDEO_CRF   = 18
VIDEO_BRATE = '8000k'
VIDEO_CODEC = 'libx264'
VIDEO_PIX   = 'yuv420p'


def apply_theme():
    """Apply the brand theme globally. Call once at the top of every notebook."""
    mpl.rcParams.update({
        'font.family':        VCR,
        'axes.unicode_minus': False,   # VCR OSD Mono has no U+2212 glyph
        'text.color':         OFF_WHITE,
        'axes.facecolor':     BG,
        'figure.facecolor':   BG,
        'axes.edgecolor':     GRID,
        'axes.labelcolor':    OFF_WHITE,
        'xtick.color':        OFF_WHITE,
        'ytick.color':        OFF_WHITE,
        'axes.spines.top':    False,
        'axes.spines.right':  False,
    })
