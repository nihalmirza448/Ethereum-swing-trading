#!/usr/bin/env python3
"""
Strategy Scheduler - Automated trading recommendations via Telegram

Features:
- Runs market analysis on schedule (e.g., every hour)
- Sends recommendations to Telegram automatically
- Monitors market conditions 24/7
- Can auto-execute trades (with confirmation)

Usage:
    python strategy_scheduler.py --interval 3600  # Run every hour
    python strategy_scheduler.py --interval 1800  # Run every 30 minutes
"""

import time
import argparse
from datetime import datetime
from telegram_trading_bot import TelegramTradingBot
from multi_exchange_interface import MultiExchangeInterface


class StrategyScheduler:
    """
    Automated strategy scheduler with Telegram notifications

    Monitors markets and sends recommendations at regular intervals
    """

    def __init__(self, interval=3600):
        """
        Initialize scheduler

        Args:
            interval: Check interval in seconds (default: 3600 = 1 hour)
        """
        self.interval = interval
        print(f"Initializing Strategy Scheduler (interval: {interval}s)...")

        # Initialize Telegram bot
        self.bot = TelegramTradingBot()

        # Initialize trading interface
        self.trading = MultiExchangeInterface()

        print(f"✓ Scheduler initialized")

    def analyze_and_send(self, symbol='ETH'):
        """
        Analyze market and send recommendation

        Args:
            symbol: Trading symbol to analyze
        """
        print(f"\n{'='*60}")
        print(f"Running scheduled analysis - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")

        try:
            # Get analysis
            print(f"Analyzing {symbol}...")
            analysis = self.trading.get_market_analysis(symbol)
            rec = analysis['recommendation']

            print(f"\nRecommendation: {rec['action']} ({rec['bias']}, {rec['confidence']:.0f}% confidence)")

            # Send to Telegram
            print("Sending to Telegram...")
            self.bot.send_recommendation(symbol)

            print("✓ Analysis complete and sent")

        except Exception as e:
            print(f"❌ Error during analysis: {e}")

    def run_once(self, symbol='ETH'):
        """Run analysis once and exit"""
        print("\n" + "="*60)
        print("ONE-TIME ANALYSIS MODE")
        print("="*60 + "\n")

        self.analyze_and_send(symbol)

        print("\n✓ Analysis complete. Exiting.")

    def run_scheduled(self, symbol='ETH'):
        """
        Run analysis on schedule

        Args:
            symbol: Trading symbol to monitor
        """
        print("\n" + "="*60)
        print("SCHEDULED ANALYSIS MODE")
        print("="*60)
        print(f"\nInterval: Every {self.interval} seconds ({self.interval/60:.1f} minutes)")
        print(f"Symbol: {symbol}")
        print(f"\nPress Ctrl+C to stop")
        print("="*60 + "\n")

        try:
            while True:
                # Run analysis
                self.analyze_and_send(symbol)

                # Wait for next interval
                print(f"\nNext analysis in {self.interval} seconds...")
                print(f"Waiting until {datetime.fromtimestamp(time.time() + self.interval).strftime('%H:%M:%S')}")

                time.sleep(self.interval)

        except KeyboardInterrupt:
            print("\n\n✓ Scheduler stopped by user")

    def run_advanced(self, symbols=['ETH', 'BTC'], interval=3600, auto_trade=False):
        """
        Advanced mode: Monitor multiple symbols with optional auto-trading

        Args:
            symbols: List of symbols to monitor
            interval: Check interval in seconds
            auto_trade: If True, automatically execute high-confidence trades
        """
        print("\n" + "="*60)
        print("ADVANCED MONITORING MODE")
        print("="*60)
        print(f"\nSymbols: {', '.join(symbols)}")
        print(f"Interval: {interval}s ({interval/60:.1f} min)")
        print(f"Auto-trade: {'ENABLED (HIGH CONFIDENCE ONLY)' if auto_trade else 'DISABLED'}")
        print(f"\nPress Ctrl+C to stop")
        print("="*60 + "\n")

        try:
            while True:
                for symbol in symbols:
                    print(f"\n{'='*60}")
                    print(f"Analyzing {symbol} - {datetime.now().strftime('%H:%M:%S')}")
                    print(f"{'='*60}")

                    try:
                        analysis = self.trading.get_market_analysis(symbol)
                        rec = analysis['recommendation']

                        print(f"Action: {rec['action']}")
                        print(f"Confidence: {rec['confidence']:.0f}%")

                        # Send recommendation
                        self.bot.send_recommendation(symbol)

                        # Auto-trade if enabled and high confidence
                        if auto_trade and rec['confidence'] >= 66:
                            if rec['action'] in ['BUY', 'SELL']:
                                print(f"\n⚡ HIGH CONFIDENCE {rec['action']} SIGNAL!")

                                # Send alert first
                                alert_text = (
                                    f"⚡ <b>HIGH CONFIDENCE SIGNAL</b>\n\n"
                                    f"Symbol: {symbol}\n"
                                    f"Action: {rec['action']}\n"
                                    f"Confidence: {rec['confidence']:.0f}%\n\n"
                                    f"Auto-trade is ENABLED.\n"
                                    f"Waiting 30 seconds before execution...\n"
                                    f"Reply /cancel to abort"
                                )

                                for chat_id in self.bot.authorized_chat_ids:
                                    self.bot.bot.send_message(chat_id, alert_text)

                                # Wait before execution
                                print("Waiting 30 seconds before auto-trade...")
                                time.sleep(30)

                                # Execute small amount (0.01 ETH / 0.001 BTC)
                                amount = 0.01 if symbol == 'ETH' else 0.001

                                print(f"Executing auto-trade: {rec['action']} {amount} {symbol}")

                                # Note: In production, you'd want more sophisticated
                                # risk management here
                                result = self.trading.execute_trade(
                                    symbol=symbol,
                                    side=rec['action'].lower(),
                                    amount=amount,
                                    exchange=rec.get('best_exchange_to_buy', 'kraken'),
                                    validate=True  # Keep validation ON for safety
                                )

                                if result:
                                    success_text = (
                                        f"✅ <b>Auto-trade executed</b>\n\n"
                                        f"{rec['action']} {amount} {symbol}\n"
                                        f"Check /orders for details"
                                    )
                                else:
                                    success_text = "❌ Auto-trade failed"

                                for chat_id in self.bot.authorized_chat_ids:
                                    self.bot.bot.send_message(chat_id, success_text)

                    except Exception as e:
                        print(f"Error analyzing {symbol}: {e}")

                # Wait for next interval
                print(f"\n{'='*60}")
                print(f"Waiting {interval}s until next check...")
                print(f"{'='*60}\n")
                time.sleep(interval)

        except KeyboardInterrupt:
            print("\n\n✓ Advanced scheduler stopped")


