"""
The paper account for FX: USD cash plus one netted position per currency pair, with leverage.

A BUY of EURUSD opens or adds to a long EUR position (or reduces a short); a SELL does the
reverse. Profit and loss accrue in the quote currency and are converted to USD. Equity is cash
plus unrealized P&L; margin used is each position's USD notional over LEVERAGE, and an order that
adds exposure needs the free margin to carry it. Everything is stored in SQLite, so the MCP server
and the approval API share one account and it survives restarts.

Prices are "quote per base" (EURUSD 1.137 = 1.137 USD per EUR; USDJPY 158.8 = 158.8 JPY per USD).
"""

from __future__ import annotations

import math
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from common.paths import data_path, ensure_parent

Quote = Callable[[str], float]

_PAIR = re.compile(r"^[A-Z]{3}[A-Z]{3}$")
# Largest single deposit, and largest cash balance, the paper account takes: far beyond any real
# account, and small enough that every sum stays finite (two 1.7e308 deposits made equity inf).
MAX_DEPOSIT_USD = 1e12
MAX_CASH_USD = 1e15


def parse_pair(symbol: str) -> Tuple[str, str]:
    """'EURUSD', 'EUR/USD', 'eur_usd', 'EURUSD=X' -> ('EUR', 'USD'). ValueError if it is not a pair."""
    s = str(symbol or "").strip().upper().replace("/", "").replace("_", "").replace("-", "")
    if s.endswith("=X"):
        s = s[:-2]
    if not _PAIR.match(s) or s[:3] == s[3:]:
        raise ValueError(f"{symbol!r} is not a currency pair (expected e.g. EURUSD or EUR/USD)")
    return s[:3], s[3:]


def usd_per(ccy: str, quote: Quote) -> float:
    """USD value of one unit of `ccy`: 1 for USD, else the XXXUSD rate or 1 / USDXXX."""
    ccy = ccy.upper()
    if ccy == "USD":
        return 1.0
    errors = []
    for pair, invert in ((f"{ccy}USD", False), (f"USD{ccy}", True)):
        try:
            rate = float(quote(pair))
            if math.isfinite(rate) and rate > 0:
                return 1.0 / rate if invert else rate
            errors.append(f"{pair}: {rate!r}")
        except Exception as e:  # a missing pair is normal; try the inverse
            errors.append(f"{pair}: {e}")
    raise ValueError(f"no USD rate for {ccy} ({'; '.join(errors)})")


def notional_usd(symbol: str, amount: float, quote: Quote) -> float:
    """USD value of `amount` units of the pair's base currency."""
    base, _ = parse_pair(symbol)
    return abs(float(amount)) * usd_per(base, quote)


def _default_quote(symbol: str) -> float:
    from app.core.container import global_container

    ticker = global_container.exchange_provider.fetch_ticker(symbol)
    price = ticker.get("last") or ticker.get("close")
    try:
        price = float(price)
    except (TypeError, ValueError):
        raise ValueError(f"no price for {symbol}") from None
    if not (math.isfinite(price) and price > 0):
        raise ValueError(f"no usable price for {symbol} ({price!r})")
    return price


