import json
import math
from typing import Any, Dict, Optional, Tuple

from fastmcp import FastMCP

from app.core.compliance import global_compliance_ledger
from app.core.config import settings
from app.core.container import global_container
from app.tools.trading import Number, _invalid_sentiment, _market_context, _sentiment_context, canonical_symbol, inactive_rules
from core.fx_account import notional_usd, parse_pair
from core.policy import PolicyError
from intelligence.core import get_news_status

PAPER_USER = "agent_zero"


def _json_ok(data: Dict[str, Any] | None = None) -> str:
    payload = {"ok": True, "data": data or {}}
    return json.dumps(payload, indent=2, sort_keys=True)


def _json_err(code: str, message: str, data: Dict[str, Any] | None = None) -> str:
    payload = {"ok": False, "error": {"code": code, "message": message, "data": data or {}}}
    return json.dumps(payload, indent=2, sort_keys=True)


# ---------------------------------------------------------------- request validation


def _invalid_order(side: Any, **amounts: Any) -> Optional[str]:
    """Why a trade request is malformed, or None. An unknown side used to execute as-is."""
    if str(side).strip().lower() not in ("buy", "sell"):
        return f"side must be 'buy' or 'sell', got {side!r}"
    for name, value in amounts.items():
        if isinstance(value, bool):
            return f"{name} must be a number, got {value!r}"
        try:
            number = float(value)
        except (TypeError, ValueError):
            return f"{name} must be a number, got {value!r}"
        if not math.isfinite(number) or number <= 0:
            return f"{name} must be a positive number, got {value!r}"
    return None


def _invalid_order_type(order_type: Any, price: Any) -> Optional[str]:
    ot = str(order_type).strip().lower()
    if ot not in ("market", "limit"):
        return f"order_type must be 'market' or 'limit', got {order_type!r}"
    if ot == "limit" and _invalid_order("buy", price=price):
        return f"a limit order needs a positive price, got {price!r}"
    return None


# ---------------------------------------------------------------- prices and account values


def _quote(symbol: str) -> float:
    """The latest rate for a pair (quote currency per unit of base) from the market-data provider."""
    ticker = global_container.exchange_provider.fetch_ticker(symbol)
    price = ticker.get("last") or ticker.get("close")
    try:
        price = float(price)
    except (TypeError, ValueError):
        raise ValueError(f"no price for {symbol}") from None
    # A NaN quote is truthy: it used to become the reference price, make the notional NaN and pass
    # the size rule (NaN > 5% is False).
    if not (math.isfinite(price) and price > 0):
        raise ValueError(f"no usable price for {symbol} ({price!r})")
    return price


def _market_price(symbol: str, market: Dict[str, Any]) -> Optional[float]:
    """The latest rate: the live quote, else the close the Falling Knife check already read."""
    try:
        return _quote(symbol)
    except Exception:
        return float(market["last_close"]) if market.get("last_close") else None


def _notional(symbol: str, amount: float, reference_price: Optional[float]) -> Optional[float]:
    """USD value of an order: `amount` units of the pair's base currency (a EURUSD order of 1,000
    is 1,000 EUR). A non-pair symbol (a stock) is valued at amount x price. None if unknown."""
    try:
        return notional_usd(symbol, amount, _quote)
    except ValueError:
        try:
            parse_pair(symbol)
            return None  # a pair whose USD rate is unavailable
        except ValueError:
            return float(amount) * reference_price if reference_price else None


def _position_units(symbol: str, exchange: str) -> Optional[float]:
    """The account's current signed position in the pair (base-currency units; negative is short),
    or None when it cannot be read. Paper: the paper account. Live: the brokerage's positions."""
    try:
        base, quote_ccy = parse_pair(symbol)
    except ValueError:
        return None
    key = base + quote_ccy
    if settings.PAPER_MODE:
        try:
            return float(global_container.paper_engine.position(PAPER_USER, symbol))
        except Exception:
            return None
    brokerage = global_container.brokerages.get((exchange or "").strip().lower())
    if brokerage is None or not brokerage.is_available():
        return None
    try:
        positions = brokerage.list_positions()
    except Exception:
        return None
    total = 0.0
    for pos in positions or []:
        name = str(pos.get("symbol") or "").upper().replace("_", "").replace("/", "")
        if name == key:
            total += float(pos.get("qty") or 0.0)
    return total


