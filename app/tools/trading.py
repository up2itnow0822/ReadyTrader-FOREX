import json
from typing import Any, Dict, List

from fastmcp import FastMCP

from app.core.config import settings
from app.core.container import global_container
from core import market_guard
from intelligence import get_cached_sentiment
from intelligence.core import (
    NEWS_STATUS_IMPLEMENTED,
    VOLATILITY_STATUS_IMPLEMENTED,
    get_news_status,
)


def _json_ok(data: Dict[str, Any] | None = None) -> str:
    payload = {"ok": True, "data": data or {}}
    return json.dumps(payload, indent=2, sort_keys=True)


def _json_err(code: str, message: str, data: Dict[str, Any] | None = None) -> str:
    payload = {"ok": False, "error": {"code": code, "message": message, "data": data or {}}}
    return json.dumps(payload, indent=2, sort_keys=True)


NOT_MEASURED_HINT = (
    "This server does not score sentiment. Call get_social_sentiment(symbol) to read the posts, "
    "and pass your own reading as sentiment_score on [-1, +1] if you want the sentiment side of the "
    "Falling Knife rule to act. Left unset it is neutral (0.0) and that side cannot fire; the price "
    "side reads daily closes on every BUY regardless."
)
NO_SOURCE_HINT = (
    "No X or Reddit credentials are set, so there are no posts to read either. "
    "Set TWITTER_BEARER_TOKEN and/or REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET."
)


def _sentiment_context(symbol: str, supplied: float | None) -> Dict[str, Any]:
    """
    What the Falling Knife rule is working from, so a neutral 0.0 is never mistaken for a
    measured calm market. `source` is the whole point: this server measures nothing, so a
    non-zero score is always the caller's own judgement and is recorded as such.
    """
    entry = get_cached_sentiment(symbol)
    context: Dict[str, Any] = {
        "score": 0.0,
        "source": "unmeasured",
        "status": "not_measured",
        "posts_available": entry["texts"] if entry else 0,
        "posts_age_seconds": entry["age_seconds"] if entry else None,
        "hint": NOT_MEASURED_HINT,
    }
    if entry is not None and not entry["configured"]:
        context["status"] = "no_source_configured"
        context["hint"] = NO_SOURCE_HINT
    if supplied is not None:
        score = max(-1.0, min(1.0, float(supplied)))
        context["score"] = score
        context["source"] = "agent_supplied"
        context["status"] = "agent_supplied"
        context.pop("hint", None)
    return context


def _fetch_daily_bars(symbol: str) -> List[Any]:
    """The market checks' only network call. Tests replace this function."""
    return global_container.exchange_provider.fetch_ohlcv(
        symbol, market_guard.TIMEFRAME, limit=market_guard.BARS_REQUESTED
    )


def _market_guard_policy() -> str:
    """What a BUY does when the daily bars cannot be read: "block" or "allow"."""
    raw = (settings.MARKET_GUARD_ON_DATA_ERROR or "").strip().lower()
    if raw in ("block", "allow"):
        return raw
    if raw:
        return "block"  # an unrecognised value fails closed
    return "allow" if settings.PAPER_MODE else "block"


def _market_context(symbol: str) -> Dict[str, Any]:
    """
    The Falling Knife reading and volatility ratio for a pair (core/market_guard.py), plus the
    policy the Risk Guardian applies to it. Read for both sides: the volatility halt applies to
    every trade, while the Falling Knife rule and the missing-data policy apply only to BUYs.
    """
    rule = {
        "window_bars": market_guard.KNIFE_WINDOW + 1,
        "min_drop": market_guard.KNIFE_MIN_DROP,
        "volatility_halt_ratio": market_guard.VOLATILITY_HALT_RATIO,
    }
    if not settings.MARKET_GUARD_ENABLED:
        reading = market_guard.MarketReading(status=market_guard.STATUS_DISABLED, detail="MARKET_GUARD_ENABLED=false")
    else:
        try:
            reading = market_guard.assess(_fetch_daily_bars(symbol))
        except Exception as e:
            reading = market_guard.MarketReading(
                status=market_guard.STATUS_UNAVAILABLE, detail=f"{type(e).__name__}: {str(e)[:160]}"
            )
    policy = _market_guard_policy()
    return {**reading.to_dict(), "rule": rule, "on_data_error": policy, "required": policy == "block"}


