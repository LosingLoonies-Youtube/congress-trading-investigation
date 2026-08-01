"""Fetch Congress trades from Quiver and print them as a big table.

Run from source_code/:
    ../venv/Scripts/python show_trades.py                # all buys, newest first
    ../venv/Scripts/python show_trades.py --all          # every transaction (buys + sells)
    ../venv/Scripts/python show_trades.py --limit 200    # show more/fewer rows
    ../venv/Scripts/python show_trades.py --csv trades.csv   # also dump full table to CSV
"""
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd

load_dotenv(Path(__file__).resolve().parents[1] / '.env')
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import data_quiver  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--all', action='store_true',
                    help='show every transaction (default: cleaned purchases only)')
    ap.add_argument('--limit', type=int, default=100,
                    help='rows to print to the terminal (default 100)')
    ap.add_argument('--csv', metavar='PATH', help='also write the FULL table to this CSV')
    args = ap.parse_args()

    print('Fetching Congress trades from Quiver...')
    raw = data_quiver.fetch_congress_trades()
    print(f'Total records fetched: {len(raw):,}\n')

    if args.all:
        df = data_quiver.canonicalize_names(raw).sort_values('TransactionDate', ascending=False)
    else:
        df = data_quiver.clean_congress_buys(raw).sort_values('TransactionDate', ascending=False)

    cols = [c for c in ['Representative', 'Party', 'House', 'Ticker', 'Transaction',
                        'TransactionDate', 'ReportDate', 'Amount'] if c in df.columns]
    table = df[cols].copy()
    if 'TransactionDate' in table:
        table['TransactionDate'] = table['TransactionDate'].dt.date
    if 'ReportDate' in table:
        table['ReportDate'] = table['ReportDate'].dt.date

    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', 30)

    print(f'Showing {min(args.limit, len(table)):,} of {len(table):,} rows '
          f'({"all transactions" if args.all else "cleaned purchases"}):\n')
    print(table.head(args.limit).to_string(index=False))

    if args.csv:
        out = Path(args.csv).resolve()
        table.to_csv(out, index=False)
        print(f'\nFull table ({len(table):,} rows) written to {out}')


if __name__ == '__main__':
    main()
