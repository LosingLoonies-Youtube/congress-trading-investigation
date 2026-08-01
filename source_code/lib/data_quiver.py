"""Quiver Quantitative client — Congress trades, lobbying, gov contracts, Trump trades.

All endpoints return normalized DataFrames with consistent column names:
Representative, Ticker, Transaction, TransactionDate, ReportDate, Amount, Party, House.
"""
import os
import re
import time
import requests
import pandas as pd

BASE = 'https://api.quiverquant.com/beta'


def _headers():
    return {'Authorization': f"Token {os.environ['QUIVER_API_KEY']}",
            'Accept': 'application/json'}


def _get(path: str, params: dict | None = None, retries: int = 6) -> list:
    for attempt in range(retries):
        resp = requests.get(BASE + path, headers=_headers(), params=params, timeout=120)
        if resp.status_code == 429 or resp.status_code >= 500:  # throttled / transient
            wait = float(resp.headers.get('Retry-After', 2 ** attempt))
            time.sleep(max(wait, 2 ** attempt))
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()


def fetch_congress_trades() -> pd.DataFrame:
    pages, page = [], 1
    while True:
        batch = _get('/bulk/congresstrading', {'page': page, 'page_size': 5000})
        if not batch:
            break
        pages.append(pd.DataFrame(batch))
        if len(batch) < 5000:
            break
        page += 1
        time.sleep(0.5)  # stay friendly to the rate limit
    df = pd.concat(pages, ignore_index=True)
    df = df.rename(columns={
        'Name': 'Representative', 'Traded': 'TransactionDate',
        'Filed': 'ReportDate', 'Trade_Size_USD': 'Amount', 'Chamber': 'House',
    })
    df['TransactionDate'] = pd.to_datetime(df['TransactionDate'], errors='coerce')
    df['ReportDate'] = pd.to_datetime(df['ReportDate'], errors='coerce')
    df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce')
    return df


_HONORIFIC = re.compile(r'\b(?:Mr|Ms|Mrs|Dr|Hon)\.?\s+')


def _strip_honorifics(name: str) -> str:
    return ' '.join(_HONORIFIC.sub('', str(name)).split())


def canonicalize_names(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    cleaned = df['Representative'].map(_strip_honorifics)
    if 'BioGuideID' in df.columns:
        canon = (pd.DataFrame({'id': df['BioGuideID'], 'name': cleaned})
                 .dropna(subset=['id'])
                 .groupby('id')['name']
                 .agg(lambda s: s.mode().iloc[0]))
        df['Representative'] = df['BioGuideID'].map(canon).fillna(cleaned)
    else:
        df['Representative'] = cleaned
    return df


def clean_congress_buys(df: pd.DataFrame) -> pd.DataFrame:
    """Purchases only, valid ticker + dates, deduplicated per member — keyed on
    BioGuideID, not the name string (see canonicalize_names). DJT excluded (own company).
    """
    df = canonicalize_names(df)
    df = df[df['Transaction'].str.lower().str.contains('purchase|buy', na=False)]
    df = df.dropna(subset=['TransactionDate', 'ReportDate', 'Ticker'])
    df['Ticker'] = df['Ticker'].str.upper().str.strip()
    df = df[df['Ticker'].str.match(r'^[A-Z]{1,5}$', na=False)]
    df = df[df['Ticker'] != 'DJT']
    member = (df['BioGuideID'].fillna(df['Representative'])
              if 'BioGuideID' in df.columns else df['Representative'])
    dup = pd.DataFrame({'m': member, 't': df['Ticker'],
                        'd': df['TransactionDate']}).duplicated()
    df = df[~dup.values]
    return df.sort_values('TransactionDate').reset_index(drop=True)


def clean_congress_sells(df: pd.DataFrame) -> pd.DataFrame:
    """Sales only (the inverse of clean_congress_buys). Used for buy-to-sell matching in v3.
    Same deduplication and cleaning as buys.
    """
    df = canonicalize_names(df)
    df = df[df['Transaction'].str.lower().str.contains('sale|sell', na=False)]
    df = df.dropna(subset=['TransactionDate', 'ReportDate', 'Ticker'])
    df['Ticker'] = df['Ticker'].str.upper().str.strip()
    df = df[df['Ticker'].str.match(r'^[A-Z]{1,5}$', na=False)]
    df = df[df['Ticker'] != 'DJT']
    member = (df['BioGuideID'].fillna(df['Representative'])
              if 'BioGuideID' in df.columns else df['Representative'])
    dup = pd.DataFrame({'m': member, 't': df['Ticker'],
                        'd': df['TransactionDate']}).duplicated()
    df = df[~dup.values]
    return df.sort_values('TransactionDate').reset_index(drop=True)


_EMPTY_ALT = pd.DataFrame({'Date': pd.Series(dtype='datetime64[ns]'),
                           'Amount': pd.Series(dtype=float)})


def fetch_lobbying(ticker: str) -> pd.DataFrame:
    """Quarterly lobbying disclosures for one ticker (LDA filings)."""
    df = pd.DataFrame(_get(f'/historical/lobbying/{ticker}'))
    if df.empty:
        return _EMPTY_ALT.copy()
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce')
    return df.dropna(subset=['Date']).sort_values('Date').reset_index(drop=True)


def fetch_gov_contracts(ticker: str) -> pd.DataFrame:
    """Federal contract awards for one ticker (USASpending/SAM)."""
    df = pd.DataFrame(_get(f'/historical/govcontractsall/{ticker}'))
    if df.empty:
        return _EMPTY_ALT.copy()
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce')
    return df.dropna(subset=['Date']).sort_values('Date').reset_index(drop=True)


def fetch_trump_trades() -> pd.DataFrame:
    """Trump stock trades (short history). Normalized to the congress schema."""
    df = pd.DataFrame(_get('/bulk/trumpstocktrades'))
    df = df.rename(columns={'Traded': 'TransactionDate', 'Filed': 'ReportDate'})
    df['TransactionDate'] = pd.to_datetime(df['TransactionDate'], errors='coerce')
    df['ReportDate'] = pd.to_datetime(df['ReportDate'], errors='coerce')
    df['Representative'] = 'Donald Trump'
    return df.dropna(subset=['TransactionDate']).sort_values('TransactionDate').reset_index(drop=True)
