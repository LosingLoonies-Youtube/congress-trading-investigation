"""Backtest engines. v1 = transaction-date entry (perfect info); v2 = filing date + 1
(the day a retail follower could actually act). Same engine, different entry column.
"""
import numpy as np
import pandas as pd
from datetime import timedelta

from .data_massive import get_price_on_or_after

INITIAL_CAPITAL = 10_000

# A trade is only priced if the ticker's series has a mark within this many days of
# the entry date. Without it, symbols whose vendor history starts years after the
# trade (reused symbols, late listings) clamp to their first bar and post a fake
# ~0% return against a real SPY window — ~3% of trades, all spurious.
ENTRY_MAX_GAP_DAYS = 7

# Massive's price history is keyed by SYMBOL, and symbols get reused by different
# companies. A trade dated before the cutoff would be priced against the wrong
# company's history (verified by hand from the extreme-return scan), so it is
# excluded. None = the symbol's whole history is unusable.
BAD_PRICE_HISTORY = {
    'PCLN': None,          # Priceline → BKNG (2018); vendor series has a bad seam
    'MICRD': None,         # junk symbol, zero prices
    'MPET': None,          # Magellan Petroleum reverse-split seam
    'DSCO': None,          # Discovery Labs → WINT (2016); series seam
    'META': '2022-06-09',  # before this, META = Roundhill ETF / Metalink, not Meta Platforms
    'FI': '2023-06-06',    # before this, FI = Frank's International, not Fiserv
    'ACT': '2021-09-16',   # before this, ACT = Actavis, not Enact Holdings
    'FCEL': '2019-05-31',  # reverse-split seam in vendor data
}


def _bad_history(ticker: str, entry_date: pd.Timestamp) -> bool:
    if ticker not in BAD_PRICE_HISTORY:
        return False
    cutoff = BAD_PRICE_HISTORY[ticker]
    return cutoff is None or entry_date < pd.Timestamp(cutoff)


def run_backtest(df: pd.DataFrame, price_cache: dict, spy_prices: pd.Series,
                 hold_days: int = 60, entry: str = 'transaction',
                 allow_open: bool = False, verbose: bool = True) -> pd.DataFrame:
    """One row per trade with entry/exit prices and returns vs SPY over the same window.

    entry='transaction' → buy the day they traded (v1, perfect info)
    entry='disclosure'  → buy the day after the filing became public (v2, realistic)
    allow_open=True     → holds that extend past the last price mark to market
                          instead of being skipped (flagged Open=True)
    """
    results, skipped = [], 0
    last_price_date = spy_prices.index.max()
    for _, row in df.iterrows():
        ticker = row['Ticker']
        if ticker not in price_cache or price_cache[ticker].empty:
            skipped += 1
            continue
        if entry == 'transaction':
            entry_date = pd.Timestamp(row['TransactionDate']).normalize()
        else:
            entry_date = pd.Timestamp(row['ReportDate']).normalize() + timedelta(days=1)
        if _bad_history(ticker, entry_date):
            skipped += 1
            continue
        exit_date = entry_date + timedelta(days=hold_days)
        is_open = exit_date > last_price_date
        if is_open:
            if not allow_open or entry_date > last_price_date:
                skipped += 1
                continue
            exit_date = last_price_date  # hold window not yet complete
        ep = get_price_on_or_after(price_cache[ticker], entry_date,
                                   max_gap_days=ENTRY_MAX_GAP_DAYS)
        xp = get_price_on_or_after(price_cache[ticker], exit_date)
        se = get_price_on_or_after(spy_prices, entry_date)
        sx = get_price_on_or_after(spy_prices, exit_date)
        if any(np.isnan([ep, xp, se, sx])) or ep <= 0 or xp <= 0 or se <= 0:
            skipped += 1  # missing or bad (zero) price data
            continue
        tr, sr = xp / ep - 1.0, sx / se - 1.0
        results.append({
            'Ticker': ticker,
            'Representative': row.get('Representative', ''),
            'Party': row.get('Party', ''), 'House': row.get('House', ''),
            'TransactionDate': pd.Timestamp(row['TransactionDate']).normalize(),
            'ReportDate': pd.Timestamp(row['ReportDate']).normalize(),
            'EntryDate': entry_date, 'ExitDate': exit_date,
            'EntryPrice': ep, 'ExitPrice': xp,
            'TradeReturn': tr, 'SPYReturn': sr, 'ExcessReturn': tr - sr,
            'Open': is_open,
        })
    out = pd.DataFrame(results).sort_values('EntryDate').reset_index(drop=True)
    if verbose:
        print(f'{len(out):,} trades complete | {skipped} skipped')
        print(f'Avg return: {out["TradeReturn"].mean():.2%} | SPY: {out["SPYReturn"].mean():.2%} '
              f'| Excess: {out["ExcessReturn"].mean():.2%}')
        print(f'Win rate: {(out["TradeReturn"] > 0).mean():.2%} '
              f'| Beat SPY: {(out["ExcessReturn"] > 0).mean():.2%}')
    return out


