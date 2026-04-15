"""
Liquidity Strategy Backtest  —  BSL / SSL  →  2% Target
=========================================================
Runs two strategy variants and compares them:

  VARIANT A  (User's stated strategy — Breakout/Momentum):
    • Price HIGH touches BSL  → LONG   (buy the breakout above swing highs)
    • Price LOW  touches SSL  → SHORT  (sell the breakdown below swing lows)

  VARIANT B  (ICT reversal — Stop Hunt / Sweep Reversal):
    • Candle wicks above BSL then CLOSES back below  → SHORT  (fade the stop hunt)
    • Candle wicks below SSL then CLOSES back above  → LONG   (buy the reversal)

Exchange:  Kraken
Fees:      0.26% taker both sides = 0.52% round-trip
Slippage:  0.05% per side        = 0.10% round-trip
Capital:   $10,500 total  ($5,250 BTC / $5,250 ETH)
Sizing:    Fixed-fraction: risk 2% of capital per trade
             → position = (capital × risk%) / SL%
             capped at 100% of capital (no leverage assumed)
Data:      5 years hourly  (Apr 2021 – Apr 2026)
"""

import pandas as pd
import numpy as np
import json, os
from datetime import datetime

# ─── CONFIGURATION ────────────────────────────────────────────────────────────
INITIAL_CAPITAL      = 10_500.00
CAPITAL_PER_ASSET    = INITIAL_CAPITAL / 2      # $5,250 per asset
TARGET_PCT           = 2.00                      # Take-profit %
STOP_PCT             = 1.00                      # Stop-loss %
RISK_PER_TRADE_PCT   = 2.00                      # Risk this % of capital per trade
KRAKEN_TAKER_FEE_PCT = 0.26                      # 0.26% per side
SLIPPAGE_PCT         = 0.05                      # 0.05% per side
SWING_ORDER          = 7                         # Candles each side for swing (stricter = fewer signals)
BSL_SSL_LOOKBACK     = 3                         # Recent swing points to form BSL/SSL level
MAX_HOLD_CANDLES     = 72                        # Max hours before forced exit
MIN_CANDLES_BETWEEN  = 6                         # Min candles between same-direction trades (avoid whipsaw)

DATA_DIR    = "data"
RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)

ASSETS = {
    "BTC": f"{DATA_DIR}/btc_usd_60m_1825d.csv",
    "ETH": f"{DATA_DIR}/eth_usd_60m_1825d.csv",
}


# ─── SWING POINT DETECTION ────────────────────────────────────────────────────
def identify_swing_points(df, order=7):
    highs = df['high'].values
    lows  = df['low'].values
    n     = len(highs)
    sh    = np.zeros(n, dtype=bool)
    sl    = np.zeros(n, dtype=bool)

    for i in range(order, n - order):
        h_win = highs[i - order: i + order + 1]
        l_win = lows [i - order: i + order + 1]
        # Strict: must be unique max/min in the window
        if highs[i] >= h_win.max() and (h_win == highs[i]).sum() == 1:
            sh[i] = True
        if lows[i] <= l_win.min() and (l_win == lows[i]).sum() == 1:
            sl[i] = True

    return sh, sl


def build_bsl_ssl_arrays(df, swing_high, swing_low, lookback=3):
    """
    Builds rolling BSL and SSL arrays.
    BSL = max of the last `lookback` confirmed swing-high prices seen up to that bar.
    SSL = min of the last `lookback` confirmed swing-low prices seen up to that bar.
    No lookahead: swing points are only 'confirmed' at i+order (already past them).
    """
    n   = len(df)
    bsl = np.full(n, np.nan)
    ssl = np.full(n, np.nan)

    sh_hist = []
    sl_hist = []

    for i in range(n):
        if swing_high[i]:
            sh_hist.append(df['high'].iloc[i])
        if swing_low[i]:
            sl_hist.append(df['low'].iloc[i])

        if len(sh_hist) >= 1:
            bsl[i] = max(sh_hist[-lookback:])
        if len(sl_hist) >= 1:
            ssl[i] = min(sl_hist[-lookback:])

    return bsl, ssl