def exposure_added(side: str, amount: float, position: Optional[float]) -> float:
    """How many units of the order open or add to a position. Selling out of a long, or buying back a
    short, reduces exposure; only what goes beyond flat adds it. Unknown position: all of it adds."""
    amount = abs(float(amount))
    if position is None:
        return amount
    signed = amount if side == "buy" else -amount
    if position == 0 or (position > 0) == (signed > 0):
        return amount
    return max(0.0, amount - abs(position))


def _live_equity(exchange: str) -> Tuple[Optional[float], str]:
    """The brokerage account's equity, or (None, why) when it cannot be read: the brokerage's own
    reason (a rejected key, a wrong account id) is what the operator needs to fix it."""
    brokerage = global_container.brokerages.get((exchange or "").strip().lower())
    if brokerage is None or not brokerage.is_available():
        return None, "the brokerage is not configured"
    try:
        equity = float(brokerage.get_account_balance().get("equity") or 0.0)
    except Exception as e:
        return None, str(e)[:200]
    return (equity, "") if equity > 0 else (None, "the brokerage reports no equity")


# ---------------------------------------------------------------- the checks every order passes


def pre_trade_check(
    symbol: str,
    side: str,
    amount: float,
    price: float = 0.0,
    sentiment_score: float | None = None,
    exchange: str = "oanda",
    order_type: str = "market",
) -> Dict[str, Any]:
    """
    The Risk Guardian check an order must pass, with fresh market data: {allowed, reason,
    sentiment, market, notional_usd, position_units, exposure_added_units, reference_price,
    market_price, inactive_rules}. place_stock_order runs it before anything is proposed or executed, and the
    approval API (app/api_server.py) runs it again at execution time, because a proposal can wait
    up to its expiry while the market moves.

    The order is valued at the market, never at a price the caller supplies alone: a currency pair
    at its USD notional from the live quote, anything else at the market price (a limit at the
    higher of its limit and the market). Without a market price, an order that adds exposure is
    refused.

    The size rule values the order at its USD notional (base currency units in USD) against the
    account's real equity: the paper account in paper mode, the brokerage's in live mode. It used to
    value `amount x price` as if the price were in USD (a USDJPY order read 159x too large) against
    a fixed 100,000.
    """
    daily_loss = drawdown = 0.0
    equity_note = "."
    symbol = canonical_symbol(symbol)
    sentiment = _sentiment_context(symbol, sentiment_score)
    market = _market_context(symbol)
    portfolio_value: Optional[float]
    if settings.PAPER_MODE:
        global_container.paper_engine.mark_day_open(PAPER_USER)
        metrics = global_container.paper_engine.get_risk_metrics(PAPER_USER)
        portfolio_value = metrics.get("equity") or None
        if metrics.get("equity") is None:
            equity_note = " (a position cannot be priced now)."
        elif not portfolio_value:
            equity_note = " (the paper account is empty: deposit_paper_funds first)."
        daily_loss = metrics.get("daily_pnl_pct", 0.0)
        drawdown = metrics.get("drawdown_pct", 0.0)
    else:
        portfolio_value, why = _live_equity(exchange)
        if portfolio_value is None:
            equity_note = f": {why}."

    market_price = _market_price(symbol, market)
    limit = None
    if str(order_type or "market").strip().lower() == "limit":
        try:
            limit = float(price) if price and math.isfinite(float(price)) and float(price) > 0 else None
        except (TypeError, ValueError):
            limit = None
    reference_price = (max(market_price, limit) if limit else market_price) if market_price else None
    # FX positions go both ways: a SELL can open a short and a BUY can close one. The rules judge the
    # part of the order that opens or adds to a position, whatever its side.
    position = _position_units(symbol, exchange)
    added_units = exposure_added(str(side).lower(), amount, position)
    increases_exposure = added_units > 0
    notional = _notional(symbol, added_units, reference_price) if increases_exposure else 0.0
    refusal = None
    if notional is None:
        refusal = f"Could not value {amount} {symbol} in USD for the position-size check (no rate); retry when prices are available."
    elif portfolio_value is None:
        refusal = (
            f"Could not read the account's equity ({'paper' if settings.PAPER_MODE else exchange}) for the position-size check"
            + equity_note
        )
    risk_result = global_container.risk_guardian.validate_trade(
        side=side,
        symbol=symbol,
        increases_exposure=increases_exposure,
        amount_usd=notional or 0.0,
        portfolio_value=portfolio_value or 0.0,
        sentiment_score=sentiment["score"],
        daily_loss_pct=daily_loss,
        current_drawdown_pct=drawdown,
        market=market,
        volatility_score=market.get("volatility_ratio"),
        is_news_event_window=get_news_status(),
    )
    allowed = bool(risk_result.get("allowed", False))
    reason = risk_result.get("reason", "Unknown risk rejection")
    if allowed and refusal and increases_exposure:
        # The size rule needs both numbers; without them it could not run, so an order that opens or
        # adds to a position fails closed. One that only reduces a position goes through: it is an exit.
        allowed, reason = False, refusal
    return {
        "allowed": allowed,
        "reason": reason,
        "sentiment": sentiment,
        "market": market,
        "notional_usd": notional,
        "position_units": position,
        "exposure_added_units": added_units,
        "reference_price": reference_price,
        "market_price": market_price,
        # The rules that could not run on this order (live accounts have no loss history here, for
        # one), so "allowed" is never read as "fully checked".
        "inactive_rules": inactive_rules(),
    }


