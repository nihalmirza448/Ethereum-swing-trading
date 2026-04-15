"""
CVD (Cumulative Volume Delta) Analysis Module

This module calculates and analyzes CVD to identify:
- Buying vs selling pressure
- Bullish and bearish divergences
- Volume surges and exhaustion signals
- Trend confirmations
"""

import pandas as pd
import numpy as np
from scipy.signal import argrelextrema


class CVDAnalyzer:
    """
    Professional CVD analysis for institutional order flow detection

    CVD = Cumulative difference between buy volume and sell volume
    Positive CVD = Net buying pressure
    Negative CVD = Net selling pressure
    """

    @staticmethod
    def calculate_cvd(df):
        """
        Calculate Cumulative Volume Delta

        For crypto, we approximate buy/sell volume using price direction:
        - Up close = buy volume
        - Down close = sell volume

        Args:
            df: DataFrame with OHLCV data

        Returns:
            Series: CVD values
        """
        # Calculate delta for each candle
        # If close > open, assume buying pressure (volume is buy volume)
        # If close < open, assume selling pressure (volume is sell volume)

        delta = np.where(
            df['close'] >= df['open'],
            df['volume'],  # Buying volume
            -df['volume']  # Selling volume
        )

        # Cumulative sum of delta
        cvd = pd.Series(delta).cumsum()

        return cvd

    @staticmethod
    def calculate_cvd_advanced(df, use_wick_analysis=True):
        """
        Advanced CVD calculation using wick analysis

        More sophisticated approach that considers:
        - Candle body direction (open to close)
        - Wick sizes (upper and lower)
        - Volume distribution

        Args:
            df: DataFrame with OHLCV data
            use_wick_analysis: Use wick-based volume distribution

        Returns:
            Series: CVD values
        """
        if not use_wick_analysis:
            return CVDAnalyzer.calculate_cvd(df)

        # Calculate body and wick proportions
        body = abs(df['close'] - df['open'])
        upper_wick = df['high'] - df[['open', 'close']].max(axis=1)
        lower_wick = df[['open', 'close']].min(axis=1) - df['low']
        total_range = df['high'] - df['low']

        # Avoid division by zero
        total_range = total_range.replace(0, 1)

        # Body percentage of total range
        body_pct = body / total_range

        # Determine buy/sell volume based on:
        # 1. Direction of close vs open
        # 2. Proportion of body to total range
        # 3. Wick distribution

        buy_volume = np.where(
            df['close'] >= df['open'],
            df['volume'] * (0.5 + body_pct * 0.5),  # More body = more conviction
            df['volume'] * (0.5 - body_pct * 0.5)   # Rejection shows some buying
        )

        sell_volume = np.where(
            df['close'] < df['open'],
            df['volume'] * (0.5 + body_pct * 0.5),  # More body = more conviction
            df['volume'] * (0.5 - body_pct * 0.5)   # Rejection shows some selling
        )

        delta = buy_volume - sell_volume
        cvd = pd.Series(delta).cumsum()

        return cvd

    @staticmethod
    def detect_divergences(df, cvd, lookback=20):
        """
        Detect bullish and bearish CVD divergences

        Bullish Divergence: Price makes lower low, CVD makes higher low
        Bearish Divergence: Price makes higher high, CVD makes lower high

        Args:
            df: DataFrame with price data
            cvd: CVD series
            lookback: Period for finding local extremes

        Returns:
            tuple: (bullish_divergence, bearish_divergence) boolean series
        """
        # Find local price extremes
        price_lows_idx = argrelextrema(df['low'].values, np.less, order=lookback)[0]
        price_highs_idx = argrelextrema(df['high'].values, np.greater, order=lookback)[0]

        # Find local CVD extremes
        cvd_lows_idx = argrelextrema(cvd.values, np.less, order=lookback)[0]
        cvd_highs_idx = argrelextrema(cvd.values, np.greater, order=lookback)[0]

        # Initialize divergence series
        bullish_div = pd.Series(False, index=df.index)
        bearish_div = pd.Series(False, index=df.index)

        # Detect bullish divergence (price lower low, CVD higher low)
        for i in range(1, len(price_lows_idx)):
            current_idx = price_lows_idx[i]
            prev_idx = price_lows_idx[i-1]

            # Check if price made lower low
            if df['low'].iloc[current_idx] < df['low'].iloc[prev_idx]:
                # Find corresponding CVD lows
                cvd_lows_in_range = [idx for idx in cvd_lows_idx
                                     if prev_idx <= idx <= current_idx]

                if len(cvd_lows_in_range) >= 2:
                    # Check if CVD made higher low
                    if cvd.iloc[cvd_lows_in_range[-1]] > cvd.iloc[cvd_lows_in_range[0]]:
                        bullish_div.iloc[current_idx] = True

        # Detect bearish divergence (price higher high, CVD lower high)
        for i in range(1, len(price_highs_idx)):
            current_idx = price_highs_idx[i]
            prev_idx = price_highs_idx[i-1]

            # Check if price made higher high
            if df['high'].iloc[current_idx] > df['high'].iloc[prev_idx]:
                # Find corresponding CVD highs
                cvd_highs_in_range = [idx for idx in cvd_highs_idx
                                      if prev_idx <= idx <= current_idx]

                if len(cvd_highs_in_range) >= 2:
                    # Check if CVD made lower high
                    if cvd.iloc[cvd_highs_in_range[-1]] < cvd.iloc[cvd_highs_in_range[0]]:
                        bearish_div.iloc[current_idx] = True

        return bullish_div, bearish_div

    @staticmethod
    def calculate_cvd_slope(cvd, period=5):
        """
        Calculate CVD slope (rate of change)

        Shows intensity of buying/selling pressure
        Steep positive slope = strong buying
        Steep negative slope = strong selling

        Args:
            cvd: CVD series
            period: Lookback period for slope calculation

        Returns:
            Series: CVD slope values
        """
        return cvd.diff(period) / period

    @staticmethod
    def detect_cvd_surge(cvd_slope, threshold_percentile=80):
        """
        Detect significant CVD surges (strong buying/selling pressure)

        Args:
            cvd_slope: CVD slope series
            threshold_percentile: Percentile for surge detection (80 = top 20%)

        Returns:
            tuple: (bullish_surge, bearish_surge) boolean series
        """
        positive_threshold = cvd_slope.quantile(threshold_percentile / 100)
        negative_threshold = cvd_slope.quantile((100 - threshold_percentile) / 100)

        bullish_surge = cvd_slope > positive_threshold
        bearish_surge = cvd_slope < negative_threshold

        return bullish_surge, bearish_surge

    @staticmethod
    def detect_cvd_exhaustion(df, cvd, cvd_slope, lookback=20):
        """
        Detect CVD exhaustion signals

        Bullish Exhaustion: CVD very high, slope flattening, price still rising
        Bearish Exhaustion: CVD very low, slope flattening, price still falling

        Args:
            df: DataFrame with price data
            cvd: CVD series
            cvd_slope: CVD slope series
            lookback: Period for analysis

        Returns:
            tuple: (bullish_exhaustion, bearish_exhaustion) boolean series
        """
        # Calculate rolling max/min CVD
        cvd_rolling_max = cvd.rolling(lookback).max()
        cvd_rolling_min = cvd.rolling(lookback).min()

        # Calculate price momentum
        price_momentum = df['close'].pct_change(lookback) * 100

        # Calculate slope change (is slope flattening?)
        slope_change = cvd_slope.diff(5)

        # Bullish exhaustion: CVD near highs, slope flattening, price up
        bullish_exhaustion = (
            (cvd >= cvd_rolling_max * 0.95) &  # CVD near highs
            (slope_change < 0) &  # Slope declining
            (price_momentum > 0)  # Price still rising
        )

        # Bearish exhaustion: CVD near lows, slope flattening, price down
        bearish_exhaustion = (
            (cvd <= cvd_rolling_min * 0.95) &  # CVD near lows
            (slope_change > 0) &  # Slope rising (becoming less negative)
            (price_momentum < 0)  # Price still falling
        )

        return bullish_exhaustion, bearish_exhaustion

    @staticmethod
    def confirm_trend_with_cvd(df, cvd, trend_direction):
        """
        Confirm if CVD supports the current trend

        Healthy uptrend: CVD should rise with price
        Healthy downtrend: CVD should fall with price

        Args:
            df: DataFrame with price data
            cvd: CVD series
            trend_direction: 1 for uptrend, -1 for downtrend

        Returns:
            Series: Boolean series indicating CVD confirmation
        """
        # Calculate short-term CVD trend
        cvd_trend = cvd.diff(10)

        # Calculate price trend
        price_trend = df['close'].diff(10)

        if trend_direction == 1:  # Uptrend
            # CVD should be positive (rising)
            confirmed = cvd_trend > 0
        else:  # Downtrend
            # CVD should be negative (falling)
            confirmed = cvd_trend < 0

        return confirmed

    @staticmethod
    def detect_cvd_reset(cvd, threshold_percentile=30):
        """
        Detect CVD reset zones (neutral territory)

        When CVD returns to neutral, market is balanced
        Next surge indicates new trend direction

        Args:
            cvd: CVD series
            threshold_percentile: Percentile for neutral zone

        Returns:
            Series: Boolean series indicating reset zones
        """
        # Calculate CVD range
        cvd_rolling_max = cvd.rolling(100).max()
        cvd_rolling_min = cvd.rolling(100).min()
        cvd_range = cvd_rolling_max - cvd_rolling_min

        # Neutral zone is within threshold of midpoint
        cvd_midpoint = (cvd_rolling_max + cvd_rolling_min) / 2
        neutral_distance = cvd_range * (threshold_percentile / 100)

        cvd_reset = abs(cvd - cvd_midpoint) <= neutral_distance

        return cvd_reset

    @staticmethod
    def add_all_cvd_indicators(df):
        """
        Add all CVD indicators to dataframe

        Args:
            df: DataFrame with OHLCV data

        Returns:
            DataFrame: Enhanced with CVD indicators
        """
        # Calculate basic CVD
        df['cvd'] = CVDAnalyzer.calculate_cvd_advanced(df, use_wick_analysis=True)

        # Calculate CVD slope
        df['cvd_slope'] = CVDAnalyzer.calculate_cvd_slope(df['cvd'], period=5)

        # Detect divergences
        bullish_div, bearish_div = CVDAnalyzer.detect_divergences(df, df['cvd'], lookback=20)
        df['cvd_bullish_divergence'] = bullish_div
        df['cvd_bearish_divergence'] = bearish_div

        # Detect surges
        bullish_surge, bearish_surge = CVDAnalyzer.detect_cvd_surge(df['cvd_slope'])
        df['cvd_bullish_surge'] = bullish_surge
        df['cvd_bearish_surge'] = bearish_surge

        # Detect exhaustion
        bullish_exh, bearish_exh = CVDAnalyzer.detect_cvd_exhaustion(
            df, df['cvd'], df['cvd_slope']
        )
        df['cvd_bullish_exhaustion'] = bullish_exh
        df['cvd_bearish_exhaustion'] = bearish_exh

        # Detect reset zones
        df['cvd_reset'] = CVDAnalyzer.detect_cvd_reset(df['cvd'])

        return df


