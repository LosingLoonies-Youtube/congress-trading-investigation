import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
import pandas as pd
from lib import brand, animation
brand.apply_theme()

df = pd.read_csv('../output/5-cross-dataset-signal/equity_curves.csv', index_col=0, parse_dates=True)
d = df.index.values
series = [
    {'label': 'Own all 32 - no signal', 'short': 'Hold all',
     'dates': d, 'values': df['Hold all 32 (no signal)'].values, 'color': brand.GREEN},
    {'label': 'Composite signal (all 3 datasets)', 'short': 'Signal',
     'dates': d, 'values': df['Composite (all 3)'].values, 'color': brand.RED},
    {'label': 'S&P 500', 'short': 'SPY',
     'dates': d, 'values': df['SPY'].values, 'color': brand.OFF_WHITE, 'alpha': 0.9},
]
animation.animate_lines(
    series=series,
    title='COMBINE THE DATA... OR JUST OWN THE BASKET?',
    output_path=Path('../output/5-cross-dataset-signal/signal_vs_hold.mp4'),
    draw_seconds=12.0, hold_seconds=2.5, ref_line=10000)
print('rendered signal_vs_hold.mp4', flush=True)
