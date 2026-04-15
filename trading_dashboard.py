"""
Trading Dashboard - Flask backend
Keeps INR-margin trades and USD/USDT trades completely separate.
"""
import time
import threading
import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

from kraken_client import KrakenClient
from coindcx_client import CoinDCXClient

log = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# ─── Server-side cache ────────────────────────────────────────────────────────
_CACHE: dict = {}
_CACHE_LOCKS: dict = {}          # per-key locks to prevent thundering herd
_CACHE_LOCKS_LOCK = threading.Lock()  # protects _CACHE_LOCKS itself

PRICE_TTL = 30        # seconds
TRADES_TTL = 120      # seconds — trades don't change every second
ASSET_PRICES_CACHE = {}
CACHE_TTL = 30


def _get_lock(key: str) -> threading.Lock:
    """Get or create a per-key lock (prevents multiple threads re-fetching simultaneously)."""
    with _CACHE_LOCKS_LOCK:
        if key not in _CACHE_LOCKS:
            _CACHE_LOCKS[key] = threading.Lock()
        return _CACHE_LOCKS[key]


def _cached(key: str, ttl: int, fn):
    """
    Return cached value if fresh.
    Uses a per-key lock so only ONE thread fetches when the cache is cold/stale.
    All other threads wait and then get the freshly-cached value.
    """
    entry = _CACHE.get(key)
    if entry and (_now_ts() - entry["ts"]) < ttl:
        return entry["val"]

    lock = _get_lock(key)
    with lock:
        # Re-check after acquiring lock (another thread may have populated it)
        entry = _CACHE.get(key)
        if entry and (_now_ts() - entry["ts"]) < ttl:
            return entry["val"]
        try:
            val = fn()
        except Exception as e:
            log.error("Cache fetch error for %s: %s", key, e)
            # Return stale value if available rather than crashing
            return entry["val"] if entry else None
        _CACHE[key] = {"val": val, "ts": _now_ts()}
        return val


def _warm_cache():
    """Pre-warm all expensive caches in background so browser requests are always fast."""
    try:
        kraken, coindcx = _get_clients()
        _dcx_futures_trades_cached()          # ~10s — the big one
        _kraken_trades_cached(days=365)        # ~1s
        _kraken_ledger_cached(days=365)        # ~1s
        _kraken_balance()
        _dcx_spot_balance()
        _dcx_futures_positions()
        _kraken_trade_balance_cached()
        log.info("Cache warmed successfully at %s", datetime.now().strftime("%H:%M:%S"))
    except Exception as e:
        log.error("Cache warm error: %s", e)


def _start_background_warmer():
    """Start a daemon thread that keeps the cache warm every 90 seconds."""
    def _loop():
        time.sleep(5)   # Let Flask finish starting up first
        while True:
            _warm_cache()
            time.sleep(90)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()


def _get_clients():
    """Return cached client instances (they're stateless so safe to reuse)."""
    return _cached("_clients", 3600, lambda: (KrakenClient(), CoinDCXClient()))


def _kraken_balance():
    kraken, _ = _get_clients()
    return _cached("kraken_balance", 30, lambda: kraken.get_account_balance())


def _dcx_spot_balance():
    _, coindcx = _get_clients()
    return _cached("dcx_spot_balance", 30, lambda: coindcx.get_account_balance())


def _dcx_futures_positions():
    _, coindcx = _get_clients()
    return _cached("dcx_futures_positions", 30, lambda: coindcx.get_futures_positions())


def _kraken_open_orders():
    kraken, _ = _get_clients()
    def _fetch():
        try:
            oo = kraken.get_open_orders()
            if hasattr(oo, "iterrows"):
                return list(oo.iterrows())
            return []
        except Exception:
            return []
    return _cached("kraken_open_orders", 30, _fetch)


def _kraken_trade_balance_cached():
    kraken, _ = _get_clients()
    return _cached("kraken_trade_balance", 30, lambda: _kraken_trade_balance(kraken))


def _dcx_spot_open_orders():
    _, coindcx = _get_clients()
    def _fetch():
        data = coindcx._make_request("exchange/v1/orders/active_orders", {}, authenticated=True)
        if not data:
            return []
        return data if isinstance(data, list) else data.get("orders", [])
    return _cached("dcx_spot_open_orders", 30, _fetch)


def _dcx_futures_open_orders():
    _, coindcx = _get_clients()
    return _cached("dcx_futures_open_orders", 30, lambda: coindcx.get_futures_orders(status="open") or [])


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _now_ts():
    return time.time()


