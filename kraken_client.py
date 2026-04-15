"""
Kraken Trading Client - Execute trades and manage positions
Handles order placement, position tracking, and account management
"""
import krakenex
from pykrakenapi import KrakenAPI
import pandas as pd
import time
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class KrakenClient:
    """
    Kraken Exchange Client for trade execution

    Features:
    - Place market and limit orders
    - Check account balance
    - Get open orders and positions
    - Cancel orders
    - Risk management
    """

    def __init__(self, api_key=None, api_secret=None):
        """
        Initialize Kraken client

        Args:
            api_key: Kraken API key (if None, loads from env)
            api_secret: Kraken API secret (if None, loads from env)
        """
        # Get credentials from environment if not provided
        if api_key is None:
            api_key = os.getenv('KRAKEN_API_KEY')
        if api_secret is None:
            api_secret = os.getenv('KRAKEN_API_SECRET')

        if not api_key or not api_secret:
            raise ValueError("Kraken API credentials not found. Set KRAKEN_API_KEY and KRAKEN_API_SECRET in .env")

        # Initialize Kraken API
        self.kraken = krakenex.API(key=api_key, secret=api_secret)
        self.api = KrakenAPI(self.kraken)

        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.5  # 500ms between requests

        # Trading pairs mapping
        self.pairs_map = {
            'ETH': 'XETHZUSD',
            'BTC': 'XXBTZUSD',
            'ETHUSD': 'XETHZUSD',
            'BTCUSD': 'XXBTZUSD'
        }

    def _rate_limit(self):
        """Ensure we don't exceed rate limits"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def _get_pair(self, symbol):
        """Convert symbol to Kraken pair format"""
        return self.pairs_map.get(symbol.upper(), f'X{symbol}ZUSD')

    def get_account_balance(self):
        """
        Get account balance for all assets

        Returns:
            dict: Balance by asset
        """
        try:
            self._rate_limit()

            # Use the raw API call instead of pykrakenapi wrapper
            response = self.kraken.query_private('Balance')

            if response.get('error'):
                print(f"Balance error: {response['error']}")
                return {}

            balance = response.get('result', {})

            # Convert to simple dict with positive balances only
            balance_dict = {}
            for asset, amount in balance.items():
                amount_float = float(amount)
                if amount_float > 0:
                    balance_dict[asset] = amount_float

            return balance_dict

        except Exception as e:
            print(f"Error getting balance: {e}")
            return {}

    def get_current_price(self, symbol='ETH'):
        """
        Get current market price

        Args:
            symbol: Trading symbol (ETH, BTC, etc.)

        Returns:
            float: Current price
        """
        try:
            self._rate_limit()
            pair = self._get_pair(symbol)

            # Use raw API call for better compatibility
            response = self.kraken.query_public('Ticker', {'pair': pair})

            if response.get('error'):
                print(f"Price error: {response['error']}")
                return None

            result = response.get('result', {})
            ticker_data = result.get(pair, {})

            # Get last price (c = last trade closed array)
            last_trade = ticker_data.get('c', [None, None])
            price = float(last_trade[0]) if last_trade[0] else None

            return price

        except Exception as e:
            print(f"Error getting price: {e}")
            return None

    def place_market_order(self, symbol, side, amount, validate=False):
        """
        Place a market order

        Args:
            symbol: Trading symbol (ETH, BTC)
            side: 'buy' or 'sell'
            amount: Amount to trade (in base currency)
            validate: If True, only validate order (don't execute)

        Returns:
            dict: Order details or None if failed
        """
        try:
            self._rate_limit()
            pair = self._get_pair(symbol)

            # Build order parameters
            order_params = {
                'pair': pair,
                'type': side.lower(),
                'ordertype': 'market',
                'volume': str(amount)
            }

            if validate:
                order_params['validate'] = True

            # Place order
            response = self.kraken.query_private('AddOrder', order_params)

            if response.get('error'):
                print(f"Order error: {response['error']}")
                return None

            result = response.get('result', {})

            if validate:
                print(f"✓ Order validation successful")
                return {'validated': True, 'description': result.get('descr', {})}
            else:
                print(f"✓ Market order placed: {side.upper()} {amount} {symbol}")
                return {
                    'txid': result.get('txid', []),
                    'description': result.get('descr', {}),
                    'timestamp': datetime.now()
                }

        except Exception as e:
            print(f"Error placing market order: {e}")
            return None

    def place_limit_order(self, symbol, side, amount, price, validate=False):
        """
        Place a limit order

        Args:
            symbol: Trading symbol
            side: 'buy' or 'sell'
            amount: Amount to trade
            price: Limit price
            validate: If True, only validate order

        Returns:
            dict: Order details or None if failed
        """
        try:
            self._rate_limit()
            pair = self._get_pair(symbol)

            order_params = {
                'pair': pair,
                'type': side.lower(),
                'ordertype': 'limit',
                'volume': str(amount),
                'price': str(price)
            }

            if validate:
                order_params['validate'] = True

            response = self.kraken.query_private('AddOrder', order_params)

            if response.get('error'):
                print(f"Order error: {response['error']}")
                return None

            result = response.get('result', {})

            if validate:
                print(f"✓ Limit order validation successful")
                return {'validated': True, 'description': result.get('descr', {})}
            else:
                print(f"✓ Limit order placed: {side.upper()} {amount} {symbol} @ ${price}")
                return {
                    'txid': result.get('txid', []),
                    'description': result.get('descr', {}),
                    'timestamp': datetime.now()
                }

        except Exception as e:
            print(f"Error placing limit order: {e}")
            return None

    def place_stop_loss_order(self, symbol, side, amount, stop_price, limit_price=None):
        """
        Place a stop-loss order

        Args:
            symbol: Trading symbol
            side: 'buy' or 'sell'
            amount: Amount to trade
            stop_price: Stop trigger price
            limit_price: Optional limit price (if None, uses market order)

        Returns:
            dict: Order details or None if failed
        """
        try:
            self._rate_limit()
            pair = self._get_pair(symbol)

            order_params = {
                'pair': pair,
                'type': side.lower(),
                'ordertype': 'stop-loss-limit' if limit_price else 'stop-loss',
                'volume': str(amount),
                'price': str(stop_price)
            }

            if limit_price:
                order_params['price2'] = str(limit_price)

            response = self.kraken.query_private('AddOrder', order_params)

            if response.get('error'):
                print(f"Stop-loss order error: {response['error']}")
                return None

            result = response.get('result', {})
            print(f"✓ Stop-loss order placed: {side.upper()} {amount} {symbol} @ ${stop_price}")

            return {
                'txid': result.get('txid', []),
                'description': result.get('descr', {}),
                'timestamp': datetime.now()
            }

        except Exception as e:
            print(f"Error placing stop-loss order: {e}")
            return None

    def get_open_orders(self):
        """
        Get all open orders

        Returns:
            DataFrame: Open orders
        """
        try:
            self._rate_limit()
            orders = self.api.get_open_orders()
            return orders

        except Exception as e:
            print(f"Error getting open orders: {e}")
            return pd.DataFrame()

    def cancel_order(self, txid):
        """
        Cancel an open order

        Args:
            txid: Transaction ID of the order to cancel

        Returns:
            bool: True if successful
        """
        try:
            self._rate_limit()
            response = self.kraken.query_private('CancelOrder', {'txid': txid})

            if response.get('error'):
                print(f"Cancel order error: {response['error']}")
                return False

            print(f"✓ Order {txid} cancelled")
            return True

        except Exception as e:
            print(f"Error cancelling order: {e}")
            return False

    def cancel_all_orders(self):
        """
        Cancel all open orders

        Returns:
            int: Number of orders cancelled
        """
        try:
            orders = self.get_open_orders()
            count = 0

            for txid in orders.index:
                if self.cancel_order(txid):
                    count += 1

            return count

        except Exception as e:
            print(f"Error cancelling all orders: {e}")
            return 0

    def get_closed_orders(self, start=None):
        """
        Get closed orders history

        Args:
            start: Start timestamp (optional)

        Returns:
            DataFrame: Closed orders
        """
        try:
            self._rate_limit()
            orders = self.api.get_closed_orders(start=start)
            return orders

        except Exception as e:
            print(f"Error getting closed orders: {e}")
            return pd.DataFrame()

    def get_trade_history(self, start=None):
        """
        Get trade history

        Args:
            start: Start timestamp (optional)

        Returns:
            DataFrame: Trade history
        """
        try:
            self._rate_limit()
            trades = self.api.get_trades_history(start=start)
            return trades

        except Exception as e:
            print(f"Error getting trade history: {e}")
            return pd.DataFrame()


def test_kraken_client():
    """Test Kraken client functionality"""
    print("\n" + "="*60)
    print("TESTING KRAKEN CLIENT")
    print("="*60 + "\n")

    try:
        # Initialize client
        client = KrakenClient()
        print("✓ Kraken client initialized")

        # Test 1: Get account balance
        print("\n1. Account Balance:")
        balance = client.get_account_balance()
        if balance:
            for asset, amount in balance.items():
                print(f"   {asset}: {amount:,.8f}")
        else:
            print("   No balance found or API error")

        # Test 2: Get current ETH price
        print("\n2. Current Prices:")
        eth_price = client.get_current_price('ETH')
        if eth_price:
            print(f"   ETH: ${eth_price:,.2f}")

        btc_price = client.get_current_price('BTC')
        if btc_price:
            print(f"   BTC: ${btc_price:,.2f}")

        # Test 3: Get open orders
        print("\n3. Open Orders:")
        open_orders = client.get_open_orders()
        if not open_orders.empty:
            print(f"   Found {len(open_orders)} open orders")
            print(open_orders)
        else:
            print("   No open orders")

        # Test 4: Validate a market order (won't execute)
        print("\n4. Order Validation Test:")
        validation = client.place_market_order('ETH', 'buy', 0.01, validate=True)
        if validation:
            print(f"   Order would execute: {validation.get('description', {})}")

        print("\n" + "="*60)
        print("KRAKEN CLIENT TEST COMPLETE")
        print("="*60 + "\n")

        return True

    except Exception as e:
        print(f"\n❌ Kraken client test failed: {e}")
        print("\nPlease verify your API credentials in .env file")
        return False


if __name__ == "__main__":
    test_kraken_client()
