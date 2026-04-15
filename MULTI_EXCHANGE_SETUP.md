# Multi-Exchange Trading Setup Guide

Complete guide to trading on Kraken and CoinDCX with Coinglass market data.

---

## 🎯 Overview

Your trading system now supports:
- **Coinglass** - Advanced market data (liquidations, funding rates, OI)
- **Kraken** - Global exchange for trading
- **CoinDCX** - Indian exchange for trading

---

## 📋 Setup Steps

### 1. Install Dependencies

```bash
cd "/Users/nihal/cursor-projects/Ethereum swing trading"
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure API Credentials

Edit your `.env` file and add your CoinDCX API credentials:

```bash
# CoinDCX API Configuration
COINDCX_API_KEY=your_actual_api_key_here
COINDCX_API_SECRET=your_actual_api_secret_here
```

**How to get CoinDCX API keys:**
1. Login to CoinDCX
2. Go to Settings → API Management
3. Create new API key
4. Enable trading permissions
5. Copy the Key and Secret to `.env`

---

## 🧪 Test Your Setup

### Test Individual Exchanges

**Test Coinglass:**
```bash
python coinglass_client.py
```

**Test Kraken:**
```bash
python kraken_client.py
```

**Test CoinDCX:**
```bash
python coindcx_client.py
```

### Test Multi-Exchange Interface

```bash
python multi_exchange_interface.py
```

---

## 💻 Usage Examples

### Basic Usage - Single Exchange

```python
from kraken_client import KrakenClient
from coindcx_client import CoinDCXClient

# Kraken trading
kraken = KrakenClient()
balance = kraken.get_account_balance()
price = kraken.get_current_price('ETH')

# Market order
kraken.place_market_order('ETH', 'buy', 0.1)

# Limit order
kraken.place_limit_order('ETH', 'buy', 0.1, price=2200)

# With stop-loss
kraken.place_market_order('ETH', 'buy', 0.1)
kraken.place_stop_loss_order('ETH', 'sell', 0.1, stop_price=2100)

# CoinDCX trading (same API)
coindcx = CoinDCXClient()
coindcx.place_market_order('ETH', 'buy', 0.1)
```

### Advanced Usage - Multi-Exchange

```python
from multi_exchange_interface import MultiExchangeInterface

# Initialize with both exchanges
interface = MultiExchangeInterface()

# Get market analysis with prices from all exchanges
analysis = interface.get_market_analysis('ETH')

# Trade on specific exchange
interface.execute_trade(
    symbol='ETH',
    side='buy',
    amount=0.1,
    exchange='kraken',  # or 'coindcx'
    order_type='market'
)

# Execute same trade on all exchanges
interface.execute_parallel_trade(
    symbol='ETH',
    side='buy',
    amount_per_exchange=0.05,
    order_type='market'
)

# Get aggregated balance across all exchanges
balance = interface.get_aggregated_balance()

# Get best price across exchanges
best_exchange, best_price = interface.get_best_price('ETH', side='buy')
print(f"Best price on {best_exchange}: ${best_price}")

# Execute on best exchange
interface.execute_trade('ETH', 'buy', 0.1, exchange=best_exchange)
```

### Market Analysis with Coinglass

```python
from coinglass_client import CoinGlassClient

coinglass = CoinGlassClient()

# Get comprehensive market summary
summary = coinglass.get_market_summary('ETH')

# Individual indicators
liquidations = coinglass.get_liquidation_heatmap('ETH')
ls_ratio = coinglass.get_long_short_ratio('ETH')
open_interest = coinglass.get_open_interest('ETH')
funding_rates = coinglass.get_funding_rates('ETH')

# Key levels
support = liquidations['high_risk_long_level']
resistance = liquidations['high_risk_short_level']
```

---

## 🛡️ Safety Features

### Order Validation

Always validate orders before executing:

```python
# Validate without executing
result = interface.execute_trade(
    'ETH', 'buy', 0.1,
    exchange='kraken',
    validate=True  # Won't execute
)

# Then execute for real
result = interface.execute_trade(
    'ETH', 'buy', 0.1,
    exchange='kraken',
    validate=False  # Will execute
)
```

### Risk Management

```python
# Always use stop-loss orders
interface.execute_trade(
    symbol='ETH',
    side='buy',
    amount=0.1,
    exchange='kraken',
    stop_loss=2100  # Automatic stop-loss
)