def _kraken_symbol(asset: str) -> str:
    m = {"XXBT": "BTC", "XBT": "BTC", "XXETH": "ETH", "XETH": "ETH",
         "ZUSD": "USD", "ZEUR": "EUR", "ZGBP": "GBP",
         "USDT": "USDT", "USDC": "USDC", "USDUC": "USD.C"}
    return m.get(asset, asset.lstrip("XZ"))


_USD_STABLES = {
    "USD", "USDT", "USDC", "BUSD", "DAI", "USDUC", "USDM",
    "TUSD", "GUSD", "PYUSD", "FDUSD", "USDD",
}

def _get_usd_price(symbol: str, kraken: KrakenClient) -> float:
    if symbol in _USD_STABLES:
        return 1.0
    # Common non-USD fiat — skip rather than hang on a bad lookup
    if symbol in {"GBP", "EUR", "JPY", "INR", "AUD", "CAD"}:
        return 0.0
    cached = ASSET_PRICES_CACHE.get(symbol)
    if cached and _now_ts() - cached["ts"] < CACHE_TTL:
        return cached["price"]
    try:
        price = kraken.get_current_price(symbol)
    except Exception:
        price = None
    if price:
        ASSET_PRICES_CACHE[symbol] = {"price": price, "ts": _now_ts()}
    return price or 0.0


def _base_from_pair(pair: str) -> str:
    """Extract base asset from a trading pair string."""
    pair = pair.replace("B-", "").replace("I-", "")
    for q in ["USDT", "USD", "INR", "EUR", "BTC"]:
        if pair.upper().endswith(q):
            return pair.upper()[:-len(q)].rstrip("_")
    return pair[:3].upper()


def _dt(ts_ms_or_s: float, is_ms=True) -> str:
    ts = ts_ms_or_s / 1000 if is_ms else ts_ms_or_s
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


# ─── Data fetchers ────────────────────────────────────────────────────────────

def _kraken_trades_cached(kraken=None, days: int = 180):
    if kraken is None:
        kraken, _ = _get_clients()
    return _cached(f"kraken_trades_{days}", TRADES_TTL, lambda: _kraken_trades(kraken, days))

def _dcx_spot_trades_cached(coindcx=None, limit: int = 500):
    if coindcx is None:
        _, coindcx = _get_clients()
    return _cached("dcx_spot_trades", TRADES_TTL, lambda: _dcx_spot_trades(coindcx, limit))

def _dcx_futures_trades_cached(coindcx=None):
    if coindcx is None:
        _, coindcx = _get_clients()
    return _cached("dcx_futures_trades", TRADES_TTL, lambda: _dcx_futures_trades(coindcx))

def _kraken_ledger_cached(kraken=None, days: int = 180):
    if kraken is None:
        kraken, _ = _get_clients()
    return _cached(f"kraken_ledger_{days}", TRADES_TTL, lambda: _kraken_ledger(kraken, days))


def _kraken_trades(kraken: KrakenClient, days: int = 365):
    """Kraken margin trades → USD-denominated, all pages."""
    try:
        start = int(_now_ts() - days * 86400)
        all_raw = {}
        ofs = 0
        while True:
            resp = kraken.kraken.query_private("TradesHistory", {"start": start, "ofs": ofs})
            if resp.get("error"):
                break
            page = resp.get("result", {}).get("trades", {})
            total = resp.get("result", {}).get("count", 0)
            all_raw.update(page)
            if len(page) < 50 or len(all_raw) >= total:
                break
            ofs += 50

        trades = []
        for txid, t in all_raw.items():
            ts = float(t.get("time", 0))
            price = float(t.get("price", 0))
            qty = float(t.get("vol", 0))
            cost = float(t.get("cost", 0))
            margin = float(t.get("margin", 0))
            leverage = t.get("leverage", "")
            misc = t.get("misc", "")
            trades.append({
                "id": txid,
                "account": "Kraken Margin",
                "currency": "USD",
                "pair": t.get("pair", ""),
                "base": _kraken_symbol(_base_from_pair(t.get("pair", ""))),
                "side": t.get("type", ""),
                "order_type": t.get("ordertype", ""),
                "price": price,
                "quantity": qty,
                "volume": round(cost, 4),       # actual cost in USD
                "fee": float(t.get("fee", 0)),
                "fee_currency": "USD",
                "margin": round(margin, 4),     # margin posted for this trade
                "leverage": leverage,
                "is_opening": "opening" in misc,
                "is_closing": "closing" in misc,
                "is_maker": t.get("maker", False),
                "timestamp": ts,
                "datetime": _dt(ts, is_ms=False),
            })
        return sorted(trades, key=lambda x: x["timestamp"], reverse=True)
    except Exception as e:
        print(f"Kraken trades error: {e}")
        return []


