"""
Professional Trading Configuration

Based on CVD + Liquidity + Market Structure methodology
Following institutional trading principles
"""
import os
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# API Configuration
# =============================================================================
KRAKEN_API_KEY = os.getenv('KRAKEN_API_KEY', '')
KRAKEN_API_SECRET = os.getenv('KRAKEN_API_SECRET', '')
COINGLASS_API_KEY = os.getenv('COINGLASS_API_KEY', '')

# =============================================================================
# Trading Parameters - PROFESSIONAL APPROACH
# =============================================================================

# Leverage & Capital
LEVERAGE = 5  # Conservative leverage (5x allows for market noise)
CAPITAL = 7500  # Starting capital in USD
POSITION_SIZE_PCT = 0.95  # Maximum position size (95% of capital)

# Risk Management - THE MOST IMPORTANT SETTINGS
RISK_PER_TRADE_PCT = 1.5  # Risk 1.5% of capital per trade (adjustable 0.5-2%)
MIN_RISK_REWARD_RATIO = 2.0  # Minimum 1:2 R:R (we target 1:4 to 1:6)

# =============================================================================
# Entry Confluence System
# =============================================================================

# Minimum confluences required for entry
MIN_CONFLUENCE_SCORE = 3  # Need at least 3 confluences (3-4 = reduced size, 5+ = full size)

# Confluence weight adjustments (if implementing weighted scoring)
CONFLUENCE_WEIGHTS = {
    'liquidity_sweep': 1.5,  # Liquidity sweeps are high probability
    'cvd_divergence': 1.5,   # CVD divergences are powerful
    'order_block': 1.0,
    'structure_break': 1.0,
    'trend_aligned': 0.5,
    'structure_strength': 0.5,
    'volume_spike': 0.5
}

# =============================================================================
# CVD (Cumulative Volume Delta) Parameters
# =============================================================================

# CVD calculation method
CVD_USE_WICK_ANALYSIS = True  # Use advanced wick-based calculation

# CVD divergence detection
CVD_DIVERGENCE_LOOKBACK = 20  # Candles to look back for divergence

# CVD surge detection
CVD_SURGE_PERCENTILE = 80  # Top 20% of slopes = surge

# CVD slope calculation
CVD_SLOPE_PERIOD = 5  # Period for slope calculation

# CVD exhaustion detection
CVD_EXHAUSTION_LOOKBACK = 20  # Period for exhaustion analysis

# =============================================================================
# Liquidity Cluster Parameters
# =============================================================================

# Swing point detection
SWING_POINT_ORDER = 5  # Number of candles on each side for swing point

# Equal highs/lows detection
EQUAL_LEVEL_TOLERANCE_PCT = 0.2  # 0.2% tolerance for "equal" levels

# Liquidity sweep detection
LIQUIDITY_SWEEP_LOOKBACK = 3  # Candles to confirm sweep reversal

# Volume profile
VOLUME_PROFILE_BINS = 50  # Number of price bins for volume profile

# Volume spike requirement
VOLUME_SPIKE_MULTIPLIER = 1.5  # 1.5x average volume required

# =============================================================================
# Market Structure Parameters
# =============================================================================

# Trend determination
MARKET_TREND_LOOKBACK = 20  # Recent structure to analyze for trend

# Structure strength
MIN_STRUCTURE_STRENGTH = 60  # Minimum structure consistency (0-100)

# Order block detection
ORDER_BLOCK_LOOKBACK = 50  # Period for identifying order blocks
ORDER_BLOCK_MIN_MOVE_PCT = 1.0  # Minimum % move to qualify as order block

# =============================================================================
# Stop Loss Configuration
# =============================================================================

# Stop loss methods (in order of preference):
# 1. Order block based (just beyond OB)
# 2. Liquidity sweep based (beyond sweep wick)
# 3. Structure based (below/above swing point)

STOP_LOSS_PCT = 2.5  # Default stop loss percentage (if structure-based)
MIN_STOP_DISTANCE_PCT = 1.0  # Minimum stop distance (avoid too tight stops)

# Stop loss adjustments
STOP_LOSS_BUFFER_PCT = 0.2  # Additional buffer beyond structure (0.2%)

# =============================================================================
# Take Profit Configuration
# =============================================================================

# Scaled exit approach (professional standard)
TP1_RATIO = 2.0  # 1:2 R:R (33% exit)
TP2_RATIO = 4.0  # 1:4 R:R (33% exit)
TP3_RATIO = 6.0  # 1:6 R:R (34% exit - let winners run)

# Take profit adjustments
USE_LIQUIDITY_VOIDS_AS_TARGETS = True  # Target low volume areas
USE_OPPOSITE_LIQUIDITY_AS_TARGETS = True  # Target BSL for longs, SSL for shorts

# =============================================================================
# Trade Management
# =============================================================================

# Maximum hold time
MAX_HOLD_TIME_HOURS = 72  # Max 72 hours (3 days) - swing trading timeframe

# Breakeven rules
MOVE_TO_BREAKEVEN_AFTER_TP1 = True  # Move stop to BE after TP1
TRAIL_STOP_AFTER_TP2 = True  # Trail stop after TP2

# Trailing stop method
TRAILING_STOP_METHOD = 'structure'  # 'structure' or 'atr' or 'percentage'
TRAILING_STOP_ATR_MULTIPLIER = 1.5  # If using ATR method

