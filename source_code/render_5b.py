import sys, json
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from dotenv import load_dotenv
load_dotenv(Path.cwd().parent / '.env')
import pandas as pd, numpy as np
from lib import brand, animation, data_massive
brand.apply_theme()

OUT = Path('../output/5-cross-dataset-signal')
s = json.load(open(OUT / 'signal_summary.json'))
st, spy = s['strategies'], s['spy']['final_10k']

# ---- A. Ablation bars: final $ per strategy vs SPY ----
items = [('Own all 32\n(no signal)', st['Hold all 32 (no signal)']['final_10k']),
         ('Composite\nsignal', st['Composite (all 3)']['final_10k']),
         ('Congress\nbuys', st['Congress buys only']['final_10k']),
         ('S&P 500', spy),
         ('Lobbying\nonly', st['Lobbying only']['final_10k']),
         ('Contracts\nonly', st['Contracts only']['final_10k'])]
items.sort(key=lambda x: -x[1])
labels = [a for a, _ in items]; vals = [v for _, v in items]
colors = [brand.GREEN if 'all 32' in a else brand.OFF_WHITE if 'S&P' in a
          else (brand.GREEN if v > spy else brand.RED) for a, v in items]
animation.animate_bars(labels=labels, values=vals, colors=colors,
    title='EVERY "SMART" VERSION LOST TO JUST HOLDING THEM ALL',
    output_path=OUT / 'ablation_bars.mp4', grow_seconds=1.8, hold_seconds=3.0,
    annotations=[f'${v:,}' for v in vals])

# ---- B. Top 8 vs Bottom 8 by composite score (does the signal separate winners?) ----
df = pd.read_csv(OUT / 'equity_curves.csv', index_col=0, parse_dates=True)
d = df.index.values
animation.animate_lines(series=[
    {'label': 'Top 8 the signal LIKED', 'short': 'Top', 'dates': d,
     'values': df['Composite (all 3)'].values, 'color': brand.GREEN},
    {'label': 'Bottom 8 the signal HATED', 'short': 'Bottom', 'dates': d,
     'values': df['Bottom 8 (composite)'].values, 'color': brand.RED},
], title='IF THE SIGNAL WORKED, GREEN SHOULD CRUSH RED', output_path=OUT / 'top_vs_bottom.mp4',
    draw_seconds=10.0, hold_seconds=2.5, ref_line=10000)

# ---- C. Per-stock contribution: a few names carried the whole basket ----
UNIV = ['LMT','NOC','RTX','GD','LHX','PLTR','BA','HII','LDOS','KTOS','AVAV','TXT','PFE','MRK',
        'MRNA','JNJ','UNH','LLY','ABBV','CVS','XOM','CVX','NEE','CEG','OXY','FSLR','MSFT','AMZN',
        'ORCL','IBM','ACN','BAH']
prices = data_massive.load_price_cache(UNIV, '2014-06-01', '2026-07-02', verbose=False)
rets = {}
for t in UNIV:
    p0 = data_massive.get_price_on_or_after(prices[t], pd.Timestamp('2015-01-31'), max_gap_days=7)
    p1 = data_massive.get_price_on_or_after(prices[t], pd.Timestamp('2026-05-31'), max_gap_days=7)
    if p0 == p0 and p1 == p1 and p0 > 0:
        rets[t] = p1 / p0 - 1.0
top = sorted(rets.items(), key=lambda x: -x[1])[:8]
animation.animate_bars(labels=[t for t, _ in top], values=[r * 100 for _, r in top],
    colors=[brand.GREEN] * len(top),
    title='THE BASKET\'S RETURN CAME FROM A HANDFUL OF NAMES',
    output_path=OUT / 'stock_contributions.mp4', grow_seconds=1.8, hold_seconds=3.0,
    annotations=[f'+{r*100:,.0f}%' for _, r in top])

print('rendered: ablation_bars.mp4, top_vs_bottom.mp4, stock_contributions.mp4', flush=True)