def inactive_rules() -> Dict[str, str]:
    """
    Risk rules that are wired into the Guardian but cannot currently fire.

    Reported alongside every verdict so that "allowed" is never read as "fully checked".
    """
    inactive = {}
    if not VOLATILITY_STATUS_IMPLEMENTED:
        inactive["volatility_halt"] = "the volatility ratio is not implemented, so the flash-crash halt never fires."
    if not settings.MARKET_GUARD_ENABLED:
        inactive["volatility_halt"] = "MARKET_GUARD_ENABLED=false, so the flash-crash halt never fires."
        inactive["falling_knife_price"] = "MARKET_GUARD_ENABLED=false, so a BUY into a collapsing pair is not blocked."
    if not NEWS_STATUS_IMPLEMENTED:
        inactive["news_guard"] = (
            "get_news_status() is not implemented and always reports no news window, "
            "so trading is never suspended around high-impact releases."
        )
    return inactive


def register_trading_tools(mcp: FastMCP):
    @mcp.tool()
    def deposit_paper_funds(asset: str, amount: float) -> str:
        """[PAPER MODE] Deposit fake funds into the paper trading account."""
        if not settings.PAPER_MODE:
            return _json_err("paper_mode_required", "Paper mode is NOT enabled.")
        return _json_ok({"result": global_container.paper_engine.deposit("agent_zero", asset, amount)})

    @mcp.tool()
    def reset_paper_account() -> str:
        """[PAPER MODE] Reset the paper trading account and trade history."""
        if not settings.PAPER_MODE:
            return _json_err("paper_mode_required", "Paper mode is NOT enabled.")
        return _json_ok({"result": global_container.paper_engine.reset_wallet("agent_zero")})

    @mcp.tool()
    def validate_trade_risk(
        side: str, symbol: str, amount_usd: float, portfolio_value: float, sentiment_score: float | None = None
    ) -> str:
        """
        [GUARDIAN] Validate if a trade is safe to execute.

        `sentiment_score` is optional and is YOUR reading of the market on [-1, +1], not a
        measurement this server makes. Below -0.5 the sentiment rule blocks a BUY. Call
        get_social_sentiment(symbol) first to read the posts and form that judgement. Left
        unset, sentiment is neutral (0.0) and that rule cannot fire.

        Returns `result` ({allowed, reason}), `sentiment` ({score, source, status,
        posts_available, posts_age_seconds}), `market` - the pair's recent daily bars read as a
        Falling Knife check and a volatility ratio ({status, falling_knife, drop_pct,
        volatility_ratio, as_of, ...}) - and `inactive_rules`, the risk rules that cannot
        currently fire, so an unblocked trade is never mistaken for a fully checked one.
        A BUY is blocked while the pair is still falling after a 5%+ drop from its highest close
        of the last four days; every trade is halted while the day's move is more than 4.5x its
        20-day norm. This check reads recent daily bars (cached for up to a minute).
        """
        try:
            sentiment = _sentiment_context(symbol, sentiment_score)
            market = _market_context(symbol)
            daily_loss = 0.0
            drawdown = 0.0

            if settings.PAPER_MODE and global_container.paper_engine:
                metrics = global_container.paper_engine.get_risk_metrics("agent_zero")
                daily_loss = metrics.get("daily_pnl_pct", 0.0)
                drawdown = metrics.get("drawdown_pct", 0.0)

            result = global_container.risk_guardian.validate_trade(
                side,
                symbol,
                amount_usd,
                portfolio_value,
                sentiment["score"],
                daily_loss,
                drawdown,
                market=market,
                volatility_score=market.get("volatility_ratio"),
                is_news_event_window=get_news_status(),
            )
            return _json_ok(
                {
                    "side": side,
                    "symbol": symbol,
                    "amount_usd": amount_usd,
                    "result": result,
                    "sentiment": sentiment,
                    "market": market,
                    "inactive_rules": inactive_rules(),
                }
            )
        except Exception as e:
            return _json_err("risk_validation_error", str(e))
