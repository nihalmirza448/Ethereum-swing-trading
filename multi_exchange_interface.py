"""
Multi-Exchange Trading Interface - Trade on Kraken and CoinDCX with unified API
Combines Coinglass market data with execution on multiple exchanges
"""
from coinglass_client import CoinGlassClient
from kraken_client import KrakenClient
from coindcx_client import CoinDCXClient
from datetime import datetime
import json


class MultiExchangeInterface:
    """
    Unified interface for trading on multiple exchanges

    Features:
    - Market data from Coinglass
    - Trade execution on Kraken and/or CoinDCX
    - Unified API across exchanges
    - Parallel order execution
    - Account aggregation

    Usage:
        interface = MultiExchangeInterface()

        # Get market analysis
        analysis = interface.get_market_analysis('ETH')

        # Execute on specific exchange
        interface.execute_trade('ETH', 'buy', 0.1, exchange='kraken')

        # Execute on both exchanges
        interface.execute_parallel_trade('ETH', 'buy', 0.1)
    """

    def __init__(self, enable_kraken=True, enable_coindcx=True):
        """
        Initialize multi-exchange interface

        Args:
            enable_kraken: Enable Kraken trading
            enable_coindcx: Enable CoinDCX trading
        """
        print("Initializing Multi-Exchange Trading Interface...")

        # Market data client
        self.coinglass = CoinGlassClient()
        print("✓ Coinglass connected (market data)")

        # Exchange clients
        self.exchanges = {}

        # Initialize Kraken
        if enable_kraken:
            try:
                self.exchanges['kraken'] = KrakenClient()
                print("✓ Kraken connected")
            except Exception as e:
                print(f"⚠ Kraken not available: {e}")

        # Initialize CoinDCX
        if enable_coindcx:
            try:
                self.exchanges['coindcx'] = CoinDCXClient()
                print("✓ CoinDCX connected")
            except Exception as e:
                print(f"⚠ CoinDCX not available: {e}")

        if not self.exchanges:
            print("⚠ No exchanges available for trading")

        print(f"\n{'='*60}")
        print(f"Active Exchanges: {', '.join(self.exchanges.keys()).upper()}")
        print(f"{'='*60}\n")

    def get_prices(self, symbol='ETH'):
        """
        Get prices from all connected exchanges

        Args:
            symbol: Trading symbol

        Returns:
            dict: Prices by exchange
        """
        prices = {}

        for exchange_name, client in self.exchanges.items():
            try:
                price = client.get_current_price(symbol)
                if price:
                    prices[exchange_name] = price
            except Exception as e:
                print(f"Error getting price from {exchange_name}: {e}")

        return prices

    def get_best_price(self, symbol='ETH', side='buy'):
        """
        Find best price across exchanges

        Args:
            symbol: Trading symbol
            side: 'buy' or 'sell'

        Returns:
            tuple: (exchange_name, price)
        """
        prices = self.get_prices(symbol)

        if not prices:
            return None, None

        if side.lower() == 'buy':
            # For buying, we want lowest price
            best_exchange = min(prices, key=prices.get)
        else:
            # For selling, we want highest price
            best_exchange = max(prices, key=prices.get)

        return best_exchange, prices[best_exchange]

    def get_market_analysis(self, symbol='ETH'):
        """
        Get comprehensive market analysis

        Args:
            symbol: Trading symbol

        Returns:
            dict: Complete market analysis with prices from all exchanges
        """
        print(f"\n{'='*60}")
        print(f"Multi-Exchange Market Analysis for {symbol}")
        print(f"{'='*60}\n")

        # Get prices from all exchanges
        print("Fetching prices from exchanges...")
        prices = self.get_prices(symbol)

        for exchange, price in prices.items():
            print(f"  {exchange.upper()}: ${price:,.2f}")

        if prices:
            avg_price = sum(prices.values()) / len(prices)
            print(f"  Average: ${avg_price:,.2f}")

            # Calculate spread
            if len(prices) > 1:
                spread = max(prices.values()) - min(prices.values())
                spread_pct = (spread / avg_price) * 100
                print(f"  Spread: ${spread:.2f} ({spread_pct:.2f}%)")

        # Get Coinglass data
        print("\nFetching market indicators...")
        coinglass_data = self.coinglass.get_market_summary(symbol)

        # Combine data
        analysis = {
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'prices': prices,
            'coinglass_data': coinglass_data,
            'recommendation': self._generate_recommendation(coinglass_data, prices)
        }

        # Print summary
        self._print_analysis_summary(analysis)

        return analysis

    def _generate_recommendation(self, coinglass_data, prices):
        """Generate trading recommendation based on market data"""
        avg_price = sum(prices.values()) / len(prices) if prices else None

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

        # Best exchange for execution
        if prices:
            best_buy_exchange, best_buy_price = self.get_best_price(list(prices.keys())[0], 'buy')
            best_sell_exchange, best_sell_price = self.get_best_price(list(prices.keys())[0], 'sell')
        else:
            best_buy_exchange = best_sell_exchange = None
            best_buy_price = best_sell_price = None

        return {
            'bias': bias,
            'action': action,
            'confidence': max(bullish_signals, bearish_signals) / len(signals) * 100,
            'support': support_level,
            'resistance': resistance_level,
            'signals': signals,
            'best_exchange_to_buy': best_buy_exchange,
            'best_exchange_to_sell': best_sell_exchange,
            'arbitrage_opportunity': abs(best_buy_price - best_sell_price) if best_buy_price and best_sell_price else 0
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

        if rec['best_exchange_to_buy']:
            print(f"\nBest Exchange:")
            print(f"  To Buy: {rec['best_exchange_to_buy'].upper()}")
            print(f"  To Sell: {rec['best_exchange_to_sell'].upper()}")
            if rec['arbitrage_opportunity'] > 0:
                print(f"  Arbitrage Opportunity: ${rec['arbitrage_opportunity']:.2f}")

        print(f"\nKey Signals:")
        for signal, sentiment in rec['signals'].items():
            print(f"  {signal.replace('_', ' ').title()}: {sentiment}")

        print(f"\n{'='*60}\n")

    def execute_trade(self, symbol, side, amount, exchange='kraken',
                     order_type='market', price=None, stop_loss=None, validate=False):
        """
        Execute trade on specific exchange

        Args:
            symbol: Trading symbol (ETH, BTC)
            side: 'buy' or 'sell'
            amount: Amount to trade
            exchange: 'kraken' or 'coindcx'
            order_type: 'market' or 'limit'
            price: Limit price (for limit orders)
            stop_loss: Stop loss price (optional)
            validate: If True, only validate (don't execute)

        Returns:
            dict: Order result
        """
        exchange = exchange.lower()

        if exchange not in self.exchanges:
            print(f"❌ Exchange '{exchange}' not available")
            return None

        client = self.exchanges[exchange]

        print(f"\n{'='*60}")
        print(f"{'VALIDATING' if validate else 'EXECUTING'} TRADE ON {exchange.upper()}")
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
            result = client.place_market_order(symbol, side, amount, validate=validate)
        elif order_type.lower() == 'limit':
            if not price:
                print("❌ Limit price required for limit orders")
                return None
            result = client.place_limit_order(symbol, side, amount, price, validate=validate)

        # Place stop loss if specified (not for validation)
        if result and stop_loss and not validate:
            print(f"\nPlacing stop-loss order at ${stop_loss:,.2f}...")
            stop_side = 'sell' if side == 'buy' else 'buy'

            if exchange == 'kraken':
                client.place_stop_loss_order(symbol, stop_side, amount, stop_loss)
            elif exchange == 'coindcx':
                # CoinDCX uses stop-limit orders
                client.place_stop_limit_order(symbol, stop_side, amount, stop_loss, stop_loss)

        return result

    def execute_parallel_trade(self, symbol, side, amount_per_exchange,
                              order_type='market', price=None, validate=False):
        """
        Execute trade on all connected exchanges in parallel

        Args:
            symbol: Trading symbol
            side: 'buy' or 'sell'
            amount_per_exchange: Amount to trade on each exchange
            order_type: 'market' or 'limit'
            price: Limit price (for limit orders)
            validate: If True, only validate

        Returns:
            dict: Results by exchange
        """
        print(f"\n{'='*60}")
        print(f"PARALLEL EXECUTION ON {len(self.exchanges)} EXCHANGES")
        print(f"{'='*60}\n")

        results = {}

        for exchange_name in self.exchanges.keys():
            print(f"Executing on {exchange_name.upper()}...")
            result = self.execute_trade(
                symbol, side, amount_per_exchange,
                exchange=exchange_name,
                order_type=order_type,
                price=price,
                validate=validate
            )
            results[exchange_name] = result
            print()

        # Summary
        successful = sum(1 for r in results.values() if r is not None)
        print(f"{'='*60}")
        print(f"Parallel Execution Complete: {successful}/{len(results)} successful")
        print(f"{'='*60}\n")

        return results

    def get_aggregated_balance(self):
        """
        Get aggregated balance across all exchanges

        Returns:
            dict: Balance by exchange and totals
        """
        print(f"\n{'='*60}")
        print("AGGREGATED ACCOUNT BALANCE")
        print(f"{'='*60}\n")

        all_balances = {}
        total_usd = 0

        for exchange_name, client in self.exchanges.items():
            print(f"{exchange_name.upper()} Balance:")
            balance = client.get_account_balance()

            if balance:
                exchange_total = 0

                for asset, data in balance.items():
                    # Handle different balance formats
                    if isinstance(data, dict):
                        amount = data.get('total', data.get('available', 0))
                    else:
                        amount = data

                    if amount > 0:
                        # Try to get USD value
                        usd_value = None
                        if asset in ['USDT', 'USDC', 'USD', 'ZUSD']:
                            usd_value = amount
                        elif asset in ['ETH', 'XETH']:
                            price = client.get_current_price('ETH')
                            if price:
                                usd_value = amount * price
                        elif asset in ['BTC', 'XXBT']:
                            price = client.get_current_price('BTC')
                            if price:
                                usd_value = amount * price

                        if usd_value:
                            print(f"  {asset}: {amount:,.8f} (≈ ${usd_value:,.2f})")
                            exchange_total += usd_value
                        else:
                            print(f"  {asset}: {amount:,.8f}")

                print(f"  Total: ≈ ${exchange_total:,.2f}\n")
                total_usd += exchange_total
                all_balances[exchange_name] = balance

        print(f"{'='*60}")
        print(f"Total Across All Exchanges: ≈ ${total_usd:,.2f}")
        print(f"{'='*60}\n")

        return {
            'by_exchange': all_balances,
            'total_usd_estimate': total_usd
        }

    def get_all_active_orders(self):
        """
        Get active orders from all exchanges

        Returns:
            dict: Active orders by exchange
        """
        print(f"\n{'='*60}")
        print("ACTIVE ORDERS - ALL EXCHANGES")
        print(f"{'='*60}\n")

        all_orders = {}

        for exchange_name, client in self.exchanges.items():
            if hasattr(client, 'get_active_orders'):
                orders = client.get_active_orders()
                all_orders[exchange_name] = orders

                print(f"{exchange_name.upper()}:")
                if orders and len(orders) > 0:
                    print(f"  {len(orders)} active orders")
                else:
                    print(f"  No active orders")

        print(f"\n{'='*60}\n")

        return all_orders


def demo():
    """Demo the multi-exchange interface"""
    print("\n" + "="*60)
    print("MULTI-EXCHANGE TRADING INTERFACE DEMO")
    print("="*60 + "\n")

    # Initialize interface
    interface = MultiExchangeInterface()

    # Get market analysis
    print("\n1. Getting multi-exchange market analysis...")
    analysis = interface.get_market_analysis('ETH')

    # Get aggregated balance
    print("\n2. Getting aggregated account balance...")
    balance = interface.get_aggregated_balance()

    # Get all active orders
    print("\n3. Getting active orders from all exchanges...")
    orders = interface.get_all_active_orders()

    # Validate a trade on best exchange
    print("\n4. Finding best exchange and validating trade...")
    rec = analysis['recommendation']
    best_exchange = rec['best_exchange_to_buy']
    if best_exchange:
        validation = interface.execute_trade(
            symbol='ETH',
            side='buy',
            amount=0.01,
            exchange=best_exchange,
            order_type='market',
            validate=True
        )

    print("\n" + "="*60)
    print("DEMO COMPLETE")
    print("="*60)
    print("\nAvailable Commands:")
    print("  - interface.execute_trade('ETH', 'buy', 0.1, exchange='kraken')")
    print("  - interface.execute_trade('ETH', 'buy', 0.1, exchange='coindcx')")
    print("  - interface.execute_parallel_trade('ETH', 'buy', 0.05)")
    print("="*60 + "\n")


if __name__ == "__main__":
    demo()
