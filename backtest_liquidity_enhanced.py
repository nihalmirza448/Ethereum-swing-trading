"""
Enhanced Liquidity Strategy Backtest  — Multi-Timeframe Edition
================================================================
Strategy: BSL/SSL → N% Target  with  Confluence Filters + Trend Filter + Limit Orders

Confluence gate (need ≥ 2 of 3):
  [1] Trend filter  — EMA50 > EMA200 → only longs  |  EMA50 < EMA200 → only shorts
  [2] CVD slope     — positive → long  |  negative → short
  [3] Volume spike  — bar volume > 1.5× 20-bar MA

Limit-order simulation:
  Entry   : LIMIT at BSL/SSL level   → Kraken MAKER fee 0.16%
  TP exit : LIMIT at target          → Kraken MAKER fee 0.16%
  SL exit : MARKET at stop           → Kraken TAKER fee 0.26% + 0.03% slippage

Timeframes : 5m  |  1h (stop-loss optimised)  |  4h
Assets     : BTC  +  ETH
Period     : Last 1 year  (Apr 2025 – Apr 2026)
Capital    : $10,500  ($5,250 per asset)
"""

import pandas as pd
import numpy as np
import json, os
from datetime import datetime

# ─── CONSTANTS ────────────────────────────────────────────────────────────────
INITIAL_CAPITAL   = 10_500.00
CAPITAL_PER_ASSET = INITIAL_CAPITAL / 2
RISK_PER_TRADE_PCT = 2.00
MAKER_FEE_PCT      = 0.16
TAKER_FEE_PCT      = 0.26
SL_SLIPPAGE_PCT    = 0.03
MIN_CONFLUENCE     = 2
VOLUME_SPIKE_MULT  = 1.5
VOL_MA_PERIOD      = 20
EMA_FAST           = 50
EMA_SLOW           = 200
DATA_DIR           = "data"
RESULTS_DIR        = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)

# Per-timeframe tuning: (swing_order, bsl_lookback, max_hold_bars, min_gap_bars)
TF_PARAMS = {
    '5m':  dict(swing_order=4,  bsl_lookback=3, max_hold=72,  min_gap=6),
    '1h':  dict(swing_order=7,  bsl_lookback=3, max_hold=72,  min_gap=6),
    '4h':  dict(swing_order=5,  bsl_lookback=3, max_hold=18,  min_gap=2),
}

# ─── DATA ─────────────────────────────────────────────────────────────────────
CUTOFF = pd.Timestamp('2025-04-12')

def load_asset(symbol, tf):
    mapping = {
        '5m':  f"{DATA_DIR}/{symbol.lower()}_usd_5m_365d.csv",
        '1h':  f"{DATA_DIR}/{symbol.lower()}_usd_60m_1825d.csv",
        '4h':  None,   # resampled from 1h
    }
    if tf == '4h':
        df_1h = pd.read_csv(mapping['1h'], parse_dates=['timestamp'])
        df_1h = df_1h[df_1h['timestamp'] >= CUTOFF].reset_index(drop=True)
        df = df_1h.set_index('timestamp').resample('4h').agg(
            {'open':'first','high':'max','low':'min','close':'last','volume':'sum'}
        ).dropna(subset=['open']).reset_index()
    else:
        df = pd.read_csv(mapping[tf], parse_dates=['timestamp'])
        df = df[df['timestamp'] >= CUTOFF].reset_index(drop=True)
    return df.sort_values('timestamp').reset_index(drop=True)


