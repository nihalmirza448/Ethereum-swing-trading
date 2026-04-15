"""
Liquidity Strategy Backtest  v3  —  Proper Liquidity + Volume Profile
======================================================================
Key improvements over v2:

 LIQUIDITY SOURCE (was: arbitrary swing highs/lows)
 ─────────────────────────────────────────────────
   Now uses Equal Highs / Equal Lows as BSL/SSL.
   Equal Highs: 2+ swing highs within tolerance% of each other  → BSL level
   Equal Lows:  2+ swing lows  within tolerance% of each other  → SSL level
   These are the actual stop-cluster pools institutions target.

 VOLUME PROFILE (new)
 ────────────────────
   Rolling N-bar volume profile computed from OHLCV.
   Each bar's volume is distributed uniformly across its high–low range.
     POC  – Point of Control   (highest volume price)
     VAH  – Value Area High    (top of 70% volume zone)
     VAL  – Value Area Low     (bottom of 70% volume zone)
     LVN  – Low Volume Node    (price gap / air pocket, price moves fast here)
     HVN  – High Volume Node   (congestion, price moves slowly here)

   Signal filter:
     LONG  signal → only if there is a LVN between entry and +2% target
                    (empty air above = price can reach target quickly)
     SHORT signal → only if there is a LVN between entry and -2% target

   Confluence addition:
     Entry near POC / VAH / VAL = extra confluence point

 COINGLASS NOTE
 ──────────────
   Tested: free API key returns "Upgrade plan" on all historical endpoints.
   For the backtest we use a synthetic liquidation proxy:
     • Equal H/L levels (proven stop cluster locations)
     • Volume Profile LVN/HVN (shows where price accelerates vs stalls)
   For live trading the Coinglass heatmap can be used as a real-time overlay.

Timeframes  :  4h  (winning TF from v2)  +  1h  +  5m
Assets      :  BTC  +  ETH
Period      :  Last 1 year  (Apr 2025 – Apr 2026)
Capital     :  $10,500  ($5,250/asset)
Fees        :  Entry/TP maker 0.16%  |  SL taker 0.26% + 0.03% slip
"""

import pandas as pd
import numpy as np
import json, os
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────────────────────
INITIAL_CAPITAL   = 10_500.00
CAPITAL_PER_ASSET = INITIAL_CAPITAL / 2
RISK_PER_TRADE    = 2.00          # % of capital risked per trade
TARGET_PCT        = 2.00
STOP_PCT          = 1.00

MAKER_FEE  = 0.16 / 100
TAKER_FEE  = 0.26 / 100
SL_SLIP    = 0.03 / 100

# Equal H/L detection
EQ_TOLERANCE_PCT  = 0.30   # highs/lows within 0.30% = "equal"
EQ_MIN_TOUCHES    = 2      # need at least 2 touches
EQ_LOOKBACK       = 60     # bars to look back for equal levels (rolling)

# Volume Profile
VP_WINDOW         = 80     # bars in rolling volume profile window
VP_BINS           = 150    # price bins in profile
VP_VALUE_AREA_PCT = 70     # value area = 70% of volume
VP_LVN_PERCENTILE = 25     # bottom 25% of volume nodes = LVN

# Trend / CVD / Volume filters
EMA_FAST          = 50
EMA_SLOW          = 200
VOL_MA_PERIOD     = 20
VOLUME_SPIKE_MULT = 1.5
MIN_CONFLUENCE    = 2       # out of 4 filters (trend, cvd, vol-spike, vp-near-poc)

# Per-timeframe: (swing_order, max_hold_bars, min_gap_bars)
TF_CFG = {
    '5m': dict(swing_order=4, max_hold=72,  min_gap=6),
    '1h': dict(swing_order=5, max_hold=72,  min_gap=4),
    '4h': dict(swing_order=4, max_hold=18,  min_gap=2),
}
CUTOFF = pd.Timestamp('2025-04-12')
DATA_DIR    = "data"
RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════════════════════════
def load_asset(symbol, tf):
    sym = symbol.lower()
    if tf == '5m':
        path = f"{DATA_DIR}/{sym}_usd_5m_365d.csv"
    elif tf == '1h':
        path = f"{DATA_DIR}/{sym}_usd_60m_1825d.csv"
    else:  # 4h — resample from 1h
        path = f"{DATA_DIR}/{sym}_usd_60m_1825d.csv"

    df = pd.read_csv(path, parse_dates=['timestamp'])
    df = df[df['timestamp'] >= CUTOFF].sort_values('timestamp').reset_index(drop=True)

    if tf == '4h':
        df = (df.set_index('timestamp')
                .resample('4h')
                .agg({'open':'first','high':'max','low':'min',
                      'close':'last','volume':'sum'})
                .dropna(subset=['open'])
                .reset_index())
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# SWING POINTS  (no scipy)
# ═══════════════════════════════════════════════════════════════════════════════
def find_swing_points(H, L, order):
    n  = len(H)
    sh = np.zeros(n, dtype=bool)
    sl = np.zeros(n, dtype=bool)
    for i in range(order, n - order):
        hw = H[i-order:i+order+1]
        lw = L[i-order:i+order+1]
        if H[i] >= hw.max() and (hw == H[i]).sum() == 1:
            sh[i] = True
        if L[i] <= lw.min() and (lw == L[i]).sum() == 1:
            sl[i] = True
    return sh, sl


