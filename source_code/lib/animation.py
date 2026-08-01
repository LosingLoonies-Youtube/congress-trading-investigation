"""Reusable animated-chart builders + render/mux helpers.

Every builder renders 2560×1440 @ 60 FPS H.264 per STYLE.md, and accepts an
optional `audio_wav` which is muxed into the MP4 after the video render.
"""
import subprocess
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.ticker import FuncFormatter, PercentFormatter
from pathlib import Path

from .brand import (BG, GREEN, OFF_WHITE, RED, OLIVE, GRID, VCR,
                    FIG_W, FIG_H, FIG_DPI, VIDEO_FPS, VIDEO_CRF,
                    VIDEO_BRATE, VIDEO_CODEC, VIDEO_PIX)


def make_writer():
    return animation.FFMpegWriter(
        fps=VIDEO_FPS,
        codec=VIDEO_CODEC,
        extra_args=['-crf', str(VIDEO_CRF), '-b:v', VIDEO_BRATE, '-pix_fmt', VIDEO_PIX],
    )


def smooth_step(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def mux_audio(video_path: Path, wav_path: Path) -> None:
    """Mux a WAV track into an MP4 in place (video stream copied, AAC audio)."""
    video_path, wav_path = Path(video_path), Path(wav_path)
    tmp = video_path.with_suffix('.tmp.mp4')
    subprocess.run([
        'ffmpeg', '-y', '-i', str(video_path), '-i', str(wav_path),
        '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
        '-shortest', '-movflags', '+faststart', str(tmp),
    ], check=True, capture_output=True)
    tmp.replace(video_path)


# Master switch: audio muxing disabled by request — all MP4s render silent.
# Flip back to True to restore the audio tracks (WAVs are still generated).
MUX_AUDIO = False


def save_animation(ani, fig, output_path: Path, audio_wav: Path | None = None) -> None:
    output_path = Path(output_path)
    ani.save(str(output_path), writer=make_writer(), dpi=FIG_DPI)
    plt.close(fig)
    if audio_wav is not None and MUX_AUDIO:
        mux_audio(output_path, audio_wav)
    mb = output_path.stat().st_size / 1e6
    print(f'Saved {output_path.name}  ({mb:.1f} MB)')


def new_axes(title: str, fontsize: int = 20):
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), facecolor=BG)
    ax.set_facecolor(BG)
    ax.set_title(title, color=OFF_WHITE, fontsize=fontsize, pad=20,
                 fontfamily=VCR, fontweight='bold')
    ax.grid(True, color=GRID, linewidth=0.6, alpha=0.6, zorder=0)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_edgecolor(GRID)
    return fig, ax


def animate_lines(series: list[dict], title: str, output_path: Path,
                  ylabel: str = 'Portfolio Value ($)', draw_seconds: float = 12.0,
                  hold_seconds: float = 2.0, ref_line: float | None = None,
                  dollar_axis: bool = True, audio_wav: Path | None = None,
                  label_fmt: str = '${:>10,.0f}', ylim: tuple | None = None) -> int:
    """Multi-line draw-in on one axes. Each series: {label, dates, values, color}.

    Returns total frame count (for building the matching audio track first,
    call with the same durations: total = (draw_seconds + hold_seconds) * 60).
    """
    n_draw = int(draw_seconds * VIDEO_FPS)
    n_hold = int(hold_seconds * VIDEO_FPS)
    n_total = n_draw + n_hold

    fig, ax = new_axes(title)
    all_vals = np.concatenate([np.asarray(s['values'], dtype=float) for s in series])
    all_dates = series[0]['dates']
    ax.set_xlim(all_dates[0], all_dates[-1])
    ax.set_ylim(*(ylim if ylim is not None else (all_vals.min() * 0.95, all_vals.max() * 1.08)))
    ax.set_xlabel('Date', color=OFF_WHITE, fontsize=13, fontfamily=VCR, labelpad=10)
    ax.set_ylabel(ylabel, color=OFF_WHITE, fontsize=13, fontfamily=VCR, labelpad=10)
    if dollar_axis:
        ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f'${x:,.0f}'))
    if ref_line is not None:
        ax.axhline(ref_line, color=GRID, linewidth=0.8, linestyle='--', alpha=0.7)

    lines, labels_ = [], []
    for k, s in enumerate(series):
        ln, = ax.plot([], [], color=s['color'], linewidth=2.5,
                      alpha=s.get('alpha', 1.0), label=s['label'], zorder=3 - k * 0)
        lines.append(ln)
        s['short'] = s.get('short', s['label'][:9].strip())
        labels_.append(ax.text(
            0.98, 0.96 - 0.07 * k, '', transform=ax.transAxes, color=s['color'],
            fontsize=16, ha='right', va='top', fontfamily=VCR))
    ax.legend(facecolor=BG, edgecolor=GRID, labelcolor=OFF_WHITE,
              loc='upper left', prop={'family': VCR, 'size': 14})

    idx_of = [np.linspace(0, len(s['values']) - 1, n_draw, dtype=int) for s in series]

    def update(frame):
        f = min(frame, n_draw - 1)
        for s, ln, txt, idx in zip(series, lines, labels_, idx_of):
            i = idx[f]
            ln.set_data(s['dates'][:i + 1], s['values'][:i + 1])
            txt.set_text(f"{s['short']:<9} " + label_fmt.format(s['values'][i]))
        return tuple(lines) + tuple(labels_)

    ani = animation.FuncAnimation(fig, update, frames=n_total,
                                  interval=1000 / VIDEO_FPS, blit=True)
    print(f'Rendering {Path(output_path).name}  ({n_total} frames @ {VIDEO_FPS} fps)...')
    save_animation(ani, fig, output_path, audio_wav)
    return n_total