class FxPaperAccount:
    def __init__(self, db_path: Optional[str] = None, quote: Optional[Quote] = None, leverage: Optional[float] = None):
        self.db_path = db_path or os.getenv("READYTRADER_PAPER_DB_PATH") or os.getenv("PAPER_DB_PATH") or data_path("paper.db")
        ensure_parent(self.db_path)
        self.quote: Quote = quote or _default_quote
        raw = leverage or os.getenv("LEVERAGE") or 30
        try:
            self.leverage = float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"LEVERAGE must be a positive number, got {raw!r}") from None
        if not (math.isfinite(self.leverage) and self.leverage > 0):
            raise ValueError(f"LEVERAGE must be a positive number, got {raw!r}")
        self._init_db()

    # ------------------------------------------------------------------ storage

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=30)

    def _init_db(self) -> None:
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS fx_cash (user_id TEXT PRIMARY KEY, usd REAL NOT NULL, deposits REAL NOT NULL)")
            c.execute(
                "CREATE TABLE IF NOT EXISTS fx_positions (user_id TEXT, symbol TEXT, qty REAL NOT NULL, "
                "avg_price REAL NOT NULL, PRIMARY KEY (user_id, symbol))"
            )
            c.execute(
                "CREATE TABLE IF NOT EXISTS fx_trades (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, ts TEXT, "
                "symbol TEXT, side TEXT, qty REAL, price REAL, realized_usd REAL, rationale TEXT)"
            )
            c.execute("CREATE TABLE IF NOT EXISTS fx_equity (user_id TEXT, ts TEXT, equity_usd REAL, deposits REAL)")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _cash(self, c: sqlite3.Connection, user_id: str) -> Tuple[float, float]:
        row = c.execute("SELECT usd, deposits FROM fx_cash WHERE user_id=?", (user_id,)).fetchone()
        return (float(row[0]), float(row[1])) if row else (0.0, 0.0)

    def _positions(self, c: sqlite3.Connection, user_id: str) -> Dict[str, Tuple[float, float]]:
        rows = c.execute("SELECT symbol, qty, avg_price FROM fx_positions WHERE user_id=?", (user_id,)).fetchall()
        return {s: (float(q), float(a)) for s, q, a in rows if q}

    # ------------------------------------------------------------------ valuation

    def _mark(self, symbol: str, fallback: float) -> Tuple[float, bool]:
        try:
            price = float(self.quote(symbol))
            if math.isfinite(price) and price > 0:
                return price, True
        except Exception:  # nosec B110 - an unpriced position is marked at its entry and flagged
            pass
        return fallback, False

    def _value(self, cash: float, positions: Dict[str, Tuple[float, float]], marks: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """Equity, margin and per-position P&L. Raises ValueError when a USD rate is unavailable."""
        marks = marks or {}
        rows: List[Dict[str, Any]] = []
        unrealized = margin = 0.0
        stale = []
        for symbol, (qty, avg) in sorted(positions.items()):
            base, quote_ccy = parse_pair(symbol)
            if symbol in marks:
                mark, live = marks[symbol], True
            else:
                mark, live = self._mark(symbol, avg)
            if not live:
                stale.append(symbol)
            pnl = (mark - avg) * qty * usd_per(quote_ccy, self.quote)
            used = abs(qty) * usd_per(base, self.quote) / self.leverage
            unrealized += pnl
            margin += used
            rows.append({"symbol": symbol, "qty": qty, "avg_price": avg, "mark": mark, "unrealized_usd": round(pnl, 2), "margin_usd": round(used, 2)})
        equity = cash + unrealized
        return {
            "cash_usd": round(cash, 2),
            "equity_usd": round(equity, 2),
            "unrealized_usd": round(unrealized, 2),
            "margin_used_usd": round(margin, 2),
            "free_margin_usd": round(equity - margin, 2),
            "leverage": self.leverage,
            "positions": rows,
            "unpriced_positions": stale,
        }

    def account(self, user_id: str) -> Dict[str, Any]:
        with self._conn() as c:
            cash, deposits = self._cash(c, user_id)
            positions = self._positions(c, user_id)
        out = self._value(cash, positions)
        out["net_deposits_usd"] = round(deposits, 2)
        return out

    def get_portfolio_value_usd(self, user_id: str) -> float:
        return float(self.account(user_id)["equity_usd"])

    def get_balances(self, user_id: str) -> Dict[str, float]:
        with self._conn() as c:
            cash, _ = self._cash(c, user_id)
            positions = self._positions(c, user_id)
        return {"USD": round(cash, 2), **{sym: qty for sym, (qty, _) in positions.items()}}

    def position(self, user_id: str, symbol: str) -> float:
        base, quote_ccy = parse_pair(symbol)
        with self._conn() as c:
            return self._positions(c, user_id).get(base + quote_ccy, (0.0, 0.0))[0]

    def _snapshot(self, c: sqlite3.Connection, user_id: str) -> None:
        cash, deposits = self._cash(c, user_id)
        try:
            value = self._value(cash, self._positions(c, user_id))
        except ValueError:
            return  # no rate to value a position: skip rather than record a wrong equity
        if value["unpriced_positions"]:
            return  # a position marked at its entry price would record a loss as never having happened
        equity = value["equity_usd"]
        c.execute("INSERT INTO fx_equity (user_id, ts, equity_usd, deposits) VALUES (?, ?, ?, ?)", (user_id, self._now(), equity, deposits))

    # ------------------------------------------------------------------ cash

    def deposit(self, user_id: str, asset: str, amount: float) -> str:
        if str(asset).strip().upper() != "USD":
            raise ValueError("the paper FX account holds USD cash; deposit USD (positions come from trades)")
        amount = float(amount)
        if not (math.isfinite(amount) and 0 < amount <= MAX_DEPOSIT_USD):
            raise ValueError(f"a deposit must be a positive number of USD no larger than {MAX_DEPOSIT_USD:g}")
        with self._conn() as c:
            cash, deposits = self._cash(c, user_id)
            if cash + amount > MAX_CASH_USD:
                raise ValueError(f"the paper account holds at most {MAX_CASH_USD:g} USD of cash")
            # A deposit is recorded with the account's value (the loss metrics net it out). While a
            # position cannot be priced that value is unknown, and a deposit left unrecorded would
            # be measured as a trading gain later (it ended a drawdown halt).
            try:
                unpriced = self._value(cash, self._positions(c, user_id))["unpriced_positions"]
            except ValueError as e:
                raise ValueError(f"deposit refused: the account cannot be valued now ({e}); retry when prices are available") from None
            if unpriced:
                raise ValueError(f"deposit refused: {', '.join(unpriced)} cannot be priced now; retry when prices are available")
            c.execute(
                "INSERT OR REPLACE INTO fx_cash (user_id, usd, deposits) VALUES (?, ?, ?)",
                (user_id, cash + amount, deposits + amount),
            )
            self._snapshot(c, user_id)
        return f"Deposited {amount:.2f} USD. Cash: {cash + amount:.2f} USD."

    def reset_wallet(self, user_id: str) -> str:
        with self._conn() as c:
            c.execute("DELETE FROM fx_cash WHERE user_id=?", (user_id,))
            c.execute("DELETE FROM fx_positions WHERE user_id=?", (user_id,))
            c.execute("DELETE FROM fx_trades WHERE user_id=?", (user_id,))
            c.execute("DELETE FROM fx_equity WHERE user_id=?", (user_id,))
        return f"Paper account for {user_id} has been reset (cash, positions and history)."

    # ------------------------------------------------------------------ trading

    def execute_trade(self, user_id: str, side: str, symbol: str, amount: float, price: float, rationale: str = "") -> str:
        """Fill `amount` units of the pair's base currency at `price` (quote per base).

        Returns "Paper Trade Executed: ..." or, when the order would leave equity below the margin
        it needs, "Insufficient margin: ..." with nothing changed.
        """
        base, quote_ccy = parse_pair(symbol)
        pair = base + quote_ccy
        side = str(side).strip().lower()
        if side not in ("buy", "sell"):
            raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")
        amount, price = float(amount), float(price)
        if not (math.isfinite(amount) and amount > 0 and math.isfinite(price) and price > 0):
            raise ValueError("amount and price must be positive numbers")
        signed = amount if side == "buy" else -amount

        with self._conn() as c:
            cash, deposits = self._cash(c, user_id)
            positions = self._positions(c, user_id)
            qty, avg = positions.get(pair, (0.0, 0.0))

            realized = 0.0
            if qty and (qty > 0) != (signed > 0):
                closing = min(abs(qty), amount)
                realized = (price - avg) * closing * (1 if qty > 0 else -1) * usd_per(quote_ccy, self.quote)
            new_qty = qty + signed
            if abs(new_qty) < 1e-9:
                new_qty, new_avg = 0.0, 0.0
            elif qty == 0 or (qty > 0) == (signed > 0):
                new_avg = (abs(qty) * avg + amount * price) / (abs(qty) + amount)
            elif (new_qty > 0) == (qty > 0):
                new_avg = avg  # partly closed: the rest keeps its entry price
            else:
                new_avg = price  # flipped: the new side opens at this fill

            after = dict(positions)
            if new_qty:
                after[pair] = (new_qty, new_avg)
            else:
                after.pop(pair, None)
            new_cash = cash + realized
            if abs(new_qty) > abs(qty):  # adds exposure: the margin must fit
                state = self._value(new_cash, after, marks={pair: price})
                if state["free_margin_usd"] < 0:
                    return (
                        f"Insufficient margin: this order needs {state['margin_used_usd']:.2f} USD of margin in total "
                        f"at {self.leverage:g}x leverage, and equity would be {state['equity_usd']:.2f} USD."
                    )

            c.execute("INSERT OR REPLACE INTO fx_cash (user_id, usd, deposits) VALUES (?, ?, ?)", (user_id, new_cash, deposits))
            if new_qty:
                c.execute(
                    "INSERT OR REPLACE INTO fx_positions (user_id, symbol, qty, avg_price) VALUES (?, ?, ?, ?)",
                    (user_id, pair, new_qty, new_avg),
                )
            else:
                c.execute("DELETE FROM fx_positions WHERE user_id=? AND symbol=?", (user_id, pair))
            c.execute(
                "INSERT INTO fx_trades (user_id, ts, symbol, side, qty, price, realized_usd, rationale) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, self._now(), pair, side, amount, price, realized, rationale),
            )
            self._snapshot(c, user_id)

        held = f"{new_qty:+g} {pair} @ {new_avg:.5f}" if new_qty else f"flat {pair}"
        return (
            f"Paper Trade Executed: {side.upper()} {amount:g} {pair} @ {price:.5f}. "
            f"Realized P&L: {realized:.2f} USD. Position: {held}. Rationale: {rationale}"
        )

    # ------------------------------------------------------------------ risk metrics

    def mark_day_open(self, user_id: str) -> None:
        """Record the account's value once per UTC day, at its first risk check: the daily-loss
        baseline when the account made no snapshot the day before."""
        today = self._now()[:10]
        with self._conn() as c:
            seen = c.execute("SELECT 1 FROM fx_equity WHERE user_id=? AND substr(ts, 1, 10)=? LIMIT 1", (user_id, today)).fetchone()
            has_any = c.execute("SELECT 1 FROM fx_equity WHERE user_id=? LIMIT 1", (user_id,)).fetchone()
            if has_any and not seen:
                self._snapshot(c, user_id)

    def get_risk_metrics(self, user_id: str) -> Dict[str, Any]:
        """Equity plus today's P&L and the drawdown, measured on trading results: deposits are
        neither gains nor losses, and neither end a halt nor start one.

        The results are chained into a performance index (time-weighted return): between two
        snapshots, the return is the change in equity less the deposits made in between, over the
        equity before. `drawdown_pct` is the index's current fall from its best level (what the
        Risk Guardian's drawdown rule reads); `max_drawdown_pct` is the deepest on record;
        `daily_pnl_pct` is the index's change since the previous UTC day's last snapshot, or since
        the day's first snapshot when there was none the day before. The account's value now ends
        the series. `equity` is None when a position cannot be priced now (its loss would be hidden),
        and the order checks then refuse anything that adds exposure.
        """
        with self._conn() as c:
            rows = c.execute("SELECT ts, equity_usd, deposits FROM fx_equity WHERE user_id=? ORDER BY ts ASC, rowid ASC", (user_id,)).fetchall()
            _, deposits_now = self._cash(c, user_id)
        equity: Optional[float]
        try:
            state = self.account(user_id)
            equity = None if state["unpriced_positions"] else float(state["equity_usd"])
        except ValueError:
            equity = None
        if not rows:
            return {"equity": equity, "daily_pnl_pct": 0.0, "drawdown_pct": 0.0, "max_drawdown_pct": 0.0}
        series = [(str(ts), float(eq), float(dep)) for ts, eq, dep in rows]
        if equity is not None:
            series.append((self._now(), equity, deposits_now))

        index = peak = 1.0
        max_dd = current_dd = 0.0
        levels = [(series[0][0], index)]
        for (_, prev_eq, prev_dep), (ts, eq, dep) in zip(series, series[1:]):
            if prev_eq > 0:
                period_return = (eq - (dep - prev_dep)) / prev_eq - 1.0
                index *= max(0.0, 1.0 + period_return)
            peak = max(peak, index)
            current_dd = 1.0 - index / peak if peak > 0 else 0.0
            max_dd = max(max_dd, current_dd)
            levels.append((ts, index))

        today = self._now()[:10]
        yesterday = (datetime.fromisoformat(today) - timedelta(days=1)).date().isoformat()
        before = [level for ts, level in levels if ts[:10] == yesterday]
        start = before[-1] if before else next((level for ts, level in levels if ts[:10] == today), levels[-1][1])
        daily = index / start - 1.0 if start > 0 else 0.0
        return {"equity": equity, "daily_pnl_pct": float(daily), "drawdown_pct": float(current_dd), "max_drawdown_pct": float(max_dd)}