# =============================================================================
# Market Regime Filter (Optional but Recommended)
# =============================================================================

# Only trade when market conditions are favorable
USE_MARKET_REGIME_FILTER = False  # Set True to only trade strong trends

# Regime requirements
MIN_MARKET_TREND_STRENGTH = 60  # Minimum trend consistency
SKIP_CONSOLIDATION = True  # Skip trades when market is ranging

# =============================================================================
# Additional Filters
# =============================================================================

# Time filters
SKIP_LOW_LIQUIDITY_HOURS = False  # Skip certain hours (if True, define below)
LOW_LIQUIDITY_HOURS = [0, 1, 2, 3, 4, 5]  # Hours to skip (UTC)

# Volatility filters
SKIP_EXTREME_VOLATILITY = True  # Skip when volatility is too high
VOLATILITY_THRESHOLD_PERCENTILE = 90  # Top 10% volatility = skip

# CVD reset zones
SKIP_CVD_RESET_ZONES = True  # Don't trade when CVD is neutral

# =============================================================================
# Data Collection
# =============================================================================

TIMEFRAME = '1h'  # Hourly candles for swing trading
LOOKBACK_DAYS = 1825  # 5 years of historical data
PAIR = 'ETHUSD'

# =============================================================================
# Backtesting Parameters
# =============================================================================

# Trading costs (CoinDCX India rates - adjust for your exchange)
SLIPPAGE_PCT = 0.05  # 0.05% slippage per trade
TRADING_FEE_MAKER_PCT = 0.04  # 0.04% maker fee
TRADING_FEE_TAKER_PCT = 0.08  # 0.08% taker fee (assume taker for all trades)
FUNDING_RATE_HOURLY = 0.0034  # 0.0034% per hour (average funding rate)

# =============================================================================
# File Paths
# =============================================================================

DATA_DIR = 'data'
RESULTS_DIR = 'results'
LOGS_DIR = 'logs'
JOURNAL_DIR = 'journal'  # For trade journal entries

# =============================================================================
# API Endpoints
# =============================================================================

KRAKEN_REST_URL = 'https://api.kraken.com'
KRAKEN_WS_URL = 'wss://ws.kraken.com'
COINGLASS_API_URL = 'https://open-api.coinglass.com/public/v2'

# =============================================================================
# Create Required Directories
# =============================================================================

for directory in [DATA_DIR, RESULTS_DIR, LOGS_DIR, JOURNAL_DIR]:
    os.makedirs(directory, exist_ok=True)

# =============================================================================
# Performance Targets (Realistic Based on Research)
# =============================================================================

"""
Expected Performance with Professional Strategy:

Win Rate: 40-50%
Average R:R: 1:3 to 1:4
Annual Return: 60-100% (highly profitable)
Max Drawdown: <20%
Sharpe Ratio: >1.5

These are REALISTIC and ACHIEVABLE targets based on:
- CVD order flow analysis
- Liquidity hunting with institutions
- Proper risk management (1-2% per trade)
- Confluence-based entries (quality over quantity)

Compare to old strategy:
- Old: 100% loss over full cycle
- New: Sustainable profitable trading

The difference:
- Edge: CVD + Liquidity + Structure (proven institutional methods)
- Discipline: Strict confluence requirements (no low-quality setups)
- Risk Management: Proper position sizing and scaled exits
- Psychology: Following a proven process, not gambling
"""

# =============================================================================
# Trading Rules (Print for Reference)
# =============================================================================

def print_trading_rules():
    """Print the core trading rules"""
    print("=" * 70)
    print("PROFESSIONAL TRADING RULES")
    print("=" * 70)
    print("\n📋 ENTRY CHECKLIST (Need 5+ for A+ Setup):")
    print("  ☐ Liquidity sweep occurred (BSL/SSL)")
    print("  ☐ CVD showing divergence or surge")
    print("  ☐ Order block holding/breaking")
    print("  ☐ Structure break in trade direction (BOS/CHOCH)")
    print("  ☐ Key S/R level alignment")
    print("  ☐ Higher timeframe confirmation")
    print("  ☐ Clean price action")
    print("\n💰 RISK MANAGEMENT:")
    print(f"  • Risk per trade: {RISK_PER_TRADE_PCT}% of capital")
    print(f"  • Minimum R:R: 1:{MIN_RISK_REWARD_RATIO}")
    print(f"  • Position sizing: Risk-based (not fixed %)")
    print("\n🎯 EXITS:")
    print(f"  • TP1 at 1:{TP1_RATIO} R:R (exit 33%)")
    print(f"  • TP2 at 1:{TP2_RATIO} R:R (exit 33%)")
    print(f"  • TP3 at 1:{TP3_RATIO} R:R (exit 34%)")
    print("  • Stop to breakeven after TP1")
    print("  • Trail stop after TP2")
    print("\n🚫 DON'T TRADE IF:")
    print("  • Less than 3 confluences")
    print("  • CVD showing exhaustion")
    print("  • In liquidity void (range, not breakout)")
    print("  • Extreme volatility (if filter enabled)")
    print("\n✅ DISCIPLINE:")
    print("  • Follow the checklist EVERY trade")
    print("  • No revenge trading after losses")
    print("  • Max 3-5 trades per day")
    print("  • Journal every trade with screenshots")
    print("=" * 70)

if __name__ == "__main__":
    print_trading_rules()