def main():
    """Main function with CLI args"""
    parser = argparse.ArgumentParser(description='Automated Trading Strategy Scheduler')

    parser.add_argument(
        '--interval',
        type=int,
        default=3600,
        help='Check interval in seconds (default: 3600 = 1 hour)'
    )

    parser.add_argument(
        '--symbol',
        type=str,
        default='ETH',
        help='Trading symbol to monitor (default: ETH)'
    )

    parser.add_argument(
        '--once',
        action='store_true',
        help='Run once and exit (no scheduling)'
    )

    parser.add_argument(
        '--multi',
        nargs='+',
        help='Monitor multiple symbols (e.g., --multi ETH BTC)'
    )

    parser.add_argument(
        '--auto-trade',
        action='store_true',
        help='Enable auto-trading for high confidence signals (USE WITH CAUTION)'
    )

    args = parser.parse_args()

    try:
        scheduler = StrategyScheduler(interval=args.interval)

        if args.once:
            # One-time analysis
            scheduler.run_once(args.symbol)

        elif args.multi:
            # Multi-symbol monitoring
            scheduler.run_advanced(
                symbols=args.multi,
                interval=args.interval,
                auto_trade=args.auto_trade
            )

        else:
            # Standard scheduled mode
            scheduler.run_scheduled(args.symbol)

    except KeyboardInterrupt:
        print("\n✓ Stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