# ─── INTRABAR EXIT SIMULATION ─────────────────────────────────────────────────
def check_exit(row, direction, tp_price, sl_price):
    """
    Wick-order assumption:
      Bullish candle (close >= open): open → low → high → close
      Bearish candle (close <  open): open → high → low → close
    """
    bullish = row['close'] >= row['open']

    if direction == 'LONG':
        if bullish:                         # low checked first
            if row['low']  <= sl_price: return 'SL', sl_price
            if row['high'] >= tp_price: return 'TP', tp_price
        else:                               # high checked first
            if row['high'] >= tp_price: return 'TP', tp_price
            if row['low']  <= sl_price: return 'SL', sl_price

    else:  # SHORT
        if bullish:                         # low checked first
            if row['low']  <= tp_price: return 'TP', tp_price
            if row['high'] >= sl_price: return 'SL', sl_price
        else:                               # high checked first
            if row['high'] >= sl_price: return 'SL', sl_price
            if row['low']  <= tp_price: return 'TP', tp_price

    return None, None


# ─── POSITION SIZING ──────────────────────────────────────────────────────────
def calc_position(capital, risk_pct, sl_pct):
    """
    Position size such that a full SL hit = risk_pct of capital.
    pos = (capital × risk_pct) / sl_pct    (capped at capital, no leverage)
    """
    pos = capital * (risk_pct / 100) / (sl_pct / 100)
    return min(pos, capital)   # no leverage