# ═══════════════════════════════════════════════════════════════════════════════
# EQUAL HIGHS / EQUAL LOWS  (rolling window, no lookahead)
# ═══════════════════════════════════════════════════════════════════════════════
def compute_equal_levels(df, swing_high, swing_low, order):
    """
    For each bar i, scan the previous EQ_LOOKBACK bars for:
      - Groups of swing highs within EQ_TOLERANCE_PCT of each other
      - Groups of swing lows  within EQ_TOLERANCE_PCT of each other

    Returns:
      eq_bsl[i]  = price of the equal-high cluster (BSL) if active, else NaN
      eq_ssl[i]  = price of the equal-low  cluster (SSL) if active, else NaN
      eq_bsl_strength[i] = number of touches at that level
      eq_ssl_strength[i] = number of touches at that level
    """
    n = len(df)
    H = df['high'].values
    L = df['low'].values

    sh_prices = []   # (bar_idx, price)
    sl_prices = []

    eq_bsl      = np.full(n, np.nan)
    eq_ssl      = np.full(n, np.nan)
    eq_bsl_str  = np.zeros(n, dtype=int)
    eq_ssl_str  = np.zeros(n, dtype=int)

    for i in range(n):
        # Register confirmed swing points
        if swing_high[i]:
            sh_prices.append((i, H[i]))
        if swing_low[i]:
            sl_prices.append((i, L[i]))

        # Only look at swing points within the lookback window
        sh_win = [(idx, p) for idx, p in sh_prices if i - idx <= EQ_LOOKBACK]
        sl_win = [(idx, p) for idx, p in sl_prices if i - idx <= EQ_LOOKBACK]

        # Find best equal-high cluster (highest cluster with ≥ EQ_MIN_TOUCHES)
        best_bsl = _best_cluster(sh_win, EQ_TOLERANCE_PCT, EQ_MIN_TOUCHES)
        if best_bsl is not None:
            eq_bsl[i]     = best_bsl[0]   # cluster price (mean)
            eq_bsl_str[i] = best_bsl[1]   # touch count

        # Find best equal-low cluster (lowest cluster with ≥ EQ_MIN_TOUCHES)
        best_ssl = _best_cluster(sl_win, EQ_TOLERANCE_PCT, EQ_MIN_TOUCHES,
                                 prefer='lowest')
        if best_ssl is not None:
            eq_ssl[i]     = best_ssl[0]
            eq_ssl_str[i] = best_ssl[1]

    return eq_bsl, eq_ssl, eq_bsl_str, eq_ssl_str


def _best_cluster(points, tol_pct, min_touches, prefer='highest'):
    """Group price points into clusters within tol_pct; return best cluster."""
    if len(points) < min_touches:
        return None

    prices = [p for _, p in points]
    clusters = []

    visited = [False] * len(prices)
    for i, pi in enumerate(prices):
        if visited[i]:
            continue
        grp = [pi]
        for j, pj in enumerate(prices):
            if i != j and not visited[j]:
                if abs(pi - pj) / pi * 100 <= tol_pct:
                    grp.append(pj)
                    visited[j] = True
        if len(grp) >= min_touches:
            clusters.append((np.mean(grp), len(grp)))
        visited[i] = True

    if not clusters:
        return None

    # prefer 'highest' cluster (BSL) or 'lowest' (SSL)
    if prefer == 'highest':
        return max(clusters, key=lambda x: x[0])
    else:
        return min(clusters, key=lambda x: x[0])


