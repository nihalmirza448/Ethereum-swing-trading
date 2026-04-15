"""
Market Structure Analysis Module

This module analyzes market structure to identify:
- BOS (Break of Structure) - trend continuation
- CHOCH (Change of Character) - trend reversal
- HH/HL (Higher Highs/Higher Lows) - uptrend structure
- LH/LL (Lower Highs/Lower Lows) - downtrend structure
- Order Blocks - institutional support/resistance zones
"""

import pandas as pd
import numpy as np


class MarketStructure:
    """
    Professional market structure analysis for trend identification
    and institutional level detection
    """

    @staticmethod
    def identify_market_structure_points(df, swing_highs, swing_lows):
        """
        Identify HH, HL, LH, LL pattern

        Args:
            df: DataFrame with price data
            swing_highs: Boolean series of swing highs
            swing_lows: Boolean series of swing lows

        Returns:
            DataFrame: Enhanced with structure labels
        """
        df['structure_type'] = ''

        # Get swing high and low prices with indices
        swing_high_data = df[swing_highs][['high']].copy()
        swing_low_data = df[swing_lows][['low']].copy()

        # Label swing highs as HH or LH
        for i in range(1, len(swing_high_data)):
            current_idx = swing_high_data.index[i]
            prev_idx = swing_high_data.index[i-1]

            current_high = swing_high_data.iloc[i]['high']
            prev_high = swing_high_data.iloc[i-1]['high']

            if current_high > prev_high:
                df.loc[current_idx, 'structure_type'] = 'HH'  # Higher High
            else:
                df.loc[current_idx, 'structure_type'] = 'LH'  # Lower High

        # Label swing lows as HL or LL
        for i in range(1, len(swing_low_data)):
            current_idx = swing_low_data.index[i]
            prev_idx = swing_low_data.index[i-1]

            current_low = swing_low_data.iloc[i]['low']
            prev_low = swing_low_data.iloc[i-1]['low']

            if current_low > prev_low:
                df.loc[current_idx, 'structure_type'] = 'HL'  # Higher Low
            else:
                df.loc[current_idx, 'structure_type'] = 'LL'  # Lower Low

        return df

    @staticmethod
    def detect_bos(df):
        """
        Detect Break of Structure (BOS)

        BOS = Price breaks recent structure in direction of trend
        Bullish BOS: Price breaks above recent high (in uptrend)
        Bearish BOS: Price breaks below recent low (in downtrend)

        Args:
            df: DataFrame with structure points

        Returns:
            tuple: (bullish_bos, bearish_bos) boolean series
        """
        bullish_bos = pd.Series(False, index=df.index)
        bearish_bos = pd.Series(False, index=df.index)

        # Get recent structure points
        structure_points = df[df['structure_type'].isin(['HH', 'HL', 'LH', 'LL'])]

        for i in range(20, len(df)):
            current = df.iloc[i]
            recent_structure = structure_points[structure_points.index < i].tail(5)

            if len(recent_structure) == 0:
                continue

            # Check for bullish BOS (breaking above recent high)
            recent_highs = recent_structure[recent_structure['structure_type'].isin(['HH', 'LH'])]
            if len(recent_highs) > 0:
                recent_high = recent_highs.iloc[-1]['high']
                if current['close'] > recent_high:
                    # Check if trend is up (last structure was HH or HL)
                    last_structure = recent_structure.iloc[-1]['structure_type']
                    if last_structure in ['HH', 'HL']:
                        bullish_bos.iloc[i] = True

            # Check for bearish BOS (breaking below recent low)
            recent_lows = recent_structure[recent_structure['structure_type'].isin(['HL', 'LL'])]
            if len(recent_lows) > 0:
                recent_low = recent_lows.iloc[-1]['low']
                if current['close'] < recent_low:
                    # Check if trend is down (last structure was LH or LL)
                    last_structure = recent_structure.iloc[-1]['structure_type']
                    if last_structure in ['LH', 'LL']:
                        bearish_bos.iloc[i] = True

        return bullish_bos, bearish_bos

    @staticmethod
    def detect_choch(df):
        """
        Detect Change of Character (CHOCH)

        CHOCH = Early sign of trend reversal
        Bullish CHOCH: In downtrend, price breaks above recent high
        Bearish CHOCH: In uptrend, price breaks below recent low

        Args:
            df: DataFrame with structure points

        Returns:
            tuple: (bullish_choch, bearish_choch) boolean series
        """
        bullish_choch = pd.Series(False, index=df.index)
        bearish_choch = pd.Series(False, index=df.index)

        structure_points = df[df['structure_type'].isin(['HH', 'HL', 'LH', 'LL'])]

        for i in range(20, len(df)):
            current = df.iloc[i]
            recent_structure = structure_points[structure_points.index < i].tail(5)

            if len(recent_structure) < 2:
                continue

            last_structure = recent_structure.iloc[-1]['structure_type']

            # Bullish CHOCH: In downtrend (LH/LL), break above recent high
            if last_structure in ['LH', 'LL']:
                recent_highs = recent_structure[recent_structure['structure_type'].isin(['LH', 'LL'])]
                if len(recent_highs) > 0:
                    recent_high = recent_highs['high'].max()
                    if current['close'] > recent_high:
                        bullish_choch.iloc[i] = True

            # Bearish CHOCH: In uptrend (HH/HL), break below recent low
            if last_structure in ['HH', 'HL']:
                recent_lows = recent_structure[recent_structure['structure_type'].isin(['HH', 'HL'])]
                if len(recent_lows) > 0:
                    recent_low = recent_lows['low'].min()
                    if current['close'] < recent_low:
                        bearish_choch.iloc[i] = True

        return bullish_choch, bearish_choch

    @staticmethod
    def identify_order_blocks(df, lookback=50):
        """
        Identify Order Blocks

        Bullish Order Block: Last bearish candle before strong bullish move
        Bearish Order Block: Last bullish candle before strong bearish move

        Order blocks represent zones where institutions placed orders

        Args:
            df: DataFrame with OHLC data
            lookback: Period to identify strong moves

        Returns:
            DataFrame: With order block levels
        """
        df['bullish_ob_high'] = np.nan
        df['bullish_ob_low'] = np.nan
        df['bearish_ob_high'] = np.nan
        df['bearish_ob_low'] = np.nan

        for i in range(10, len(df)):
            # Look for bullish order blocks
            # Find last bearish candle before strong up move
            if df.iloc[i]['close'] > df.iloc[i]['open']:  # Current is bullish
                # Check if there's a strong move (>1%)
                move_pct = (df.iloc[i]['close'] - df.iloc[i-5]['close']) / df.iloc[i-5]['close'] * 100

                if move_pct > 1.0:  # Strong bullish move
                    # Find last bearish candle before this move
                    for j in range(i-1, max(i-10, 0), -1):
                        if df.iloc[j]['close'] < df.iloc[j]['open']:  # Bearish candle
                            # This is the order block
                            df.loc[i, 'bullish_ob_high'] = df.iloc[j]['high']
                            df.loc[i, 'bullish_ob_low'] = df.iloc[j]['low']
                            break

            # Look for bearish order blocks
            # Find last bullish candle before strong down move
            if df.iloc[i]['close'] < df.iloc[i]['open']:  # Current is bearish
                # Check if there's a strong move (>1%)
                move_pct = (df.iloc[i-5]['close'] - df.iloc[i]['close']) / df.iloc[i-5]['close'] * 100

                if move_pct > 1.0:  # Strong bearish move
                    # Find last bullish candle before this move
                    for j in range(i-1, max(i-10, 0), -1):
                        if df.iloc[j]['close'] > df.iloc[j]['open']:  # Bullish candle
                            # This is the order block
                            df.loc[i, 'bearish_ob_high'] = df.iloc[j]['high']
                            df.loc[i, 'bearish_ob_low'] = df.iloc[j]['low']
                            break

        # Forward fill order blocks (they remain valid until tested)
        df['bullish_ob_high'] = df['bullish_ob_high'].ffill()
        df['bullish_ob_low'] = df['bullish_ob_low'].ffill()
        df['bearish_ob_high'] = df['bearish_ob_high'].ffill()
        df['bearish_ob_low'] = df['bearish_ob_low'].ffill()

        return df

    @staticmethod
    def detect_order_block_test(df):
        """
        Detect when price tests (respects or breaks) order blocks

        Args:
            df: DataFrame with order blocks

        Returns:
            tuple: (bullish_ob_hold, bearish_ob_hold) boolean series
        """
        bullish_ob_hold = pd.Series(False, index=df.index)
        bearish_ob_hold = pd.Series(False, index=df.index)

        for i in range(len(df)):
            current = df.iloc[i]

            # Test bullish order block (support)
            if pd.notna(current['bullish_ob_high']) and pd.notna(current['bullish_ob_low']):
                # Check if price entered the OB zone
                if current['low'] <= current['bullish_ob_high']:
                    # Check if it held (closed above OB low)
                    if current['close'] > current['bullish_ob_low']:
                        bullish_ob_hold.iloc[i] = True

            # Test bearish order block (resistance)
            if pd.notna(current['bearish_ob_high']) and pd.notna(current['bearish_ob_low']):
                # Check if price entered the OB zone
                if current['high'] >= current['bearish_ob_low']:
                    # Check if it held (closed below OB high)
                    if current['close'] < current['bearish_ob_high']:
                        bearish_ob_hold.iloc[i] = True

        return bullish_ob_hold, bearish_ob_hold

    @staticmethod
    def determine_trend(df, lookback=20):
        """
        Determine current trend based on structure

        Args:
            df: DataFrame with structure labels
            lookback: Recent structure to analyze

        Returns:
            Series: Trend direction (1=up, -1=down, 0=neutral)
        """
        trend = pd.Series(0, index=df.index)

        structure_points = df[df['structure_type'].isin(['HH', 'HL', 'LH', 'LL'])]

        for i in range(lookback, len(df)):
            # Get recent structure
            recent_structure = structure_points[structure_points.index <= i].tail(lookback)

            if len(recent_structure) == 0:
                continue

            # Count structure types
            hh_count = (recent_structure['structure_type'] == 'HH').sum()
            hl_count = (recent_structure['structure_type'] == 'HL').sum()
            lh_count = (recent_structure['structure_type'] == 'LH').sum()
            ll_count = (recent_structure['structure_type'] == 'LL').sum()

            bullish_structure = hh_count + hl_count
            bearish_structure = lh_count + ll_count

            # Determine trend
            if bullish_structure > bearish_structure * 1.5:
                trend.iloc[i] = 1  # Uptrend
            elif bearish_structure > bullish_structure * 1.5:
                trend.iloc[i] = -1  # Downtrend
            else:
                trend.iloc[i] = 0  # Neutral/Ranging

        return trend

    @staticmethod
    def calculate_structure_strength(df):
        """
        Calculate strength of current structure

        Stronger structure = more consistent HH/HL or LH/LL pattern

        Args:
            df: DataFrame with structure labels

        Returns:
            Series: Structure strength (0-100)
        """
        strength = pd.Series(0.0, index=df.index)

        structure_points = df[df['structure_type'].isin(['HH', 'HL', 'LH', 'LL'])]

        for i in range(20, len(df)):
            recent_structure = structure_points[structure_points.index <= i].tail(5)

            if len(recent_structure) < 3:
                continue

            # Check consistency
            types = recent_structure['structure_type'].values

            # Count bullish vs bearish structure
            bullish = sum([1 for t in types if t in ['HH', 'HL']])
            bearish = sum([1 for t in types if t in ['LH', 'LL']])

            # Strength = consistency of direction
            total = len(types)
            max_count = max(bullish, bearish)

            strength.iloc[i] = (max_count / total) * 100

        return strength

    @staticmethod
    def add_all_market_structure_indicators(df, swing_highs, swing_lows):
        """
        Add all market structure indicators

        Args:
            df: DataFrame with price data
            swing_highs: Boolean series of swing highs
            swing_lows: Boolean series of swing lows

        Returns:
            DataFrame: Enhanced with market structure indicators
        """
        # Identify structure points (HH, HL, LH, LL)
        df = MarketStructure.identify_market_structure_points(df, swing_highs, swing_lows)

        # Detect BOS and CHOCH
        bullish_bos, bearish_bos = MarketStructure.detect_bos(df)
        df['bullish_bos'] = bullish_bos
        df['bearish_bos'] = bearish_bos

        bullish_choch, bearish_choch = MarketStructure.detect_choch(df)
        df['bullish_choch'] = bullish_choch
        df['bearish_choch'] = bearish_choch

        # Identify order blocks
        df = MarketStructure.identify_order_blocks(df)

        # Detect order block tests
        bullish_ob_hold, bearish_ob_hold = MarketStructure.detect_order_block_test(df)
        df['bullish_ob_hold'] = bullish_ob_hold
        df['bearish_ob_hold'] = bearish_ob_hold

        # Determine trend
        df['market_trend'] = MarketStructure.determine_trend(df)

        # Calculate structure strength
        df['structure_strength'] = MarketStructure.calculate_structure_strength(df)

        return df


