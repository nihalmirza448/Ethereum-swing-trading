#!/usr/bin/env python3
"""
Helper script to get your Telegram Chat ID

Usage:
1. Create a bot with @BotFather
2. Add the bot token below or in .env
3. Run this script
4. Send /start to your bot
5. Your chat ID will be printed here
"""

import os
from dotenv import load_dotenv

load_dotenv()

try:
    import telebot
except ImportError:
    print("Installing pyTelegramBotAPI...")
    os.system("pip install pyTelegramBotAPI -q")
    import telebot


def get_chat_id():
    """Simple bot to display your chat ID"""

    # Get token
    token = os.getenv('TELEGRAM_BOT_TOKEN')

    if not token or token == 'your_telegram_bot_token':
        token = input("\nEnter your Telegram bot token: ").strip()

    if not token:
        print("❌ No token provided")
        return

    print("\n" + "="*60)
    print("TELEGRAM CHAT ID HELPER")
    print("="*60)
    print("\nBot is running...")
    print("Send /start to your bot to get your chat ID")
    print("Press Ctrl+C to stop\n")
    print("="*60 + "\n")

    bot = telebot.TeleBot(token)

    @bot.message_handler(commands=['start'])
    def start(message):
        chat_id = message.chat.id
        username = message.from_user.username or "Unknown"
        first_name = message.from_user.first_name or ""

        print("\n" + "="*60)
        print("✅ CHAT ID RECEIVED")
        print("="*60)
        print(f"\nUser: {first_name} (@{username})")
        print(f"Chat ID: {chat_id}")
        print("\nAdd this to your .env file:")
        print(f"TELEGRAM_CHAT_ID={chat_id}")
        print("="*60 + "\n")

        bot.reply_to(
            message,
            f"✅ <b>Your Chat ID:</b>\n\n"
            f"<code>{chat_id}</code>\n\n"
            f"Add this to TELEGRAM_CHAT_ID in your .env file",
            parse_mode='HTML'
        )

    @bot.message_handler(func=lambda m: True)
    def echo_all(message):
        chat_id = message.chat.id
        bot.reply_to(
            message,
            f"Your chat ID is: <code>{chat_id}</code>\n\n"
            f"Send /start to see formatted output",
            parse_mode='HTML'
        )

    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("\n✓ Stopped by user")


if __name__ == "__main__":
    try:
        get_chat_id()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure you've created a bot with @BotFather")
        print("and have a valid bot token")