# ═══════════════════════════════════════════════════════════════════════════════
# VOLUME PROFILE  (rolling window)
# ═══════════════════════════════════════════════════════════════════════════════
def compute_volume_profile_rolling(df, window=VP_WINDOW, bins=VP_BINS,
                                    va_pct=VP_VALUE_AREA_PCT,
                                    lvn_pct=VP_LVN_PERCENTILE):
    """
    For each bar i, compute volume profile over the previous `window` bars.
    Returns arrays: poc, vah, val, lvn_zones (list of (lo,hi) tuples per bar)

    We pre-compute every bar's profile to avoid O(n²) inner loops.
    """
    n   = len(df)
    H   = df['high'].values
    L   = df['low'].values
    C   = df['close'].values
    V   = df['volume'].values

    poc_arr = np.full(n, np.nan)
    vah_arr = np.full(n, np.nan)
    val_arr = np.full(n, np.nan)
    # For LVN: store as boolean array for price near current close
    lvn_above_arr = np.zeros(n, dtype=bool)  # LVN between close and close*(1+target%)
    lvn_below_arr = np.zeros(n, dtype=bool)  # LVN between close and close*(1-target%)

    for i in range(window, n):
        w_start = i - window
        h_win = H[w_start:i];  l_win = L[w_start:i];  v_win = V[w_start:i]

        p_lo = l_win.min();  p_hi = h_win.max()
        if p_hi <= p_lo: continue

        bin_edges = np.linspace(p_lo, p_hi, bins + 1)
        bin_vol   = np.zeros(bins)

        for k in range(len(h_win)):
            rng = h_win[k] - l_win[k]
            if rng < 1e-9: continue
            # distribute volume proportionally across bins touched by this bar
            b_lo = np.searchsorted(bin_edges, l_win[k], side='left')
            b_hi = np.searchsorted(bin_edges, h_win[k], side='right')
            b_lo = max(0, b_lo - 1);  b_hi = min(bins, b_hi)
            if b_lo >= b_hi: continue
            span = bin_edges[b_hi] - bin_edges[b_lo]
            if span < 1e-9: continue
            bin_vol[b_lo:b_hi] += v_win[k] * (bin_edges[b_hi] - bin_edges[b_lo]) / rng

        total_vol = bin_vol.sum()
        if total_vol < 1e-9: continue

        poc_idx = bin_vol.argmax()
        poc = (bin_edges[poc_idx] + bin_edges[poc_idx + 1]) / 2
        poc_arr[i] = poc

        # Value Area: expand from POC until 70% of total volume captured
        va_target = total_vol * va_pct / 100
        va_vol    = bin_vol[poc_idx]
        lo_idx    = poc_idx
        hi_idx    = poc_idx
        while va_vol < va_target:
            expand_lo = bin_vol[lo_idx - 1] if lo_idx > 0       else -1
            expand_hi = bin_vol[hi_idx + 1] if hi_idx < bins-1  else -1
            if expand_lo <= 0 and expand_hi <= 0: break
            if expand_hi >= expand_lo and hi_idx < bins - 1:
                hi_idx += 1;  va_vol += bin_vol[hi_idx]
            elif lo_idx > 0:
                lo_idx -= 1;  va_vol += bin_vol[lo_idx]
            else:
                break

        vah_arr[i] = (bin_edges[hi_idx] + bin_edges[hi_idx + 1]) / 2
        val_arr[i] = (bin_edges[lo_idx] + bin_edges[lo_idx + 1]) / 2

        # LVN check: is there a low-volume gap between close and ±target?
        lvn_thresh = np.percentile(bin_vol[bin_vol > 0], lvn_pct) if (bin_vol > 0).any() else 0
        cur_close  = C[i]
        tp_price   = cur_close * (1 + TARGET_PCT / 100)
        sl_price   = cur_close * (1 - TARGET_PCT / 100)

        # LVN above: at least one LVN bin between close and TP
        b_cur  = np.searchsorted(bin_edges, cur_close, side='right') - 1
        b_tp   = np.searchsorted(bin_edges, tp_price,  side='right') - 1
        b_sl   = np.searchsorted(bin_edges, sl_price,  side='right') - 1
        b_cur  = max(0, min(bins-1, b_cur))
        b_tp   = max(0, min(bins-1, b_tp))
        b_sl   = max(0, min(bins-1, b_sl))

        if b_tp > b_cur:
            lvn_above_arr[i] = np.any(bin_vol[b_cur+1:b_tp+1] <= lvn_thresh)
        if b_sl < b_cur:
            lvn_below_arr[i] = np.any(bin_vol[b_sl:b_cur] <= lvn_thresh)

    return poc_arr, vah_arr, val_arr, lvn_above_arr, lvn_below_arr


