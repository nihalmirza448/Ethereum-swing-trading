"""
Professional Trading Strategy - CVD + Liquidity + Market Structure

Based on institutional trading methodology:
- CVD analysis for order flow
- Liquidity cluster hunting
- Market structure confirmation
- Confluence-based entries (minimum 3 confirmations)
- Scaled exits with proper risk management
"""

import pandas as pd
import numpy as np
try:
    import config_professional as config
except ImportError:
    import config


class ProfessionalStrategy:
    """
    Professional trading strategy using CVD, liquidity, and market structure

    Entry Requirements (Need 5+ for A+ setup):
    ☐ Liquidity sweep occurred (BSL/SSL)
    ☐ CVD showing divergence or surge
    ☐ Order block holding/breaking
    ☐ Structure break in trade direction (BOS/CHOCH)
    ☐ Key S/R level alignment
    ☐ Higher timeframe confirmation
    ☐ Clean price action

    Risk Management:
    - 1-2% risk per trade (adjustable based on confluence)
    - Scaled exits: TP1 (33%), TP2 (33%), TP3 (34%)
    - Stop to breakeven after TP1
    - Trail stops using structure

    Target Win Rate: 40-50% (with proper R:R, highly profitable)
    """

    def __init__(self, leverage=5, capital=7500, risk_pct=1.5):
        self.leverage = leverage
        self.capital = capital
        self.risk_pct = risk_pct  # Percentage of capital to risk per trade
        self.position = None
        self.entry_price = 0
        self.entry_time = None
        self.position_size = 0
        self.stop_loss_price = 0
        self.tp1_price = 0
        self.tp2_price = 0
        self.tp3_price = 0
        self.tp1_hit = False
        self.tp2_hit = False
        self.entry_confluence_score = 0

    def calculate_confluence_score(self, df, idx):
        """
        Calculate confluence score for entry

        Returns:
            tuple: (score, direction, details_dict)

        Score interpretation:
            0-2: Skip the trade
            3-4: Consider with reduced size
            5-6: Standard size trade
            7+: Maximum confidence (rare)
        """
        row = df.iloc[idx]
        score = 0
        direction = 0  # 1 = long, -1 = short
        details = {}

        # CONFLUENCE 1: Liquidity Sweep (+1)
        if row.get('ssl_sweep', False):  # SSL swept = bullish
            score += 1
            direction = 1
            details['liquidity_sweep'] = 'SSL'
        elif row.get('bsl_sweep', False):  # BSL swept = bearish
            score += 1
            direction = -1
            details['liquidity_sweep'] = 'BSL'

        # If no sweep, check for equal highs/lows
        if score == 0:
            if row.get('equal_lows', False):  # At major support
                direction = 1
                details['at_liquidity_pool'] = 'equal_lows'
            elif row.get('equal_highs', False):  # At major resistance
                direction = -1
                details['at_liquidity_pool'] = 'equal_highs'

        # CONFLUENCE 2: CVD Confirmation (+1)
        if direction == 1:  # Looking for long
            if row.get('cvd_bullish_divergence', False):
                score += 1
                details['cvd'] = 'bullish_divergence'
            elif row.get('cvd_bullish_surge', False):
                score += 1
                details['cvd'] = 'bullish_surge'
        elif direction == -1:  # Looking for short
            if row.get('cvd_bearish_divergence', False):
                score += 1
                details['cvd'] = 'bearish_divergence'
            elif row.get('cvd_bearish_surge', False):
                score += 1
                details['cvd'] = 'bearish_surge'

        # CONFLUENCE 3: Order Block Alignment (+1)
        if direction == 1:
            if row.get('bullish_ob_hold', False):
                score += 1
                details['order_block'] = 'bullish_hold'
        elif direction == -1:
            if row.get('bearish_ob_hold', False):
                score += 1
                details['order_block'] = 'bearish_hold'

        # CONFLUENCE 4: Market Structure (+1)
        if direction == 1:
            if row.get('bullish_bos', False):
                score += 1
                details['structure'] = 'bullish_bos'
            elif row.get('bullish_choch', False):
                score += 1
                details['structure'] = 'bullish_choch'
        elif direction == -1:
            if row.get('bearish_bos', False):
                score += 1
                details['structure'] = 'bearish_bos'
            elif row.get('bearish_choch', False):
                score += 1
                details['structure'] = 'bearish_choch'

        # CONFLUENCE 5: Trend Alignment (+1)
        market_trend = row.get('market_trend', 0)
        if (direction == 1 and market_trend == 1) or (direction == -1 and market_trend == -1):
            score += 1
            details['trend_aligned'] = True

        # CONFLUENCE 6: Structure Strength (+1)
        structure_strength = row.get('structure_strength', 0)
        if structure_strength >= 60:  # Strong structure
            score += 1
            details['structure_strength'] = structure_strength

        # CONFLUENCE 7: Volume Confirmation (+1)
        volume_spike = row.get('volume_spike', 1.0)
        if volume_spike >= config.VOLUME_SPIKE_MULTIPLIER:
            score += 1
            details['volume_spike'] = volume_spike

        return score, direction, details

    def check_entry_conditions(self, df, idx):
        """
        Check if entry conditions are met

        Returns:
            tuple: (should_enter, direction, confluence_score, details)
        """
        if idx < 100:  # Need enough data
            return False, 0, 0, {}

        # Calculate confluence score
        score, direction, details = self.calculate_confluence_score(df, idx)

        # Minimum confluence requirement
        if score < config.MIN_CONFLUENCE_SCORE:
            return False, 0, score, details

        # Additional filters
        row = df.iloc[idx]

        # Don't enter if CVD shows exhaustion
        if direction == 1 and row.get('cvd_bullish_exhaustion', False):
            return False, 0, score, details
        if direction == -1 and row.get('cvd_bearish_exhaustion', False):
            return False, 0, score, details

        # Don't enter in liquidity voids (unless using as target)
        if row.get('liquidity_void', False):
            return False, 0, score, details

        return True, direction, score, details

    def calculate_position_size(self, entry_price, stop_loss_price, confluence_score):
        """
        Calculate position size based on risk percentage and confluence

        Higher confluence = can risk more (up to max 2%)
        Lower confluence = risk less

        Args:
            entry_price: Entry price
            stop_loss_price: Stop loss price
            confluence_score: Entry confluence score (3-7)

        Returns:
            float: Position size in USD
        """
        # Adjust risk based on confluence
        if confluence_score >= 5:
            risk_multiplier = 1.0  # Full risk (1.5% or 2%)
        elif confluence_score == 4:
            risk_multiplier = 0.75  # 75% of max risk
        else:  # score == 3
            risk_multiplier = 0.5  # 50% of max risk

        # Calculate risk amount
        risk_amount = self.capital * (self.risk_pct / 100) * risk_multiplier

        # Calculate stop distance
        stop_distance_pct = abs(entry_price - stop_loss_price) / entry_price

        # Position size = risk amount / stop distance / leverage
        # This ensures we only risk the specified amount
        position_size = risk_amount / stop_distance_pct

        # Don't exceed max position size
        max_position_size = self.capital * config.POSITION_SIZE_PCT
        position_size = min(position_size, max_position_size)

        return position_size

    def calculate_stop_loss(self, df, idx, direction, details):
        """
        Calculate stop loss based on structure

        Stop loss placement:
        - Below/above order block if present
        - Beyond liquidity sweep wick
        - Below/above recent swing point
        - Minimum distance to avoid noise

        Args:
            df: DataFrame
            idx: Current index
            direction: 1 for long, -1 for short
            details: Entry details dict

        Returns:
            float: Stop loss price
        """
        row = df.iloc[idx]
        entry_price = row['close']

        # Method 1: Order block based stop
        if 'order_block' in details:
            if direction == 1 and pd.notna(row.get('bullish_ob_low')):
                stop = row['bullish_ob_low'] * 0.998  # Just below OB
                if abs(entry_price - stop) / entry_price * 100 >= config.MIN_STOP_DISTANCE_PCT:
                    return stop
            elif direction == -1 and pd.notna(row.get('bearish_ob_high')):
                stop = row['bearish_ob_high'] * 1.002  # Just above OB
                if abs(entry_price - stop) / entry_price * 100 >= config.MIN_STOP_DISTANCE_PCT:
                    return stop

        # Method 2: Liquidity sweep based stop
        if 'liquidity_sweep' in details:
            if direction == 1:  # Long after SSL sweep
                # Stop below the sweep low
                recent_low = df.iloc[max(0, idx-5):idx]['low'].min()
                stop = recent_low * 0.998
                if abs(entry_price - stop) / entry_price * 100 >= config.MIN_STOP_DISTANCE_PCT:
                    return stop
            elif direction == -1:  # Short after BSL sweep
                # Stop above the sweep high
                recent_high = df.iloc[max(0, idx-5):idx]['high'].max()
                stop = recent_high * 1.002
                if abs(entry_price - stop) / entry_price * 100 >= config.MIN_STOP_DISTANCE_PCT:
                    return stop

        # Method 3: Structure-based stop (default)
        if direction == 1:
            # Long: stop below recent swing low
            recent_low = df.iloc[max(0, idx-20):idx]['low'].min()
            stop = recent_low * (1 - config.STOP_LOSS_PCT / 100)
        else:
            # Short: stop above recent swing high
            recent_high = df.iloc[max(0, idx-20):idx]['high'].max()
            stop = recent_high * (1 + config.STOP_LOSS_PCT / 100)

        return stop

    def calculate_take_profits(self, entry_price, stop_loss_price, direction):
        """
        Calculate take profit levels (1:2, 1:4, 1:6 R:R)

        Args:
            entry_price: Entry price
            stop_loss_price: Stop loss price
            direction: 1 for long, -1 for short

        Returns:
            tuple: (tp1, tp2, tp3)
        """
        # Calculate R (risk distance)
        risk_distance = abs(entry_price - stop_loss_price)

        if direction == 1:  # Long
            tp1 = entry_price + (risk_distance * 2)  # 1:2 R:R
            tp2 = entry_price + (risk_distance * 4)  # 1:4 R:R
            tp3 = entry_price + (risk_distance * 6)  # 1:6 R:R
        else:  # Short
            tp1 = entry_price - (risk_distance * 2)
            tp2 = entry_price - (risk_distance * 4)
            tp3 = entry_price - (risk_distance * 6)

        return tp1, tp2, tp3

    def enter_position(self, df, idx, direction, confluence_score, details):
        """Enter a position with proper risk management"""
        row = df.iloc[idx]
        entry_price = row['close']

        # Calculate stop loss
        stop_loss_price = self.calculate_stop_loss(df, idx, direction, details)

        # Calculate position size based on risk
        position_size = self.calculate_position_size(entry_price, stop_loss_price, confluence_score)

        # Calculate take profits
        tp1, tp2, tp3 = self.calculate_take_profits(entry_price, stop_loss_price, direction)

        # Store position details
        self.position = direction
        self.entry_price = entry_price
        self.entry_time = row['timestamp']
        self.position_size = position_size
        self.stop_loss_price = stop_loss_price
        self.tp1_price = tp1
        self.tp2_price = tp2
        self.tp3_price = tp3
        self.tp1_hit = False
        self.tp2_hit = False
        self.entry_confluence_score = confluence_score

        return {
            'timestamp': row['timestamp'],
            'action': 'ENTER',
            'direction': 'LONG' if direction == 1 else 'SHORT',
            'price': entry_price,
            'position_size': position_size,
            'stop_loss': stop_loss_price,
            'tp1': tp1,
            'tp2': tp2,
            'tp3': tp3,
            'confluence_score': confluence_score,
            'confluence_details': details,
            'leverage': self.leverage
        }

    def check_exit_conditions(self, df, idx):
        """
        Check if should exit position

        Exit scenarios:
        1. Stop loss hit
        2. Take profit levels hit (scaled exits)
        3. Structure break against position
        4. CVD divergence against position
        5. Maximum hold time

        Returns:
            tuple: (should_exit, reason, exit_portion)
        """
        if self.position is None:
            return False, None, 1.0

        row = df.iloc[idx]
        current_price = row['close']

        # Calculate current P&L
        if self.position == 1:  # Long
            pnl_pct = (current_price - self.entry_price) / self.entry_price * 100
        else:  # Short
            pnl_pct = (self.entry_price - current_price) / self.entry_price * 100

        # 1. Stop Loss
        if self.position == 1:
            if current_price <= self.stop_loss_price:
                return True, 'stop_loss', 1.0
        else:
            if current_price >= self.stop_loss_price:
                return True, 'stop_loss', 1.0

        # 2. Take Profit Levels (Scaled Exits)
        if not self.tp1_hit:
            if (self.position == 1 and current_price >= self.tp1_price) or \
               (self.position == -1 and current_price <= self.tp1_price):
                self.tp1_hit = True
                # Move stop to breakeven
                self.stop_loss_price = self.entry_price
                return True, 'tp1', 0.33  # Exit 33%

        if not self.tp2_hit and self.tp1_hit:
            if (self.position == 1 and current_price >= self.tp2_price) or \
               (self.position == -1 and current_price <= self.tp2_price):
                self.tp2_hit = True
                # Move stop to TP1
                self.stop_loss_price = self.tp1_price
                return True, 'tp2', 0.33  # Exit another 33%

        if self.tp1_hit and self.tp2_hit:
            if (self.position == 1 and current_price >= self.tp3_price) or \
               (self.position == -1 and current_price <= self.tp3_price):
                return True, 'tp3', 1.0  # Exit remaining

        # 3. Structure Break Against Position
        if self.position == 1 and row.get('bearish_choch', False):
            return True, 'structure_break_bearish', 1.0
        if self.position == -1 and row.get('bullish_choch', False):
            return True, 'structure_break_bullish', 1.0

        # 4. CVD Divergence Against Position
        if self.position == 1 and row.get('cvd_bearish_divergence', False):
            return True, 'cvd_bearish_divergence', 1.0
        if self.position == -1 and row.get('cvd_bullish_divergence', False):
            return True, 'cvd_bullish_divergence', 1.0

        # 5. Maximum Hold Time
        hold_time_hours = (row['timestamp'] - self.entry_time).total_seconds() / 3600
        if hold_time_hours >= config.MAX_HOLD_TIME_HOURS:
            return True, 'max_hold_time', 1.0

        return False, None, 1.0

    def exit_position(self, df, idx, reason, exit_portion=1.0):
        """Exit position (full or partial)"""
        row = df.iloc[idx]
        exit_price = row['close']

        # Calculate P&L for this portion
        if self.position == 1:  # Long
            pnl_pct = (exit_price - self.entry_price) / self.entry_price * 100
        else:  # Short
            pnl_pct = (self.entry_price - exit_price) / self.entry_price * 100

        # Apply leverage
        pnl_pct_leveraged = pnl_pct * self.leverage

        # Calculate dollar P&L for this portion
        portion_size = self.position_size * exit_portion
        pnl_dollar = portion_size * (pnl_pct_leveraged / 100)

        # Apply fees and slippage
        fees = portion_size * self.leverage * (config.TRADING_FEE_TAKER_PCT / 100) * 2
        slippage = portion_size * self.leverage * (config.SLIPPAGE_PCT / 100) * 2

        # Calculate funding costs
        hold_time_hours = (row['timestamp'] - self.entry_time).total_seconds() / 3600
        funding_cost = portion_size * self.leverage * config.FUNDING_RATE_HOURLY * hold_time_hours

        net_pnl = pnl_dollar - fees - slippage - funding_cost

        trade_result = {
            'timestamp': row['timestamp'],
            'action': 'EXIT',
            'direction': 'LONG' if self.position == 1 else 'SHORT',
            'entry_price': self.entry_price,
            'exit_price': exit_price,
            'exit_portion': exit_portion,
            'pnl_pct': pnl_pct,
            'pnl_pct_leveraged': pnl_pct_leveraged,
            'pnl_dollar': pnl_dollar,
            'fees': fees,
            'slippage': slippage,
            'funding_cost': funding_cost,
            'net_pnl': net_pnl,
            'hold_time_hours': hold_time_hours,
            'exit_reason': reason,
            'confluence_score': self.entry_confluence_score
        }

        # Update capital
        self.capital += net_pnl

        # If full exit, reset position
        if exit_portion == 1.0 or reason == 'stop_loss':
            self.position = None
            self.entry_price = 0
            self.entry_time = None
            self.position_size = 0
            self.tp1_hit = False
            self.tp2_hit = False
        else:
            # Partial exit, reduce position size
            self.position_size *= (1 - exit_portion)

        return trade_result

    def run(self, df):
        """
        Run strategy on historical data

        Args:
            df: DataFrame with all indicators calculated

        Returns:
            list: List of all trades executed
        """
        trades = []

        for idx in range(len(df)):
            if self.position is None:
                # Look for entry
                should_enter, direction, score, details = self.check_entry_conditions(df, idx)
                if should_enter:
                    entry = self.enter_position(df, idx, direction, score, details)
                    trades.append(entry)
            else:
                # Look for exit
                should_exit, reason, portion = self.check_exit_conditions(df, idx)
                if should_exit:
                    exit_trade = self.exit_position(df, idx, reason, portion)
                    trades.append(exit_trade)

        return trades


if __name__ == "__main__":
    print("Professional Strategy Module")
    print("=" * 60)
    print("Use with backtester.py to test this strategy")
    print("\nEntry requirements: Minimum 3 confluences")
    print("Recommended: 5+ confluences for A+ setups")
