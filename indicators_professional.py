"""
Professional Technical Indicators

Integrates:
- CVD (Cumulative Volume Delta) analysis
- Liquidity cluster detection
- Market structure analysis
- Traditional indicators (minimal, as per methodology)
"""

import pandas as pd
import numpy as np
try:
    import config_professional as config
except ImportError:
    import config

from cvd_analyzer import CVDAnalyzer
from liquidity_analyzer import LiquidityAnalyzer
from market_structure import MarketStructure


class ProfessionalIndicators:
    """
    Unified indicator system for professional trading strategy

    Combines:
    - CVD order flow analysis
    - Liquidity hunting signals
    - Market structure patterns
    - Essential traditional indicators
    """

    @staticmethod
    def add_all_indicators(df, timeframe='1h'):
        """
        Add all professional trading indicators to dataframe

        This is the main function called by the backtester

        Args:
            df: DataFrame with OHLCV data
            timeframe: Timeframe string ('1h', '4h', '1d')

        Returns:
            DataFrame: Enhanced with all indicators
        """
        print("Calculating professional indicators...")
        print("  Step 1/4: CVD Analysis...")

        # 1. CVD ANALYSIS
        df = CVDAnalyzer.add_all_cvd_indicators(df)

        print("  Step 2/4: Liquidity Clusters...")

        # 2. LIQUIDITY ANALYSIS
        df = LiquidityAnalyzer.add_all_liquidity_indicators(df)

        print("  Step 3/4: Market Structure...")

        # 3. MARKET STRUCTURE ANALYSIS
        # (Needs swing points from liquidity analysis)
        swing_highs = df['swing_high']
        swing_lows = df['swing_low']
        df = MarketStructure.add_all_market_structure_indicators(df, swing_highs, swing_lows)

        print("  Step 4/4: Traditional Indicators...")

        # 4. TRADITIONAL INDICATORS (Minimal set)
        df = ProfessionalIndicators.add_traditional_indicators(df)

        print("✅ All indicators calculated successfully!")

        return df

    @staticmethod
    def add_traditional_indicators(df):
        """
        Add minimal traditional indicators

        Professional approach: Less is more
        Focus on price action, not indicator overload

        Args:
            df: DataFrame with OHLC data

        Returns:
            DataFrame: Enhanced with traditional indicators
        """
        # Moving Averages (for trend context only)
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema_100'] = df['close'].ewm(span=100, adjust=False).mean()
        df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()

        # RSI (only for extreme levels)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # ATR (for volatility-based stops)
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        df['atr'] = true_range.rolling(window=14).mean()

        # Bollinger Bands (for volatility context)
        sma_20 = df['close'].rolling(window=20).mean()
        std_20 = df['close'].rolling(window=20).std()
        df['bb_upper'] = sma_20 + (std_20 * 2)
        df['bb_middle'] = sma_20
        df['bb_lower'] = sma_20 - (std_20 * 2)
        df['bb_bandwidth'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']

        # Volume analysis (already have volume_spike from liquidity module)
        if 'volume_ma' not in df.columns:
            df['volume_ma'] = df['volume'].rolling(window=20).mean()

        return df

    @staticmethod
    def calculate_signal_strength(df, idx):
        """
        Calculate overall signal strength at a given point

        Combines multiple indicators to give confidence level

        Args:
            df: DataFrame with all indicators
            idx: Index to calculate for

        Returns:
            dict: Signal strength breakdown
        """
        row = df.iloc[idx]

        signals = {
            'bullish': 0,
            'bearish': 0,
            'neutral': 0,
            'details': []
        }

        # CVD signals
        if row.get('cvd_bullish_divergence', False):
            signals['bullish'] += 2
            signals['details'].append('CVD bullish divergence')
        if row.get('cvd_bearish_divergence', False):
            signals['bearish'] += 2
            signals['details'].append('CVD bearish divergence')
        if row.get('cvd_bullish_surge', False):
            signals['bullish'] += 1
            signals['details'].append('CVD bullish surge')
        if row.get('cvd_bearish_surge', False):
            signals['bearish'] += 1
            signals['details'].append('CVD bearish surge')

        # Liquidity signals
        if row.get('ssl_sweep', False):
            signals['bullish'] += 2
            signals['details'].append('SSL sweep (bullish)')
        if row.get('bsl_sweep', False):
            signals['bearish'] += 2
            signals['details'].append('BSL sweep (bearish)')

        # Structure signals
        if row.get('bullish_bos', False):
            signals['bullish'] += 1
            signals['details'].append('Bullish BOS')
        if row.get('bearish_bos', False):
            signals['bearish'] += 1
            signals['details'].append('Bearish BOS')
        if row.get('bullish_choch', False):
            signals['bullish'] += 2
            signals['details'].append('Bullish CHOCH')
        if row.get('bearish_choch', False):
            signals['bearish'] += 2
            signals['details'].append('Bearish CHOCH')

        # Order blocks
        if row.get('bullish_ob_hold', False):
            signals['bullish'] += 1
            signals['details'].append('Bullish OB hold')
        if row.get('bearish_ob_hold', False):
            signals['bearish'] += 1
            signals['details'].append('Bearish OB hold')

        # Trend alignment
        market_trend = row.get('market_trend', 0)
        if market_trend == 1:
            signals['bullish'] += 1
            signals['details'].append('Uptrend')
        elif market_trend == -1:
            signals['bearish'] += 1
            signals['details'].append('Downtrend')
        else:
            signals['neutral'] += 1

        # Calculate dominant signal
        if signals['bullish'] > signals['bearish'] and signals['bullish'] >= 3:
            signals['dominant'] = 'BULLISH'
            signals['strength'] = signals['bullish']
        elif signals['bearish'] > signals['bullish'] and signals['bearish'] >= 3:
            signals['dominant'] = 'BEARISH'
            signals['strength'] = signals['bearish']
        else:
            signals['dominant'] = 'NEUTRAL'
            signals['strength'] = 0

        return signals

    @staticmethod
    def validate_data_quality(df):
        """
        Validate that all required indicators are present and valid

        Args:
            df: DataFrame with indicators

        Returns:
            tuple: (is_valid, missing_indicators, error_message)
        """
        required_indicators = [
            # CVD indicators
            'cvd', 'cvd_slope', 'cvd_bullish_divergence', 'cvd_bearish_divergence',
            'cvd_bullish_surge', 'cvd_bearish_surge',

            # Liquidity indicators
            'swing_high', 'swing_low', 'bsl_level', 'ssl_level',
            'bsl_sweep', 'ssl_sweep', 'equal_highs', 'equal_lows',

            # Market structure indicators
            'structure_type', 'bullish_bos', 'bearish_bos',
            'bullish_choch', 'bearish_choch', 'market_trend',

            # Order blocks
            'bullish_ob_high', 'bullish_ob_low', 'bearish_ob_high', 'bearish_ob_low',
            'bullish_ob_hold', 'bearish_ob_hold',

            # Traditional indicators
            'ema_50', 'ema_100', 'ema_200', 'rsi', 'atr'
        ]

        missing = []
        for indicator in required_indicators:
            if indicator not in df.columns:
                missing.append(indicator)

        if missing:
            error_msg = f"Missing indicators: {', '.join(missing)}"
            return False, missing, error_msg

        # Check for excessive NaN values
        nan_counts = df[required_indicators].isna().sum()
        excessive_nan = nan_counts[nan_counts > len(df) * 0.3]  # More than 30% NaN

        if len(excessive_nan) > 0:
            error_msg = f"Excessive NaN values in: {', '.join(excessive_nan.index.tolist())}"
            return False, excessive_nan.index.tolist(), error_msg

        return True, [], "All indicators present and valid"

    @staticmethod
    def get_current_market_state(df, idx=-1):
        """
        Get comprehensive market state at given index

        Useful for displaying current conditions or debugging

        Args:
            df: DataFrame with all indicators
            idx: Index to check (default: -1 for latest)

        Returns:
            dict: Current market state
        """
        row = df.iloc[idx]

        state = {
            'timestamp': row.get('timestamp', 'N/A'),
            'price': row['close'],

            # CVD
            'cvd': row.get('cvd', np.nan),
            'cvd_slope': row.get('cvd_slope', np.nan),
            'cvd_signals': [],

            # Liquidity
            'bsl_level': row.get('bsl_level', np.nan),
            'ssl_level': row.get('ssl_level', np.nan),
            'liquidity_signals': [],

            # Structure
            'structure_type': row.get('structure_type', ''),
            'market_trend': row.get('market_trend', 0),
            'structure_strength': row.get('structure_strength', 0),
            'structure_signals': [],

            # Order blocks
            'bullish_ob': f"{row.get('bullish_ob_low', np.nan):.2f} - {row.get('bullish_ob_high', np.nan):.2f}",
            'bearish_ob': f"{row.get('bearish_ob_low', np.nan):.2f} - {row.get('bearish_ob_high', np.nan):.2f}",

            # Traditional
            'rsi': row.get('rsi', np.nan),
            'atr': row.get('atr', np.nan),
        }

        # Collect active signals
        if row.get('cvd_bullish_divergence', False):
            state['cvd_signals'].append('Bullish Divergence')
        if row.get('cvd_bearish_divergence', False):
            state['cvd_signals'].append('Bearish Divergence')
        if row.get('cvd_bullish_surge', False):
            state['cvd_signals'].append('Bullish Surge')
        if row.get('cvd_bearish_surge', False):
            state['cvd_signals'].append('Bearish Surge')

        if row.get('ssl_sweep', False):
            state['liquidity_signals'].append('SSL Sweep')
        if row.get('bsl_sweep', False):
            state['liquidity_signals'].append('BSL Sweep')
        if row.get('equal_highs', False):
            state['liquidity_signals'].append('Equal Highs')
        if row.get('equal_lows', False):
            state['liquidity_signals'].append('Equal Lows')

        if row.get('bullish_bos', False):
            state['structure_signals'].append('Bullish BOS')
        if row.get('bearish_bos', False):
            state['structure_signals'].append('Bearish BOS')
        if row.get('bullish_choch', False):
            state['structure_signals'].append('Bullish CHOCH')
        if row.get('bearish_choch', False):
            state['structure_signals'].append('Bearish CHOCH')

        return state


def test_professional_indicators():
    """Test indicator system with real data"""
    import sys
    sys.path.append('.')

    try:
        df = pd.read_csv('data/eth_usd_60m_1825d.csv')
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        print("Testing Professional Indicator System...")
        print("=" * 70)
        print(f"Data loaded: {len(df)} candles")
        print(f"Date range: {df.iloc[0]['timestamp']} to {df.iloc[-1]['timestamp']}")

        # Add all indicators
        df = ProfessionalIndicators.add_all_indicators(df)

        # Validate data quality
        is_valid, missing, error_msg = ProfessionalIndicators.validate_data_quality(df)

        print("\n" + "=" * 70)
        if is_valid:
            print("✅ DATA QUALITY: EXCELLENT")
            print("All required indicators present and valid")
        else:
            print("❌ DATA QUALITY: ISSUES DETECTED")
            print(f"Error: {error_msg}")
            return

        # Show current market state
        print("\n" + "=" * 70)
        print("CURRENT MARKET STATE")
        print("=" * 70)

        state = ProfessionalIndicators.get_current_market_state(df)

        print(f"\n📊 Price: ${state['price']:.2f}")
        print(f"📅 Timestamp: {state['timestamp']}")

        print(f"\n💹 CVD: {state['cvd']:.2f} (Slope: {state['cvd_slope']:.2f})")
        if state['cvd_signals']:
            print(f"   Signals: {', '.join(state['cvd_signals'])}")

        print(f"\n🎯 Liquidity Levels:")
        print(f"   BSL: ${state['bsl_level']:.2f}")
        print(f"   SSL: ${state['ssl_level']:.2f}")
        if state['liquidity_signals']:
            print(f"   Signals: {', '.join(state['liquidity_signals'])}")

        trend_label = 'UPTREND' if state['market_trend'] == 1 else 'DOWNTREND' if state['market_trend'] == -1 else 'NEUTRAL'
        print(f"\n📈 Market Structure:")
        print(f"   Trend: {trend_label}")
        print(f"   Strength: {state['structure_strength']:.1f}%")
        print(f"   Last Structure: {state['structure_type']}")
        if state['structure_signals']:
            print(f"   Signals: {', '.join(state['structure_signals'])}")

        print(f"\n🎲 Order Blocks:")
        print(f"   Bullish: {state['bullish_ob']}")
        print(f"   Bearish: {state['bearish_ob']}")

        print(f"\n📉 Traditional:")
        print(f"   RSI: {state['rsi']:.1f}")
        print(f"   ATR: {state['atr']:.2f}")

        # Calculate signal strength
        print("\n" + "=" * 70)
        print("SIGNAL STRENGTH ANALYSIS")
        print("=" * 70)

        signals = ProfessionalIndicators.calculate_signal_strength(df, -1)
        print(f"\nDominant Signal: {signals['dominant']} (Strength: {signals['strength']})")
        print(f"\nBullish Signals: {signals['bullish']}")
        print(f"Bearish Signals: {signals['bearish']}")
        print(f"Neutral Signals: {signals['neutral']}")

        if signals['details']:
            print(f"\nActive Signals:")
            for detail in signals['details']:
                print(f"  • {detail}")

        print("\n" + "=" * 70)
        print("✅ Professional Indicator System Ready!")
        print("=" * 70)

    except FileNotFoundError:
        print("❌ No data file found. Run coinbase_collector.py first.")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_professional_indicators()
