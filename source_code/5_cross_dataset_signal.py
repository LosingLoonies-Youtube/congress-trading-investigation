import sys, json
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from dotenv import load_dotenv

load_dotenv(Path.cwd().parent / '.env') #
import numpy as np, pandas as pd
from lib import data_quiver, data_massive

TICKER_SECTOR = {
    'LMT':'defense','NOC':'defense','RTX':'defense','GD':'defense','LHX':'defense',
    'PLTR':'defense','BA':'defense','HII':'defense','LDOS':'defense','KTOS':'defense',
    'AVAV':'defense','TXT':'defense','PFE':'pharma','MRK':'pharma','MRNA':'pharma',
    'JNJ':'pharma','UNH':'pharma','LLY':'pharma','ABBV':'pharma','CVS':'pharma',
    'XOM':'energy','CVX':'energy','NEE':'energy','CEG':'energy','OXY':'energy','FSLR':'energy',
    'MSFT':'fedtech','AMZN':'fedtech','ORCL':'fedtech','IBM':'fedtech','ACN':'fedtech','BAH':'fedtech',
}


UNIVERSE = sorted(TICKER_SECTOR)
START, END = '2015-01-31', '2026-05-31'
TOP_K = 8
OUT = Path('../output/5-cross-dataset-signal'); OUT.mkdir(parents=True, exist_ok=True)
CACHE = Path('cache')

def norm_contracts(df):
    df = df.drop_duplicates().copy()
    aw = pd.to_datetime(df['action_date'], errors='coerce') if 'action_date' in df else pd.NaT
    df['AwardDate'] = aw.fillna(df['Date']) if 'action_date' in df else df['Date']
    return df

print('Loading data...', flush=True)
prices = data_massive.load_price_cache(['SPY']+UNIVERSE, '2014-01-01', '2026-07-02', verbose=False)
lob = {t: pd.read_pickle(CACHE/f'lobbying_{t}.pkl') for t in UNIVERSE if (CACHE/f'lobbying_{t}.pkl').exists()}
con = {t: norm_contracts(pd.read_pickle(CACHE/f'contracts_{t}.pkl')) for t in UNIVERSE if (CACHE/f'contracts_{t}.pkl').exists()}
raw = pd.read_pickle(CACHE/'congress_raw.pkl')
buys = data_quiver.clean_congress_buys(raw)
buys = buys[buys['Ticker'].isin(UNIVERSE)][['Ticker','Representative','ReportDate']].dropna()
print(f'  {len(UNIVERSE)} tickers | {len(buys):,} in-universe congress buys', flush=True)

def px(t, d):
    s = prices.get(t)
    if s is None or s.empty: return np.nan
    return data_massive.get_price_on_or_after(s, pd.Timestamp(d), max_gap_days=7)

def ttm(df, datecol, t):
    d = df[datecol]
    now = df.loc[(d > t - pd.Timedelta(days=365)) & (d <= t), 'Amount'].sum()
    return now

def zscore(s):
    s = pd.Series(s, dtype=float); m, sd = s.mean(), s.std(ddof=0)
    return (s - m) / sd if sd > 0 else s * 0.0

dates = pd.date_range(START, END, freq='ME')
rows = []            # per (date,ticker): signals + fwd return
for i in range(len(dates) - 1):
    t, t1 = dates[i], dates[i+1]
    rec = {}
    for tk in UNIVERSE:
        p0, p1 = px(tk, t), px(tk, t1)
        if not (p0 == p0 and p1 == p1 and p0 > 0): continue
        lb = ttm(lob[tk], 'Date', t) if tk in lob else 0.0
        ct = ttm(con[tk], 'AwardDate', t) if tk in con else 0.0
        b = buys[buys['Ticker'] == tk]
        cm = b.loc[(b['ReportDate'] > t - pd.Timedelta(days=180)) & (b['ReportDate'] <= t),
                   'Representative'].nunique()
        rec[tk] = dict(fwd=p1/p0 - 1.0, lob=np.log1p(lb), con=np.log1p(ct), cm=float(cm))
    if len(rec) < TOP_K + 2: continue
    df = pd.DataFrame(rec).T
    df['z_lob'], df['z_con'], df['z_cm'] = zscore(df['lob']), zscore(df['con']), zscore(df['cm'])
    df['composite'] = df[['z_lob','z_con','z_cm']].mean(axis=1)
    df['date'] = t
    rows.append(df)

