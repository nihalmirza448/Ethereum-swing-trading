"""
Fetch BTC OHLCV data from Binance public API (no auth needed)
Saves to data/btc_usd_60m_1825d.csv matching ETH data format
"""
import requests
import pandas as pd
import time
import os
from datetime import datetime, timezone

def fetch_binance_klines(symbol, interval, start_ms, end_ms, limit=1000):
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_ms,
        "endTime": end_ms,
        "limit": limit
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()

def fetch_full_history_binance(symbol="BTCUSDT", interval="1h", days=1825):
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = now_ms - (days * 24 * 3600 * 1000)

    all_candles = []
    current_ms = start_ms
    batch = 0

    print(f"Fetching {symbol} {interval} data for {days} days from Binance...")
    print(f"From: {datetime.fromtimestamp(start_ms/1000, tz=timezone.utc).strftime('%Y-%m-%d')} "
          f"to: {datetime.fromtimestamp(now_ms/1000, tz=timezone.utc).strftime('%Y-%m-%d')}")

    while current_ms < now_ms:
        candles = fetch_binance_klines(symbol, interval, current_ms, now_ms, limit=1000)
        if not candles:
            break

        all_candles.extend(candles)
        batch += 1

        last_open_time = candles[-1][0]
        last_dt = datetime.fromtimestamp(last_open_time/1000, tz=timezone.utc)
        print(f"  Batch {batch}: {len(candles)} candles, up to {last_dt.strftime('%Y-%m-%d %H:%M')}")

        if len(candles) < 1000:
            break

        # Move forward past the last candle
        current_ms = last_open_time + 1
        time.sleep(0.3)

    print(f"\nTotal raw candles: {len(all_candles)}")
    return all_candles

def save_binance_ohlcv(candles, filepath):
    """
    Binance kline format:
    [open_time, open, high, low, close, volume, close_time,
     quote_asset_volume, num_trades, taker_buy_base_vol, taker_buy_quote_vol, ignore]
    """
    rows = []
    for c in candles:
        rows.append({
            "timestamp": datetime.fromtimestamp(c[0]/1000, tz=timezone.utc).replace(tzinfo=None),
            "open":   float(c[1]),
            "high":   float(c[2]),
            "low":    float(c[3]),
            "close":  float(c[4]),
            "volume": float(c[5]),
            "vwap":   float(c[7]) / float(c[5]) if float(c[5]) > 0 else float(c[4]),
            "count":  int(c[8])
        })

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    df.to_csv(filepath, index=False)
    print(f"Saved {len(df)} candles to {filepath}")
    print(f"Date range: {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}")
    return df

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    candles = fetch_full_history_binance("BTCUSDT", "1h", days=1825)
    df = save_binance_ohlcv(candles, "data/btc_usd_60m_1825d.csv")
    print(f"\nBTC data ready: {len(df)} hourly candles")