# ─── INDICATORS ───────────────────────────────────────────────────────────────
def add_indicators(df, swing_order, bsl_lookback):
    df = df.copy()
    df['ema_fast'] = df['close'].ewm(span=EMA_FAST, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=EMA_SLOW, adjust=False).mean()
    df['vol_ma']   = df['volume'].rolling(VOL_MA_PERIOD).mean()

    # CVD wick-weighted
    body      = (df['close'] - df['open']).abs()
    rng       = (df['high'] - df['low']).replace(0, 1e-9)
    bp        = body / rng
    buy_vol   = np.where(df['close'] >= df['open'],
                         df['volume'] * (0.5 + bp * 0.5),
                         df['volume'] * (0.5 - bp * 0.5))
    sell_vol  = np.where(df['close'] <  df['open'],
                         df['volume'] * (0.5 + bp * 0.5),
                         df['volume'] * (0.5 - bp * 0.5))
    cvd = pd.Series(buy_vol - sell_vol).cumsum()
    df['cvd_slope'] = cvd.diff(5)

    # Swing highs / lows (pure numpy, no scipy)
    H, L, n, o = df['high'].values, df['low'].values, len(df), swing_order
    sh = np.zeros(n, dtype=bool)
    sl = np.zeros(n, dtype=bool)
    for i in range(o, n - o):
        hw = H[i-o:i+o+1];  lw = L[i-o:i+o+1]
        if H[i] >= hw.max() and (hw == H[i]).sum() == 1: sh[i] = True
        if L[i] <= lw.min() and (lw == L[i]).sum() == 1: sl[i] = True
    df['swing_high'] = sh
    df['swing_low']  = sl

    # Rolling BSL / SSL (no lookahead)
    bsl_a = np.full(n, np.nan);  ssl_a = np.full(n, np.nan)
    sh_h, sl_h = [], []
    for i in range(n):
        if sh[i]: sh_h.append(H[i])
        if sl[i]: sl_h.append(L[i])
        if sh_h: bsl_a[i] = max(sh_h[-bsl_lookback:])
        if sl_h: ssl_a[i] = min(sl_h[-bsl_lookback:])
    df['bsl'] = bsl_a
    df['ssl'] = ssl_a
    return df


# ─── INTRABAR EXIT ────────────────────────────────────────────────────────────
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


# ─── CORE BACKTEST ────────────────────────────────────────────────────────────
def run_backtest(symbol, df, tf_key, target_pct, stop_pct):
    p         = TF_PARAMS[tf_key]
    df        = add_indicators(df, p['swing_order'], p['bsl_lookback'])
    capital   = CAPITAL_PER_ASSET
    trades, equity = [], [{'timestamp': df['timestamp'].iloc[0], 'equity': capital}]

    in_trade = False
    direction = entry_px = tp_px = sl_px = pos_val = None
    entry_idx = entry_time = None
    last_long = last_short = -9999

    mk  = MAKER_FEE_PCT  / 100
    tk  = TAKER_FEE_PCT  / 100
    slp = SL_SLIPPAGE_PCT / 100
    warm = max(EMA_SLOW + 5, p['swing_order']*2+5, VOL_MA_PERIOD+5)

    for i in range(warm, len(df)):
        row  = df.iloc[i]
        prev = df.iloc[i - 1]

        bsl  = prev['bsl'];   ssl  = prev['ssl']
        emaf = prev['ema_fast']; emas = prev['ema_slow']
        cvds = prev['cvd_slope']
        vol  = prev['volume']; volma = prev['vol_ma']

        # ── Manage open trade ──────────────────────────────────────────────
        if in_trade:
            rsn, ex = check_exit(row, direction, tp_px, sl_px)
            if rsn is None and (i - entry_idx) >= p['max_hold']:
                rsn, ex = 'TIMEOUT', row['close']
            if rsn:
                qty = pos_val / entry_px
                gross = qty*(ex-entry_px) if direction=='LONG' else qty*(entry_px-ex)
                ef_entry = pos_val * mk
                ef_exit  = abs(qty*ex) * (mk if rsn=='TP' else tk+slp)
                net = gross - ef_entry - ef_exit
                capital += net
                trades.append({
                    'symbol': symbol, 'tf': tf_key,
                    'direction': direction,
                    'entry_time': entry_time, 'exit_time': row['timestamp'],
                    'entry_px': round(entry_px,4), 'exit_px': round(ex,4),
                    'tp_px': round(tp_px,4), 'sl_px': round(sl_px,4),
                    'exit_reason': rsn, 'pos_value': round(pos_val,2),
                    'gross_pnl': round(gross,2), 'fees': round(ef_entry+ef_exit,2),
                    'net_pnl': round(net,2), 'return_pct': round(net/pos_val*100,4),
                    'hold_bars': i-entry_idx, 'cap_after': round(capital,2),
                    'target_pct': target_pct, 'stop_pct': stop_pct,
                })
                equity.append({'timestamp': row['timestamp'], 'equity': capital})
                if direction=='LONG': last_long=i
                else:                 last_short=i
                in_trade = False

        if in_trade or capital <= 10: continue
        if any(pd.isna(x) for x in [bsl, ssl, emaf, emas, cvds, volma]) or volma==0:
            continue

        trend_up   = emaf > emas;   trend_dn = emaf < emas
        cvd_bull   = cvds > 0;      cvd_bear  = cvds < 0
        vol_spike  = vol > (VOLUME_SPIKE_MULT * volma)

        bsl_hit = prev['high'] >= bsl
        ssl_hit = prev['low']  <= ssl

        if bsl_hit and (i - last_long  >= p['min_gap']):
            score = int(trend_up) + int(cvd_bull) + int(vol_spike)
            if score >= MIN_CONFLUENCE:
                ep = bsl
                pv = pos_size(capital, RISK_PER_TRADE_PCT, stop_pct)
                tp_px = ep * (1 + target_pct/100)
                sl_px = ep * (1 - stop_pct/100)
                entry_px, direction, in_trade = ep, 'LONG', True
                pos_val, entry_idx, entry_time = pv, i, row['timestamp']

        elif ssl_hit and (i - last_short >= p['min_gap']):
            score = int(trend_dn) + int(cvd_bear) + int(vol_spike)
            if score >= MIN_CONFLUENCE:
                ep = ssl
                pv = pos_size(capital, RISK_PER_TRADE_PCT, stop_pct)
                tp_px = ep * (1 - target_pct/100)
                sl_px = ep * (1 + stop_pct/100)
                entry_px, direction, in_trade = ep, 'SHORT', True
                pos_val, entry_idx, entry_time = pv, i, row['timestamp']

    # Force-close lingering trade
    if in_trade:
        last = df.iloc[-1]; ep2 = last['close']
        qty = pos_val/entry_px
        g = qty*(ep2-entry_px) if direction=='LONG' else qty*(entry_px-ep2)
        ef = pos_val*mk + abs(qty*ep2)*tk
        net = g - ef; capital += net
        trades.append({'symbol':symbol,'tf':tf_key,'direction':direction,
                       'entry_time':entry_time,'exit_time':last['timestamp'],
                       'entry_px':round(entry_px,4),'exit_px':round(ep2,4),
                       'tp_px':round(tp_px,4),'sl_px':round(sl_px,4),
                       'exit_reason':'END','pos_value':round(pos_val,2),
                       'gross_pnl':round(g,2),'fees':round(ef,2),
                       'net_pnl':round(net,2),'return_pct':round(net/pos_val*100,4),
                       'hold_bars':len(df)-1-entry_idx,'cap_after':round(capital,2),
                       'target_pct':target_pct,'stop_pct':stop_pct})
        equity.append({'timestamp':last['timestamp'],'equity':capital})

    return trades, equity, capital


