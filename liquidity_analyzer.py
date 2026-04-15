"""
Liquidity Cluster Analysis Module

This module identifies and analyzes liquidity zones:
- BSL (Buy-Side Liquidity) - above swing highs
- SSL (Sell-Side Liquidity) - below swing lows
- Equal highs/lows (major liquidity pools)
- Liquidity sweeps and grabs
"""

import pandas as pd
import numpy as np
from scipy.signal import argrelextrema


class LiquidityAnalyzer:
    """
    Professional liquidity analysis for institutional order flow

    Liquidity represents areas where stop losses and limit orders cluster.
    Smart money hunts liquidity before major moves.
    """

    @staticmethod
    def identify_swing_points(df, order=5):
        """
        Identify swing highs and swing lows

        Args:
            df: DataFrame with OHLC data
            order: Number of candles on each side for comparison

        Returns:
            tuple: (swing_highs, swing_lows) with indices
        """
        # Find local maxima (swing highs)
        swing_high_idx = argrelextrema(df['high'].values, np.greater, order=order)[0]

        # Find local minima (swing lows)
        swing_low_idx = argrelextrema(df['low'].values, np.less, order=order)[0]

        # Create boolean series
        swing_highs = pd.Series(False, index=df.index)
        swing_lows = pd.Series(False, index=df.index)

        swing_highs.iloc[swing_high_idx] = True
        swing_lows.iloc[swing_low_idx] = True

        return swing_highs, swing_lows

    @staticmethod
    def identify_bsl_ssl(df, swing_highs, swing_lows):
        """
        Identify Buy-Side Liquidity and Sell-Side Liquidity zones

        BSL: Above recent swing highs (where buy stops rest)
        SSL: Below recent swing lows (where sell stops rest)

        Args:
            df: DataFrame with price data
            swing_highs: Boolean series of swing highs
            swing_lows: Boolean series of swing lows

        Returns:
            DataFrame: With BSL and SSL price levels
        """
        # Get swing high and low prices
        df['bsl_level'] = np.nan
        df['ssl_level'] = np.nan

        # For each candle, find nearest swing high (BSL) and swing low (SSL)
        swing_high_prices = df.loc[swing_highs, 'high']
        swing_low_prices = df.loc[swing_lows, 'low']

        for idx in df.index:
            # Find most recent swing high before current index
            recent_swing_highs = swing_high_prices[swing_high_prices.index < idx]
            if len(recent_swing_highs) > 0:
                # Take the highest of recent swing highs as BSL
                df.loc[idx, 'bsl_level'] = recent_swing_highs.iloc[-5:].max()

            # Find most recent swing low before current index
            recent_swing_lows = swing_low_prices[swing_low_prices.index < idx]
            if len(recent_swing_lows) > 0:
                # Take the lowest of recent swing lows as SSL
                df.loc[idx, 'ssl_level'] = recent_swing_lows.iloc[-5:].min()

        return df

    @staticmethod
    def identify_equal_highs_lows(df, tolerance_pct=0.2):
        """
        Identify equal highs and equal lows (major liquidity pools)

        Equal highs/lows are multiple swing points at approximately same level
        These represent significant liquidity clusters

        Args:
            df: DataFrame with swing points
            tolerance_pct: Price tolerance for "equal" (0.2 = 0.2%)

        Returns:
            tuple: (equal_highs, equal_lows) boolean series
        """
        swing_highs, swing_lows = LiquidityAnalyzer.identify_swing_points(df)

        equal_highs = pd.Series(False, index=df.index)
        equal_lows = pd.Series(False, index=df.index)

        # Get swing high prices
        swing_high_prices = df.loc[swing_highs, 'high'].reset_index()

        # Check for equal highs (within tolerance)
        for i in range(len(swing_high_prices)):
            current_price = swing_high_prices.iloc[i]['high']
            current_idx = swing_high_prices.iloc[i]['index']

            # Check next few swing highs
            matches = 0
            for j in range(i+1, min(i+5, len(swing_high_prices))):
                compare_price = swing_high_prices.iloc[j]['high']
                price_diff_pct = abs(current_price - compare_price) / current_price * 100

                if price_diff_pct <= tolerance_pct:
                    matches += 1

            # If 2+ matches found, mark as equal high
            if matches >= 1:
                equal_highs.loc[current_idx] = True

        # Get swing low prices
        swing_low_prices = df.loc[swing_lows, 'low'].reset_index()

        # Check for equal lows (within tolerance)
        for i in range(len(swing_low_prices)):
            current_price = swing_low_prices.iloc[i]['low']
            current_idx = swing_low_prices.iloc[i]['index']

            # Check next few swing lows
            matches = 0
            for j in range(i+1, min(i+5, len(swing_low_prices))):
                compare_price = swing_low_prices.iloc[j]['low']
                price_diff_pct = abs(current_price - compare_price) / current_price * 100

                if price_diff_pct <= tolerance_pct:
                    matches += 1

            # If 2+ matches found, mark as equal low
            if matches >= 1:
                equal_lows.loc[current_idx] = True

        return equal_highs, equal_lows

    @staticmethod
    def detect_liquidity_sweep(df, lookback=3):
        """
        Detect liquidity sweeps (stop hunts)

        Liquidity Sweep:
        - Price briefly moves through a level (triggers stops)
        - Then reverses back (shows trap)

        Args:
            df: DataFrame with price and BSL/SSL data
            lookback: Candles to check for reversal

        Returns:
            tuple: (bsl_sweep, ssl_sweep) boolean series
        """
        bsl_sweep = pd.Series(False, index=df.index)
        ssl_sweep = pd.Series(False, index=df.index)

        for i in range(lookback, len(df)):
            current = df.iloc[i]
            previous = df.iloc[i-lookback:i]

            # BSL Sweep Detection (bullish reversal after taking out highs)
            if 'bsl_level' in df.columns and pd.notna(current['bsl_level']):
                # Check if wick went above BSL
                if current['high'] > current['bsl_level']:
                    # Check if closed back below BSL (rejection)
                    if current['close'] < current['bsl_level']:
                        # Check if previous candles were below BSL
                        if all(previous['high'] < current['bsl_level']):
                            bsl_sweep.iloc[i] = True

            # SSL Sweep Detection (bearish reversal after taking out lows)
            if 'ssl_level' in df.columns and pd.notna(current['ssl_level']):
                # Check if wick went below SSL
                if current['low'] < current['ssl_level']:
                    # Check if closed back above SSL (rejection)
                    if current['close'] > current['ssl_level']:
                        # Check if previous candles were above SSL
                        if all(previous['low'] > current['ssl_level']):
                            ssl_sweep.iloc[i] = True

        return bsl_sweep, ssl_sweep

    @staticmethod
    def calculate_liquidity_strength(df, volume_lookback=20):
        """
        Calculate strength of liquidity zones

        Stronger liquidity = more touches + higher volume

        Args:
            df: DataFrame with swing points
            volume_lookback: Period for volume analysis

        Returns:
            DataFrame: With liquidity strength scores
        """
        swing_highs, swing_lows = LiquidityAnalyzer.identify_swing_points(df)

        df['bsl_strength'] = 0.0
        df['ssl_strength'] = 0.0

        # Calculate average volume
        df['volume_ma'] = df['volume'].rolling(volume_lookback).mean()

        # For each swing point, calculate strength based on:
        # 1. Number of times level was tested
        # 2. Volume at those tests
        # 3. Time since last test (recency)

        swing_high_indices = df[swing_highs].index
        for idx in swing_high_indices:
            price = df.loc[idx, 'high']
            volume = df.loc[idx, 'volume']
            volume_ma = df.loc[idx, 'volume_ma']

            # Base strength = volume ratio
            strength = volume / volume_ma if pd.notna(volume_ma) and volume_ma > 0 else 1.0

            # Check how many times this level was tested
            tolerance = price * 0.002  # 0.2% tolerance
            tests = df[(abs(df['high'] - price) <= tolerance) & (df.index < idx)]
            touch_count = len(tests)

            # Adjust strength by touch count (more touches = stronger level)
            strength *= (1 + touch_count * 0.2)

            df.loc[idx, 'bsl_strength'] = strength

        swing_low_indices = df[swing_lows].index
        for idx in swing_low_indices:
            price = df.loc[idx, 'low']
            volume = df.loc[idx, 'volume']
            volume_ma = df.loc[idx, 'volume_ma']

            # Base strength = volume ratio
            strength = volume / volume_ma if pd.notna(volume_ma) and volume_ma > 0 else 1.0

            # Check how many times this level was tested
            tolerance = price * 0.002  # 0.2% tolerance
            tests = df[(abs(df['low'] - price) <= tolerance) & (df.index < idx)]
            touch_count = len(tests)

            # Adjust strength by touch count
            strength *= (1 + touch_count * 0.2)

            df.loc[idx, 'ssl_strength'] = strength

        return df

    @staticmethod
    def identify_liquidity_voids(df, volume_profile_bins=50):
        """
        Identify low volume areas (liquidity voids)

        Price moves quickly through these areas
        Good targets for take profit

        Args:
            df: DataFrame with volume data
            volume_profile_bins: Number of price bins

        Returns:
            Series: Boolean series indicating void zones
        """
        # Create price bins
        price_min = df['low'].min()
        price_max = df['high'].max()
        bins = np.linspace(price_min, price_max, volume_profile_bins)

        # Calculate volume at each price level
        volume_profile = []
        for i in range(len(bins) - 1):
            bin_low = bins[i]
            bin_high = bins[i + 1]

            # Sum volume for candles in this price range
            in_range = df[(df['low'] <= bin_high) & (df['high'] >= bin_low)]
            total_volume = in_range['volume'].sum()

            volume_profile.append(total_volume)

        # Identify low volume nodes (bottom 20%)
        volume_threshold = np.percentile(volume_profile, 20)

        # Mark candles in low volume zones
        liquidity_void = pd.Series(False, index=df.index)

        for i, volume in enumerate(volume_profile):
            if volume < volume_threshold:
                bin_low = bins[i]
                bin_high = bins[i + 1]

                # Mark candles in this range
                in_void = (df['close'] >= bin_low) & (df['close'] <= bin_high)
                liquidity_void = liquidity_void | in_void

        return liquidity_void

    @staticmethod
    def add_all_liquidity_indicators(df):
        """
        Add all liquidity indicators to dataframe

        Args:
            df: DataFrame with OHLCV data

        Returns:
            DataFrame: Enhanced with liquidity indicators
        """
        # Identify swing points
        swing_highs, swing_lows = LiquidityAnalyzer.identify_swing_points(df, order=5)
        df['swing_high'] = swing_highs
        df['swing_low'] = swing_lows

        # Identify BSL and SSL levels
        df = LiquidityAnalyzer.identify_bsl_ssl(df, swing_highs, swing_lows)

        # Identify equal highs/lows
        equal_highs, equal_lows = LiquidityAnalyzer.identify_equal_highs_lows(df)
        df['equal_highs'] = equal_highs
        df['equal_lows'] = equal_lows

        # Detect liquidity sweeps
        bsl_sweep, ssl_sweep = LiquidityAnalyzer.detect_liquidity_sweep(df)
        df['bsl_sweep'] = bsl_sweep
        df['ssl_sweep'] = ssl_sweep

        # Calculate liquidity strength
        df = LiquidityAnalyzer.calculate_liquidity_strength(df)

        # Identify liquidity voids
        df['liquidity_void'] = LiquidityAnalyzer.identify_liquidity_voids(df)

        return df


