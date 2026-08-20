"""
test_provider.py — prove Twelve Data works for YOUR tickers before rewiring the app.

Run:  python test_provider.py

It checks a NASDAQ name and tries several formats for a Singapore stock, because
Twelve Data's SGX symbol format may differ from yfinance's '.SI'. Whichever format
returns rows is the one to use — tell me which, and I'll wire the app to match.
"""

from data_provider import get_history

# NASDAQ should just work:
nasdaq_tests = ["AAPL", "ASML"]

# SGX format is uncertain — try candidates for DBS and see which returns data.
sgx_candidates = ["D05.SI", "D05:SGX", "D05", "D05.SGX"]

print("=== NASDAQ ===")
for sym in nasdaq_tests:
    try:
        df = get_history(sym)
        print(f"  {sym:<10} OK  {len(df)} rows, last {df.index[-1].date()} close {df['Close'].iloc[-1]:.2f}")
    except Exception as e:
        print(f"  {sym:<10} FAILED: {e}")

print("\n=== SGX (DBS) — find the format that works ===")
for sym in sgx_candidates:
    try:
        df = get_history(sym)
        print(f"  {sym:<10} OK  {len(df)} rows, last {df.index[-1].date()} close {df['Close'].iloc[-1]:.2f}")
    except Exception as e:
        print(f"  {sym:<10} FAILED: {e}")

print("\nReport back: which NASDAQ worked, and which SGX format returned rows.")