def paper_fill_price(side: str, limit: float, market_price: Optional[float]) -> Tuple[Optional[float], Optional[Dict[str, str]]]:
    """
    Where a paper order fills: at the latest market rate. A limit order fills only if it is
    marketable (a BUY at or above the market, a SELL at or below), and then at the market; resting
    orders are not simulated. It used to fill every limit at its own price, so a BUY limit far
    under the market bought far below it. Returns (price, None) or (None, {code, message}).
    """
    if not market_price:
        return None, {"code": "market_data_error", "message": "No market rate to fill the paper order at; retry."}
    if limit and limit > 0:
        marketable = limit >= market_price if side == "buy" else limit <= market_price
        if not marketable:
            return None, {
                "code": "limit_not_marketable",
                "message": (
                    f"Paper mode fills marketable limit orders only: {side} limit {limit:.5f} vs market "
                    f"{market_price:.5f}. Resting orders are not simulated."
                ),
            }
    return float(market_price), None


def live_execution_refusal() -> Optional[Dict[str, str]]:
    """The two operator switches every live order must pass. Both were documented but never read."""
    if not settings.LIVE_TRADING_ENABLED:
        return {
            "code": "live_trading_disabled",
            "message": "PAPER_MODE is false but LIVE_TRADING_ENABLED is not true: no live order was sent.",
        }
    if settings.TRADING_HALTED:
        return {"code": "trading_halted", "message": "TRADING_HALTED is set: live trading is halted, no order was sent."}
    return None


def live_order_refusal(exchange: str, symbol: str, side: str, amount: float, order_type: str, price: float) -> Optional[Dict[str, Any]]:
    """
    Everything a live order must pass before it may reach a brokerage: the operator switches and
    the live policy (ALLOW_EXCHANGES, ALLOW_BROKERAGE_SYMBOLS, MAX_BROKERAGE_ORDER_AMOUNT;
    core/policy.py). Checked when an order is proposed and again when it executes, including after
    an approval. Returns {"code", "message", "data"} or None.
    """
    refusal = live_execution_refusal()
    if refusal:
        return {**refusal, "data": {}}
    try:
        pair = "".join(parse_pair(symbol))  # "EUR/USD" and "EURUSD" match the same allowlist entry
    except ValueError:
        pair = symbol
    try:
        global_container.policy_engine.validate_brokerage_order(
            exchange_id=exchange,
            symbol=pair,
            side=side,
            amount=amount,
            market_type="spot",
            order_type=order_type,
            price=price if price and price > 0 else None,
        )
    except PolicyError as e:
        return {"code": e.code, "message": e.message, "data": e.data}
    return None