panel = pd.concat(rows)
spy = pd.Series({d: (px('SPY', dates[i+1]) / px('SPY', dates[i]) - 1.0)
                 for i, d in enumerate(dates[:-1])})


_tsum = panel.groupby(panel.index)['composite'].mean().rename('mean_composite')
_tr = {}


for _t in UNIVERSE:

    _p0, _p1 = px(_t, dates[0]), px(_t, dates[-1])
    if _p0 == _p0 and _p1 == _p1 and _p0 > 0:
        _tr[_t] = _p1 / _p0 - 1.0
pd.DataFrame({'mean_composite': _tsum, 'total_return': pd.Series(_tr),
              'sector': pd.Series(TICKER_SECTOR)}).dropna().to_csv(OUT / 'ticker_summary.csv')

def strat_returns(score_col, bottom=False):
    out = {}
    
    for t, g in panel.groupby('date'):
        sel = g.nsmallest(TOP_K, score_col) if bottom else g.nlargest(TOP_K, score_col)
        out[t] = sel['fwd'].mean()
    return pd.Series(out)

strategies = {
    'Composite (all 3)': strat_returns('composite'),
    'Bottom 8 (composite)': strat_returns('composite', bottom=True),
    'Lobbying only':     strat_returns('z_lob'),
    'Contracts only':    strat_returns('z_con'),
    'Congress buys only':strat_returns('z_cm'),
    'Hold all 32 (no signal)': panel.groupby('date')['fwd'].mean(),
}

def curve(r):  # compound $10k
    return 10000 * (1 + r.reindex(spy.index).fillna(0)).cumprod()

summary = {'universe': len(UNIVERSE), 'top_k': TOP_K, 'start': START, 'end': END,
           'n_months': int(len(spy)), 'strategies': {}}
spy_curve = curve(spy)
for name, r in strategies.items():
    c = curve(r)
    yrs = len(spy) / 12.0
    excess = (r.reindex(spy.index).fillna(0) - spy)
    summary['strategies'][name] = {
        'final_10k': round(float(c.iloc[-1])),
        'cagr': round(float((c.iloc[-1]/10000)**(1/yrs) - 1), 4),
        'avg_monthly_excess': round(float(excess.mean()), 5),
        'pct_months_beat_spy': round(float((excess > 0).mean()), 3),
    }
summary['spy'] = {'final_10k': round(float(spy_curve.iloc[-1])),
                  'cagr': round(float((spy_curve.iloc[-1]/10000)**(1/(len(spy)/12.0)) - 1), 4)}

# Information Coefficient: monthly Spearman(composite, fwd), averaged (robust to small universe)
ics = [g['composite'].corr(g['fwd'], method='spearman') for _, g in panel.groupby('date')]
ics = [x for x in ics if x == x]
summary['composite_IC_mean'] = round(float(np.mean(ics)), 4)
summary['composite_IC_pct_positive'] = round(float(np.mean([x > 0 for x in ics])), 3)

pd.DataFrame({name: curve(r) for name, r in strategies.items()} | {'SPY': spy_curve}).to_csv(OUT/'equity_curves.csv')
json.dump(summary, open(OUT/'signal_summary.json','w'), indent=2)

print('\n===== RESULTS ($10k, %s to %s, top-%d, monthly) =====' % (START[:4], END[:4], TOP_K), flush=True)
print(f"{'SPY (benchmark)':28} ${summary['spy']['final_10k']:>8,}  CAGR {summary['spy']['cagr']:+.1%}", flush=True)
for name, s in summary['strategies'].items():
    print(f"{name:28} ${s['final_10k']:>8,}  CAGR {s['cagr']:+.1%}  beat-SPY {s['pct_months_beat_spy']:.0%} of months", flush=True)
print(f"\nComposite Information Coefficient: mean {summary['composite_IC_mean']:+.3f} "
      f"({summary['composite_IC_pct_positive']:.0%} of months positive)", flush=True)
print('  (IC > 0 = higher composite score predicted higher forward return)', flush=True)
print('\nSaved -> output/5-cross-dataset-signal/{signal_summary.json, equity_curves.csv}', flush=True)
