"""
Test Vnstock API - verify if vnstock can replace TCBS OpenAPI for historical and intraday data.
"""
import sys


def test_vnstock_install():
    """Test 1: Check if vnstock is installed"""
    print("\n" + "=" * 60)
    print("TEST 1: Check vnstock installation")
    print("=" * 60)
    try:
        import vnstock
        print("✅ vnstock is installed")
        print(f"   Version: {vnstock.__version__ if hasattr(vnstock, '__version__') else 'unknown'}")
        return True
    except ImportError as e:
        print(f"❌ vnstock not installed: {e}")
        print("\n💡 Install with: pip install vnstock -U")
        return False


def test_realtime_quote():
    """Test 2: Get real-time quote"""
    print("\n" + "=" * 60)
    print("TEST 2: Real-time Quote (TCB)")
    print("=" * 60)
    try:
        from vnstock.api.quote import Quote
        q = Quote(symbol='TCB', source='VCI')
        print("✅ Real-time quote retrieved:")
        print(q)
        return True, q
    except Exception as e:
        print(f"❌ Failed to get real-time quote: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def test_historical_data():
    """Test 3: Get historical data"""
    print("\n" + "=" * 60)
    print("TEST 3: Historical Data (TCB, last 60 days)")
    print("=" * 60)
    try:
        from vnstock.api.quote import Quote
        q = Quote(symbol='TCB', source='VCI')
        df = q.history(start='2026-04-21', end='2026-06-20', interval='1D')
        print(f"✅ Historical data retrieved: {len(df)} records")
        print("\nFirst 5 rows:")
        print(df.head())
        print("\nLast 5 rows:")
        print(df.tail())
        print("\nColumns:", df.columns.tolist() if hasattr(df, 'columns') else 'N/A')
        return True, df
    except Exception as e:
        print(f"❌ Failed to get historical data: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def test_intraday_data():
    """Test 4: Get intraday trade data."""
    print("\n" + "=" * 60)
    print("TEST 4: Intraday Data (TCB)")
    print("=" * 60)
    try:
        from vnstock.api.quote import Quote
        q = Quote(symbol='TCB', source='VCI')
        df = q.provider.intraday(page_size=20)
        print("✅ q.provider.intraday() returned intraday data:")
        print(df.head())
        return True, df
    except Exception as e:
        print(f"❌ Failed to get intraday data: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def test_multiple_tickers():
    """Test 5: Get data for multiple tickers"""
    print("\n" + "=" * 60)
    print("TEST 5: Multiple Tickers (TCB, HPG, SSI)")
    print("=" * 60)
    tickers = ['TCB', 'HPG', 'SSI']
    results = {}
    try:
        from vnstock.api.quote import Quote
        for ticker in tickers:
            q = Quote(symbol=ticker, source='VCI')
            results[ticker] = q
            print(f"✅ {ticker}: {q}")
        return True, results
    except Exception as e:
        print(f"❌ Failed to get multiple tickers: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def test_extract_fields():
    """Test 6: Extract common fields from Quote object."""
    print("\n" + "=" * 60)
    print("TEST 6: Extract Common Fields from Quote")
    print("=" * 60)
    try:
        from vnstock.api.quote import Quote
        q = Quote(symbol='TCB', source='VCI')

        print("Available non-callable attributes in quote object:")
        for attr in dir(q):
            if not attr.startswith('_'):
                try:
                    val = getattr(q, attr)
                    if not callable(val):
                        print(f"  - {attr}: {val}")
                except Exception:
                    pass

        price = None
        for field in ['last_price', 'price', 'c', 'close', 'last']:
            price = getattr(q, field, None)
            if price is not None:
                print(f"\n✅ Current price found in field '{field}': {price}")
                break

        if price is None:
            print("\n⚠️  Could not find a standard price field")

        return True
    except Exception as e:
        print(f"❌ Failed to extract fields: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("VNSTOCK API TEST SUITE")
    print("=" * 60)

    if not test_vnstock_install():
        print("\n⚠️  Installing vnstock...")
        import subprocess
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "vnstock", "-U"])
            print("✅ vnstock installed successfully")
        except Exception as e:
            print(f"❌ Failed to install vnstock: {e}")
            sys.exit(1)

    success_rt, quote = test_realtime_quote()
    success_hist, df_hist = test_historical_data()
    success_intraday, df_intraday = test_intraday_data()
    success_multi, results = test_multiple_tickers()
    test_extract_fields()

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Real-time quote: {'✅ PASS' if success_rt else '❌ FAIL'}")
    print(f"Historical data: {'✅ PASS' if success_hist else '❌ FAIL'}")
    print(f"Intraday data: {'✅ PASS' if success_intraday else '❌ FAIL'}")
    print(f"Multiple tickers: {'✅ PASS' if success_multi else '❌ FAIL'}")

    if success_rt and success_hist and success_intraday:
        print("\n✅ vnstock can be used as a replacement candidate for TCBS data.")
        print("\n💡 Next step: Implement MarketAPIAdapter using vnstock Quote and provider intraday methods.")
    else:
        print("\n❌ Some vnstock tests failed. Check errors above.")