def execute_order(
    symbol: str, side: str, amount: float, price: float, order_type: str, exchange: str, rationale: str, market_price: Optional[float]
) -> Dict[str, Any]:
    """
    Execute an order that has passed its checks: in the paper account, or at the brokerage.
    Shared by the order tools and the approval API so both execute the same way.
    Returns {"ok": True, "data": ...} or {"ok": False, "code", "message", "data", "status"}.
    """
    if settings.PAPER_MODE:
        fill, problem = paper_fill_price(side, price if order_type == "limit" else 0.0, market_price)
        if problem:
            return {"ok": False, **problem, "data": {"market_price": market_price}, "status": 409}
        try:
            res = global_container.paper_engine.execute_trade(
                user_id=PAPER_USER, side=side, symbol=symbol, amount=amount, price=fill, rationale=rationale or "paper_order"
            )
        except ValueError as e:
            return {"ok": False, "code": "invalid_request", "message": str(e), "data": {}, "status": 400}
        except Exception as e:
            return {"ok": False, "code": "execution_error", "message": str(e), "data": {}, "status": 500}
        if res.startswith("Insufficient margin"):
            return {"ok": False, "code": "insufficient_margin", "message": res, "data": {}, "status": 409}
        return {"ok": True, "data": {"venue": "paper", "result": res, "account": global_container.paper_engine.account(PAPER_USER)}}

    refusal = live_order_refusal(exchange, symbol, side, amount, order_type, price)
    if refusal:
        return {"ok": False, **refusal, "status": 409}
    ex = (exchange or "").strip().lower()
    if ex not in global_container.brokerages:
        return {"ok": False, "code": "brokerage_not_supported", "message": f"Brokerage {exchange} is not supported.", "data": {}, "status": 400}
    brokerage = global_container.brokerages[ex]
    if not brokerage.is_available():
        return {"ok": False, "code": "brokerage_not_configured", "message": f"{exchange} keys are missing: no live order was sent.", "data": {}, "status": 400}
    try:
        res = brokerage.place_order(symbol=symbol, side=side, qty=amount, order_type=order_type, price=price if price > 0 else None)
    except Exception as e:
        return {"ok": False, "code": "execution_error", "message": str(e), "data": {}, "status": 500}
    return {"ok": True, "data": {"venue": ex, "mode": "live", "result": res}}


# ---------------------------------------------------------------- MCP tools


def place_market_order(symbol: str, side: str, amount: Number, rationale: str = "", sentiment_score: Number | None = None) -> str:
    """Place a market order for a currency pair: `amount` units of the base currency (EURUSD 1000 = 1,000 EUR).

    Paper mode fills at the latest rate in the paper account; live orders go to OANDA. `sentiment_score`
    is your own reading on [-1, +1] (see validate_trade_risk); below -0.5 the sentiment rule blocks a
    BUY. Independently, every BUY is checked against recent daily closes (Falling Knife, price) and
    every trade against the volatility halt - see validate_trade_risk.
    """
    return place_stock_order(symbol, side, amount, order_type="market", exchange="oanda", rationale=rationale, sentiment_score=sentiment_score)