def _kraken_ledger(kraken: KrakenClient, days: int = 365):
    """Kraken ledger, all pages."""
    try:
        start = int(_now_ts() - days * 86400)
        all_raw = {}
        ofs = 0
        while True:
            resp = kraken.kraken.query_private("Ledgers", {"start": start, "ofs": ofs})
            if resp.get("error"):
                break
            page = resp.get("result", {}).get("ledger", {})
            total = resp.get("result", {}).get("count", 0)
            all_raw.update(page)
            if len(page) < 50 or len(all_raw) >= total:
                break
            ofs += 50

        entries = []
        for lid, l in all_raw.items():
            ts = float(l.get("time", 0))
            entries.append({
                "id": lid, "account": "Kraken",
                "type": l.get("type", ""),
                "asset": _kraken_symbol(l.get("asset", "")),
                "amount": float(l.get("amount", 0)),
                "fee": float(l.get("fee", 0)),
                "balance": float(l.get("balance", 0)),
                "timestamp": ts, "datetime": _dt(ts, is_ms=False),
            })
        return sorted(entries, key=lambda x: x["timestamp"], reverse=True)
    except Exception as e:
        print(f"Kraken ledger error: {e}")
        return []


def _kraken_trade_balance(kraken: KrakenClient):
    """Kraken margin account summary (equity, free margin, open position margin)."""
    try:
        resp = kraken.kraken.query_private("TradeBalance", {"asset": "USDT"})
        if resp.get("error"):
            return {}
        r = resp.get("result", {})
        return {
            "equity": float(r.get("e", 0)),           # total equity
            "free_margin": float(r.get("mf", 0)),     # available for new positions
            "margin_used": float(r.get("m", 0)),       # in open positions
            "unrealized_pnl": float(r.get("n", 0)),   # floating P&L
            "trade_balance": float(r.get("tb", 0)),    # collateral base
            "equiv_balance": float(r.get("eb", 0)),    # total including all assets
        }
    except Exception as e:
        print(f"Kraken trade balance error: {e}")
        return {}


def _dcx_spot_trades(coindcx: CoinDCXClient, limit: int = 500):
    """CoinDCX spot trades → USDT-denominated."""
    try:
        data = coindcx._make_request(
            "exchange/v1/orders/trade_history", {"limit": limit}, authenticated=True
        )
        if not data or not isinstance(data, list):
            return []
        trades = []
        for t in data:
            ts = (t.get("created_at", 0) or 0) / 1000
            price = float(t.get("price", 0))
            qty = float(t.get("quantity", 0))
            trades.append({
                "id": str(t.get("id", "")),
                "account": "CoinDCX Spot",
                "currency": "USDT",
                "pair": t.get("market", ""),
                "base": _base_from_pair(t.get("market", "")),
                "side": t.get("side", ""),
                "order_type": t.get("order_type", ""),
                "price": price,
                "quantity": qty,
                "volume": round(price * qty, 4),   # in USDT
                "fee": float(t.get("fee_amount", 0)),
                "fee_currency": "USDT",
                "is_maker": None,
                "timestamp": ts,
                "datetime": _dt(ts),
            })
        return sorted(trades, key=lambda x: x["timestamp"], reverse=True)
    except Exception as e:
        print(f"DCX spot trades error: {e}")
        return []


def _dcx_futures_trades(coindcx: CoinDCXClient):
    """CoinDCX futures trades → INR-margin account. Fees in INR."""
    try:
        raw = coindcx.get_futures_trades(max_pages=100)
        trades = []
        for t in raw:
            ts = (t.get("timestamp", 0) or 0) / 1000
            price = float(t.get("price", 0))
            qty = float(t.get("quantity", 0))
            trades.append({
                "id": str(t.get("fill_id", t.get("order_id", ""))),
                "account": "CoinDCX Futures",
                "currency": "INR",       # margin / fee currency
                "quote_currency": "USDT", # instrument quote
                "pair": t.get("pair", ""),
                "base": _base_from_pair(t.get("pair", "")),
                "side": t.get("side", ""),
                "order_type": "futures",
                "price": price,          # price in USDT
                "quantity": qty,
                "volume": round(price * qty, 4),  # notional in USDT
                "fee": float(t.get("fee_amount", 0)),
                "fee_currency": "USDT",   # fee charged in USDT (instrument settlement currency)
                "is_maker": t.get("is_maker", False),
                "timestamp": ts,
                "datetime": _dt(ts),
            })
        return sorted(trades, key=lambda x: x["timestamp"], reverse=True)
    except Exception as e:
        print(f"DCX futures trades error: {e}")
        return []