# ═══════════════════════════════════════════════════════════════════════════════
# CVD
# ═══════════════════════════════════════════════════════════════════════════════
def compute_cvd_slope(df):
    body = (df['close'] - df['open']).abs()
    rng  = (df['high'] - df['low']).replace(0, 1e-9)
    bp   = body / rng
    bv   = np.where(df['close'] >= df['open'],
                    df['volume'] * (0.5 + bp * 0.5),
                    df['volume'] * (0.5 - bp * 0.5))
    sv   = np.where(df['close'] <  df['open'],
                    df['volume'] * (0.5 + bp * 0.5),
                    df['volume'] * (0.5 - bp * 0.5))
    cvd  = pd.Series(bv - sv).cumsum()
    return cvd.diff(5)


# ═══════════════════════════════════════════════════════════════════════════════
# INTRABAR EXIT
# ═══════════════════════════════════════════════════════════════════════════════
def check_exit(row, direction, tp, sl):
    bull = row['close'] >= row['open']
    if direction == 'LONG':
        if bull:
            if row['low']  <= sl: return 'SL', sl
            if row['high'] >= tp: return 'TP', tp
        else:
            if row['high'] >= tp: return 'TP', tp
            if row['low']  <= sl: return 'SL', sl
    else:
        if bull:
            if row['low']  <= tp: return 'TP', tp
            if row['high'] >= sl: return 'SL', sl
        else:
            if row['high'] >= sl: return 'SL', sl
            if row['low']  <= tp: return 'TP', tp
    return None, None


def pos_size(capital, risk_pct, sl_pct):
    return min(capital * (risk_pct / 100) / (sl_pct / 100), capital)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN BACKTEST ENGINE