# ─── METRICS ──────────────────────────────────────────────────────────────────
def metrics(trades, equity_curve, init_cap):
    if not trades: return None
    dt   = pd.DataFrame(trades)
    wins = dt[dt['net_pnl'] > 0]; loss = dt[dt['net_pnl'] <= 0]
    n = len(dt)
    gp = wins['net_pnl'].sum() if len(wins) else 0
    gl = abs(loss['net_pnl'].sum()) if len(loss) else 0
    pf = gp/gl if gl > 0 else float('inf')
    aw = wins['net_pnl'].mean() if len(wins) else 0
    al = loss['net_pnl'].mean() if len(loss) else 0

    eq = pd.DataFrame(equity_curve)
    eq['peak'] = eq['equity'].cummax()
    eq['dd']   = (eq['equity']-eq['peak'])/eq['peak']*100
    mdd = eq['dd'].min(); fin = eq['equity'].iloc[-1]
    days = (eq['timestamp'].iloc[-1]-eq['timestamp'].iloc[0]).days
    ann  = ((fin/init_cap)**(365/max(days,1))-1)*100

    def streak(lst,v):
        best=cur=0
        for x in lst:
            cur=(cur+1) if x==v else 0; best=max(best,cur)
        return best

    signs = [1 if p>0 else -1 for p in dt['net_pnl']]
    lt = dt[dt['direction']=='LONG']; st = dt[dt['direction']=='SHORT']
    return {
        'n_trades':n,'n_long':len(lt),'n_short':len(st),
        'n_wins':len(wins),'n_losses':len(loss),
        'win_rate':round(len(wins)/n*100,2),
        'long_wr':round(len(lt[lt['net_pnl']>0])/len(lt)*100,1) if len(lt) else 0,
        'short_wr':round(len(st[st['net_pnl']>0])/len(st)*100,1) if len(st) else 0,
        'total_pnl':round(dt['net_pnl'].sum(),2),
        'gross_profit':round(gp,2),'gross_loss':round(gl,2),
        'profit_factor':round(pf,3) if pf!=float('inf') else 'inf',
        'avg_win':round(aw,2),'avg_loss':round(al,2),
        'actual_rr':round(abs(aw/al),2) if al!=0 else 0,
        'total_fees':round(dt['fees'].sum(),2),
        'avg_hold':round(dt['hold_bars'].mean(),1),
        'start_cap':round(init_cap,2),'final_cap':round(fin,2),
        'total_ret':round((fin-init_cap)/init_cap*100,2),
        'ann_ret':round(ann,2),'max_dd':round(mdd,2),
        'max_win_streak':streak(signs,1),'max_loss_streak':streak(signs,-1),
        'exits':dt['exit_reason'].value_counts().to_dict(),
    }


