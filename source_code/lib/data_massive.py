"""Massive (formerly Polygon.io) client — daily + intraday prices, disk-cached.

All price/benchmark data in this project comes from Massive (affiliate agreement).
The pickle cache lives in source_code/cache/ and is gitignored.
"""
import os
import time
import pickle
import pandas as pd
from pathlib import Path
from polygon import RESTClient

CACHE_DIR = Path(__file__).resolve().parents[1] / 'cache'
CACHE_DIR.mkdir(exist_ok=True)

_client = None


def client() -> RESTClient:
    global _client
    if _client is None:
        _client = RESTClient(api_key=os.environ['MASSIVE_API_KEY'])
    return _client


def fetch_daily_prices(ticker: str, start: str, end: str) -> pd.Series:
    """Adjusted daily closes indexed by normalized timestamp. Empty series on failure."""
    try:
        aggs = client().get_aggs(ticker, 1, 'day', start, end, adjusted=True, limit=50000)
        if not aggs:
            return pd.Series(dtype=float, name=ticker)
        return pd.Series(
            {pd.Timestamp(a.timestamp, unit='ms').normalize(): a.close for a in aggs},
            name=ticker,
        ).sort_index()
    except Exception:
        return pd.Series(dtype=float, name=ticker)


def fetch_minute_bars(ticker: str, day: str) -> pd.DataFrame:
    """Minute OHLCV for one session, indexed by US/Eastern timestamp."""
    aggs = client().get_aggs(ticker, 1, 'minute', day, day, adjusted=True, limit=50000)
    df = pd.DataFrame([{
        'timestamp': pd.Timestamp(a.timestamp, unit='ms', tz='UTC').tz_convert('US/Eastern'),
        'open': a.open, 'high': a.high, 'low': a.low, 'close': a.close, 'volume': a.volume,
    } for a in aggs])
    return df.set_index('timestamp').sort_index()


def get_price_on_or_after(prices: pd.Series, date: pd.Timestamp,
                          max_gap_days: int | None = None) -> float:
    """First close on/after date. With max_gap_days set, returns NaN when the first
    available mark is further out than that — guards against series that begin long
    after the requested date (reused symbols, late listings), where the clamped
    price belongs to a different market regime or a different company entirely.
    """
    date = pd.Timestamp(date).normalize()
    future = prices[prices.index >= date]
    if future.empty:
        return float('nan')
    if max_gap_days is not None and (future.index[0] - date).days > max_gap_days:
        return float('nan')
    return float(future.iloc[0])


def load_price_cache(tickers: list[str], start: str, end: str,
                     cache_name: str = 'prices_daily.pkl',
                     verbose: bool = True) -> dict[str, pd.Series]:
    """Daily closes for many tickers, backed by a pickle cache.

    Only missing tickers are fetched from Massive; the cache persists across
    notebooks so Deliverables 1-4 share one download.
    """
    cache_file = CACHE_DIR / cache_name
    cache = {}
    if cache_file.exists():
        with open(cache_file, 'rb') as f:
            cache = pickle.load(f)
    missing = [t for t in tickers if t not in cache]
    if verbose:
        print(f'Price cache: {len(cache)} tickers cached | {len(missing)} to fetch')
    for i, ticker in enumerate(missing):
        cache[ticker] = fetch_daily_prices(ticker, start, end)
        if i % 100 == 99:
            if verbose:
                print(f'  {i + 1}/{len(missing)} fetched — checkpointing cache...')
            with open(cache_file, 'wb') as f:
                pickle.dump(cache, f)
        time.sleep(0.02)  # rate-limit courtesy
    if missing:
        with open(cache_file, 'wb') as f:
            pickle.dump(cache, f)
    empty = sum(1 for t in tickers if cache.get(t) is None or cache[t].empty)
    if verbose:
        print(f'Done: {len(tickers) - empty} tickers with data | {empty} empty (delisted/bad symbol)')
    return {t: cache[t] for t in tickers if t in cache}
