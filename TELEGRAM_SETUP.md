# Telegram Trading Bot Setup Guide

Control your trading system via Telegram messages - get recommendations, execute trades, and monitor your portfolio from your phone!

---

## 🎯 Features

✅ **Get market analysis** via Telegram commands  
✅ **Execute trades** with confirmation buttons  
✅ **Check balances** across all exchanges  
✅ **View prices** in real-time  
✅ **Automated recommendations** sent on schedule  
✅ **Secure** - only authorized users can trade  

---

## 📱 Setup Instructions

### Step 1: Create Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` command
3. Choose a name (e.g., "My Trading Bot")
4. Choose a username (e.g., "my_trading_bot")
5. **Copy the API token** you receive (looks like: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### Step 2: Get Your Chat ID

**Option A - Use the bot to find your chat ID:**
1. Start your bot temporarily without authorization
2. Send `/start` to your bot
3. It will reply with your chat ID

**Option B - Use a helper bot:**
1. Search for **@userinfobot** on Telegram
2. Send `/start` and it will show your chat ID

### Step 3: Configure Credentials

Edit your `.env` file and add:

```bash
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=your_chat_id_here
```

Replace with your actual values!

### Step 4: Install Dependencies

```bash
cd "/Users/nihal/cursor-projects/Ethereum swing trading"
source .venv/bin/activate
pip install pyTelegramBotAPI
```

### Step 5: Test Your Bot

```bash
python telegram_trading_bot.py
```

Then send `/start` to your bot on Telegram!

---

## 🤖 Bot Commands

### Market Data

```
/analysis [SYMBOL]     - Full market analysis
/price [SYMBOL]        - Current prices on all exchanges
/ticker [SYMBOL]       - Detailed ticker info
```

**Examples:**
- `/analysis` or `/analysis ETH`
- `/price BTC`

### Account Management

```
/balance              - Check account balance
/orders               - View active orders
/history              - Recent trade history
```

### Trading

```
/buy [AMOUNT] [SYMBOL] [EXCHANGE]    - Buy crypto
/sell [AMOUNT] [SYMBOL] [EXCHANGE]   - Sell crypto
/cancel [ORDER_ID]                   - Cancel order
```

**Examples:**
- `/buy 0.1 ETH` - Buy 0.1 ETH on default exchange (Kraken)
- `/buy 0.1 ETH kraken` - Buy on Kraken
- `/buy 0.1 ETH coindcx` - Buy on CoinDCX
- `/sell 0.05 BTC kraken` - Sell BTC on Kraken

### System

```
/status              - Bot status
/exchanges           - Connected exchanges
/help                - Show all commands
```

---

## 📊 Automated Recommendations

### Option 1: One-Time Analysis

Send recommendation right now:

```bash
python strategy_scheduler.py --once
```

### Option 2: Scheduled Recommendations

Run analysis every hour and send to Telegram:

```bash
# Every hour (3600 seconds)
python strategy_scheduler.py --interval 3600

# Every 30 minutes
python strategy_scheduler.py --interval 1800

# Every 4 hours
python strategy_scheduler.py --interval 14400
```

### Option 3: Multi-Symbol Monitoring

Monitor multiple cryptocurrencies:

```bash
python strategy_scheduler.py --multi ETH BTC --interval 3600
```

### Option 4: Auto-Trading (Advanced)

⚠️ **USE WITH EXTREME CAUTION** - This will automatically execute trades on high-confidence signals!

```bash
# Monitor and auto-trade on 66%+ confidence signals
python strategy_scheduler.py --multi ETH BTC --interval 3600 --auto-trade
```

**Safety Features:**
- Only trades on signals with 66%+ confidence
- Sends alert 30 seconds before execution
- Small amounts only (0.01 ETH / 0.001 BTC)
- You can reply `/cancel` to abort

---

## 🔒 Security Features

### Authorization

Only users with chat IDs in `TELEGRAM_CHAT_ID` can:
- Execute trades
- View balances
- Get market data

### Trade Confirmations

All trades require confirmation via inline buttons:
1. You send `/buy 0.1 ETH`
2. Bot shows summary with ✅ Confirm and ❌ Cancel buttons
3. You click ✅ to execute or ❌ to cancel

### Best Practices

✅ **Do:**
- Keep your bot token secret
- Only add your chat ID to `.env`
- Start with small amounts
- Test with `/buy` commands first

❌ **Don't:**
- Share your bot token publicly
- Enable auto-trade without testing
- Trade more than you can afford to lose

---

## 📱 Usage Examples

### Morning Routine

```telegram
You: /status
Bot: ✅ System Status
     🔗 Connected Exchanges: 2
       • KRAKEN
       • COINDCX

You: /price ETH
Bot: 💵 ETH Prices:
     KRAKEN: $2,198.51
     COINDCX: $2,197.50
     Average: $2,198.00

You: /analysis ETH
Bot: 📊 ETH Market Analysis
     💵 Prices:
       kraken: $2,198.51
       coindcx: $2,197.50
     
     🎯 Recommendation:
       Bias: BULLISH
       Action: BUY
       Confidence: 66%
     
     📍 Key Levels:
       Support: $3,325.00
       Resistance: $3,675.00
```

### Executing a Trade

```telegram
You: /buy 0.1 ETH kraken
Bot: 🔔 Confirm BUY Order
     
     Symbol: ETH
     Amount: 0.1
     Exchange: KRAKEN
     Price: $2,198.51
     Total: $219.85
     
     ⚠️ Confirm to execute
     [✅ Confirm] [❌ Cancel]

You: *click ✅ Confirm*
Bot: ✅ Trade Executed
     
     BUY 0.1 ETH
     Exchange: KRAKEN
     Price: $2,198.51
     Total: $219.85
     
     Order ID: ABCD-1234
```

---

## 🚀 Running as Background Service

### Option 1: Using screen (Simple)

```bash
# Start in background
screen -S trading-bot
python telegram_trading_bot.py

# Detach: Press Ctrl+A, then D

# Reattach later
screen -r trading-bot
```

### Option 2: Using systemd (Production)

Create `/etc/systemd/system/trading-bot.service`:

```ini
[Unit]
Description=Telegram Trading Bot
After=network.target

[Service]
Type=simple
User=nihal
WorkingDirectory=/Users/nihal/cursor-projects/Ethereum swing trading
ExecStart=/Users/nihal/cursor-projects/Ethereum swing trading/.venv/bin/python telegram_trading_bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl enable trading-bot
sudo systemctl start trading-bot
sudo systemctl status trading-bot
```

### Option 3: Using PM2 (Node.js)

```bash
npm install -g pm2
pm2 start telegram_trading_bot.py --interpreter python3
pm2 save
pm2 startup
```

---

## 🔧 Troubleshooting

### Bot not responding

1. Check bot is running: `ps aux | grep telegram`
2. Check credentials in `.env`
3. Make sure you're authorized (correct chat ID)

### "Unauthorized" error

Add your chat ID to `.env`:
```bash
TELEGRAM_CHAT_ID=123456789
```

### Trade not executing

1. Check exchange API credentials
2. Check sufficient balance
3. Check minimum order sizes
4. View logs for errors

### Bot crashes

Check Python dependencies:
```bash
pip install pyTelegramBotAPI --upgrade
```

---

## 📝 Advanced Configuration

### Custom Intervals

Edit `strategy_scheduler.py` to customize:

```python
# Check every 15 minutes
scheduler = StrategyScheduler(interval=900)

# Different intervals for different symbols
symbols_config = {
    'ETH': 1800,  # 30 min
    'BTC': 3600,  # 1 hour
}
```

### Custom Signals

Integrate your own strategy in `strategy_scheduler.py`:

```python
# Import your strategy
from strategy import MyTradingStrategy

# Use it for recommendations
strategy = MyTradingStrategy()
signal = strategy.generate_signal('ETH')

if signal == 'BUY':
    bot.send_recommendation('ETH')
```

---

## 📞 Quick Reference

| Command | Description |
|---------|-------------|
| `/start` | Start bot |
| `/help` | Show commands |
| `/status` | System status |
| `/price ETH` | Get ETH price |
| `/analysis` | Market analysis |
| `/balance` | Check balance |
| `/buy 0.1 ETH` | Buy 0.1 ETH |
| `/sell 0.05 BTC` | Sell 0.05 BTC |
| `/orders` | Active orders |

---

## ✅ Setup Checklist

- [ ] Created bot with @BotFather
- [ ] Got bot token
- [ ] Got your chat ID
- [ ] Added credentials to `.env`
- [ ] Installed `pyTelegramBotAPI`
- [ ] Tested bot with `/start`
- [ ] Tested `/price` command
- [ ] Tested `/analysis` command
- [ ] Tested `/balance` command
- [ ] Tested `/buy` with validation
- [ ] Set up scheduled recommendations
- [ ] (Optional) Configured as background service

---

## 🎉 You're Ready!

Your Telegram trading bot is now set up! You can:

1. **Get recommendations** automatically via Telegram
2. **Execute trades** from your phone
3. **Monitor markets** 24/7
4. **Check balances** anytime

Start the bot and send `/help` to begin trading! 🚀

---

## ⚠️ Important Notes

1. **Test First**: Always test with small amounts
2. **Never Share**: Keep your bot token private
3. **Secure Your Phone**: Use 2FA on Telegram
4. **Monitor Actively**: Check bot logs regularly
5. **Risk Management**: Never invest more than you can afford to lose

---

**Happy Trading!** 📈🚀
