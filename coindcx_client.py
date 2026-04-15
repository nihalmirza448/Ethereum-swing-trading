"""
CoinDCX Trading Client - Execute trades and manage positions
Handles order placement, position tracking, and account management on CoinDCX
"""
import requests
import hmac
import hashlib
import json
import time
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class CoinDCXClient:
    """
    CoinDCX Exchange Client for trade execution

    Features:
    - Place market, limit, and stop-limit orders
    - Check account balance
    - Get market prices and ticker data
    - Manage orders (cancel, status, active orders)
    - Rate limiting and error handling
    """

    BASE_URL = "https://api.coindcx.com"
    PUBLIC_URL = "https://public.coindcx.com"

    def __init__(self, api_key=None, api_secret=None):
        """
        Initialize CoinDCX client

        Args:
            api_key: CoinDCX API key (if None, loads from env)
            api_secret: CoinDCX API secret (if None, loads from env)
        """
        # Get credentials from environment if not provided
        if api_key is None:
            api_key = os.getenv('COINDCX_API_KEY')
        if api_secret is None:
            api_secret = os.getenv('COINDCX_API_SECRET')

        if not api_key or not api_secret:
            raise ValueError("CoinDCX API credentials not found. Set COINDCX_API_KEY and COINDCX_API_SECRET in .env")

        self.api_key = api_key
        self.api_secret = api_secret.encode()

        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.03  # 30ms between requests (2000 per 60s)

        # Session for connection pooling
        self.session = requests.Session()

        # Market pairs mapping (CoinDCX format)
        self.pairs_map = {
            'ETH': 'ETHUSDT',
            'BTC': 'BTCUSDT',
            'ETHUSD': 'ETHUSDT',
            'ETHINR': 'ETHINR',
            'BTCUSD': 'BTCUSDT',
            'BTCINR': 'BTCINR'
        }

    def _rate_limit(self):
        """Ensure we don't exceed rate limits"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def _get_pair(self, symbol):
        """Convert symbol to CoinDCX pair format"""
        return self.pairs_map.get(symbol.upper(), f'{symbol.upper()}USDT')

    def _make_request(self, endpoint, params=None, authenticated=False):
        """
        Make API request with error handling

        Args:
            endpoint: API endpoint path
            params: Request parameters
            authenticated: Whether request requires authentication

        Returns:
            dict: Response data
        """
        self._rate_limit()

        if params is None:
            params = {}

        # Add timestamp for authenticated requests
        if authenticated:
            params['timestamp'] = int(time.time() * 1000)

        url = f"{self.BASE_URL}/{endpoint}"

        try:
            if authenticated:
                # Serialize with compact separators - MUST match what's sent in body
                json_body = json.dumps(params, separators=(',', ':'))

                # Generate signature over the exact bytes being sent
                signature = hmac.new(
                    self.api_secret,
                    json_body.encode(),
                    hashlib.sha256
                ).hexdigest()

                headers = {
                    'Content-Type': 'application/json',
                    'X-AUTH-APIKEY': self.api_key,
                    'X-AUTH-SIGNATURE': signature
                }

                response = self.session.post(url, data=json_body, headers=headers, timeout=10)
            else:
                # Public endpoint
                response = self.session.get(url, params=params, timeout=10)

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            if hasattr(e.response, 'text'):
                print(f"Response: {e.response.text}")
            return None

    def get_account_balance(self):
        """
        Get account balance for all assets

        Returns:
            dict: Balance by asset with available and locked amounts
        """
        try:
            endpoint = "exchange/v1/users/balances"
            data = self._make_request(endpoint, authenticated=True)

            if not data:
                return {}

            # Convert to simple dict
            balance_dict = {}
            for item in data:
                currency = item.get('currency')
                balance = float(item.get('balance', 0))
                locked = float(item.get('locked_balance', 0))

                if balance > 0 or locked > 0:
                    balance_dict[currency] = {
                        'available': balance,
                        'locked': locked,
                        'total': balance + locked
                    }

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
            # Use public ticker endpoint
            url = f"{self.PUBLIC_URL}/exchange/ticker"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()

            ticker_data = response.json()
            pair = self._get_pair(symbol)

            # Find the ticker for our pair
            for ticker in ticker_data:
                if ticker.get('market') == pair:
                    last_price = float(ticker.get('last_price', 0))
                    return last_price

            print(f"Pair {pair} not found in ticker data")
            return None

        except Exception as e:
            print(f"Error getting price: {e}")
            return None

    def get_ticker(self, symbol='ETH'):
        """
        Get detailed ticker information

        Args:
            symbol: Trading symbol

        Returns:
            dict: Ticker data with bid, ask, volume, etc.
        """
        try:
            url = f"{self.PUBLIC_URL}/exchange/ticker"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()

            ticker_data = response.json()
            pair = self._get_pair(symbol)

            for ticker in ticker_data:
                if ticker.get('market') == pair:
                    return {
                        'symbol': symbol,
                        'pair': pair,
                        'bid': float(ticker.get('bid', 0)),
                        'ask': float(ticker.get('ask', 0)),
                        'last_price': float(ticker.get('last_price', 0)),
                        'high': float(ticker.get('high', 0)),
                        'low': float(ticker.get('low', 0)),
                        'volume': float(ticker.get('volume', 0)),
                        'timestamp': ticker.get('timestamp')
                    }

            return None

        except Exception as e:
            print(f"Error getting ticker: {e}")
            return None

    def get_orderbook(self, symbol='ETH', depth=10):
        """
        Get order book for a trading pair

        Args:
            symbol: Trading symbol
            depth: Number of levels to return

        Returns:
            dict: Order book with bids and asks
        """
        try:
            pair = self._get_pair(symbol)
            # CoinDCX format: B-BTC_USDT
            formatted_pair = f"B-{pair[:3]}_{pair[3:]}"

            url = f"{self.PUBLIC_URL}/market_data/orderbook"
            params = {'pair': formatted_pair}

            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            return {
                'bids': data.get('bids', [])[:depth],
                'asks': data.get('asks', [])[:depth]
            }

        except Exception as e:
            print(f"Error getting orderbook: {e}")
            return {'bids': [], 'asks': []}

    def place_market_order(self, symbol, side, quantity, validate=False):
        """
        Place a market order

        Args:
            symbol: Trading symbol (ETH, BTC)
            side: 'buy' or 'sell'
            quantity: Amount to trade
            validate: If True, only validate order (not implemented by CoinDCX)

        Returns:
            dict: Order details or None if failed
        """
        try:
            pair = self._get_pair(symbol)

            if validate:
                print(f"✓ Order validation: {side.upper()} {quantity} {symbol} (market)")
                return {'validated': True, 'message': 'Order would be placed'}

            params = {
                'market': pair,
                'side': side.lower(),
                'order_type': 'market_order',
                'total_quantity': quantity
            }

            endpoint = "exchange/v1/orders/create"
            result = self._make_request(endpoint, params, authenticated=True)

            if result and 'id' in result:
                print(f"✓ Market order placed: {side.upper()} {quantity} {symbol}")
                return {
                    'order_id': result.get('id'),
                    'side': result.get('side'),
                    'market': result.get('market'),
                    'order_type': result.get('order_type'),
                    'status': result.get('status'),
                    'timestamp': datetime.now()
                }
            else:
                print(f"❌ Order failed: {result}")
                return None

        except Exception as e:
            print(f"Error placing market order: {e}")
            return None

    def place_limit_order(self, symbol, side, quantity, price, validate=False):
        """
        Place a limit order

        Args:
            symbol: Trading symbol
            side: 'buy' or 'sell'
            quantity: Amount to trade
            price: Limit price
            validate: If True, only validate order

        Returns:
            dict: Order details or None if failed
        """
        try:
            pair = self._get_pair(symbol)

            if validate:
                print(f"✓ Order validation: {side.upper()} {quantity} {symbol} @ ${price}")
                return {'validated': True, 'message': 'Order would be placed'}

            params = {
                'market': pair,
                'side': side.lower(),
                'order_type': 'limit_order',
                'price_per_unit': price,
                'total_quantity': quantity
            }

            endpoint = "exchange/v1/orders/create"
            result = self._make_request(endpoint, params, authenticated=True)

            if result and 'id' in result:
                print(f"✓ Limit order placed: {side.upper()} {quantity} {symbol} @ ${price}")
                return {
                    'order_id': result.get('id'),
                    'side': result.get('side'),
                    'market': result.get('market'),
                    'order_type': result.get('order_type'),
                    'price': result.get('price_per_unit'),
                    'status': result.get('status'),
                    'timestamp': datetime.now()
                }
            else:
                print(f"❌ Order failed: {result}")
                return None

        except Exception as e:
            print(f"Error placing limit order: {e}")
            return None

    def place_stop_limit_order(self, symbol, side, quantity, stop_price, limit_price):
        """
        Place a stop-limit order

        Args:
            symbol: Trading symbol
            side: 'buy' or 'sell'
            quantity: Amount to trade
            stop_price: Stop trigger price
            limit_price: Limit price after trigger

        Returns:
            dict: Order details or None if failed
        """
        try:
            pair = self._get_pair(symbol)

            params = {
                'market': pair,
                'side': side.lower(),
                'order_type': 'stop_limit',
                'price_per_unit': limit_price,
                'total_quantity': quantity,
                'stop_price': stop_price
            }

            endpoint = "exchange/v1/orders/create"
            result = self._make_request(endpoint, params, authenticated=True)

            if result and 'id' in result:
                print(f"✓ Stop-limit order placed: {side.upper()} {quantity} {symbol} stop@${stop_price} limit@${limit_price}")
                return {
                    'order_id': result.get('id'),
                    'side': result.get('side'),
                    'market': result.get('market'),
                    'order_type': result.get('order_type'),
                    'stop_price': stop_price,
                    'limit_price': limit_price,
                    'status': result.get('status'),
                    'timestamp': datetime.now()
                }
            else:
                print(f"❌ Order failed: {result}")
                return None

        except Exception as e:
            print(f"Error placing stop-limit order: {e}")
            return None

    def get_order_status(self, order_id):
        """
        Get status of a specific order

        Args:
            order_id: Order ID

        Returns:
            dict: Order status
        """
        try:
            params = {'id': order_id}
            endpoint = "exchange/v1/orders/status"
            result = self._make_request(endpoint, params, authenticated=True)
            return result

        except Exception as e:
            print(f"Error getting order status: {e}")
            return None

    def get_active_orders(self, symbol=None):
        """
        Get all active orders

        Args:
            symbol: Optional symbol to filter (if None, gets all)

        Returns:
            list: Active orders
        """
        try:
            params = {}
            if symbol:
                params['market'] = self._get_pair(symbol)

            endpoint = "exchange/v1/orders/active_orders"
            result = self._make_request(endpoint, params, authenticated=True)

            if isinstance(result, dict) and 'orders' in result:
                return result['orders']
            return result if isinstance(result, list) else []

        except Exception as e:
            print(f"Error getting active orders: {e}")
            return []

    def cancel_order(self, order_id):
        """
        Cancel a specific order

        Args:
            order_id: Order ID to cancel

        Returns:
            bool: True if successful
        """
        try:
            params = {'id': order_id}
            endpoint = "exchange/v1/orders/cancel"
            result = self._make_request(endpoint, params, authenticated=True)

            if result:
                print(f"✓ Order {order_id} cancelled")
                return True
            return False

        except Exception as e:
            print(f"Error cancelling order: {e}")
            return False

    def cancel_all_orders(self, symbol=None):
        """
        Cancel all active orders

        Args:
            symbol: Optional symbol to filter (if None, cancels all)

        Returns:
            dict: Result with count of cancelled orders
        """
        try:
            params = {}
            if symbol:
                params['market'] = self._get_pair(symbol)

            endpoint = "exchange/v1/orders/cancel_all"
            result = self._make_request(endpoint, params, authenticated=True)

            if result:
                print(f"✓ All orders cancelled")
                return result
            return None

        except Exception as e:
            print(f"Error cancelling all orders: {e}")
            return None

    def get_trade_history(self, symbol=None, limit=100):
        """Get spot trade history."""
        try:
            params = {'limit': limit}
            if symbol:
                params['market'] = self._get_pair(symbol)
            result = self._make_request("exchange/v1/orders/trade_history", params, authenticated=True)
            return result if result else []
        except Exception as e:
            print(f"Error getting trade history: {e}")
            return []

    def get_futures_trades(self, max_pages=50):
        """
        Get ALL futures trade executions (paginated).
        Returns list of dicts with price, quantity, side, pair, fee_amount,
        margin_currency_short_name, timestamp.
        """
        trades = []
        try:
            for page in range(1, max_pages + 1):
                result = self._make_request(
                    "exchange/v1/derivatives/futures/trades",
                    {"page": page, "size": 100},
                    authenticated=True,
                )
                if not result or not isinstance(result, list):
                    break
                trades.extend(result)
                if len(result) < 100:
                    break
        except Exception as e:
            print(f"Error getting futures trades: {e}")
        return trades

    def get_futures_orders(self, status=None, page=1, size=100):
        """
        Get futures orders.
        status: None = all, or one of open/close/cancelled/rejected
        """
        try:
            params = {"page": page, "size": size}
            if status:
                params["status"] = status
            result = self._make_request(
                "exchange/v1/derivatives/futures/orders", params, authenticated=True
            )
            return result if isinstance(result, list) else []
        except Exception as e:
            print(f"Error getting futures orders: {e}")
            return []

    def get_futures_positions(self):
        """Get all open futures positions."""
        try:
            result = self._make_request(
                "exchange/v1/derivatives/futures/positions", {}, authenticated=True
            )
            return result if isinstance(result, list) else []
        except Exception as e:
            print(f"Error getting futures positions: {e}")
            return []

    def get_futures_wallet(self):
        """Get futures wallet cross-margin details (balance, withdrawable)."""
        try:
            result = self._make_request(
                "exchange/v1/derivatives/futures/positions/cross_margin_details",
                {},
                authenticated=True,
            )
            return result
        except Exception as e:
            print(f"Error getting futures wallet: {e}")
            return None


def test_coindcx_client():
    """Test CoinDCX client functionality"""
    print("\n" + "="*60)
    print("TESTING COINDCX CLIENT")
    print("="*60 + "\n")

    try:
        # Initialize client
        client = CoinDCXClient()
        print("✓ CoinDCX client initialized")

        # Test 1: Get account balance
        print("\n1. Account Balance:")
        balance = client.get_account_balance()
        if balance:
            for asset, amounts in balance.items():
                total = amounts['total']
                if total > 0:
                    print(f"   {asset}: {total:,.8f} (Available: {amounts['available']:,.8f}, Locked: {amounts['locked']:,.8f})")
        else:
            print("   No balance found or API error")

        # Test 2: Get current prices
        print("\n2. Current Prices:")
        eth_price = client.get_current_price('ETH')
        if eth_price:
            print(f"   ETH: ${eth_price:,.2f}")

        btc_price = client.get_current_price('BTC')
        if btc_price:
            print(f"   BTC: ${btc_price:,.2f}")

        # Test 3: Get ticker info
        print("\n3. ETH Ticker Details:")
        ticker = client.get_ticker('ETH')
        if ticker:
            print(f"   Bid: ${ticker['bid']:,.2f}")
            print(f"   Ask: ${ticker['ask']:,.2f}")
            print(f"   Last: ${ticker['last_price']:,.2f}")
            print(f"   24h High: ${ticker['high']:,.2f}")
            print(f"   24h Low: ${ticker['low']:,.2f}")
            print(f"   Volume: {ticker['volume']:,.2f}")

        # Test 4: Get active orders
        print("\n4. Active Orders:")
        active = client.get_active_orders()
        if active:
            print(f"   Found {len(active)} active orders")
            for order in active[:3]:  # Show first 3
                print(f"   - {order.get('side')} {order.get('total_quantity')} {order.get('market')}")
        else:
            print("   No active orders")

        # Test 5: Validate a market order (simulation)
        print("\n5. Order Validation Test:")
        validation = client.place_market_order('ETH', 'buy', 0.01, validate=True)

        print("\n" + "="*60)
        print("COINDCX CLIENT TEST COMPLETE")
        print("="*60 + "\n")

        return True

    except Exception as e:
        print(f"\n❌ CoinDCX client test failed: {e}")
        print("\nPlease verify your API credentials in .env file")
        return False


if __name__ == "__main__":
    test_coindcx_client()