def print_report(m, label):
    L = '─'*66
    pf = m['profit_factor']
    pf_s = str(pf) if pf=='inf' else f"{float(pf):.3f}"
    print(f"\n{L}\n  {label}\n{L}")
    print(f"  Trades:            {m['n_trades']:>4}  ({m['n_long']} long / {m['n_short']} short)")
    print(f"  Win Rate:          {m['win_rate']:>5.1f}%  (L {m['long_wr']:.1f}% / S {m['short_wr']:.1f}%)")
    print(f"  Profit Factor:    {pf_s}")
    print(f"  Avg Win:         ${m['avg_win']:>9,.2f}   |  Avg Loss: ${m['avg_loss']:>9,.2f}")
    print(f"  Actual R:R:       1 : {m['actual_rr']:.2f}")
    print(f"  Win/Loss Streak:  {m['max_win_streak']} / {m['max_loss_streak']}")
    print(f"  Avg Hold:         {m['avg_hold']:.1f} bars  |  Fees: ${m['total_fees']:,.2f}")
    print(L)
    print(f"  Capital:  ${m['start_cap']:,.2f}  →  ${m['final_cap']:,.2f}   "
          f"({m['total_ret']:+.2f}%  /  Ann {m['ann_ret']:+.2f}%)")
    print(f"  Max Drawdown:     {m['max_dd']:.2f}%")
    exits_str = "  ".join(f"{k}:{v}" for k,v in
                           sorted(m['exits'].items(), key=lambda x:-x[1]))
    print(f"  Exits:  {exits_str}")
    print(L)
    pf_v = float(str(pf)) if pf!='inf' else 9999
    if   pf_v>=1.5 and m['win_rate']>=48: vrd="EXCELLENT  ✓"
    elif pf_v>=1.2:                        vrd="GOOD  — profitable"
    elif pf_v>1.0:                         vrd="MARGINAL  — barely profitable"
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


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    ts_str = datetime.now().strftime('%Y%m%d_%H%M%S')

    # ── Step 1: Stop-loss grid search on 1h ───────────────────────────────
    # Combinations (stop%, target%) — all maintain ≥ 1:2 R:R
    SL_TP_GRID = [
        (1.0, 2.0),   # original
        (1.5, 3.0),   # 1:2 wider
        (2.0, 4.0),   # 1:2 widest
        (1.5, 3.5),   # 1:2.3
        (2.0, 5.0),   # 1:2.5
        (2.5, 5.0),   # 1:2
    ]

    print(f"""
{'='*66}
  ENHANCED LIQUIDITY STRATEGY  |  Last 1 Year (Apr 2025–Apr 2026)
  5-Minute  +  1-Hour (SL-optimised)  +  4-Hour
  BTC  +  ETH  |  $10,500 capital
{'='*66}

  FEES (Kraken):
    Entry / TP  — LIMIT  → maker {MAKER_FEE_PCT}%
    SL exit     — MARKET → taker {TAKER_FEE_PCT}% + {SL_SLIPPAGE_PCT}% slippage
    Best-case RT (TP):  {MAKER_FEE_PCT*2:.2f}%
    Worst-case RT (SL): {MAKER_FEE_PCT+TAKER_FEE_PCT+SL_SLIPPAGE_PCT:.2f}%
{'='*66}""")

    print("\n  ════════════════════════════════════════════════")
    print("  STEP 1 — STOP-LOSS OPTIMISATION ON 1H TIMEFRAME")
    print("  ════════════════════════════════════════════════")
    print(f"  Testing {len(SL_TP_GRID)} stop/target combinations on BTC+ETH 1h ...\n")

    btc_1h = load_asset('BTC', '1h')
    eth_1h = load_asset('ETH', '1h')

    opt_rows = []
    for (sl, tp) in SL_TP_GRID:
        btc_t, btc_eq, btc_fc = run_backtest('BTC', btc_1h, '1h', tp, sl)
        eth_t, eth_eq, eth_fc = run_backtest('ETH', eth_1h, '1h', tp, sl)
        all_t  = btc_t + eth_t
        c_eq   = merge_equity(btc_eq, eth_eq, INITIAL_CAPITAL)
        m      = metrics(all_t, c_eq, INITIAL_CAPITAL)
        if not m: continue
        pf_v = float(str(m['profit_factor'])) if m['profit_factor']!='inf' else 99
        opt_rows.append({
            'stop': sl, 'target': tp, 'rr': round(tp/sl,1),
            **{k: m[k] for k in ['n_trades','win_rate','profit_factor',
                                   'total_pnl','ann_ret','max_dd','total_fees','final_cap']},
            'pf_num': pf_v,
        })
        pf_str = str(m['profit_factor']) if m['profit_factor']=='inf' else f"{pf_v:.3f}"
        status = "✓ PROFIT" if pf_v>1.0 else "  loss"
        print(f"  SL {sl:4.1f}% / TP {tp:4.1f}%  (1:{tp/sl:.1f})  →  "
              f"WR {m['win_rate']:>5.1f}%  PF {pf_str:>6}  "
              f"P&L ${m['total_pnl']:>+8,.0f}  Ann {m['ann_ret']:>+6.1f}%  "
              f"DD {m['max_dd']:>6.1f}%   {status}")

    # Best 1h config (highest profit factor among profitable, else highest PF overall)
    opt_df  = pd.DataFrame(opt_rows)
    profitable = opt_df[opt_df['pf_num'] > 1.0]
    if len(profitable):
        best_row = profitable.sort_values('ann_ret', ascending=False).iloc[0]
    else:
        best_row = opt_df.sort_values('pf_num', ascending=False).iloc[0]
    BEST_SL_1H = best_row['stop']
    BEST_TP_1H = best_row['target']

    print(f"\n  ▶ Best 1h config: SL {BEST_SL_1H}% / TP {BEST_TP_1H}%  "
          f"(1:{BEST_TP_1H/BEST_SL_1H:.1f})  "
          f"PF {best_row['profit_factor']}  Ann {best_row['ann_ret']:+.1f}%")

    # ── Step 2: Full per-asset runs with chosen configs ────────────────────
    RUN_CONFIGS = [
        # (tf_label, symbol, data_fn, target_pct, stop_pct)
        ('5m',  'BTC', lambda: load_asset('BTC','5m'), 2.0, 1.0),
        ('5m',  'ETH', lambda: load_asset('ETH','5m'), 2.0, 1.0),
        ('1h',  'BTC', lambda: btc_1h,                 BEST_TP_1H, BEST_SL_1H),
        ('1h',  'ETH', lambda: eth_1h,                 BEST_TP_1H, BEST_SL_1H),
        ('4h',  'BTC', lambda: load_asset('BTC','4h'), 2.0, 1.0),
        ('4h',  'ETH', lambda: load_asset('ETH','4h'), 2.0, 1.0),
    ]

    all_results = {}
    all_trades  = []
    tf_eq       = {'5m':{}, '1h':{}, '4h':{}}

    print(f"\n\n  ════════════════════════════════════════════════")
    print(f"  STEP 2 — FULL BACKTEST ACROSS ALL TIMEFRAMES")
    print(f"  ════════════════════════════════════════════════")

    for (tf, sym, df_fn, tp, sl) in RUN_CONFIGS:
        key = f"{sym}_{tf}"
        lbl = f"  SL {sl}% / TP {tp}%" if tf=='1h' else ""
        print(f"\n  ▶ {sym} [{tf}]{lbl} ...")
        df_data = df_fn()
        t, eq, fc = run_backtest(sym, df_data, tf, tp, sl)
        m = metrics(t, eq, CAPITAL_PER_ASSET)
        all_results[key] = {'metrics': m, 'equity': eq}
        all_trades.extend([{**tr, 'timeframe': tf} for tr in t])
        tf_eq[tf][sym] = {'equity': eq, 'trades': t}
        if m:
            slabel = f"SL {sl}% / TP {tp}%  " if tf=='1h' else ""
            print_report(m, f"{sym} [{tf.upper()}]  {slabel}|  ${CAPITAL_PER_ASSET:,.0f} start")
        else:
            print(f"  No trades for {sym} [{tf}]")

    # ── Step 3: Combined portfolio per timeframe ───────────────────────────
    print(f"\n\n  ════════════════════════════════════════════════")
    print(f"  STEP 3 — COMBINED PORTFOLIO (BTC + ETH)")
    print(f"  ════════════════════════════════════════════════")

    for tf in ['5m', '1h', '4h']:
        bd = tf_eq[tf].get('BTC'); ed = tf_eq[tf].get('ETH')
        if not (bd and ed): continue
        ceq = merge_equity(bd['equity'], ed['equity'], INITIAL_CAPITAL)
        ct  = bd['trades'] + ed['trades']
        m   = metrics(ct, ceq, INITIAL_CAPITAL)
        if m:
            sl_note = f"SL {BEST_SL_1H}%/TP {BEST_TP_1H}%  " if tf=='1h' else ""
            print_report(m, f"COMBINED [{tf.upper()}]  {sl_note}|  ${INITIAL_CAPITAL:,.0f} start")
            all_results[f"COMBINED_{tf}"] = {'metrics': m, 'equity': ceq}

    # ── Summary table ──────────────────────────────────────────────────────
    print(f"\n\n{'='*66}")
    print("  FINAL SUMMARY  —  Last 1 Year  |  All Timeframes + Assets")
    print(f"{'='*66}")
    cols = ['BTC_5m','ETH_5m','BTC_1h','ETH_1h','BTC_4h','ETH_4h']
    print(f"  {'Metric':<22}" + "".join(f"{c:>10}" for c in cols))
    print(f"  {'─'*62}")
    for label, key, fmt in [
        ("Trades",       'n_trades',       lambda v: str(v)),
        ("Win Rate",     'win_rate',        lambda v: f"{v:.1f}%"),
        ("Profit Factor",'profit_factor',   lambda v: str(v)[:6]),
        ("Total P&L",    'total_pnl',       lambda v: f"${v:+,.0f}"),
        ("Ann Return",   'ann_ret',         lambda v: f"{v:+.1f}%"),
        ("Max Drawdown", 'max_dd',          lambda v: f"{v:.1f}%"),
        ("Fees Paid",    'total_fees',      lambda v: f"${v:,.0f}"),
        ("Final Capital",'final_cap',       lambda v: f"${v:,.0f}"),
    ]:
        row = f"  {label:<22}"
        for c in cols:
            m = all_results.get(c,{}).get('metrics')
            v = m.get(key,'—') if m else '—'
            row += f"{fmt(v):>10}" if v!='—' else f"{'—':>10}"
        print(row)

    print(f"\n  {'─'*62}")
    print("  Combined Portfolio (BTC+ETH per timeframe):")
    for tf, lab in [('5m','5m'),('1h',f"1h [SL {BEST_SL_1H}%/TP {BEST_TP_1H}%]"),('4h','4h')]:
        m = all_results.get(f"COMBINED_{tf}",{}).get('metrics')
        if m:
            pf = m['profit_factor']
            print(f"    {lab:<24}  WR {m['win_rate']:.1f}%  "
                  f"PF {str(pf)[:5]}  P&L ${m['total_pnl']:>+8,.0f}  "
                  f"Ann {m['ann_ret']:>+5.1f}%  DD {m['max_dd']:>6.1f}%  "
                  f"Final ${m['final_cap']:,.0f}")
    print(f"{'='*66}")

    # ── Save ───────────────────────────────────────────────────────────────
    pd.DataFrame(all_trades).to_csv(
        f"{RESULTS_DIR}/enhanced_multi_trades_{ts_str}.csv", index=False)
    with open(f"{RESULTS_DIR}/enhanced_multi_metrics_{ts_str}.json",'w') as f:
        json.dump({'run_at':ts_str,
                   'best_1h_config':{'stop':BEST_SL_1H,'target':BEST_TP_1H},
                   'results':{k:v['metrics'] for k,v in all_results.items() if v.get('metrics')}},
                  f, indent=2, default=str)
    print(f"\n  Saved → {RESULTS_DIR}/  ({ts_str})\n")


if __name__ == "__main__":
    main()