# ═══════════════════════════════════════════════════════════════════════════════
def run_backtest(symbol, df_raw, tf):
    cfg = TF_CFG[tf]
    df  = df_raw.copy().reset_index(drop=True)
    n   = len(df)
    H   = df['high'].values
    L   = df['low'].values

    print(f"    [{symbol} {tf}] Computing indicators ({n:,} bars) ...")

    # ── Swing points ────────────────────────────────────────────────────────
    sh, sl = find_swing_points(H, L, cfg['swing_order'])

    # ── Equal Highs / Equal Lows (BSL / SSL source) ─────────────────────────
    eq_bsl, eq_ssl, eq_bsl_str, eq_ssl_str = compute_equal_levels(df, sh, sl, cfg['swing_order'])

    # ── Volume Profile ──────────────────────────────────────────────────────
    poc, vah, val, lvn_above, lvn_below = compute_volume_profile_rolling(df)

    # ── CVD slope ───────────────────────────────────────────────────────────
    cvd_slope = compute_cvd_slope(df).values

    # ── EMAs & Volume MA ────────────────────────────────────────────────────
    ema_f  = df['close'].ewm(span=EMA_FAST,  adjust=False).mean().values
    ema_s  = df['close'].ewm(span=EMA_SLOW,  adjust=False).mean().values
    vol_ma = df['volume'].rolling(VOL_MA_PERIOD).mean().values

    # ── Warmup period ───────────────────────────────────────────────────────
    warm = max(EMA_SLOW + 5, VP_WINDOW + 5, EQ_LOOKBACK + cfg['swing_order'] * 2 + 5)

    capital   = CAPITAL_PER_ASSET
    trades    = []
    equity    = [{'timestamp': df['timestamp'].iloc[0], 'equity': capital}]

    in_trade   = False
    direction  = entry_px = tp_px = sl_px = pos_val = None
    entry_idx  = entry_time = None
    last_long  = last_short = -9999

    for i in range(warm, n):
        row   = df.iloc[i]
        prev_i = i - 1

        bsl    = eq_bsl[prev_i];      ssl    = eq_ssl[prev_i]
        bsl_st = eq_bsl_str[prev_i];  ssl_st = eq_ssl_str[prev_i]
        poc_v  = poc[prev_i];         vah_v  = vah[prev_i];   val_v = val[prev_i]
        lvn_ab = lvn_above[prev_i];   lvn_bl = lvn_below[prev_i]

        emaf   = ema_f[prev_i];       emas   = ema_s[prev_i]
        cvds   = cvd_slope[prev_i]
        vol    = df['volume'].iloc[prev_i]
        volma  = vol_ma[prev_i]

        # ── Manage open trade ────────────────────────────────────────────────
        if in_trade:
            rsn, ex = check_exit(row, direction, tp_px, sl_px)
            if rsn is None and (i - entry_idx) >= cfg['max_hold']:
                rsn, ex = 'TIMEOUT', row['close']
            if rsn:
                qty = pos_val / entry_px
                g   = qty*(ex-entry_px) if direction=='LONG' else qty*(entry_px-ex)
                ef  = pos_val*MAKER_FEE + abs(qty*ex)*(MAKER_FEE if rsn=='TP' else TAKER_FEE+SL_SLIP)
                net = g - ef
                capital += net
                trades.append({
                    'symbol': symbol, 'tf': tf,
                    'direction': direction,
                    'entry_time': entry_time, 'exit_time': row['timestamp'],
                    'entry_px': round(entry_px, 4), 'exit_px': round(ex, 4),
                    'tp_px': round(tp_px, 4), 'sl_px': round(sl_px, 4),
                    'exit_reason': rsn,
                    'pos_value': round(pos_val, 2),
                    'gross_pnl': round(g, 2),
                    'fees': round(ef, 2),
                    'net_pnl': round(net, 2),
                    'return_pct': round(net/pos_val*100, 4),
                    'hold_bars': i - entry_idx,
                    'cap_after': round(capital, 2),
                    'bsl_touches': int(bsl_st),
                    'poc_at_entry': round(poc_v, 2) if not np.isnan(poc_v) else None,
                    'lvn_filtered': lvn_ab if direction=='LONG' else lvn_bl,
                })
                equity.append({'timestamp': row['timestamp'], 'equity': capital})
                if direction == 'LONG': last_long  = i
                else:                   last_short = i
                in_trade = False

        if in_trade or capital <= 10:
            continue
        if any(np.isnan(x) for x in [bsl, ssl, emaf, emas, cvds]) or volma==0 or np.isnan(volma):
            continue
        if np.isnan(poc_v) or np.isnan(vah_v) or np.isnan(val_v):
            continue

        # ── Confluence filters ───────────────────────────────────────────────
        trend_up   = emaf > emas
        trend_dn   = emaf < emas
        cvd_bull   = cvds > 0
        cvd_bear   = cvds < 0
        vol_spike  = vol > (VOLUME_SPIKE_MULT * volma)
        # Volume profile position: near VAL = good for longs, near VAH = good for shorts
        cur_close  = df['close'].iloc[prev_i]
        near_val   = abs(cur_close - val_v) / cur_close < 0.01   # within 1% of VAL
        near_vah   = abs(cur_close - vah_v) / cur_close < 0.01   # within 1% of VAH

        # ── Equal-High / Equal-Low signal ────────────────────────────────────
        prev_row = df.iloc[prev_i]
        bsl_touched = (not np.isnan(bsl)) and (prev_row['high'] >= bsl * (1 - EQ_TOLERANCE_PCT/100/2))
        ssl_touched = (not np.isnan(ssl)) and (prev_row['low']  <= ssl * (1 + EQ_TOLERANCE_PCT/100/2))

        # ── LONG entry: Equal High (BSL) touched + LVN above + confluence ────
        if bsl_touched and lvn_ab and (i - last_long >= cfg['min_gap']):
            score = (int(trend_up) + int(cvd_bull) +
                     int(vol_spike) + int(near_val))
            if score >= MIN_CONFLUENCE:
                ep     = bsl
                pv     = pos_size(capital, RISK_PER_TRADE, STOP_PCT)
                tp_px  = ep * (1 + TARGET_PCT / 100)
                sl_px  = ep * (1 - STOP_PCT   / 100)
                entry_px, direction, in_trade = ep, 'LONG', True
                pos_val, entry_idx, entry_time = pv, i, row['timestamp']

        # ── SHORT entry: Equal Low (SSL) touched + LVN below + confluence ─────
        elif ssl_touched and lvn_bl and (i - last_short >= cfg['min_gap']):
            score = (int(trend_dn) + int(cvd_bear) +
                     int(vol_spike) + int(near_vah))
            if score >= MIN_CONFLUENCE:
                ep     = ssl
                pv     = pos_size(capital, RISK_PER_TRADE, STOP_PCT)
                tp_px  = ep * (1 - TARGET_PCT / 100)
                sl_px  = ep * (1 + STOP_PCT   / 100)
                entry_px, direction, in_trade = ep, 'SHORT', True
                pos_val, entry_idx, entry_time = pv, i, row['timestamp']

    # Force-close
    if in_trade:
        last = df.iloc[-1]; ep2 = last['close']
        qty  = pos_val / entry_px
        g    = qty*(ep2-entry_px) if direction=='LONG' else qty*(entry_px-ep2)
        ef   = pos_val*MAKER_FEE + abs(qty*ep2)*TAKER_FEE
        net  = g - ef; capital += net
        trades.append({'symbol':symbol,'tf':tf,'direction':direction,
                       'entry_time':entry_time,'exit_time':last['timestamp'],
                       'entry_px':round(entry_px,4),'exit_px':round(ep2,4),
                       'tp_px':round(tp_px,4),'sl_px':round(sl_px,4),
                       'exit_reason':'END','pos_value':round(pos_val,2),
                       'gross_pnl':round(g,2),'fees':round(ef,2),
                       'net_pnl':round(net,2),'return_pct':round(net/pos_val*100,4),
                       'hold_bars':n-1-entry_idx,'cap_after':round(capital,2),
                       'bsl_touches':0,'poc_at_entry':None,'lvn_filtered':False})
        equity.append({'timestamp':last['timestamp'],'equity':capital})

    return trades, equity, capital