def test_cvd_analyzer():
    """Test CVD analyzer with sample data"""
    import sys
    sys.path.append('.')

    # Load some real data if available
    try:
        df = pd.read_csv('data/eth_usd_60m_1825d.csv')
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        print("Testing CVD Analyzer...")
        print("=" * 60)

        # Add CVD indicators
        df = CVDAnalyzer.add_all_cvd_indicators(df)

        print(f"\nCVD calculated for {len(df)} candles")
        print(f"CVD range: {df['cvd'].min():.2f} to {df['cvd'].max():.2f}")
        print(f"\nBullish divergences detected: {df['cvd_bullish_divergence'].sum()}")
        print(f"Bearish divergences detected: {df['cvd_bearish_divergence'].sum()}")
        print(f"Bullish surges detected: {df['cvd_bullish_surge'].sum()}")
        print(f"Bearish surges detected: {df['cvd_bearish_surge'].sum()}")

        # Show latest values
        print("\n" + "=" * 60)
        print("Latest CVD readings:")
        print("=" * 60)
        print(df[['timestamp', 'close', 'cvd', 'cvd_slope',
                  'cvd_bullish_surge', 'cvd_bearish_surge']].tail(10))

    except FileNotFoundError:
        print("No data file found. Run coinbase_collector.py first.")


if __name__ == "__main__":
    test_cvd_analyzer()