def place_limit_order(symbol: str, side: str, amount: Number, price: Number, rationale: str = "", sentiment_score: Number | None = None) -> str:
    """Place a limit order for a currency pair (`amount` units of the base currency, `price` in the quote currency).

    Paper mode fills a limit only when it is marketable (a BUY at or above the market, a SELL at or
    below), at the market rate; resting orders are not simulated. Live orders go to OANDA as
    fill-or-kill: filled now at `price` or better, or cancelled (nothing rests at the broker). The
    same risk checks as place_market_order apply.
    """
    return place_stock_order(
        symbol, side, amount, price=price, order_type="limit", exchange="oanda", rationale=rationale, sentiment_score=sentiment_score
    )


def place_forex_order(
    symbol: str,
    side: str,
    amount: Number,
    order_type: str = "market",
    price: Number = 0.0,
    exchange: str = "oanda",
    rationale: str = "",
    sentiment_score: Number | None = None,
) -> str:
    """[RISK] Place an order for a currency pair through OANDA (default) or another brokerage.

    `amount` is units of the base currency; `order_type` is market or limit (`price` > 0 for a
    limit). `sentiment_score` is your own reading on [-1, +1] (see validate_trade_risk); below -0.5
    the sentiment rule blocks a BUY. Independently, every BUY is checked against recent daily closes
    (Falling Knife, price) and every trade against the volatility halt - see validate_trade_risk.
    """
    return place_stock_order(
        symbol,
        side,
        amount,
        price=price,
        order_type=order_type,
        exchange=exchange,
        rationale=rationale,
        audit_context="forex_trade",
        sentiment_score=sentiment_score,
    )


def place_stock_order(
    symbol: str,
    side: str,
    amount: Number,
    price: Number = 0.0,
    order_type: str = "market",
    exchange: str = "oanda",
    rationale: str = "",
    audit_context: str = "",
    sentiment_score: Number | None = None,
) -> str:
    """[RISK] Place an order through the Risk Guardian at any configured brokerage (`exchange`, default oanda).

    Paper mode trades currency pairs only (in the paper FX account). With
    EXECUTION_APPROVAL_MODE=approve_each the order is returned as a pending proposal instead.
    """
    problem = _invalid_order(side, amount=amount) or _invalid_order_type(order_type, price) or _invalid_sentiment(sentiment_score)
    if problem:
        return _json_err("invalid_request", problem)
    side, order_type, amount = side.strip().lower(), order_type.strip().lower(), float(amount)
    symbol = canonical_symbol(symbol)
    # A market order fills at the market whatever price it carries: the price is dropped, so it can
    # neither size the order nor reach a proposal or the brokerage (a NaN there broke the API).
    price = float(price) if order_type == "limit" else 0.0
    # Every well-formed order request is audited, including one the switches refuse: those are the
    # attempts an operator reviews after a halt (docs/CUSTODY.md, docs/THREAT_MODEL.md).
    global_compliance_ledger.record_event(
        "trade_start", {"symbol": symbol, "side": side, "amount": amount, "rationale": rationale, "audit_context": audit_context}
    )
    if settings.PAPER_MODE:
        try:
            parse_pair(symbol)
        except ValueError as e:
            return _json_err("invalid_request", f"{e}; paper mode trades currency pairs only.")
    elif live_execution_refusal():
        # The operator's switches answer first: with the kill switch set, "halted" is the answer,
        # whatever else is wrong with the order or the brokerage's configuration.
        switch = live_execution_refusal()
        return _json_err(switch["code"], switch["message"])
    elif (exchange or "").strip().lower() not in global_container.brokerages:
        return _json_err(
            "brokerage_not_supported",
            f"Brokerage {exchange!r} is not supported; choose one of {', '.join(sorted(global_container.brokerages))}. "
            "Paper trading is PAPER_MODE=true.",
        )
    elif not global_container.brokerages[exchange.strip().lower()].is_available():
        return _json_err("brokerage_not_configured", f"{exchange} keys are missing: no live order was sent.")

    try:
        check = pre_trade_check(symbol, side, amount, price, sentiment_score, exchange, order_type)
    except Exception as e:
        return _json_err("risk_validation_error", str(e))
    if not check["allowed"]:
        return _json_err(
            "risk_blocked",
            check["reason"],
            {
                "sentiment": check["sentiment"],
                "market": check["market"],
                "inactive_rules": check["inactive_rules"],
                "reference_price": check["reference_price"],
                "position_units": check["position_units"],
                "exposure_added_units": check["exposure_added_units"],
                "notional_usd": check["notional_usd"],
            },
        )

    # A live order that the switches or the live policy would refuse is refused now, not after a
    # human has been asked to approve it.
    if not settings.PAPER_MODE:
        refusal = live_order_refusal(exchange, symbol, side, amount, order_type, price)
        if refusal:
            return _json_err(refusal["code"], refusal["message"], refusal["data"])

    if settings.EXECUTION_APPROVAL_MODE == "approve_each":
        proposal = global_container.execution_store.create(
            kind="stock_order",
            payload={
                "symbol": symbol,
                "side": side,
                "amount": amount,
                "price": price,
                "order_type": order_type,
                "rationale": rationale,
                "exchange": exchange,
                # Kept so the approval path can re-run the same check at execution time.
                "sentiment_score": sentiment_score,
                # A proposal executes only in the mode it was made in (a paper proposal is never sent
                # to a broker by an API process running live, and the reverse).
                "paper_mode": settings.PAPER_MODE,
            },
        )
        return _json_ok(
            {
                "status": "pending_approval",
                "message": f"Order for {amount} {symbol} ({side}) requires manual confirmation.",
                "request_id": proposal.request_id,
                "confirm_token": proposal.confirm_token,
                "order_details": proposal.payload,
            }
        )

    out = execute_order(symbol, side, amount, price, order_type, exchange, rationale, check["market_price"])
    if not out["ok"]:
        return _json_err(out["code"], out["message"], out.get("data"))
    return _json_ok({**out["data"], "inactive_rules": check["inactive_rules"]})