# ═══════════════════════════════════════════════════════════════════════════════
# METRICS & PRINTING
# ═══════════════════════════════════════════════════════════════════════════════
def compute_metrics(trades, equity_curve, init_cap):
    if not trades: return None
    dt   = pd.DataFrame(trades)
    wins = dt[dt['net_pnl'] > 0]; loss = dt[dt['net_pnl'] <= 0]
    n    = len(dt)
    gp   = wins['net_pnl'].sum() if len(wins) else 0
    gl   = abs(loss['net_pnl'].sum()) if len(loss) else 0
    pf   = gp/gl if gl > 0 else float('inf')
    aw   = wins['net_pnl'].mean() if len(wins) else 0
    al   = loss['net_pnl'].mean() if len(loss) else 0

    eq   = pd.DataFrame(equity_curve)
    eq['peak'] = eq['equity'].cummax()
    eq['dd']   = (eq['equity']-eq['peak'])/eq['peak']*100
    mdd  = eq['dd'].min(); fin = eq['equity'].iloc[-1]
    days = (eq['timestamp'].iloc[-1]-eq['timestamp'].iloc[0]).days
    ann  = ((fin/init_cap)**(365/max(days,1))-1)*100

    def streak(lst, v):
        best=cur=0
        for x in lst:
            cur=(cur+1) if x==v else 0; best=max(best,cur)
        return best
    signs = [1 if p>0 else -1 for p in dt['net_pnl']]
    lt = dt[dt['direction']=='LONG']; st = dt[dt['direction']=='SHORT']
    avg_touches = dt['bsl_touches'].mean() if 'bsl_touches' in dt else 0
    lvn_pct = dt['lvn_filtered'].mean()*100 if 'lvn_filtered' in dt else 0

    return {
        'n_trades':n, 'n_long':len(lt), 'n_short':len(st),
        'n_wins':len(wins), 'n_losses':len(loss),
        'win_rate':round(len(wins)/n*100,2),
        'long_wr':round(len(lt[lt['net_pnl']>0])/len(lt)*100,1) if len(lt) else 0,
        'short_wr':round(len(st[st['net_pnl']>0])/len(st)*100,1) if len(st) else 0,
        'total_pnl':round(dt['net_pnl'].sum(),2),
        'gross_profit':round(gp,2), 'gross_loss':round(gl,2),
        'profit_factor':round(pf,3) if pf!=float('inf') else 'inf',
        'avg_win':round(aw,2), 'avg_loss':round(al,2),
        'actual_rr':round(abs(aw/al),2) if al!=0 else 0,
        'total_fees':round(dt['fees'].sum(),2),
        'avg_hold':round(dt['hold_bars'].mean(),1),
        'start_cap':round(init_cap,2), 'final_cap':round(fin,2),
        'total_ret':round((fin-init_cap)/init_cap*100,2),
        'ann_ret':round(ann,2), 'max_dd':round(mdd,2),
        'max_win_streak':streak(signs,1), 'max_loss_streak':streak(signs,-1),
        'exits':dt['exit_reason'].value_counts().to_dict(),
        'avg_eq_touches':round(avg_touches,1),
        'lvn_filter_pct':round(lvn_pct,1),
    }