def run_backtest_hold_until_sell(buys: pd.DataFrame, sells: pd.DataFrame,
                                  price_cache: dict, spy_prices: pd.Series,
                                  entry: str = 'transaction', exit: str = 'transaction',
                                  allow_open: bool = False, verbose: bool = True) -> pd.DataFrame:
    """Buy, then hold until Congress sells that same position.

    Matches each buy to the next sale of the same ticker by the same representative.
    Returns one row per matched buy-sell pair. Unmatched buys (no subsequent sale in data)
    are skipped unless allow_open=True.

    entry='transaction' → enter on buy TransactionDate (perfect info)
    entry='disclosure'  → enter on buy ReportDate + 1 (realistic retail follower)
    exit='transaction'  → exit on the sale's TransactionDate (perfect info on the exit)
    exit='disclosure'   → exit on the sale's ReportDate + 1 (fully realistic — both ends
                          use only public filing dates a follower could actually act on)
    """
    results, skipped = [], 0
    last_price_date = spy_prices.index.max()

    # Pre-group sells by (Representative, Ticker): sorted transaction dates with the
    # parallel report dates. The inner match is then a dict lookup + binary search
    # instead of a full scan of the sells frame per buy (~47k x 40k datetime conversions).
    sell_dates: dict[tuple, tuple] = {}
    _s = sells.copy()
    _s['_td'] = pd.to_datetime(_s['TransactionDate']).dt.normalize()
    _s['_rd'] = pd.to_datetime(_s['ReportDate']).dt.normalize()
    for (rep_k, tkr_k), grp in _s.groupby(['Representative', 'Ticker']):
        grp = grp.sort_values('_td')
        sell_dates[(rep_k, tkr_k)] = (grp['_td'].values, grp['_rd'].values)

    for _, buy_row in buys.iterrows():
        ticker = buy_row['Ticker']
        rep = buy_row['Representative']
        buy_date = pd.Timestamp(buy_row['TransactionDate']).normalize()

        if ticker not in price_cache or price_cache[ticker].empty:
            skipped += 1
            continue

        # Find the next sale by the same rep in the same ticker, strictly after this buy
        candidates = sell_dates.get((rep, ticker))
        sell_txn = sell_rep = None
        if candidates is not None:
            tds, rds = candidates
            pos = np.searchsorted(tds, np.datetime64(buy_date), side='right')
            if pos < len(tds):
                sell_txn = pd.Timestamp(tds[pos])
                sell_rep = pd.Timestamp(rds[pos])

        if sell_txn is None:
            # No matching sell — skip unless allow_open
            if not allow_open:
                skipped += 1
                continue
            # If allow_open, mark to the last available price date
            sell_date = last_price_date
            is_open = True
        else:
            sell_date = sell_txn if exit == 'transaction' else sell_rep + timedelta(days=1)
            is_open = sell_date > last_price_date
            if is_open and not allow_open:
                skipped += 1
                continue

        # Entry date logic
        if entry == 'transaction':
            entry_date = buy_date
        else:  # 'disclosure'
            entry_date = pd.Timestamp(buy_row['ReportDate']).normalize() + timedelta(days=1)

        # A realistic exit disclosed before/at the realistic entry is not tradeable — skip.
        if sell_txn is not None and sell_date <= entry_date:
            skipped += 1
            continue

        if _bad_history(ticker, entry_date):
            skipped += 1
            continue

        # Get prices
        ep = get_price_on_or_after(price_cache[ticker], entry_date,
                                   max_gap_days=ENTRY_MAX_GAP_DAYS)
        xp = get_price_on_or_after(price_cache[ticker], sell_date)
        se = get_price_on_or_after(spy_prices, entry_date)
        sx = get_price_on_or_after(spy_prices, sell_date)

        if any(np.isnan([ep, xp, se, sx])) or ep <= 0 or xp <= 0 or se <= 0:
            skipped += 1
            continue

        tr, sr = xp / ep - 1.0, sx / se - 1.0
        hold_days = (sell_date - entry_date).days

        results.append({
            'Ticker': ticker,
            'Representative': rep,
            'Party': buy_row.get('Party', ''),
            'House': buy_row.get('House', ''),
            'BuyDate': buy_date,
            'SellDate': sell_date,
            'BuyReportDate': pd.Timestamp(buy_row['ReportDate']).normalize(),
            'EntryDate': entry_date,
            'ExitDate': sell_date,
            'HoldDays': hold_days,
            'EntryPrice': ep,
            'ExitPrice': xp,
            'TradeReturn': tr,
            'SPYReturn': sr,
            'ExcessReturn': tr - sr,
            'Open': is_open,
        })

    out = pd.DataFrame(results).sort_values('EntryDate').reset_index(drop=True)
    if verbose:
        print(f'{len(out):,} buy-sell matched pairs | {skipped} unmatched buys')
        print(f'Avg hold: {out["HoldDays"].mean():.0f} days')
        print(f'Avg return: {out["TradeReturn"].mean():.2%} | SPY: {out["SPYReturn"].mean():.2%} '
              f'| Excess: {out["ExcessReturn"].mean():.2%}')
        print(f'Win rate: {(out["TradeReturn"] > 0).mean():.2%} '
              f'| Beat SPY: {(out["ExcessReturn"] > 0).mean():.2%}')
    return out