def animate_paired_bars(labels: list[str], values_a: list[float], values_b: list[float],
                        title: str, output_path: Path,
                        label_a: str = 'v1 — perfect info', label_b: str = 'v2 — reality',
                        grow_seconds: float = 1.5, gap_seconds: float = 1.5,
                        hold_seconds: float = 2.5, tick_fontsize: int = 11,
                        audio_wav: Path | None = None) -> int:
    """Horizontal paired bars: green (v1) grows first, red (v2) lands after a beat.

    Returns total frame count.
    """
    fps = VIDEO_FPS
    n_grow = int(grow_seconds * fps)
    b_start = n_grow + int(gap_seconds * fps)
    n_total = b_start + n_grow + int(hold_seconds * fps)
    n = len(labels)

    fig, ax = new_axes(title, fontsize=18)
    va, vb = np.asarray(values_a, dtype=float), np.asarray(values_b, dtype=float)
    lo = min(0, va.min(), vb.min()) * 1.3
    hi = max(0, va.max(), vb.max()) * 1.3
    ax.set_xlim(lo, hi)
    ax.set_ylim(-0.7, n - 0.3)
    y = np.arange(n)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=tick_fontsize + 2, color=OFF_WHITE, fontfamily=VCR)
    ax.xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    ax.grid(axis='x', color=GRID, linewidth=0.6, alpha=0.6, zorder=0)
    ax.axvline(0, color=GRID, linewidth=1)

    bars_a = ax.barh(y + 0.19, [0.0] * n, color=GREEN, height=0.34,
                     zorder=3, edgecolor=BG, linewidth=0.4, label=label_a)
    bars_b = ax.barh(y - 0.19, [0.0] * n, color=RED, height=0.34,
                     zorder=3, edgecolor=BG, linewidth=0.4, label=label_b)
    ax.legend(facecolor=BG, edgecolor=GRID, labelcolor=OFF_WHITE,
              loc='lower right', prop={'family': VCR, 'size': 13})

    txt_a = [ax.text(0, i + 0.19, '', ha='left', va='center', color=GREEN,
                     fontsize=tick_fontsize, fontfamily=VCR, zorder=4) for i in range(n)]
    txt_b = [ax.text(0, i - 0.19, '', ha='left', va='center', color=RED,
                     fontsize=tick_fontsize, fontfamily=VCR, zorder=4) for i in range(n)]

    def set_group(bars, vals, texts, t):
        for bar, val, txt in zip(bars, vals, texts):
            bar.set_width(val * t)
            if t >= 1.0:
                txt.set_text(f'  {val:+.1%}' if val >= 0 else f'  {val:+.1%}')
                txt.set_x(max(val, 0) * 1.0 + hi * 0.005 if val >= 0 else hi * 0.005)
            else:
                txt.set_text('')

    def update(frame):
        ta = smooth_step(frame / (n_grow - 1))
        tb = smooth_step((frame - b_start) / (n_grow - 1))
        set_group(bars_a, va, txt_a, ta)
        set_group(bars_b, vb, txt_b, tb)
        return tuple(bars_a) + tuple(bars_b) + tuple(txt_a) + tuple(txt_b)

    ani = animation.FuncAnimation(fig, update, frames=n_total,
                                  interval=1000 / fps, blit=True)
    print(f'Rendering {Path(output_path).name}  ({n_total} frames @ {fps} fps)...')
    save_animation(ani, fig, output_path, audio_wav)
    return n_total