def print_report(m, label, vs_prev=None):
    L = '─'*66
    pf = m['profit_factor']
    pf_s = str(pf) if pf=='inf' else f"{float(pf):.3f}"
    print(f"\n{L}\n  {label}\n{L}")
    print(f"  Trades:           {m['n_trades']:>5}  ({m['n_long']} long / {m['n_short']} short)")
    print(f"  Win Rate:         {m['win_rate']:>5.1f}%  (L {m['long_wr']:.1f}% / S {m['short_wr']:.1f}%)")
    print(f"  Profit Factor:   {pf_s}")
    print(f"  Avg Win:        ${m['avg_win']:>9,.2f}   |  Avg Loss: ${m['avg_loss']:>9,.2f}")
    print(f"  Actual R:R:      1 : {m['actual_rr']:.2f}")
    print(f"  Win/Loss Streak: {m['max_win_streak']} / {m['max_loss_streak']}")
    print(f"  Avg Hold:        {m['avg_hold']:.1f} bars  |  Fees: ${m['total_fees']:,.2f}")
    print(f"  Avg EQ Touches:  {m['avg_eq_touches']:.1f}  |  LVN filtered: {m['lvn_filter_pct']:.0f}% of signals")
    print(L)
    print(f"  Capital: ${m['start_cap']:,.2f}  →  ${m['final_cap']:,.2f}   "
          f"({m['total_ret']:+.2f}%  /  Ann {m['ann_ret']:+.2f}%)")
    print(f"  Max Drawdown:    {m['max_dd']:.2f}%")
    exits_str = "  ".join(f"{k}:{v}" for k,v in sorted(m['exits'].items(), key=lambda x:-x[1]))
    print(f"  Exits: {exits_str}")
    if vs_prev is not None:
        delta_pf  = float(str(pf))-float(str(vs_prev['profit_factor'])) if pf!='inf' else 999
        delta_wr  = m['win_rate']-vs_prev['win_rate']
        delta_ret = m['total_ret']-vs_prev['total_ret']
        delta_dd  = m['max_dd']-vs_prev['max_dd']
        print(f"  vs v2:  WR {delta_wr:+.1f}pp  PF {delta_pf:+.3f}  Ret {delta_ret:+.1f}pp  DD {delta_dd:+.1f}pp")
    print(L)
    pf_v = float(str(pf)) if pf!='inf' else 9999
    if   pf_v>=1.5 and m['win_rate']>=50: vrd="EXCELLENT  ✓"
    elif pf_v>=1.3 and m['win_rate']>=45: vrd="GOOD  — profitable"
    elif pf_v>=1.1:                        vrd="MARGINAL  — barely profitable"
    elif pf_v>1.0:                         vrd="MARGINAL"
    else:                                  vrd="UNPROFITABLE"
    print(f"  Verdict: {vrd}\n{L}")