# Check order status
kraken = KrakenClient()
orders = kraken.get_open_orders()

# Cancel if needed
kraken.cancel_order(order_id)
kraken.cancel_all_orders()
```

---

## 📊 Available Methods

### CoinGlassClient
- `get_liquidation_heatmap(symbol)` - Liquidation clusters
- `get_long_short_ratio(symbol)` - Long/short sentiment
- `get_open_interest(symbol)` - Total open interest
- `get_funding_rates(symbol)` - Funding rates
- `get_market_summary(symbol)` - Complete analysis

### KrakenClient
- `get_account_balance()` - Account balance
- `get_current_price(symbol)` - Current price
- `place_market_order(symbol, side, amount)` - Market order
- `place_limit_order(symbol, side, amount, price)` - Limit order
- `place_stop_loss_order(symbol, side, amount, stop_price)` - Stop-loss
- `get_open_orders()` - Active orders
- `cancel_order(txid)` - Cancel order
- `cancel_all_orders()` - Cancel all

### CoinDCXClient
- `get_account_balance()` - Account balance
- `get_current_price(symbol)` - Current price
- `get_ticker(symbol)` - Detailed ticker info
- `get_orderbook(symbol)` - Order book
- `place_market_order(symbol, side, quantity)` - Market order
- `place_limit_order(symbol, side, quantity, price)` - Limit order
- `place_stop_limit_order(symbol, side, quantity, stop_price, limit_price)` - Stop-limit
- `get_active_orders()` - Active orders
- `get_order_status(order_id)` - Order status
- `cancel_order(order_id)` - Cancel order
- `cancel_all_orders()` - Cancel all
- `get_trade_history(limit)` - Trade history

### MultiExchangeInterface
- `get_market_analysis(symbol)` - Multi-exchange analysis
- `get_prices(symbol)` - Prices from all exchanges
- `get_best_price(symbol, side)` - Best price across exchanges
- `execute_trade(...)` - Trade on specific exchange
- `execute_parallel_trade(...)` - Trade on all exchanges
- `get_aggregated_balance()` - Total balance across exchanges
- `get_all_active_orders()` - All active orders

---

## ⚠️ Important Notes

### Rate Limits

**Kraken:**
- Public: 15 calls / 3 seconds
- Private: 20 calls / 1 second

**CoinDCX:**
- Orders: 2,000 / 60 seconds
- Cancel All: 30 / 60 seconds

The clients handle rate limiting automatically.

### Supported Trading Pairs

**Kraken:**
- ETHUSD, BTCUSD
- All major pairs

**CoinDCX:**
- ETHUSDT, BTCUSDT
- ETHINR, BTCINR
- Many altcoins

### Order Types

Both exchanges support:
- ✅ Market orders
- ✅ Limit orders
- ✅ Stop-loss orders

### Trading Fees

**Kraken:** 0.16% - 0.26% (volume-based)
**CoinDCX:** 0.04% - 0.10% (volume-based)

---

## 🚀 Next Steps

1. **Test with Small Amounts First**
   - Always validate orders
   - Start with minimum trade sizes
   - Verify everything works

2. **Build Your Strategy**
   - Use Coinglass data for signals
   - Implement entry/exit rules
   - Add risk management

3. **Automate Execution**
   - Connect your strategy to the interface
   - Set up monitoring
   - Add notifications

4. **Monitor Performance**
   - Track trades
   - Calculate P&L
   - Optimize strategy

---

## 📞 Support

- **Kraken API Docs:** https://docs.kraken.com/rest/
- **CoinDCX API Docs:** https://docs.coindcx.com/
- **Coinglass Docs:** https://coinglass.com/

---

## ✅ Checklist

- [ ] Install dependencies (`pip install -r requirements.txt`)
- [ ] Add CoinDCX API credentials to `.env`
- [ ] Test Coinglass connection
- [ ] Test Kraken connection
- [ ] Test CoinDCX connection
- [ ] Run multi-exchange demo
- [ ] Validate test orders
- [ ] Start with small real trades
- [ ] Implement your strategy
- [ ] Set up monitoring

---

**Status:** Your Kraken and Coinglass are already working. Add your CoinDCX credentials to complete the setup!
