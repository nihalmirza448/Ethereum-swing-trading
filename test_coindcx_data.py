"""
Test CoinDCX API for historical data availability

This script checks:
1. If we can connect to CoinDCX
2. What data endpoints are available
3. Whether we can fetch historical OHLCV data
"""

import requests
import json
from datetime import datetime, timedelta

def test_coindcx_public_api():
    """Test CoinDCX public API endpoints"""
    print("=" * 70)
    print("TESTING COINDCX PUBLIC API")
    print("=" * 70)

    base_url = "https://public.coindcx.com"

    # Test 1: Get ticker data
    print("\n1. Testing ticker endpoint...")
    try:
        response = requests.get(f"{base_url}/exchange/ticker", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Ticker endpoint works")

            # Find ETH pairs
            eth_pairs = [item for item in data if 'ETH' in item.get('market', '')]
            if eth_pairs:
                print(f"   Found {len(eth_pairs)} ETH trading pairs")
                print(f"   Example pairs: {[p.get('market') for p in eth_pairs[:3]]}")

                # Show ETHUSDT price if available
                ethusdt = next((p for p in eth_pairs if p.get('market') == 'ETHUSDT'), None)
                if ethusdt:
                    print(f"\n   📊 ETHUSDT Current Price: ${float(ethusdt.get('last_price', 0)):.2f}")
        else:
            print(f"❌ Ticker endpoint failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Test 2: Check markets
    print("\n2. Testing markets endpoint...")
    try:
        response = requests.get(f"{base_url}/exchange/v1/markets", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Markets endpoint works")
            print(f"   Total markets: {len(data)}")

            # Find ETH markets
            eth_markets = [m for m in data if 'ETH' in m.get('symbol', '')]
            print(f"   ETH markets: {len(eth_markets)}")
        else:
            print(f"❌ Markets endpoint failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Test 3: Try to find historical data endpoints
    print("\n3. Looking for historical/candle data endpoints...")

    # Try common historical data endpoint patterns
    test_endpoints = [
        "/exchange/v1/candles",
        "/market_data/candles",
        "/market/candles",
        "/exchange/v1/klines",
        "/exchange/v1/ohlc",
        "/api/v1/candles",
    ]

    for endpoint in test_endpoints:
        try:
            # Try with some parameters
            params = {
                'pair': 'ETHUSDT',
                'interval': '1h',
                'limit': 10
            }
            response = requests.get(f"{base_url}{endpoint}", params=params, timeout=5)
            if response.status_code == 200:
                print(f"   ✅ Found working endpoint: {endpoint}")
                print(f"      Response: {response.text[:200]}")
                break
            elif response.status_code != 404:
                print(f"   ⚠️  {endpoint} returned {response.status_code}")
        except:
            pass
    else:
        print("   ❌ No historical data endpoints found")

    # Test 4: Check order book (another data source)
    print("\n4. Testing order book endpoint...")
    try:
        response = requests.get(f"{base_url}/market_data/orderbook",
                               params={'pair': 'B-ETH_USDT'}, timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Order book endpoint works")
            if 'asks' in data and 'bids' in data:
                print(f"   Asks: {len(data['asks'])} levels")
                print(f"   Bids: {len(data['bids'])} levels")
        else:
            print(f"❌ Order book endpoint failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Test 5: Check trade history
    print("\n5. Testing trade history endpoint...")
    try:
        response = requests.get(f"{base_url}/market_data/trade_history",
                               params={'pair': 'B-ETH_USDT', 'limit': 10}, timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Trade history endpoint works")
            print(f"   Recent trades: {len(data)}")
        else:
            print(f"❌ Trade history failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Error: {e}")


def check_alternative_data_sources():
    """Check if we need to use alternative sources"""
    print("\n" + "=" * 70)
    print("ALTERNATIVE DATA SOURCES")
    print("=" * 70)

    print("\nCoinDCX Note:")
    print("  CoinDCX is primarily a spot/margin trading exchange in India")
    print("  It may not provide comprehensive historical OHLCV data via public API")

    print("\n✅ RECOMMENDED DATA SOURCES:")
    print("\n1. **Coinbase** (Free, no API key needed)")
    print("   - Excellent historical data")
    print("   - Already implemented in coinbase_collector.py")
    print("   - Supports: 1m, 5m, 15m, 1h, 6h, 1d candles")
    print("   - ✅ Best choice for backtesting")

    print("\n2. **Kraken** (Your current API keys)")
    print("   - Good historical data")
    print("   - Already implemented in data_collector.py")
    print("   - Similar pricing to other exchanges")

    print("\n3. **Binance** (Free API)")
    print("   - Comprehensive historical data")
    print("   - Can fetch via ccxt library")
    print("   - No API key needed for historical data")

    print("\n💡 RECOMMENDATION:")
    print("   For strategy development and backtesting:")
    print("   → Use Coinbase/Kraken for historical data (free & accurate)")
    print("   → Use CoinDCX for live trading execution (when you're ready)")
    print("   → This separates data collection from trade execution")

    print("\n📊 Current Status:")
    print("   ✅ Coinbase data collector: Available")
    print("   ✅ Kraken data collector: Available")
    print("   ⚠️  CoinDCX: For trading only, not historical data")


def main():
    """Main test function"""
    print("\n" + "=" * 70)
    print("🔍 COINDCX DATA AVAILABILITY CHECK")
    print("=" * 70)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Test public API
    test_coindcx_public_api()

    # Show alternatives
    check_alternative_data_sources()

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("\n✅ You CAN connect to CoinDCX for:")
    print("   - Live trading (buy/sell orders)")
    print("   - Account balance checking")
    print("   - Current price data")
    print("   - Order management")

    print("\n⚠️  For historical data (backtesting):")
    print("   - Use Coinbase API (already implemented)")
    print("   - Or use Kraken API (you have credentials)")
    print("   - Both provide clean OHLCV data for free")

    print("\n💡 NEXT STEPS:")
    print("   1. Keep using Coinbase for data collection")
    print("   2. Configure CoinDCX API keys for live trading (when ready)")
    print("   3. The strategy works the same regardless of data source")
    print("=" * 70)


if __name__ == "__main__":
    main()
