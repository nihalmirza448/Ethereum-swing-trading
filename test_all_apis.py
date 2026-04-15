#!/usr/bin/env python3
"""
Quick test script to verify all API connections
Run this after adding your CoinDCX credentials
"""

def test_coinglass():
    """Test Coinglass API"""
    print("\n" + "="*60)
    print("TESTING COINGLASS API")
    print("="*60)

    try:
        from coinglass_client import CoinGlassClient
        client = CoinGlassClient()

        # Test liquidation data
        liq = client.get_liquidation_heatmap('ETH')
        print(f"✓ Coinglass connected")
        print(f"  Current Price: ${liq['current_price']:,.2f}")
        print(f"  Support Level: ${liq['high_risk_long_level']:,.2f}")
        print(f"  Resistance Level: ${liq['high_risk_short_level']:,.2f}")
        return True
    except Exception as e:
        print(f"❌ Coinglass failed: {e}")
        return False


def test_kraken():
    """Test Kraken API"""
    print("\n" + "="*60)
    print("TESTING KRAKEN API")
    print("="*60)

    try:
        from kraken_client import KrakenClient
        client = KrakenClient()

        # Test price
        price = client.get_current_price('ETH')
        if price:
            print(f"✓ Kraken connected")
            print(f"  ETH Price: ${price:,.2f}")

        # Test balance
        balance = client.get_account_balance()
        if balance:
            print(f"  Account has {len(balance)} assets")

        # Test order validation
        validation = client.place_market_order('ETH', 'buy', 0.01, validate=True)
        if validation:
            print(f"  ✓ Order validation working")

        return True
    except Exception as e:
        print(f"❌ Kraken failed: {e}")
        return False


def test_coindcx():
    """Test CoinDCX API"""
    print("\n" + "="*60)
    print("TESTING COINDCX API")
    print("="*60)

    try:
        from coindcx_client import CoinDCXClient
        client = CoinDCXClient()

        # Test price
        price = client.get_current_price('ETH')
        if price:
            print(f"✓ CoinDCX connected")
            print(f"  ETH Price: ${price:,.2f}")
        else:
            print(f"⚠ Could not get price")

        # Test ticker
        ticker = client.get_ticker('ETH')
        if ticker:
            print(f"  Bid: ${ticker['bid']:,.2f}")
            print(f"  Ask: ${ticker['ask']:,.2f}")
            print(f"  24h Volume: {ticker['volume']:,.2f}")

        # Test balance
        balance = client.get_account_balance()
        if balance:
            print(f"  Account has {len(balance)} assets")
        else:
            print(f"  ⚠ Could not get balance")

        # Test order validation
        validation = client.place_market_order('ETH', 'buy', 0.01, validate=True)
        if validation:
            print(f"  ✓ Order validation working")

        return True
    except Exception as e:
        print(f"❌ CoinDCX failed: {e}")
        print(f"   Make sure you've added COINDCX_API_KEY and COINDCX_API_SECRET to .env")
        return False


def test_multi_exchange():
    """Test Multi-Exchange Interface"""
    print("\n" + "="*60)
    print("TESTING MULTI-EXCHANGE INTERFACE")
    print("="*60)

    try:
        from multi_exchange_interface import MultiExchangeInterface
        interface = MultiExchangeInterface()

        # Get prices from all exchanges
        prices = interface.get_prices('ETH')
        print(f"\n✓ Multi-exchange interface working")
        print(f"  Connected to {len(prices)} exchange(s)")

        for exchange, price in prices.items():
            print(f"  {exchange.upper()}: ${price:,.2f}")

        # Find best price
        best_buy_ex, best_buy_price = interface.get_best_price('ETH', 'buy')
        best_sell_ex, best_sell_price = interface.get_best_price('ETH', 'sell')

        if best_buy_ex:
            print(f"\n  Best Exchange to Buy: {best_buy_ex.upper()} @ ${best_buy_price:,.2f}")
        if best_sell_ex:
            print(f"  Best Exchange to Sell: {best_sell_ex.upper()} @ ${best_sell_price:,.2f}")

        if best_buy_price and best_sell_price:
            spread = best_sell_price - best_buy_price
            print(f"  Arbitrage Spread: ${spread:.2f}")

        return True
    except Exception as e:
        print(f"❌ Multi-exchange interface failed: {e}")
        return False


def main():
    """Run all tests"""
    print("\n" + "="*70)
    print(" "*20 + "API CONNECTION TESTS")
    print("="*70)

    results = {
        'Coinglass': test_coinglass(),
        'Kraken': test_kraken(),
        'CoinDCX': test_coindcx(),
        'Multi-Exchange': test_multi_exchange()
    }

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    for service, status in results.items():
        status_icon = "✓" if status else "❌"
        status_text = "PASSED" if status else "FAILED"
        print(f"{status_icon} {service:20s} : {status_text}")

    passed = sum(results.values())
    total = len(results)

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All systems operational! Ready to trade!")
    else:
        print("\n⚠️  Some tests failed. Check the errors above.")
        if not results['CoinDCX']:
            print("\n💡 Tip: Add your CoinDCX API credentials to .env file:")
            print("   COINDCX_API_KEY=your_key")
            print("   COINDCX_API_SECRET=your_secret")

    print("="*70 + "\n")


if __name__ == "__main__":
    main()
