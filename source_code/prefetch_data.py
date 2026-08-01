"""One-time prefetch: full Congress history from Quiver + daily prices from Massive
into the shared cache. Notebooks hit the same cache, so they re-run fast.
Run from source_code/: python prefetch_data.py
"""
import sys
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / '.env')
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import data_quiver, data_massive  # noqa: E402

raw = data_quiver.fetch_congress_trades()
print(f'Congress records: {len(raw):,}')
buys = data_quiver.clean_congress_buys(raw)
print(f'Clean buys: {len(buys):,} | tickers: {buys["Ticker"].nunique()} '
      f'| reps: {buys["Representative"].nunique()}')
print(f'Range: {buys["TransactionDate"].min().date()} → {buys["TransactionDate"].max().date()}')

start = (buys['TransactionDate'].min() - timedelta(days=5)).strftime('%Y-%m-%d')
end = '2026-07-02'
print(f'Price window: {start} → {end}')

tickers = ['SPY'] + sorted(buys['Ticker'].unique().tolist())
cache = data_massive.load_price_cache(tickers, start, end)
print('Prefetch complete.')