def equity_curve(results: pd.DataFrame, price_cache: dict, spy_prices: pd.Series,
                 capital: float = INITIAL_CAPITAL) -> pd.DataFrame:
    """Daily equal-weight portfolio curve vs SPY buy-and-hold.

    Each trading day the portfolio return is the mean daily return of all open
    positions (equal weight, rebalanced daily). Sequential compounding of tens of
    thousands of overlapping trade returns is not a portfolio — this is.
    """
    start = results['EntryDate'].min()
    end = results['ExitDate'].max()
    days = spy_prices.index[(spy_prices.index >= start) & (spy_prices.index <= end)]
    sums = np.zeros(len(days))
    cnts = np.zeros(len(days))
    for row in results.itertuples():
        px = price_cache[row.Ticker]
        w = px[(px.index >= row.EntryDate) & (px.index <= row.ExitDate)]
        if len(w) < 2:
            continue
        r = w.pct_change().dropna()
        pos = days.searchsorted(r.index)
        ok = (pos < len(days)) & (days[np.minimum(pos, len(days) - 1)] == r.index)
        np.add.at(sums, pos[ok], r.values[ok])
        np.add.at(cnts, pos[ok], 1)
    daily = np.where(cnts > 0, sums / np.maximum(cnts, 1), 0.0)
    spy_win = spy_prices.reindex(days).ffill()
    return pd.DataFrame({
        'Date': days,
        'OpenPositions': cnts.astype(int),
        'CumPortfolio': capital * np.cumprod(1 + daily),
        'CumSPY': capital * (spy_win / spy_win.iloc[0]).values,
    })


def politician_stats(results: pd.DataFrame, min_trades: int = 5) -> pd.DataFrame:
    return (
        results
        .groupby('Representative', as_index=False)
        .agg(
            AvgTradeReturn=('TradeReturn', 'mean'),
            AvgSPYReturn=('SPYReturn', 'mean'),
            AvgExcessReturn=('ExcessReturn', 'mean'),
            NumTrades=('TradeReturn', 'count'),
            WinRate=('TradeReturn', lambda x: (x > 0).mean()),
            BeatSPYRate=('ExcessReturn', lambda x: (x > 0).mean()),
            Party=('Party', 'first'),
        )
        .query(f'NumTrades >= {min_trades}')
        .sort_values('AvgTradeReturn', ascending=False)
        .reset_index(drop=True)
    )


def summarize(results: pd.DataFrame, curve: pd.DataFrame) -> dict:
    # run_backtest names the buy date 'TransactionDate'; the hold-until-sell engine
    # names it 'BuyDate' (it has a sale date to disambiguate against).
    buy_col = 'TransactionDate' if 'TransactionDate' in results.columns else 'BuyDate'
    return {
        'total_trades': int(len(results)),
        'unique_tickers': int(results['Ticker'].nunique()),
        'unique_reps': int(results['Representative'].nunique()),
        'date_start': str(results[buy_col].min().date()),
        'date_end': str(results[buy_col].max().date()),
        'avg_trade_return': float(results['TradeReturn'].mean()),
        'avg_spy_return': float(results['SPYReturn'].mean()),
        'avg_excess_return': float(results['ExcessReturn'].mean()),
        'win_rate': float((results['TradeReturn'] > 0).mean()),
        'beat_spy_rate': float((results['ExcessReturn'] > 0).mean()),
        'final_portfolio': float(curve['CumPortfolio'].iloc[-1]),
        'final_spy': float(curve['CumSPY'].iloc[-1]),
    }