def _compute_pnl_usd(trades: list, kraken: KrakenClient):
    """FIFO realized P&L for USD/USDT-denominated trades."""
    buy_queues = defaultdict(list)
    realized = defaultdict(float)
    fees_by_asset = defaultdict(float)

    for t in sorted(trades, key=lambda x: x["timestamp"]):
        key = t["base"]
        qty = t["quantity"]
        price = t["price"]
        fees_by_asset[key] += t["fee"]

        if t["side"] == "buy":
            buy_queues[key].append({"qty": qty, "price": price})
        elif t["side"] == "sell":
            rem = qty
            while rem > 0 and buy_queues[key]:
                oldest = buy_queues[key][0]
                if oldest["qty"] <= rem:
                    realized[key] += (price - oldest["price"]) * oldest["qty"]
                    rem -= oldest["qty"]
                    buy_queues[key].pop(0)
                else:
                    realized[key] += (price - oldest["price"]) * rem
                    oldest["qty"] -= rem
                    rem = 0

    # Unrealized from open positions
    unrealized = defaultdict(float)
    for asset, queue in buy_queues.items():
        if not queue:
            continue
        cur_price = _get_usd_price(asset, kraken)
        if cur_price:
            for pos in queue:
                unrealized[asset] += (cur_price - pos["price"]) * pos["qty"]

    return {
        "realized": dict(realized),
        "unrealized": dict(unrealized),
        "fees_by_asset": dict(fees_by_asset),
        "total_realized": sum(realized.values()),
        "total_unrealized": sum(unrealized.values()),
        "total_fees": sum(fees_by_asset.values()),
    }


def _compute_pnl_inr(trades: list, kraken: KrakenClient = None):
    """
    Correct P&L for INR-margin futures using cash-flow + mark-to-market.

    Why not FIFO: futures "buy" can be opening a long OR closing a short.
    We cannot distinguish direction from fills alone, so FIFO gives nonsense.

    Cash-flow approach:
      cash_flow  = total sell proceeds - total buy cost  (per asset)
      unrealized = net_open_qty * current_mark_price
      total_pnl  = cash_flow + unrealized

    For fully-closed positions (net_qty == 0): total_pnl == cash_flow (exact).
    For open positions: total_pnl includes unrealized MTM.
    """
    stats = defaultdict(lambda: {
        "buy_cost": 0.0, "sell_proceeds": 0.0,
        "buy_qty": 0.0, "sell_qty": 0.0, "fees_usdt": 0.0,
    })

    for t in trades:
        key = t["base"]
        price = t["price"]
        qty = t["quantity"]
        stats[key]["fees_usdt"] += t["fee"]   # fee_amount is in USDT
        if t["side"] == "buy":
            stats[key]["buy_cost"] += price * qty
            stats[key]["buy_qty"] += qty
        else:
            stats[key]["sell_proceeds"] += price * qty
            stats[key]["sell_qty"] += qty

    realized_usdt = {}
    unrealized_usdt = {}
    fees_usdt = {}

    for asset, s in stats.items():
        net_qty = s["buy_qty"] - s["sell_qty"]
        cash_flow = s["sell_proceeds"] - s["buy_cost"]

        mark = 0.0
        if abs(net_qty) > 1e-8 and kraken:
            mark_price = _get_usd_price(asset, kraken)
            mark = net_qty * mark_price

        realized_usdt[asset] = round(cash_flow, 4)
        unrealized_usdt[asset] = round(mark, 4)
        fees_usdt[asset] = round(s["fees_usdt"], 4)

    return {
        "realized_usdt": realized_usdt,
        "unrealized_usdt": unrealized_usdt,
        "fees_usdt": fees_usdt,
        "total_realized_usdt": round(sum(realized_usdt.values()), 2),
        "total_unrealized_usdt": round(sum(unrealized_usdt.values()), 2),
        "total_fees_usdt": round(sum(fees_usdt.values()), 4),
    }