def test_liquidity_analyzer():
    """Test liquidity analyzer with sample data"""
    import sys
    sys.path.append('.')

    try:
        df = pd.read_csv('data/eth_usd_60m_1825d.csv')
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        print("Testing Liquidity Analyzer...")
        print("=" * 60)

        # Add liquidity indicators
        df = LiquidityAnalyzer.add_all_liquidity_indicators(df)

        print(f"\nSwing highs detected: {df['swing_high'].sum()}")
        print(f"Swing lows detected: {df['swing_low'].sum()}")
        print(f"Equal highs detected: {df['equal_highs'].sum()}")
        print(f"Equal lows detected: {df['equal_lows'].sum()}")
        print(f"BSL sweeps detected: {df['bsl_sweep'].sum()}")
        print(f"SSL sweeps detected: {df['ssl_sweep'].sum()}")

        # Show latest liquidity levels
        print("\n" + "=" * 60)
        print("Latest Liquidity Levels:")
        print("=" * 60)
        print(df[['timestamp', 'close', 'bsl_level', 'ssl_level',
                  'bsl_sweep', 'ssl_sweep']].tail(10))

        # Show equal highs/lows
        if df['equal_highs'].sum() > 0:
            print("\n" + "=" * 60)
            print("Recent Equal Highs (Major Liquidity Pools):")
            print("=" * 60)
            equal_high_data = df[df['equal_highs']][['timestamp', 'high']].tail(5)
            print(equal_high_data)

        if df['equal_lows'].sum() > 0:
            print("\n" + "=" * 60)
            print("Recent Equal Lows (Major Liquidity Pools):")
            print("=" * 60)
            equal_low_data = df[df['equal_lows']][['timestamp', 'low']].tail(5)
            print(equal_low_data)

    except FileNotFoundError:
        print("No data file found. Run coinbase_collector.py first.")


if __name__ == "__main__":
    test_liquidity_analyzer()
