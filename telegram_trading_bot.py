#!/usr/bin/env python3
"""
Telegram Trading Bot - Control your trading system via Telegram

Features:
- Get market analysis and recommendations
- Execute trades via chat commands
- Check account balance
- View prices across exchanges
- Risk management with confirmations

Setup:
1. Create bot with @BotFather on Telegram
2. Get bot token and add to .env
3. Get your chat ID and add to .env
4. Run: python telegram_trading_bot.py
"""

import os
import time
import json
from datetime import datetime
from threading import Thread
from dotenv import load_dotenv

# Import trading clients
from multi_exchange_interface import MultiExchangeInterface
from coinglass_client import CoinGlassClient

# Load environment
load_dotenv()

try:
    import telebot
    from telebot import types
except ImportError:
    print("Installing pyTelegramBotAPI...")
    os.system("pip install pyTelegramBotAPI -q")
    import telebot
    from telebot import types


class TelegramTradingBot:
    """
    Telegram bot for trading automation

    Commands:
    /start - Welcome message
    /help - Show all commands
    /analysis - Get market analysis
    /price - Get current prices
    /balance - Check account balance
    /buy - Buy crypto
    /sell - Sell crypto
    /orders - View active orders
    /status - System status
    """

    def __init__(self, bot_token=None, authorized_chat_ids=None):
        """
        Initialize Telegram trading bot

        Args:
            bot_token: Telegram bot token (from @BotFather)
            authorized_chat_ids: List of authorized chat IDs (for security)
        """
        # Get credentials
        if bot_token is None:
            bot_token = os.getenv('TELEGRAM_BOT_TOKEN')

        if not bot_token or bot_token == 'your_telegram_bot_token':
            raise ValueError(
                "Telegram bot token not configured.\n"
                "1. Message @BotFather on Telegram\n"
                "2. Create new bot with /newbot\n"
                "3. Copy token to TELEGRAM_BOT_TOKEN in .env"
            )

        # Initialize bot
        self.bot = telebot.TeleBot(bot_token, parse_mode='HTML')

        # Authorized users
        if authorized_chat_ids is None:
            chat_id = os.getenv('TELEGRAM_CHAT_ID')
            if chat_id and chat_id != 'your_telegram_chat_id':
                self.authorized_chat_ids = [int(chat_id)]
            else:
                self.authorized_chat_ids = []  # Allow all initially
        else:
            self.authorized_chat_ids = authorized_chat_ids

        # Initialize trading interface
        print("Initializing trading interface...")
        self.trading = MultiExchangeInterface()

        # Pending confirmations
        self.pending_trades = {}

        # Register handlers
        self._register_handlers()

        print(f"✓ Telegram bot initialized")
        if self.authorized_chat_ids:
            print(f"✓ Authorized for {len(self.authorized_chat_ids)} user(s)")
        else:
            print("⚠ WARNING: No authorized users set - anyone can use this bot!")
            print("  Add TELEGRAM_CHAT_ID to .env for security")

    def _is_authorized(self, chat_id):
        """Check if user is authorized"""
        if not self.authorized_chat_ids:
            return True  # No restrictions if not configured
        return chat_id in self.authorized_chat_ids

    def _require_auth(self, func):
        """Decorator to require authorization"""
        def wrapper(message):
            if not self._is_authorized(message.chat.id):
                self.bot.reply_to(
                    message,
                    "❌ Unauthorized. Contact the bot owner to get access."
                )
                return
            return func(message)
        return wrapper

    def _register_handlers(self):
        """Register all command handlers"""

        @self.bot.message_handler(commands=['start'])
        def start(message):
            if not self._is_authorized(message.chat.id):
                self.bot.reply_to(
                    message,
                    f"👋 Hello!\n\n"
                    f"Your chat ID is: <code>{message.chat.id}</code>\n\n"
                    f"Add this to TELEGRAM_CHAT_ID in .env to authorize yourself."
                )
                return

            self.bot.reply_to(
                message,
                "🤖 <b>Trading Bot Active</b>\n\n"
                "I can help you trade crypto across multiple exchanges.\n\n"
                "Use /help to see available commands."
            )

        @self.bot.message_handler(commands=['help'])
        @self._require_auth
        def help_command(message):
            help_text = """
🤖 <b>Trading Bot Commands</b>

📊 <b>Market Data:</b>
/analysis - Full market analysis
/price [SYMBOL] - Get current prices
/ticker [SYMBOL] - Detailed ticker info

💰 <b>Account:</b>
/balance - Check account balance
/orders - View active orders
/history - Recent trades

🔄 <b>Trading:</b>
/buy [AMOUNT] [SYMBOL] - Buy crypto
/sell [AMOUNT] [SYMBOL] - Sell crypto
/cancel [ORDER_ID] - Cancel order

⚙️ <b>System:</b>
/status - Bot status
/exchanges - Connected exchanges
/help - Show this message

<b>Examples:</b>
• /price ETH
• /buy 0.1 ETH
• /sell 0.05 BTC
• /analysis ETH
"""
            self.bot.reply_to(message, help_text)

        @self.bot.message_handler(commands=['status'])
        @self._require_auth
        def status(message):
            exchanges = list(self.trading.exchanges.keys())
            status_text = (
                f"✅ <b>System Status</b>\n\n"
                f"🔗 Connected Exchanges: {len(exchanges)}\n"
                f"{'  • ' + chr(10) + '  • '.join(e.upper() for e in exchanges)}\n\n"
                f"📡 Coinglass: Active\n"
                f"🤖 Bot: Running\n"
                f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            self.bot.reply_to(message, status_text)

        @self.bot.message_handler(commands=['exchanges'])
        @self._require_auth
        def exchanges(message):
            text = "🏦 <b>Connected Exchanges:</b>\n\n"
            for exchange_name in self.trading.exchanges.keys():
                text += f"✅ {exchange_name.upper()}\n"
            self.bot.reply_to(message, text)

        @self.bot.message_handler(commands=['price'])
        @self._require_auth
        def price(message):
            args = message.text.split()
            symbol = args[1].upper() if len(args) > 1 else 'ETH'

            try:
                prices = self.trading.get_prices(symbol)

                if not prices:
                    self.bot.reply_to(message, f"❌ Could not get price for {symbol}")
                    return

                text = f"💵 <b>{symbol} Prices:</b>\n\n"
                for exchange, price in prices.items():
                    text += f"{exchange.upper()}: ${price:,.2f}\n"

                if len(prices) > 1:
                    avg = sum(prices.values()) / len(prices)
                    text += f"\nAverage: ${avg:,.2f}"

                self.bot.reply_to(message, text)

            except Exception as e:
                self.bot.reply_to(message, f"❌ Error: {str(e)}")

        @self.bot.message_handler(commands=['analysis'])
        @self._require_auth
        def analysis(message):
            args = message.text.split()
            symbol = args[1].upper() if len(args) > 1 else 'ETH'

            self.bot.reply_to(message, f"🔍 Analyzing {symbol}... Please wait.")

            try:
                analysis = self.trading.get_market_analysis(symbol)
                rec = analysis['recommendation']

                text = f"📊 <b>{symbol} Market Analysis</b>\n\n"

                # Prices
                text += "💵 <b>Prices:</b>\n"
                for exchange, price in analysis['prices'].items():
                    text += f"  {exchange.upper()}: ${price:,.2f}\n"

                # Recommendation
                text += f"\n🎯 <b>Recommendation:</b>\n"
                text += f"  Bias: {rec['bias']}\n"
                text += f"  Action: <b>{rec['action']}</b>\n"
                text += f"  Confidence: {rec['confidence']:.0f}%\n"

                # Levels
                text += f"\n📍 <b>Key Levels:</b>\n"
                text += f"  Support: ${rec['support']:,.2f}\n"
                text += f"  Resistance: ${rec['resistance']:,.2f}\n"

                # Best exchange
                if rec.get('best_exchange_to_buy'):
                    text += f"\n🏦 <b>Best Exchange:</b>\n"
                    text += f"  Buy on: {rec['best_exchange_to_buy'].upper()}\n"
                    text += f"  Sell on: {rec['best_exchange_to_sell'].upper()}\n"

                # Signals
                text += f"\n📡 <b>Signals:</b>\n"
                for signal, sentiment in rec['signals'].items():
                    emoji = "🟢" if sentiment in ["BULLISH", "INCREASING"] else "🔴" if sentiment in ["BEARISH", "DECREASING"] else "🟡"
                    text += f"  {emoji} {signal.replace('_', ' ').title()}: {sentiment}\n"

                self.bot.reply_to(message, text)

            except Exception as e:
                self.bot.reply_to(message, f"❌ Error: {str(e)}")

        @self.bot.message_handler(commands=['balance'])
        @self._require_auth
        def balance(message):
            self.bot.reply_to(message, "💰 Fetching balance...")

            try:
                balance_data = self.trading.get_aggregated_balance()

                text = "💰 <b>Account Balance:</b>\n\n"

                for exchange, balances in balance_data['by_exchange'].items():
                    text += f"<b>{exchange.upper()}:</b>\n"

                    if isinstance(balances, dict):
                        for asset, data in list(balances.items())[:5]:  # Top 5
                            if isinstance(data, dict):
                                amount = data.get('total', data.get('available', 0))
                            else:
                                amount = data

                            if amount > 0:
                                text += f"  {asset}: {amount:,.6f}\n"

                    text += "\n"

                total = balance_data.get('total_usd_estimate', 0)
                text += f"<b>Total (est):</b> ${total:,.2f}"

                self.bot.reply_to(message, text)

            except Exception as e:
                self.bot.reply_to(message, f"❌ Error: {str(e)}")

        @self.bot.message_handler(commands=['buy', 'sell'])
        @self._require_auth
        def trade(message):
            try:
                parts = message.text.split()
                command = parts[0][1:]  # Remove '/'

                if len(parts) < 3:
                    self.bot.reply_to(
                        message,
                        f"Usage: /{command} [AMOUNT] [SYMBOL] [EXCHANGE]\n"
                        f"Example: /{command} 0.1 ETH kraken"
                    )
                    return

                amount = float(parts[1])
                symbol = parts[2].upper()
                exchange = parts[3].lower() if len(parts) > 3 else 'kraken'

                # Get current price
                prices = self.trading.get_prices(symbol)
                current_price = prices.get(exchange, 0)

                if not current_price:
                    self.bot.reply_to(message, f"❌ Could not get price for {symbol} on {exchange}")
                    return

                # Estimate cost/proceeds
                total = amount * current_price

                # Create confirmation
                trade_id = f"{message.chat.id}_{int(time.time())}"
                self.pending_trades[trade_id] = {
                    'symbol': symbol,
                    'side': command,
                    'amount': amount,
                    'exchange': exchange,
                    'price': current_price,
                    'total': total
                }

                # Create inline keyboard
                markup = types.InlineKeyboardMarkup()
                markup.row(
                    types.InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_{trade_id}"),
                    types.InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{trade_id}")
                )

                confirm_text = (
                    f"🔔 <b>Confirm {command.upper()} Order</b>\n\n"
                    f"Symbol: {symbol}\n"
                    f"Amount: {amount}\n"
                    f"Exchange: {exchange.upper()}\n"
                    f"Price: ${current_price:,.2f}\n"
                    f"Total: ${total:,.2f}\n\n"
                    f"⚠️ Confirm to execute"
                )

                self.bot.reply_to(message, confirm_text, reply_markup=markup)

            except ValueError:
                self.bot.reply_to(message, "❌ Invalid amount. Use a number (e.g., 0.1)")
            except Exception as e:
                self.bot.reply_to(message, f"❌ Error: {str(e)}")

        @self.bot.callback_query_handler(func=lambda call: True)
        def callback_handler(call):
            try:
                action, trade_id = call.data.split('_', 1)

                if trade_id not in self.pending_trades:
                    self.bot.answer_callback_query(call.id, "❌ Trade expired")
                    return

                trade = self.pending_trades[trade_id]

                if action == 'confirm':
                    # Execute trade
                    self.bot.answer_callback_query(call.id, "Executing trade...")

                    result = self.trading.execute_trade(
                        symbol=trade['symbol'],
                        side=trade['side'],
                        amount=trade['amount'],
                        exchange=trade['exchange'],
                        order_type='market'
                    )

                    if result:
                        response = (
                            f"✅ <b>Trade Executed</b>\n\n"
                            f"{trade['side'].upper()} {trade['amount']} {trade['symbol']}\n"
                            f"Exchange: {trade['exchange'].upper()}\n"
                            f"Price: ${trade['price']:,.2f}\n"
                            f"Total: ${trade['total']:,.2f}\n\n"
                            f"Order ID: {result.get('order_id', 'N/A')}"
                        )
                    else:
                        response = "❌ Trade failed. Check logs."

                    self.bot.edit_message_text(
                        response,
                        call.message.chat.id,
                        call.message.message_id
                    )

                elif action == 'cancel':
                    self.bot.answer_callback_query(call.id, "Trade cancelled")
                    self.bot.edit_message_text(
                        "❌ Trade cancelled",
                        call.message.chat.id,
                        call.message.message_id
                    )

                # Remove pending trade
                del self.pending_trades[trade_id]

            except Exception as e:
                self.bot.answer_callback_query(call.id, f"Error: {str(e)}")

        @self.bot.message_handler(commands=['orders'])
        @self._require_auth
        def orders(message):
            try:
                all_orders = self.trading.get_all_active_orders()

                text = "📋 <b>Active Orders:</b>\n\n"

                total_orders = 0
                for exchange, orders in all_orders.items():
                    if orders and len(orders) > 0:
                        text += f"<b>{exchange.upper()}:</b>\n"
                        for order in orders[:5]:  # Show first 5
                            text += f"  • {order.get('side', 'N/A')} {order.get('market', 'N/A')}\n"
                        total_orders += len(orders)
                        text += "\n"

                if total_orders == 0:
                    text += "No active orders"
                else:
                    text += f"Total: {total_orders} orders"

                self.bot.reply_to(message, text)

            except Exception as e:
                self.bot.reply_to(message, f"❌ Error: {str(e)}")

    def send_recommendation(self, symbol='ETH'):
        """
        Send trading recommendation to authorized users

        Args:
            symbol: Trading symbol to analyze
        """
        if not self.authorized_chat_ids:
            print("⚠ No authorized users to send recommendation to")
            return

        try:
            analysis = self.trading.get_market_analysis(symbol)
            rec = analysis['recommendation']

            # Emoji for action
            action_emoji = "🟢" if rec['action'] == 'BUY' else "🔴" if rec['action'] == 'SELL' else "🟡"

            text = f"{action_emoji} <b>Trading Signal: {symbol}</b>\n\n"
            text += f"<b>Action: {rec['action']}</b>\n"
            text += f"Bias: {rec['bias']}\n"
            text += f"Confidence: {rec['confidence']:.0f}%\n\n"

            # Prices
            text += "💵 <b>Current Prices:</b>\n"
            for exchange, price in analysis['prices'].items():
                text += f"  {exchange.upper()}: ${price:,.2f}\n"

            # Levels
            text += f"\n📍 <b>Key Levels:</b>\n"
            text += f"  Support: ${rec['support']:,.2f}\n"
            text += f"  Resistance: ${rec['resistance']:,.2f}\n"

            # Send to all authorized users
            for chat_id in self.authorized_chat_ids:
                self.bot.send_message(chat_id, text)

            print(f"✓ Recommendation sent to {len(self.authorized_chat_ids)} user(s)")

        except Exception as e:
            print(f"❌ Error sending recommendation: {e}")

    def run(self):
        """Start the bot"""
        print("\n" + "="*60)
        print("🤖 TELEGRAM TRADING BOT STARTED")
        print("="*60)
        print("\nBot is running... Press Ctrl+C to stop")
        print("\nSend /start to your bot to begin trading")
        print("="*60 + "\n")

        self.bot.infinity_polling()


def main():
    """Main function"""
    try:
        bot = TelegramTradingBot()
        bot.run()
    except KeyboardInterrupt:
        print("\n\n✓ Bot stopped by user")
    except Exception as e:
        print(f"\n❌ Bot error: {e}")
        print("\nMake sure you've:")
        print("1. Created a bot with @BotFather")
        print("2. Added TELEGRAM_BOT_TOKEN to .env")
        print("3. (Optional) Added TELEGRAM_CHAT_ID to .env for security")


if __name__ == "__main__":
    main()
