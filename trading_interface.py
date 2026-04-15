"""
Unified Trading Interface - Combines Coinglass market data with Kraken trade execution
"""
from coinglass_client import CoinGlassClient
from kraken_client import KrakenClient
from datetime import datetime
import json


class TradingInterface:
    """
    Unified interface combining market data from Coinglass and trade execution on Kraken

    Usage:
        interface = TradingInterface()

        # Get market analysis
        analysis = interface.get_market_analysis('ETH')

        # Execute trade
        interface.execute_trade('ETH', 'buy', 0.1, order_type='market')
    """

    def __init__(self):
        """Initialize Coinglass and Kraken clients"""
        print("Initializing Trading Interface...")

        self.coinglass = CoinGlassClient()
        print("✓ Coinglass connected (market data)")

        try:
            self.kraken = KrakenClient()
            print("✓ Kraken connected (trade execution)")
            self.kraken_available = True
        except Exception as e:
            print(f"⚠ Kraken not available: {e}")
            self.kraken_available = False

    def get_market_analysis(self, symbol='ETH'):
        """
        Get comprehensive market analysis combining multiple data sources

        Args:
            symbol: Trading symbol (ETH, BTC, etc.)

        Returns:
            dict: Complete market analysis with:
                - Current price
                - Coinglass indicators (liquidations, OI, funding, etc.)
                - Trading recommendation
        """
        print(f"\n{'='*60}")
        print(f"Market Analysis for {symbol}")
        print(f"{'='*60}\n")

        # Get current price from Kraken
        current_price = None
        if self.kraken_available:
            current_price = self.kraken.get_current_price(symbol)
            if current_price:
                print(f"Current Price: ${current_price:,.2f}")

        # Get Coinglass data
        print("\nFetching market indicators...")
        coinglass_data = self.coinglass.get_market_summary(symbol)

        # Combine data
        analysis = {
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'current_price': current_price,
            'coinglass_data': coinglass_data,
            'recommendation': self._generate_recommendation(coinglass_data, current_price)
        }

        # Print summary
        self._print_analysis_summary(analysis)

        return analysis

    def _generate_recommendation(self, coinglass_data, current_price):
        """
        Generate trading recommendation based on market data

        Args:
            coinglass_data: Data from Coinglass
            current_price: Current market price

        Returns:
            dict: Trading recommendation
        """
        signals = {
            'long_short_ratio': coinglass_data['long_short_ratio']['sentiment'],
            'funding_rate': coinglass_data['funding_rates']['sentiment'],
            'open_interest_trend': coinglass_data['open_interest']['trend']
        }

        # Liquidation levels
        liq_data = coinglass_data['liquidations']
        support_level = liq_data['high_risk_long_level']
        resistance_level = liq_data['high_risk_short_level']

        # Simple sentiment scoring
        bullish_signals = sum(1 for s in signals.values() if s in ['BULLISH', 'INCREASING'])
        bearish_signals = sum(1 for s in signals.values() if s in ['BEARISH', 'DECREASING'])

        if bullish_signals > bearish_signals:
            bias = 'BULLISH'
            action = 'BUY'
        elif bearish_signals > bullish_signals:
            bias = 'BEARISH'
            action = 'SELL'
        else:
            bias = 'NEUTRAL'
            action = 'WAIT'

        return {
            'bias': bias,
            'action': action,
            'confidence': max(bullish_signals, bearish_signals) / len(signals) * 100,
            'support': support_level,
            'resistance': resistance_level,
            'signals': signals
        }

    def _print_analysis_summary(self, analysis):
        """Print formatted analysis summary"""
        print(f"\n{'='*60}")
        print("MARKET SUMMARY")
        print(f"{'='*60}")

        rec = analysis['recommendation']
        print(f"\nTrading Recommendation:")
        print(f"  Bias: {rec['bias']}")
        print(f"  Action: {rec['action']}")
        print(f"  Confidence: {rec['confidence']:.0f}%")
        print(f"  Support Level: ${rec['support']:,.2f}")
        print(f"  Resistance Level: ${rec['resistance']:,.2f}")

        print(f"\nKey Signals:")
        for signal, sentiment in rec['signals'].items():
            print(f"  {signal.replace('_', ' ').title()}: {sentiment}")

        print(f"\n{'='*60}\n")

    def execute_trade(self, symbol, side, amount, order_type='market',
                     price=None, stop_loss=None, validate=False):
        """
        Execute a trade on Kraken

        Args:
            symbol: Trading symbol (ETH, BTC)
            side: 'buy' or 'sell'
            amount: Amount to trade (in base currency)
            order_type: 'market', 'limit', or 'stop-loss'
            price: Limit price (required for limit orders)
            stop_loss: Stop loss price (optional)
            validate: If True, only validate (don't execute)

        Returns:
            dict: Order result or None if failed
        """
        if not self.kraken_available:
            print("❌ Kraken not available - cannot execute trade")
            return None

        print(f"\n{'='*60}")
        print(f"{'VALIDATING' if validate else 'EXECUTING'} TRADE")
        print(f"{'='*60}")
        print(f"Symbol: {symbol}")
        print(f"Side: {side.upper()}")
        print(f"Amount: {amount}")
        print(f"Type: {order_type}")
        if price:
            print(f"Price: ${price:,.2f}")
        if stop_loss:
            print(f"Stop Loss: ${stop_loss:,.2f}")
        print(f"{'='*60}\n")

        # Execute based on order type
        result = None

        if order_type.lower() == 'market':
            result = self.kraken.place_market_order(symbol, side, amount, validate=validate)

        elif order_type.lower() == 'limit':
            if not price:
                print("❌ Limit price required for limit orders")
                return None
            result = self.kraken.place_limit_order(symbol, side, amount, price, validate=validate)

        elif order_type.lower() == 'stop-loss':
            if not stop_loss:
                print("❌ Stop loss price required for stop-loss orders")
                return None
            result = self.kraken.place_stop_loss_order(symbol, side, amount, stop_loss, price)

        # If successful and stop loss requested, place stop loss order
        if result and stop_loss and order_type != 'stop-loss' and not validate:
            print(f"\nPlacing stop-loss order at ${stop_loss:,.2f}...")
            stop_side = 'sell' if side == 'buy' else 'buy'
            self.kraken.place_stop_loss_order(symbol, stop_side, amount, stop_loss)

        return result

    def get_account_info(self):
        """
        Get account information including balance and open positions

        Returns:
            dict: Account information
        """
        if not self.kraken_available:
            print("❌ Kraken not available")
            return None

        print(f"\n{'='*60}")
        print("ACCOUNT INFORMATION")
        print(f"{'='*60}\n")

        # Get balance
        balance = self.kraken.get_account_balance()
        print("Balance:")
        if balance:
            for asset, amount in balance.items():
                # Get USD value for crypto assets
                usd_value = None
                if asset in ['XETH', 'XXBT'] and amount > 0:
                    symbol = 'ETH' if asset == 'XETH' else 'BTC'
                    price = self.kraken.get_current_price(symbol)
                    if price:
                        usd_value = amount * price

                if usd_value:
                    print(f"  {asset}: {amount:,.8f} (≈ ${usd_value:,.2f})")
                else:
                    print(f"  {asset}: {amount:,.8f}")
        else:
            print("  No balance found")

        # Get open orders
        print("\nOpen Orders:")
        open_orders = self.kraken.get_open_orders()
        if not open_orders.empty:
            print(f"  {len(open_orders)} open orders")
            print(open_orders)
        else:
            print("  No open orders")

        print(f"\n{'='*60}\n")

        return {
            'balance': balance,
            'open_orders': open_orders
        }


def demo():
    """Demo the trading interface"""
    print("\n" + "="*60)
    print("TRADING INTERFACE DEMO")
    print("="*60 + "\n")

    # Initialize interface
    interface = TradingInterface()

    # Get market analysis
    print("\n1. Getting market analysis...")
    analysis = interface.get_market_analysis('ETH')

    # Get account info
    print("\n2. Getting account information...")
    account = interface.get_account_info()

    # Validate a trade (won't execute)
    print("\n3. Validating a trade (simulation)...")
    validation = interface.execute_trade(
        symbol='ETH',
        side='buy',
        amount=0.01,
        order_type='market',
        validate=True
    )

    print("\n" + "="*60)
    print("DEMO COMPLETE")
    print("="*60)
    print("\nTo execute a real trade, set validate=False")
    print("Example: interface.execute_trade('ETH', 'buy', 0.01, validate=False)")
    print("="*60 + "\n")


if __name__ == "__main__":
    demo()