# ─── SINGLE-ASSET BACKTEST ────────────────────────────────────────────────────
def backtest_asset(symbol, filepath, starting_capital, variant='B'):
    """
    variant='A'  Breakout:  BSL touch → LONG,  SSL touch → SHORT
    variant='B'  Reversal:  BSL sweep → SHORT, SSL sweep → LONG  (ICT)
    """
    df = pd.read_csv(filepath, parse_dates=['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)

    sw_high, sw_low = identify_swing_points(df, order=SWING_ORDER)
    bsl_arr, ssl_arr = build_bsl_ssl_arrays(df, sw_high, sw_low, lookback=BSL_SSL_LOOKBACK)
    df['bsl'] = bsl_arr
    df['ssl'] = ssl_arr

    capital    = starting_capital
    trades     = []
    equity     = [{'timestamp': df['timestamp'].iloc[0], 'equity': capital}]

    in_trade        = False
    direction       = None
    entry_price     = None
    tp_price        = None
    sl_price        = None
    entry_idx       = None
    entry_time      = None
    pos_value       = None
    last_long_idx   = -999
    last_short_idx  = -999

    fee_rate  = KRAKEN_TAKER_FEE_PCT / 100
    slip_rate = SLIPPAGE_PCT         / 100
    start_idx = SWING_ORDER * 2 + 5

    for i in range(start_idx, len(df)):
        row  = df.iloc[i]
        prev = df.iloc[i - 1]

        # Previous bar's BSL/SSL (no lookahead)
        bsl = df['bsl'].iloc[i - 1]
        ssl = df['ssl'].iloc[i - 1]

        # ── Manage open trade ──────────────────────────────────────────────
        if in_trade:
            reason, exit_px = check_exit(row, direction, tp_price, sl_price)

            if reason is None and (i - entry_idx) >= MAX_HOLD_CANDLES:
                reason  = 'TIMEOUT'
                exit_px = row['close']

            if reason:
                qty = pos_value / entry_price

                if direction == 'LONG':
                    gross = qty * (exit_px - entry_price)
                else:
                    gross = qty * (entry_price - exit_px)

                entry_fee = pos_value * (fee_rate + slip_rate)
                exit_fee  = abs(qty * exit_px) * (fee_rate + slip_rate)
                net       = gross - entry_fee - exit_fee

                capital  += net

                trades.append({
                    'symbol':     symbol,
                    'variant':    variant,
                    'direction':  direction,
                    'entry_time': entry_time,
                    'exit_time':  row['timestamp'],
                    'entry_px':   round(entry_price, 4),
                    'exit_px':    round(exit_px, 4),
                    'tp_px':      round(tp_price, 4),
                    'sl_px':      round(sl_price, 4),
                    'exit_reason':reason,
                    'pos_value':  round(pos_value, 2),
                    'gross_pnl':  round(gross, 2),
                    'fees':       round(entry_fee + exit_fee, 2),
                    'net_pnl':    round(net, 2),
                    'return_pct': round(net / pos_value * 100, 4),
                    'hold_h':     i - entry_idx,
                    'cap_after':  round(capital, 2),
                })
                equity.append({'timestamp': row['timestamp'], 'equity': capital})

                if direction == 'LONG':  last_long_idx  = i
                else:                    last_short_idx = i
                in_trade = False

        # ── Look for entry signals ─────────────────────────────────────────
        if in_trade or pd.isna(bsl) or pd.isna(ssl):
            continue
        if capital <= 10:
            continue

        if variant == 'A':
            # Breakout: price touches the liquidity zone
            long_sig  = (prev['high'] >= bsl) and (i - last_long_idx  >= MIN_CANDLES_BETWEEN)
            short_sig = (prev['low']  <= ssl) and (i - last_short_idx >= MIN_CANDLES_BETWEEN)

        else:  # variant B — Sweep Reversal (ICT)
            # BSL sweep: wick above BSL but closed BELOW it → expect reversal DOWN → SHORT
            bsl_sweep = (prev['high'] > bsl) and (prev['close'] < bsl)
            # SSL sweep: wick below SSL but closed ABOVE it → expect reversal UP → LONG
            ssl_sweep = (prev['low']  < ssl) and (prev['close'] > ssl)
            long_sig  = ssl_sweep and (i - last_long_idx  >= MIN_CANDLES_BETWEEN)
            short_sig = bsl_sweep and (i - last_short_idx >= MIN_CANDLES_BETWEEN)

        # Prioritise: if both fire, skip (conflicting signals)
        if long_sig and short_sig:
            continue

        if long_sig:
            ep       = row['open'] * (1 + slip_rate)
            pv       = calc_position(capital, RISK_PER_TRADE_PCT, STOP_PCT)
            entry_price, tp_price, sl_price = ep, ep * (1 + TARGET_PCT/100), ep * (1 - STOP_PCT/100)
            direction, in_trade = 'LONG', True
            pos_value, entry_idx, entry_time = pv, i, row['timestamp']

        elif short_sig:
            ep       = row['open'] * (1 - slip_rate)
            pv       = calc_position(capital, RISK_PER_TRADE_PCT, STOP_PCT)
            entry_price, tp_price, sl_price = ep, ep * (1 - TARGET_PCT/100), ep * (1 + STOP_PCT/100)
            direction, in_trade = 'SHORT', True
            pos_value, entry_idx, entry_time = pv, i, row['timestamp']

    # Close any lingering trade
    if in_trade:
        ep2 = df.iloc[-1]['close']
        qty = pos_value / entry_price
        g   = qty * (ep2 - entry_price) if direction == 'LONG' else qty * (entry_price - ep2)
        ef  = pos_value * (fee_rate + slip_rate) + abs(qty * ep2) * (fee_rate + slip_rate)
        net = g - ef
        capital += net
        trades.append({'symbol': symbol, 'variant': variant, 'direction': direction,
                       'entry_time': entry_time, 'exit_time': df.iloc[-1]['timestamp'],
                       'entry_px': round(entry_price,4), 'exit_px': round(ep2,4),
                       'tp_px': round(tp_price,4), 'sl_px': round(sl_price,4),
                       'exit_reason': 'END', 'pos_value': round(pos_value,2),
                       'gross_pnl': round(g,2), 'fees': round(ef,2),
                       'net_pnl': round(net,2), 'return_pct': round(net/pos_value*100,4),
                       'hold_h': len(df)-1-entry_idx, 'cap_after': round(capital,2)})
        equity.append({'timestamp': df.iloc[-1]['timestamp'], 'equity': capital})

    return trades, equity, capital


# ─── METRICS ──────────────────────────────────────────────────────────────────
def metrics(trades, equity_curve, init_cap):
    if not trades:
        return None
    dt   = pd.DataFrame(trades)
    wins = dt[dt['net_pnl'] > 0]
    loss = dt[dt['net_pnl'] <= 0]
    n    = len(dt)

    gp = wins['net_pnl'].sum() if len(wins) else 0
    gl = abs(loss['net_pnl'].sum()) if len(loss) else 0
    pf = (gp / gl) if gl > 0 else float('inf')

    eq = pd.DataFrame(equity_curve)
    eq['peak'] = eq['equity'].cummax()
    eq['dd']   = (eq['equity'] - eq['peak']) / eq['peak'] * 100
    mdd        = eq['dd'].min()
    fin        = eq['equity'].iloc[-1]
    days       = (eq['timestamp'].iloc[-1] - eq['timestamp'].iloc[0]).days
    ann        = ((fin / init_cap) ** (365 / max(days,1)) - 1) * 100

    def max_streak(lst, val):
        best = cur = 0
        for x in lst:
            cur  = (cur+1) if x == val else 0
            best = max(best, cur)
        return best

    signs = [1 if p > 0 else -1 for p in dt['net_pnl']]

    return {
        'n_trades':       n,
        'n_wins':         len(wins),
        'n_losses':       len(loss),
        'win_rate':       round(len(wins)/n*100, 2),
        'total_pnl':      round(dt['net_pnl'].sum(), 2),
        'gross_profit':   round(gp, 2),
        'gross_loss':     round(gl, 2),
        'profit_factor':  round(pf, 3) if pf != float('inf') else 'inf',
        'avg_win':        round(wins['net_pnl'].mean(), 2) if len(wins) else 0,
        'avg_loss':       round(loss['net_pnl'].mean(), 2) if len(loss) else 0,
        'rr_actual':      round(abs(wins['net_pnl'].mean()/loss['net_pnl'].mean()), 2) if len(wins) and len(loss) else 0,
        'total_fees':     round(dt['fees'].sum(), 2),
        'avg_hold_h':     round(dt['hold_h'].mean(), 1),
        'start_cap':      round(init_cap, 2),
        'final_cap':      round(fin, 2),
        'total_ret_pct':  round((fin-init_cap)/init_cap*100, 2),
        'ann_ret_pct':    round(ann, 2),
        'max_dd_pct':     round(mdd, 2),
        'max_win_streak': max_streak(signs,  1),
        'max_loss_streak':max_streak(signs, -1),
        'exit_breakdown': dt['exit_reason'].value_counts().to_dict(),
    }


# ─── PRINT REPORT ─────────────────────────────────────────────────────────────
def print_report(m, label):
    L = "─" * 62
    print(f"\n{L}")
    print(f"  {label}")
    print(L)
    print(f"  Trades:           {m['n_trades']:>5}  "
          f"({m['n_wins']} wins / {m['n_losses']} losses)")
    print(f"  Win Rate:         {m['win_rate']:>5.1f}%")
    print(f"  Profit Factor:    {m['profit_factor']}")
    print(f"  Avg Win  (net):  ${m['avg_win']:>9,.2f}")
    print(f"  Avg Loss (net):  ${m['avg_loss']:>9,.2f}")
    print(f"  Actual R:R:       1 : {m['rr_actual']}")
    print(f"  Max Win Streak:   {m['max_win_streak']}")
    print(f"  Max Loss Streak:  {m['max_loss_streak']}")
    print(f"  Avg Hold:         {m['avg_hold_h']} hours")
    print(f"  Total Fees Paid: ${m['total_fees']:>9,.2f}")
    print(L)
    print(f"  Starting Capital:${m['start_cap']:>10,.2f}")
    print(f"  Final Capital:   ${m['final_cap']:>10,.2f}")
    print(f"  Total P&L:       ${m['total_pnl']:>+10,.2f}")
    print(f"  Total Return:     {m['total_ret_pct']:>+6.2f}%")
    print(f"  Annualised Ret:   {m['ann_ret_pct']:>+6.2f}%")
    print(f"  Max Drawdown:     {m['max_dd_pct']:>6.2f}%")
    print(L)
    print(f"  Exit Breakdown:")
    for k, v in sorted(m['exit_breakdown'].items(), key=lambda x: -x[1]):
        print(f"    {k:<16} {v:>4}  ({v/m['n_trades']*100:.1f}%)")
    print(L)

    pf_val = m['profit_factor'] if m['profit_factor'] == 'inf' else float(str(m['profit_factor']))
    if pf_val == 'inf' or (isinstance(pf_val, float) and pf_val >= 1.5 and m['win_rate'] >= 45):
        v = "EXCELLENT  ✓  Meets professional benchmarks"
    elif isinstance(pf_val, float) and pf_val >= 1.2:
        v = "GOOD  —  Profitable, room to optimise"
    elif isinstance(pf_val, float) and pf_val > 1.0:
        v = "MARGINAL  —  Barely profitable"
    else:
        v = "UNPROFITABLE  —  Needs rethinking"
    print(f"  Verdict: {v}")
    print(L)


# ─── COMBINED EQUITY ──────────────────────────────────────────────────────────
def merge_equity(eq_btc_list, eq_eth_list, init):
    eq_btc = {e['timestamp']: e['equity'] for e in eq_btc_list}
    eq_eth = {e['timestamp']: e['equity'] for e in eq_eth_list}
    all_ts  = sorted(set(list(eq_btc) + list(eq_eth)))
    lb = le = init / 2
    combined = []
    for ts in all_ts:
        if ts in eq_btc: lb = eq_btc[ts]
        if ts in eq_eth: le = eq_eth[ts]
        combined.append({'timestamp': ts, 'equity': lb + le})
    return combined


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    ts_str = datetime.now().strftime('%Y%m%d_%H%M%S')

    round_trip_cost = (KRAKEN_TAKER_FEE_PCT + SLIPPAGE_PCT) * 2
    print(f"""
{'='*62}
  LIQUIDITY STRATEGY BACKTEST  |  BTC + ETH  |  Apr 2021–2026
{'='*62}
  Capital:         ${INITIAL_CAPITAL:,.0f}  (${CAPITAL_PER_ASSET:,.0f} per asset)
  Target:          +{TARGET_PCT}%   |   Stop-Loss: -{STOP_PCT}%
  Theoretical R:R:  1:{TARGET_PCT/STOP_PCT:.1f}
  Risk/Trade:       {RISK_PER_TRADE_PCT}% of capital
  Swing Order:      {SWING_ORDER} candles each side
  BSL/SSL Lookback: Last {BSL_SSL_LOOKBACK} swing points
  Kraken Fee:       {KRAKEN_TAKER_FEE_PCT}% taker × 2 = {KRAKEN_TAKER_FEE_PCT*2:.2f}% round-trip
  Slippage:         {SLIPPAGE_PCT}% × 2 = {SLIPPAGE_PCT*2:.2f}% round-trip
  Total cost/trip:  {round_trip_cost:.2f}%
  Min candles gap:  {MIN_CANDLES_BETWEEN} hours between same-direction trades
  Max hold:         {MAX_HOLD_CANDLES} hours
{'='*62}

  VARIANT A — Breakout/Momentum
    BSL reached → LONG  (buy the break above swing highs)
    SSL reached → SHORT (sell the break below swing lows)

  VARIANT B — ICT Stop-Hunt Reversal  (recommended)
    BSL swept (wick above, close below) → SHORT (fade the stop hunt)
    SSL swept (wick below, close above) → LONG  (buy the reversal)
{'='*62}""")

    all_summary = {}

    for vname, vlabel in [('A', 'VARIANT A — Breakout/Momentum'),
                           ('B', 'VARIANT B — ICT Stop-Hunt Reversal')]:
        print(f"\n\n{'#'*62}")
        print(f"  {vlabel}")
        print(f"{'#'*62}")

        bt = {}; eq = {}; fc = {}
        for sym, path in ASSETS.items():
            print(f"\n  ▶ {sym} ...")
            tr, eqc, cap = backtest_asset(sym, path, CAPITAL_PER_ASSET, variant=vname)
            bt[sym] = tr; eq[sym] = eqc; fc[sym] = cap
            m = metrics(tr, eqc, CAPITAL_PER_ASSET)
            if m:
                print_report(m, f"{sym}  [{vlabel}]  |  ${CAPITAL_PER_ASSET:,.0f} start")
                all_summary[f"{vname}_{sym}"] = m

        # Combined
        if 'BTC' in eq and 'ETH' in eq:
            combined_eq  = merge_equity(eq['BTC'], eq['ETH'], INITIAL_CAPITAL)
            all_trades   = bt.get('BTC', []) + bt.get('ETH', [])
            m_combined   = metrics(all_trades, combined_eq, INITIAL_CAPITAL)
            if m_combined:
                print_report(m_combined, f"COMBINED PORTFOLIO  [{vlabel}]  |  ${INITIAL_CAPITAL:,.0f} start")
                all_summary[f"{vname}_COMBINED"] = m_combined

        # Save variant trades
        all_tr = bt.get('BTC', []) + bt.get('ETH', [])
        pd.DataFrame(all_tr).to_csv(
            f"{RESULTS_DIR}/liq_trades_{vname}_{ts_str}.csv", index=False)

    # ── Head-to-head comparison ────────────────────────────────────────────
    print(f"\n\n{'='*62}")
    print("  HEAD-TO-HEAD COMPARISON  (Combined Portfolio)")
    print(f"{'='*62}")
    header = f"  {'Metric':<28} {'Variant A':>12} {'Variant B':>12}"
    print(header)
    print(f"  {'-'*56}")

    rows = [
        ('Trades',         'n_trades',       lambda v: f"{v:,}"),
        ('Win Rate',       'win_rate',        lambda v: f"{v:.1f}%"),
        ('Profit Factor',  'profit_factor',   lambda v: str(v)),
        ('Total P&L ($)',  'total_pnl',       lambda v: f"${v:+,.2f}"),
        ('Total Return',   'total_ret_pct',   lambda v: f"{v:+.2f}%"),
        ('Ann. Return',    'ann_ret_pct',     lambda v: f"{v:+.2f}%"),
        ('Max Drawdown',   'max_dd_pct',      lambda v: f"{v:.2f}%"),
        ('Fees Paid ($)',  'total_fees',      lambda v: f"${v:,.2f}"),
        ('Final Capital',  'final_cap',       lambda v: f"${v:,.2f}"),
    ]
    for label, key, fmt in rows:
        va = all_summary.get('A_COMBINED', {}).get(key, 'N/A')
        vb = all_summary.get('B_COMBINED', {}).get(key, 'N/A')
        fa = fmt(va) if va != 'N/A' else 'N/A'
        fb = fmt(vb) if vb != 'N/A' else 'N/A'
        print(f"  {label:<28} {fa:>12} {fb:>12}")

    print(f"{'='*62}")

    # Save full summary
    with open(f"{RESULTS_DIR}/liq_summary_{ts_str}.json", 'w') as f:
        json.dump({'config': {
            'capital': INITIAL_CAPITAL, 'target_pct': TARGET_PCT,
            'stop_pct': STOP_PCT, 'risk_per_trade_pct': RISK_PER_TRADE_PCT,
            'taker_fee': KRAKEN_TAKER_FEE_PCT, 'slippage': SLIPPAGE_PCT,
            'swing_order': SWING_ORDER, 'bsl_ssl_lookback': BSL_SSL_LOOKBACK,
            'max_hold_h': MAX_HOLD_CANDLES,
        }, 'results': all_summary}, f, indent=2, default=str)

    print(f"\n  Results saved to {RESULTS_DIR}/")
    print(f"{'='*62}\n")


if __name__ == "__main__":
    main()