def _daily_series(trades: list, days: int, fee_currency: str = "USD"):
    """Build (date_labels, daily_fee_values) for a set of trades."""
    now = _now_ts()
    cutoff = now - days * 86400
    end_dt = datetime.now(tz=timezone.utc)
    labels = [(end_dt - timedelta(days=i)).strftime("%Y-%m-%d")
              for i in range(days - 1, -1, -1)]
    daily_fees = defaultdict(float)
    for t in trades:
        if t["timestamp"] >= cutoff:
            d = datetime.fromtimestamp(t["timestamp"], tz=timezone.utc).strftime("%Y-%m-%d")
            daily_fees[d] += t["fee"]
    return labels, [round(daily_fees.get(d, 0), 4) for d in labels]


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    resp = render_template("trading_dashboard.html")
    from flask import make_response
    r = make_response(resp)
    r.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    r.headers["Pragma"] = "no-cache"
    return r


@app.route("/api/summary")
def api_summary():
    """Separate headline stats for INR and USD accounts."""
    try:
        kraken, _ = _get_clients()

        # ── USD account ──
        kb = _kraken_balance()
        db_spot = _dcx_spot_balance()

        kraken_val = sum(_get_usd_price(_kraken_symbol(a), kraken) * v for a, v in kb.items())
        dcx_spot_val = sum(_get_usd_price(a, kraken) * v["total"]
                           for a, v in db_spot.items() if v["total"] > 0)

        k_trades = _kraken_trades_cached(kraken)
        d_spot = _dcx_spot_trades_cached(None)  # uses cached clients internally
        usd_trades = k_trades + d_spot
        usd_pnl = _compute_pnl_usd(usd_trades, kraken)

        k_open = len(_kraken_open_orders())

        # ── INR account ──
        fut_positions = _dcx_futures_positions()
        active_positions = [p for p in fut_positions if float(p.get("active_pos", 0) or 0) != 0]
        locked_margin_inr = sum(float(p.get("locked_user_margin", 0) or 0) for p in fut_positions)

        d_fut = _dcx_futures_trades_cached()
        inr_pnl = _compute_pnl_inr(d_fut, kraken)

        dcx_fut_open_orders = _dcx_futures_open_orders()

        k_margin = _kraken_trade_balance_cached()
        k_ledger = _kraken_ledger_cached(days=365)
        kraken_trade_fees = sum(t["fee"] for t in k_trades)
        kraken_rollover_fees = sum(abs(l["fee"]) for l in k_ledger if l["type"] == "rollover")

        return jsonify({
            "usd": {
                "portfolio_value": round(kraken_val + dcx_spot_val, 2),
                "kraken_spot_balance": round(kraken_val, 2),
                "dcx_spot_value": round(dcx_spot_val, 2),
                "kraken_margin": {
                    "equity": round(k_margin.get("equity", 0), 2),
                    "free_margin": round(k_margin.get("free_margin", 0), 2),
                    "margin_in_use": round(k_margin.get("margin_used", 0), 2),
                    "unrealized_pnl": round(k_margin.get("unrealized_pnl", 0), 2),
                },
                "realized_pnl": round(usd_pnl["total_realized"], 2),
                "unrealized_pnl": round(usd_pnl["total_unrealized"], 2),
                "total_fees": round(kraken_trade_fees, 2),
                "rollover_fees": round(kraken_rollover_fees, 4),
                "trade_count": len(usd_trades),
                "open_orders": k_open,
                "fee_currency": "USD",
            },
            "inr": {
                "locked_margin_inr": round(locked_margin_inr, 2),
                "active_positions": len(active_positions),
                "realized_pnl_usdt": round(inr_pnl["total_realized_usdt"], 2),
                "unrealized_pnl_usdt": round(inr_pnl["total_unrealized_usdt"], 2),
                "total_pnl_usdt": round(inr_pnl["total_realized_usdt"] + inr_pnl["total_unrealized_usdt"], 2),
                "total_fees_usdt": round(inr_pnl["total_fees_usdt"], 4),
                "net_pnl_usdt": round(
                    inr_pnl["total_realized_usdt"]
                    + inr_pnl["total_unrealized_usdt"]
                    - inr_pnl["total_fees_usdt"], 2
                ),
                "trade_count": len(d_fut),
                "open_orders": len(dcx_fut_open_orders),
                "fee_currency": "USDT",
            },
            "last_updated": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/portfolio")
def api_portfolio():
    """Portfolio holdings, split by account currency."""
    try:
        kraken, _ = _get_clients()

        # ── USD holdings ──
        usd_holdings = []
        for raw_asset, qty in _kraken_balance().items():
            sym = _kraken_symbol(raw_asset)
            price = _get_usd_price(sym, kraken)
            usd_holdings.append({
                "account": "Kraken", "currency": "USD",
                "asset": sym, "quantity": round(qty, 8),
                "price": round(price, 4), "value": round(qty * price, 2),
                "price_label": "USD", "value_label": "USD",
            })
        for asset, amounts in _dcx_spot_balance().items():
            qty = amounts["total"]
            if qty <= 0:
                continue
            price = _get_usd_price(asset, kraken)
            usd_holdings.append({
                "account": "CoinDCX Spot", "currency": "USDT",
                "asset": asset, "quantity": round(qty, 8),
                "available": round(amounts["available"], 8),
                "locked": round(amounts["locked"], 8),
                "price": round(price, 4), "value": round(qty * price, 2),
                "price_label": "USDT", "value_label": "USDT",
            })

        # ── INR holdings (futures positions) ──
        inr_holdings = []
        for pos in _dcx_futures_positions():
            active = float(pos.get("active_pos", 0) or 0)
            pair = pos.get("pair", "")
            base = _base_from_pair(pair)
            avg_price = float(pos.get("avg_price", 0) or 0)
            liq_price = float(pos.get("liquidation_price", 0) or 0)
            locked = float(pos.get("locked_user_margin", 0) or 0)
            cur_price = _get_usd_price(base, kraken) if active else avg_price
            inr_holdings.append({
                "account": "CoinDCX Futures", "currency": "INR",
                "asset": base, "pair": pair,
                "quantity": round(active, 8),
                "avg_entry_price": round(avg_price, 4),
                "current_price_usdt": round(cur_price, 4),
                "liquidation_price": round(liq_price, 4),
                "leverage": pos.get("leverage"),
                "locked_margin_inr": round(locked, 2),
                "notional_usdt": round(active * cur_price, 2) if active else 0,
                "unrealized_pnl_usdt": round((cur_price - avg_price) * active, 2) if active and avg_price else 0,
                "price_label": "USDT", "value_label": "USDT",
            })

        total_usd = sum(h["value"] for h in usd_holdings)
        for h in usd_holdings:
            h["allocation_pct"] = round(h["value"] / total_usd * 100, 1) if total_usd else 0

        return jsonify({
            "usd": {
                "holdings": sorted(usd_holdings, key=lambda x: x["value"], reverse=True),
                "total_value_usd": round(total_usd, 2),
            },
            "inr": {
                "positions": inr_holdings,
                "total_locked_margin_inr": round(sum(h["locked_margin_inr"] for h in inr_holdings), 2),
                "total_notional_usdt": round(sum(h["notional_usdt"] for h in inr_holdings), 2),
            },
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/trades")
def api_trades():
    """Trades split by account currency. Never mixed."""
    try:
        days = int(request.args.get("days", 90))
        currency = request.args.get("currency", "all")
        side_filter = request.args.get("side", "all")
        cutoff = _now_ts() - days * 86400

        usd_trades, inr_trades = [], []

        if currency in ("all", "usd"):
            k = _kraken_trades_cached(days=days)
            s = _dcx_spot_trades_cached()
            usd_trades = [t for t in k + s if t["timestamp"] >= cutoff]
            if side_filter != "all":
                usd_trades = [t for t in usd_trades if t["side"] == side_filter]
            usd_trades.sort(key=lambda x: x["timestamp"], reverse=True)

        if currency in ("all", "inr"):
            f = _dcx_futures_trades_cached()
            inr_trades = [t for t in f if t["timestamp"] >= cutoff]
            if side_filter != "all":
                inr_trades = [t for t in inr_trades if t["side"] == side_filter]
            inr_trades.sort(key=lambda x: x["timestamp"], reverse=True)

        return jsonify({
            "usd": {
                "trades": usd_trades,
                "count": len(usd_trades),
                "total_fees": round(sum(t["fee"] for t in usd_trades), 4),
                "total_volume": round(sum(t["volume"] for t in usd_trades), 2),
                "fee_currency": "USD/USDT",
            },
            "inr": {
                "trades": inr_trades,
                "count": len(inr_trades),
                "total_fees_usdt": round(sum(t["fee"] for t in inr_trades), 4),
                "total_volume_usdt": round(sum(t["volume"] for t in inr_trades), 2),
                "fee_currency": "USDT",
                "note": "Margin in INR, instrument prices and fees in USDT",
            },
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/pnl")
def api_pnl():
    """P&L completely separate: USD account vs INR account."""
    try:
        days = int(request.args.get("days", 30))
        kraken, _ = _get_clients()

        # ── USD P&L ──
        usd_trades = _kraken_trades_cached(days=max(days, 180)) + _dcx_spot_trades_cached()
        usd_pnl = _compute_pnl_usd(usd_trades, kraken)

        usd_labels, usd_daily_fees = _daily_series(usd_trades, days, "USD")
        usd_cumulative = []
        running = 0
        for v in usd_daily_fees:
            running -= v
            usd_cumulative.append(round(running, 4))

        # ── INR P&L ──
        inr_trades = _dcx_futures_trades_cached()
        inr_pnl = _compute_pnl_inr(inr_trades, kraken)

        inr_labels, inr_daily_fees = _daily_series(inr_trades, days, "INR")
        inr_cumulative = []
        running = 0
        for v in inr_daily_fees:
            running -= v
            inr_cumulative.append(round(running, 4))

        # By-asset breakdown (INR account uses USDT for P&L, INR for fees)
        inr_assets = set(inr_pnl["realized_usdt"]) | set(inr_pnl["unrealized_usdt"]) | set(inr_pnl["fees_usdt"])
        usd_assets = set(usd_pnl["realized"]) | set(usd_pnl["unrealized"]) | set(usd_pnl["fees_by_asset"])

        return jsonify({
            "usd": {
                "realized_pnl": round(usd_pnl["total_realized"], 2),
                "unrealized_pnl": round(usd_pnl["total_unrealized"], 2),
                "total_fees": round(usd_pnl["total_fees"], 4),
                "fee_currency": "USD/USDT",
                "by_asset": {
                    a: {
                        "realized": round(usd_pnl["realized"].get(a, 0), 2),
                        "unrealized": round(usd_pnl["unrealized"].get(a, 0), 2),
                        "fees_usd": round(usd_pnl["fees_by_asset"].get(a, 0), 4),
                    }
                    for a in usd_assets
                },
                "chart": {"labels": usd_labels, "daily_fees": usd_daily_fees, "cumulative": usd_cumulative},
            },
            "inr": {
                "realized_pnl_usdt": round(inr_pnl["total_realized_usdt"], 2),
                "unrealized_pnl_usdt": round(inr_pnl["total_unrealized_usdt"], 2),
                "total_pnl_usdt": round(inr_pnl["total_realized_usdt"] + inr_pnl["total_unrealized_usdt"], 2),
                "total_fees_usdt": round(inr_pnl["total_fees_usdt"], 4),
                "fee_currency": "USDT",
                "note": "Cash-flow P&L in USDT + MTM of open positions. Fees also in USDT.",
                "by_asset": {
                    a: {
                        "realized_usdt": round(inr_pnl["realized_usdt"].get(a, 0), 2),
                        "unrealized_usdt": round(inr_pnl["unrealized_usdt"].get(a, 0), 2),
                        "total_usdt": round(inr_pnl["realized_usdt"].get(a, 0) + inr_pnl["unrealized_usdt"].get(a, 0), 2),
                        "fees_usdt": round(inr_pnl["fees_usdt"].get(a, 0), 4),
                    }
                    for a in inr_assets
                },
                "chart": {"labels": inr_labels, "daily_fees_usdt": inr_daily_fees},
            },
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/fees")
def api_fees():
    """Fees completely separated: USD fees vs INR fees."""
    try:
        days = int(request.args.get("days", 30))
        cutoff = _now_ts() - days * 86400

        k_trades = _kraken_trades_cached(days=days)
        d_spot = _dcx_spot_trades_cached()
        d_fut = _dcx_futures_trades_cached()
        k_ledger = _kraken_ledger_cached(days=days)

        # ── USD fees ──
        kraken_trade_fees = sum(t["fee"] for t in k_trades)
        kraken_rollover_fees = sum(abs(l["fee"]) for l in k_ledger if l["type"] == "rollover")
        dcx_spot_fees = sum(t["fee"] for t in d_spot if t["timestamp"] >= cutoff)

        usd_by_asset = defaultdict(float)
        for t in k_trades + d_spot:
            usd_by_asset[t["base"]] += t["fee"]

        usd_labels, usd_daily = _daily_series(k_trades + d_spot, days)

        # ── INR fees ──
        inr_fut_fees = sum(t["fee"] for t in d_fut if t["timestamp"] >= cutoff)
        inr_by_asset = defaultdict(float)
        for t in d_fut:
            if t["timestamp"] >= cutoff:
                inr_by_asset[t["base"]] += t["fee"]

        inr_labels, inr_daily = _daily_series(d_fut, days)

        return jsonify({
            "usd": {
                "total_fees": round(kraken_trade_fees + kraken_rollover_fees + dcx_spot_fees, 4),
                "fee_currency": "USD/USDT",
                "kraken": {
                    "trading_fees": round(kraken_trade_fees, 4),
                    "funding_rates": round(kraken_rollover_fees, 4),
                    "total": round(kraken_trade_fees + kraken_rollover_fees, 4),
                },
                "dcx_spot": {
                    "trading_fees": round(dcx_spot_fees, 4),
                    "total": round(dcx_spot_fees, 4),
                },
                "by_asset": {k: round(v, 4) for k, v in usd_by_asset.items()},
                "chart": {"labels": usd_labels, "daily": usd_daily},
                "ledger": [l for l in k_ledger if l["type"] in ("rollover", "margin") and l["fee"] > 0][:50],
            },
            "inr": {
                "total_fees_usdt": round(inr_fut_fees, 4),
                "fee_currency": "USDT",
                "account": "CoinDCX Futures (INR margin, USDT fees)",
                "by_asset": {k: round(v, 4) for k, v in inr_by_asset.items()},
                "chart": {"labels": inr_labels, "daily": inr_daily},
            },
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/open-orders")
def api_open_orders():
    try:
        usd_orders = []
        for idx, row in _kraken_open_orders():
            ts = float(row.get("opentm", 0) or 0)
            usd_orders.append({
                "id": str(idx), "account": "Kraken", "currency": "USD",
                "pair": row.get("descr_pair", ""),
                "side": row.get("descr_type", ""),
                "order_type": row.get("descr_ordertype", ""),
                "price": float(row.get("descr_price", 0) or 0),
                "quantity": float(row.get("vol", 0) or 0),
                "filled": float(row.get("vol_exec", 0) or 0),
                "status": row.get("status", ""),
                "datetime": _dt(ts, is_ms=False),
            })

        dcx_spot_orders = []
        for o in _dcx_spot_open_orders():
            ts = (o.get("created_at", 0) or 0) / 1000
            dcx_spot_orders.append({
                "id": str(o.get("id", "")), "account": "CoinDCX Spot", "currency": "USDT",
                "pair": o.get("market", ""),
                "side": o.get("side", ""),
                "order_type": o.get("order_type", ""),
                "price": float(o.get("price_per_unit", 0) or 0),
                "quantity": float(o.get("total_quantity", 0) or 0),
                "filled": float(o.get("remaining_quantity", 0) or 0),
                "status": o.get("status", ""),
                "datetime": _dt(ts),
            })

        inr_orders = []
        for o in _dcx_futures_open_orders():
            ts = (o.get("created_at", 0) or 0) / 1000
            inr_orders.append({
                "id": str(o.get("id", "")), "account": "CoinDCX Futures", "currency": "INR",
                "pair": o.get("pair", ""),
                "side": o.get("side", ""),
                "order_type": o.get("order_type", ""),
                "price": float(o.get("price", 0) or 0),
                "quantity": float(o.get("quantity", 0) or 0),
                "filled": float(o.get("filled_quantity", 0) or 0),
                "status": o.get("status", ""),
                "datetime": _dt(ts),
            })

        return jsonify({
            "usd": {"orders": usd_orders + dcx_spot_orders, "count": len(usd_orders) + len(dcx_spot_orders)},
            "inr": {"orders": inr_orders, "count": len(inr_orders)},
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/prices")
def api_prices():
    try:
        kraken, coindcx = _get_clients()
        assets = ["ETH", "BTC", "SOL", "ZEC", "ONT", "TAO", "MATIC", "LINK", "AVAX"]

        def _fetch_prices():
            result = {}
            for a in assets:
                k = kraken.get_current_price(a)
                d = coindcx.get_current_price(a)
                result[a] = {
                    "kraken_usd": round(k, 2) if k else None,
                    "coindcx_usdt": round(d, 2) if d else None,
                    "spread": round(abs((k or 0) - (d or 0)), 2) if k and d else None,
                }
            return result

        prices = _cached("live_prices", PRICE_TTL, _fetch_prices)
        return jsonify({"prices": prices, "ts": datetime.now(tz=timezone.utc).isoformat()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("=" * 60)
    print("  Trading Dashboard  →  http://localhost:5001")
    print("=" * 60)
    _start_background_warmer()
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)