def animate_bars(labels: list[str], values: list[float], colors: list[str],
                 title: str, output_path: Path, horizontal: bool = False,
                 grow_seconds: float = 1.5, hold_seconds: float = 2.0,
                 value_fmt: str = '{:.1%}', dollar: bool = False, tick_fontsize: int = 10,
                 annotations: list[str] | None = None,
                 divider_after: int | None = None,
                 group_labels: tuple[str, str] | None = None,
                 audio_wav: Path | None = None) -> int:
    """Bars grow from zero with smooth-step easing; value labels appear when grown.

    Returns total frame count.
    """
    n_grow = int(grow_seconds * VIDEO_FPS)
    n_hold = int(hold_seconds * VIDEO_FPS)
    n_total = n_grow + n_hold
    n = len(labels)

    fig, ax = new_axes(title, fontsize=18)
    v = np.asarray(values, dtype=float)
    lo, hi = min(0.0, float(v.min())), max(0.0, float(v.max()))
    span = hi - lo
    pad = span * 0.15

    if horizontal:
        ax.set_xlim(min(0, v.min() * 1.35), max(0, v.max() * 1.35))
        ax.set_ylim(-0.6, n - 0.4)
        ax.set_yticks(range(n))
        ax.set_yticklabels(labels, fontsize=tick_fontsize + 3, color=OFF_WHITE, fontfamily=VCR)
        ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f'${x:,.0f}') if dollar
                                     else PercentFormatter(xmax=1, decimals=0))
        ax.grid(axis='x', color=GRID, linewidth=0.6, alpha=0.6, zorder=0)
        ax.axvline(0, color=GRID, linewidth=1)
        bars = ax.barh(range(n), [0.0] * n, color=colors, height=0.6,
                       zorder=3, edgecolor=BG, linewidth=0.4)
    else:
        ax.set_xlim(-0.6, n - 0.4)
        ax.set_ylim(lo - pad, hi + pad * 1.8)
        ax.axhline(0, color=GRID, linewidth=1, zorder=2)
        ax.grid(axis='y', color=GRID, linewidth=0.6, alpha=0.6, zorder=0)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f'${x:,.0f}') if dollar
                                     else PercentFormatter(xmax=1, decimals=0))
        ax.set_xticks(range(n))
        ax.set_xticklabels(labels, fontsize=tick_fontsize, color=OFF_WHITE,
                           fontfamily=VCR, linespacing=1.3)
        bars = ax.bar(range(n), [0.0] * n, color=colors, width=0.65,
                      zorder=3, edgecolor=BG, linewidth=0.5)
        if divider_after is not None:
            ax.axvline(divider_after - 0.5, color=GRID, linewidth=1.5,
                       linestyle='--', alpha=0.6)
            if group_labels:
                y_top = hi + pad * 1.1
                ax.text((divider_after - 1) / 2, y_top, group_labels[0],
                        color=GREEN, fontsize=14, ha='center', fontfamily=VCR)
                ax.text((divider_after + n - 1) / 2, y_top, group_labels[1],
                        color=RED, fontsize=14, ha='center', fontfamily=VCR)

    val_texts = []
    for i, val in enumerate(v):
        if horizontal:
            val_texts.append(ax.text(0, i, '', ha='left', va='center',
                                     color=OFF_WHITE, fontsize=tick_fontsize + 2,
                                     fontfamily=VCR, zorder=4))
        else:
            val_texts.append(ax.text(i, 0, '', ha='center',
                                     va='bottom' if val >= 0 else 'top',
                                     color=colors[i], fontsize=tick_fontsize + 2,
                                     fontfamily=VCR, zorder=4))
    note_texts = []
    if annotations:
        for i, (val, note) in enumerate(zip(v, annotations)):
            if horizontal:
                note_texts.append(ax.text(0.002, i, note, ha='left', va='center',
                                          color=OLIVE, fontsize=tick_fontsize,
                                          fontfamily=VCR, zorder=4, alpha=0.0))

    def update(frame):
        t = smooth_step(frame / (n_grow - 1)) if frame < n_grow else 1.0
        for i, (bar, val, txt) in enumerate(zip(bars, v, val_texts)):
            cur = val * t
            if horizontal:
                bar.set_width(cur)
                if t >= 1.0:
                    txt.set_text('  ' + value_fmt.format(val))
                    txt.set_x(cur)
                else:
                    txt.set_text('')
            else:
                bar.set_height(cur)
                bar.set_y(min(cur, 0))
                if t >= 1.0:
                    txt.set_text(value_fmt.format(val))
                    txt.set_y(val + (0.02 if val >= 0 else -0.06) * span)
                else:
                    txt.set_text('')
        for nt in note_texts:
            nt.set_alpha(t)
        return tuple(bars) + tuple(val_texts) + tuple(note_texts)

    ani = animation.FuncAnimation(fig, update, frames=n_total,
                                  interval=1000 / VIDEO_FPS, blit=True)
    print(f'Rendering {Path(output_path).name}  ({n_total} frames @ {VIDEO_FPS} fps)...')
    save_animation(ani, fig, output_path, audio_wav)
    return n_total