def test_market_structure():
    """Test market structure analyzer with sample data"""
    import sys
    sys.path.append('.')
    from liquidity_analyzer import LiquidityAnalyzer

    try:
        df = pd.read_csv('data/eth_usd_60m_1825d.csv')
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        print("Testing Market Structure Analyzer...")
        print("=" * 60)

        # Need swing points first
        swing_highs, swing_lows = LiquidityAnalyzer.identify_swing_points(df)

        # Add market structure indicators
        df = MarketStructure.add_all_market_structure_indicators(df, swing_highs, swing_lows)

        print(f"\nStructure points identified:")
        print(f"  HH (Higher Highs): {(df['structure_type'] == 'HH').sum()}")
        print(f"  HL (Higher Lows): {(df['structure_type'] == 'HL').sum()}")
        print(f"  LH (Lower Highs): {(df['structure_type'] == 'LH').sum()}")
        print(f"  LL (Lower Lows): {(df['structure_type'] == 'LL').sum()}")

        print(f"\nBullish BOS detected: {df['bullish_bos'].sum()}")
        print(f"Bearish BOS detected: {df['bearish_bos'].sum()}")
        print(f"Bullish CHOCH detected: {df['bullish_choch'].sum()}")
        print(f"Bearish CHOCH detected: {df['bearish_choch'].sum()}")

        print(f"\nBullish Order Block holds: {df['bullish_ob_hold'].sum()}")
        print(f"Bearish Order Block holds: {df['bearish_ob_hold'].sum()}")

        # Show latest structure
        print("\n" + "=" * 60)
        print("Latest Market Structure:")
        print("=" * 60)
        recent = df[['timestamp', 'close', 'structure_type', 'market_trend',
                     'structure_strength']].tail(20)
        print(recent[recent['structure_type'] != ''])

        # Show current trend
        current_trend = df.iloc[-1]['market_trend']
        trend_label = 'UPTREND' if current_trend == 1 else 'DOWNTREND' if current_trend == -1 else 'NEUTRAL'
        print(f"\nCurrent Market Trend: {trend_label}")
        print(f"Structure Strength: {df.iloc[-1]['structure_strength']:.1f}%")

    except FileNotFoundError:
        print("No data file found. Run coinbase_collector.py first.")


if __name__ == "__main__":
    test_market_structure()