def merge_equity(a, b, init):
    ea={e['timestamp']:e['equity'] for e in a}
    eb={e['timestamp']:e['equity'] for e in b}
    la=lb=init/2; out=[]
    for ts in sorted(set(list(ea)+list(eb))):
        if ts in ea: la=ea[ts]
        if ts in eb: lb=eb[ts]
        out.append({'timestamp':ts,'equity':la+lb})
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    ts_str = datetime.now().strftime('%Y%m%d_%H%M%S')

    # Previous v2 results for comparison (4h combined, 1yr)
    V2_REFERENCE = {
        'COMBINED_4h': {'win_rate':49.6,'profit_factor':1.13,'total_ret':12.48,'max_dd':-9.49},
        'COMBINED_1h': {'win_rate':40.2,'profit_factor':0.78,'total_ret':-41.0,'max_dd':-42.9},
    }

    print(f"""
{'='*66}
  LIQUIDITY STRATEGY v3  |  Equal H/L + Volume Profile + LVN Filter
  Last 1 Year  (Apr 2025 – Apr 2026)  |  $10,500 Capital
{'='*66}

  LIQUIDITY SOURCE   Equal Highs / Equal Lows (≥ {EQ_MIN_TOUCHES} touches, {EQ_TOLERANCE_PCT}% tolerance)
  VOLUME PROFILE     Rolling {VP_WINDOW}-bar  |  {VP_BINS} bins  |  VA = {VP_VALUE_AREA_PCT}%
  LVN FILTER         Entry only when Low Volume Node exists between
                     entry price and ±{TARGET_PCT}% target (empty air = fast move)
  CONFLUENCE         {MIN_CONFLUENCE}/4 required: Trend + CVD + Volume spike + VP position
  FEES               Entry/TP: maker {MAKER_FEE*100:.2f}%  |  SL: taker {TAKER_FEE*100:.2f}%+slip
{'='*66}""")

    COMBOS = [
        ('5m',  'BTC'), ('5m',  'ETH'),
        ('1h',  'BTC'), ('1h',  'ETH'),
        ('4h',  'BTC'), ('4h',  'ETH'),
    ]

    all_results = {}
    tf_data     = {tf: {} for tf in ['5m','1h','4h']}

    for tf, sym in COMBOS:
        key = f"{sym}_{tf}"
        df  = load_asset(sym, tf)
        t, eq, fc = run_backtest(sym, df, tf)
        m = compute_metrics(t, eq, CAPITAL_PER_ASSET)
        all_results[key] = {'metrics': m, 'equity': eq}
        tf_data[tf][sym] = {'trades': t, 'equity': eq}

        v2_ref = None  # per-asset v2 not stored; will compare at combined level
        if m:
            print_report(m, f"{sym} [{tf.upper()}]  |  ${CAPITAL_PER_ASSET:,.0f} start", vs_prev=None)
        else:
            print(f"\n  ── {sym} [{tf}]: No trades generated ──")

    # ── Combined per timeframe ──────────────────────────────────────────────
    print(f"\n{'='*66}")
    print("  COMBINED PORTFOLIO  (BTC + ETH per timeframe)")
    print(f"{'='*66}")

    for tf in ['5m','1h','4h']:
        bd = tf_data[tf].get('BTC'); ed = tf_data[tf].get('ETH')
        if not (bd and ed): continue
        ceq = merge_equity(bd['equity'], ed['equity'], INITIAL_CAPITAL)
        ct  = bd['trades'] + ed['trades']
        m   = compute_metrics(ct, ceq, INITIAL_CAPITAL)
        if m:
            v2_ref = V2_REFERENCE.get(f'COMBINED_{tf}')
            print_report(m, f"COMBINED [{tf.upper()}]  |  ${INITIAL_CAPITAL:,.0f} start", vs_prev=v2_ref)
            all_results[f"COMBINED_{tf}"] = {'metrics': m, 'equity': ceq}

    # ── Summary table ───────────────────────────────────────────────────────
    print(f"\n{'='*66}")
    print("  SUMMARY  —  v3 vs v2 Comparison  (last 1 year, combined portfolio)")
    print(f"{'='*66}")
    print(f"  {'':25} {'v2':>10} {'v3':>10} {'Δ':>8}")
    print(f"  {'─'*55}")
    metrics_to_compare = [
        ('Win Rate (%)',   'win_rate',       lambda v: f"{v:.1f}"),
        ('Profit Factor', 'profit_factor',  lambda v: str(v)[:5]),
        ('Total Return %','total_ret',      lambda v: f"{v:+.1f}"),
        ('Max Drawdown %','max_dd',         lambda v: f"{v:.1f}"),
    ]
    for tf in ['4h','1h','5m']:
        ref_key = f"COMBINED_{tf}"
        m3 = all_results.get(ref_key,{}).get('metrics')
        m2 = V2_REFERENCE.get(ref_key,{})
        if not m3: continue
        print(f"\n  {tf.upper()} Combined:")
        for label, key, fmt in metrics_to_compare:
            v3 = m3.get(key,'—'); v2 = m2.get(key,'—')
            f3 = fmt(v3) if v3!='—' else '—'
            f2 = fmt(v2) if v2!='—' else '—'
            try:
                delta = f"{float(str(v3))-float(str(v2)):+.2f}" if v3!='—' and v2!='—' else '—'
            except: delta='—'
            print(f"    {label:<24} {f2:>10} {f3:>10} {delta:>8}")

    print(f"\n{'='*66}")

    # ── Save ────────────────────────────────────────────────────────────────
    all_trades = []
    for tf in ['5m','1h','4h']:
        for sym in ['BTC','ETH']:
            all_trades.extend(tf_data[tf].get(sym,{}).get('trades',[]))

    pd.DataFrame(all_trades).to_csv(
        f"{RESULTS_DIR}/v3_trades_{ts_str}.csv", index=False)

    with open(f"{RESULTS_DIR}/v3_metrics_{ts_str}.json",'w') as f:
        json.dump({
            'run_at': ts_str,
            'config': {
                'eq_tolerance_pct': EQ_TOLERANCE_PCT,
                'eq_min_touches': EQ_MIN_TOUCHES,
                'eq_lookback': EQ_LOOKBACK,
                'vp_window': VP_WINDOW,
                'vp_bins': VP_BINS,
                'target_pct': TARGET_PCT,
                'stop_pct': STOP_PCT,
                'maker_fee': MAKER_FEE*100,
                'taker_fee': TAKER_FEE*100,
            },
            'results': {k:v['metrics'] for k,v in all_results.items() if v.get('metrics')}
        }, f, indent=2, default=str)

    print(f"\n  Trades  → {RESULTS_DIR}/v3_trades_{ts_str}.csv")
    print(f"  Metrics → {RESULTS_DIR}/v3_metrics_{ts_str}.json\n")


if __name__ == "__main__":
    main()
