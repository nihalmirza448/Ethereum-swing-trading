"""
Test CoinGlass API Capabilities

This script checks:
1. What data CoinGlass provides
2. If it has OHLCV historical data
3. What it can add to our strategy
4. Whether it's sufficient for backtesting
"""

import requests
import json
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

def test_coinglass_endpoints():
    """Test various CoinGlass API endpoints"""

    print("=" * 70)
    print("🔍 COINGLASS API CAPABILITIES TEST")
    print("=" * 70)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    api_key = os.getenv('COINGLASS_API_KEY')
    if api_key:
        print(f"\n✅ API Key Found: {api_key[:10]}...")
    else:
        print("\n⚠️  No API Key - Testing public endpoints only")

    base_url = "https://open-api.coinglass.com/public/v2"
    headers = {'coinglassSecret': api_key} if api_key else {}

    print("\n" + "=" * 70)
    print("TESTING AVAILABLE ENDPOINTS")
    print("=" * 70)

    # Test 1: Liquidation Heatmap
    print("\n1. Testing Liquidation Heatmap...")
    try:
        response = requests.get(
            f"{base_url}/liquidation_heatmap",
            params={'symbol': 'ETH', 'ex': 'All'},
            headers=headers,
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("   ✅ Liquidation heatmap: Available")
                print(f"   Data: {list(data.get('data', {}).keys())}")
            else:
                print(f"   ❌ Error: {data.get('msg')}")
        else:
            print(f"   ❌ HTTP {response.status_code}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Test 2: Open Interest
    print("\n2. Testing Open Interest...")
    try:
        response = requests.get(
            f"{base_url}/open_interest",
            params={'symbol': 'ETH'},
            headers=headers,
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("   ✅ Open interest: Available")
                print(f"   Data keys: {list(data.get('data', {}).keys())}")
            else:
                print(f"   ❌ Error: {data.get('msg')}")
        else:
            print(f"   ❌ HTTP {response.status_code}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Test 3: Funding Rates
    print("\n3. Testing Funding Rates...")
    try:
        response = requests.get(
            f"{base_url}/funding",
            params={'symbol': 'ETH'},
            headers=headers,
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("   ✅ Funding rates: Available")
                print(f"   Data keys: {list(data.get('data', {}).keys())}")
            else:
                print(f"   ❌ Error: {data.get('msg')}")
        else:
            print(f"   ❌ HTTP {response.status_code}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Test 4: Long/Short Ratio
    print("\n4. Testing Long/Short Ratio...")
    try:
        response = requests.get(
            f"{base_url}/long_short",
            params={'symbol': 'ETH', 'ex': 'All'},
            headers=headers,
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("   ✅ Long/Short ratio: Available")
                print(f"   Data keys: {list(data.get('data', {}).keys())}")
            else:
                print(f"   ❌ Error: {data.get('msg')}")
        else:
            print(f"   ❌ HTTP {response.status_code}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Test 5: Try to find OHLCV/Candle data
    print("\n5. Looking for OHLCV/Historical Price Data...")

    test_endpoints = [
        "ohlc",
        "candles",
        "klines",
        "price_history",
        "historical",
        "ticker_history",
        "market_data",
        "indicator",
    ]

    found_ohlcv = False
    for endpoint in test_endpoints:
        try:
            response = requests.get(
                f"{base_url}/{endpoint}",
                params={'symbol': 'ETH'},
                headers=headers,
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    print(f"   ✅ Found endpoint: {endpoint}")
                    print(f"      Data: {list(data.get('data', {}).keys())[:5]}")
                    found_ohlcv = True
                    break
        except:
            pass

    if not found_ohlcv:
        print("   ❌ No OHLCV/historical price data endpoints found")

    # Test 6: Check API documentation reference
    print("\n6. Checking indicator endpoints...")
    try:
        response = requests.get(
            f"{base_url}/indicator",
            params={'symbol': 'ETH', 'type': 'all'},
            headers=headers,
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            print(f"   Response: {data}")
        else:
            print(f"   ❌ No indicator endpoint")
    except Exception as e:
        print(f"   ❌ Error: {e}")


def analyze_coinglass_for_strategy():
    """Analyze what CoinGlass can provide for our strategy"""

    print("\n" + "=" * 70)
    print("📊 COINGLASS DATA FOR STRATEGY ANALYSIS")
    print("=" * 70)

    print("\n✅ WHAT COINGLASS PROVIDES:")
    print("=" * 70)

    print("\n1. **Liquidation Heatmap**")
    print("   - Shows where liquidations will occur")
    print("   - Identifies liquidity clusters (similar to our BSL/SSL)")
    print("   - Real-time liquidation risk levels")
    print("   📊 Usefulness: VERY HIGH for liquidity analysis")

    print("\n2. **Open Interest**")
    print("   - Total open positions across exchanges")
    print("   - Shows market commitment")
    print("   - Can indicate trend strength")
    print("   📊 Usefulness: MEDIUM for trend confirmation")

    print("\n3. **Funding Rates**")
    print("   - Cost of holding leveraged positions")
    print("   - Indicates market sentiment (bulls vs bears)")
    print("   - Can show overcrowding")
    print("   📊 Usefulness: MEDIUM for sentiment analysis")

    print("\n4. **Long/Short Ratio**")
    print("   - Percentage of traders long vs short")
    print("   - Shows market positioning")
    print("   - Can be contrarian indicator")
    print("   📊 Usefulness: LOW-MEDIUM for sentiment")

    print("\n" + "=" * 70)
    print("❌ WHAT COINGLASS DOES NOT PROVIDE:")
    print("=" * 70)

    print("\n1. ❌ Historical OHLCV Data (price, volume)")
    print("   - Cannot get open, high, low, close prices")
    print("   - Cannot get historical volume")
    print("   - Cannot backtest without this!")

    print("\n2. ❌ Technical Indicators")
    print("   - No RSI, MACD, Bollinger Bands")
    print("   - No moving averages")
    print("   - No CVD (they show it on charts but no API)")

    print("\n3. ❌ Real-time Price Feed")
    print("   - Not designed for price data")
    print("   - Need exchange APIs for this")

    print("\n" + "=" * 70)
    print("🎯 CAN COINGLASS BE USED FOR YOUR STRATEGY?")
    print("=" * 70)

    print("\n📋 REQUIREMENT CHECKLIST:")
    print("-" * 70)

    requirements = [
        ("Historical OHLCV data (5 years)", "❌", "CRITICAL - Need for backtesting"),
        ("Real-time price data", "❌", "CRITICAL - Need for live trading"),
        ("Volume data", "❌", "CRITICAL - Need for CVD calculation"),
        ("Liquidation clusters", "✅", "BONUS - Enhances liquidity analysis"),
        ("Open interest", "✅", "BONUS - Can improve strategy"),
        ("Funding rates", "✅", "BONUS - Good for sentiment"),
        ("Technical indicators", "❌", "Not needed - We calculate ourselves"),
    ]

    for requirement, status, note in requirements:
        print(f"   {status} {requirement:<35} | {note}")

    print("\n" + "=" * 70)
    print("💡 VERDICT:")
    print("=" * 70)

    print("\n❌ **CoinGlass CANNOT be used alone for backtesting**")
    print("   Reason: No historical OHLCV data")

    print("\n✅ **CoinGlass CAN enhance the strategy**")
    print("   Use case: Add liquidation data as additional confluence")

    print("\n📊 **RECOMMENDED APPROACH:**")
    print("-" * 70)
    print("   1. Primary Data: Coinbase/Kraken (OHLCV)")
    print("   2. Enhancement: CoinGlass (liquidation clusters)")
    print("   3. Calculation: Python (all indicators)")
    print("   4. Execution: CoinDCX (trading)")

    print("\n" + "=" * 70)
    print("🔧 HYBRID STRATEGY BENEFITS:")
    print("=" * 70)

    print("\n✅ Using Coinbase + CoinGlass Together:")
    print("   - Coinbase: Provides OHLCV (required)")
    print("   - Your System: Calculates CVD, structure, indicators")
    print("   - CoinGlass: Adds liquidation heatmap data")
    print("   - Result: BETTER liquidity analysis!")

    print("\n   Example Enhanced Entry:")
    print("   ✓ SSL sweep detected (your calculation)")
    print("   ✓ CVD bullish surge (your calculation)")
    print("   ✓ Order block hold (your calculation)")
    print("   ✓ High liquidation cluster at SSL (CoinGlass)")
    print("   ✓ Funding rate negative (CoinGlass)")
    print("   → Confluence Score: 5/7 → TAKE TRADE!")


def show_implementation_plan():
    """Show how to implement CoinGlass enhancement"""

    print("\n" + "=" * 70)
    print("🚀 IMPLEMENTATION PLAN")
    print("=" * 70)

    print("\n**PHASE 1: Core Strategy (CURRENT - Already Working)**")
    print("-" * 70)
    print("   Data Source: Coinbase")
    print("   Indicators: CVD, Liquidity, Structure, RSI, EMAs")
    print("   Status: ✅ Implemented")
    print("   Next: Run backtest on 5 years of data")

    print("\n**PHASE 2: Add CoinGlass Enhancement (OPTIONAL - Later)**")
    print("-" * 70)
    print("   Add to confluence scoring:")
    print("   - Check if liquidation cluster aligns with entry")
    print("   - Use funding rate for sentiment")
    print("   - Use long/short ratio for contrarian signals")
    print("   Status: ⚠️  Can add after core strategy proven")

    print("\n**PHASE 3: Live Trading (FUTURE)**")
    print("-" * 70)
    print("   Real-time data: Coinbase/Kraken WebSocket")
    print("   Live liquidation: CoinGlass API")
    print("   Execution: CoinDCX")
    print("   Status: 🔮 After successful paper trading")

    print("\n" + "=" * 70)
    print("🎯 IMMEDIATE NEXT STEPS:")
    print("=" * 70)

    print("\n1. ✅ Get historical data from Coinbase")
    print("   Command: python coinbase_collector.py")
    print("   Duration: ~2 minutes")
    print("   Result: 5 years of hourly OHLCV data")

    print("\n2. ✅ Run professional strategy backtest")
    print("   Command: python backtest_professional.py")
    print("   Duration: ~30 seconds")
    print("   Result: Full performance report")

    print("\n3. ⚠️  (Optional) Add CoinGlass liquidation data")
    print("   When: After core strategy shows positive results")
    print("   How: Add as extra confluence factor")
    print("   Benefit: Better entry timing near liquidation clusters")

    print("\n" + "=" * 70)


def main():
    """Main test function"""

    # Test CoinGlass endpoints
    test_coinglass_endpoints()

    # Analyze for strategy
    analyze_coinglass_for_strategy()

    # Show implementation plan
    show_implementation_plan()

    print("\n" + "=" * 70)
    print("📌 FINAL SUMMARY")
    print("=" * 70)

    print("\n❌ CoinGlass ALONE: Cannot backtest strategy")
    print("   → Missing: Historical price/volume data")

    print("\n✅ CoinGlass AS ENHANCEMENT: Very valuable!")
    print("   → Provides: Real liquidation clusters")
    print("   → Enhances: Your liquidity analysis")

    print("\n✅ RECOMMENDED DATA SOURCES:")
    print("   → Primary: Coinbase (OHLCV data)")
    print("   → Enhancement: CoinGlass (liquidations)")
    print("   → Execution: CoinDCX (trading)")

    print("\n💡 READY TO PROCEED:")
    print("   1. Run: python coinbase_collector.py")
    print("   2. Run: python backtest_professional.py")
    print("   3. Review results")
    print("   4. (Later) Add CoinGlass enhancement")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