def reset_paper_account() -> str:
    """[PAPER MODE] Clear the paper account: cash, positions and history."""
    if not settings.PAPER_MODE:
        return _json_err("invalid_mode", "Account reset only available in paper mode.")
    return _json_ok({"message": global_container.paper_engine.reset_wallet(PAPER_USER)})


def deposit_paper_funds(asset: str, amount: Number) -> str:
    """[PAPER MODE] Add virtual USD cash to the paper account (`asset` must be USD)."""
    if not settings.PAPER_MODE:
        return _json_err("invalid_mode", "Deposits only available in paper mode.")
    problem = _invalid_order("buy", amount=amount)
    if problem:
        return _json_err("invalid_request", problem)
    try:
        message = global_container.paper_engine.deposit(PAPER_USER, asset, float(amount))
    except ValueError as e:
        return _json_err("invalid_request", str(e))
    return _json_ok({"message": message, "account": global_container.paper_engine.account(PAPER_USER)})


def get_paper_account() -> str:
    """[PAPER MODE] The paper account: cash, equity, open positions with unrealized P&L, margin used and free."""
    if not settings.PAPER_MODE:
        return _json_err("invalid_mode", "The paper account exists only in paper mode.")
    try:
        return _json_ok(global_container.paper_engine.account(PAPER_USER))
    except ValueError as e:
        return _json_err("market_data_error", str(e))


def start_brokerage_private_ws(exchange: str, market_type: str) -> str:
    """Private order-update streams are not implemented; poll the brokerage instead."""
    if settings.PAPER_MODE:
        return _json_err("paper_mode_not_supported", "Private streams are not used in paper mode.")
    # It used to answer {"status": "connected"} without opening anything.
    return _json_err("not_implemented", f"Private {exchange} streams are not implemented; poll the brokerage instead.")


def register_execution_tools(mcp: FastMCP):
    mcp.tool(place_market_order)
    mcp.tool(place_limit_order)
    mcp.tool(place_forex_order)
    mcp.tool(place_stock_order)
    mcp.tool(reset_paper_account)
    mcp.tool(deposit_paper_funds)
    mcp.tool(get_paper_account)
    mcp.tool(start_brokerage_private_ws)