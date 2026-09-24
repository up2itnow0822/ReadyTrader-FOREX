from typing import Any, Dict, Optional

from core.market_guard import VOLATILITY_HALT_RATIO


class RiskGuardian:
    def __init__(self):
        pass

    def validate_trade(
        self,
        side: str,
        symbol: str,
        amount_usd: float,
        portfolio_value: float,
        sentiment_score: float = 0.0,
        daily_loss_pct: float = 0.0,
        current_drawdown_pct: float = 0.0,
        force_approval: bool = False,
        price: Optional[float] = None,
        last_close_price: Optional[float] = None,
        day_trades_count: int = 0,
        market: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Validate a trade against safety rules.
        """
        # Rule 0: System State Checks
        # Max Drawdown Check (10%)
        # If drawdown is 10%, we only allow reducing risk (SELLs), not BUYs?
        # Or we block everything? Usually block BUYs.
        if current_drawdown_pct >= 0.10 and side.lower() == "buy":
            return {"allowed": False, "reason": f"Max Drawdown Limit Hit ({current_drawdown_pct:.1%}). Trading HALTED for Buys."}

        # Rule 0.5: Margin Utilization Check (Forex)
        if portfolio_value > 0 and amount_usd > 0:
            pass

        # Rule 0.6: Volatility Halt. volatility_score is today's close-to-close move over the mean of
        # the 20 before it (core/market_guard.py). Above VOLATILITY_HALT_RATIO every side is halted,
        # as an exchange circuit breaker would: executing into a dislocation is the risk, whichever
        # the direction. Exits during a halt go through the broker directly.
        volatility_score = kwargs.get("volatility_score")
        if volatility_score is None:
            volatility_score = 1.0
        if volatility_score > VOLATILITY_HALT_RATIO:
            return {
                "allowed": False,
                "reason": (
                    f"Volatility Halt: today's move is {volatility_score:.1f}x the 20-day norm, above the "
                    f"{VOLATILITY_HALT_RATIO:.1f}x limit. Flash Crash Protection: every trade on this pair is "
                    "halted until the move subsides; close positions through the broker if you must."
                ),
            }

        # Rule 0.7: News Guard
        # If 'is_news_event_window' is True, block.
        if kwargs.get("is_news_event_window", False):
            return {"allowed": False, "reason": "News Guard: High Impact Economic Event imminent or in progress. Trading suspended."}

        # Daily Loss Limit (5%)
        # If we lost 5% today, stop trading.
        # daily_loss_pct is usually negative (e.g. -0.05)
        if daily_loss_pct <= -0.05 and side.lower() == "buy":
            return {"allowed": False, "reason": f"Daily Loss Limit Hit ({daily_loss_pct:.1%}). Trading HALTED for Buys."}

        # Rule 1: Position Sizing
        # Max 5% of portfolio per trade
        max_alloc_pct = 0.05
        if portfolio_value > 0:
            trade_pct = amount_usd / portfolio_value
            if trade_pct > max_alloc_pct:
                return {"allowed": False, "reason": f"Position size too large ({trade_pct:.1%}). Max allowed is {max_alloc_pct:.0%}."}

        # Rule 2: "Don't Catch Falling Knives"
        # If sentiment is very bearish (< -0.5) and trying to Buy
        if side.lower() == "buy" and sentiment_score < -0.5:
            return {"allowed": False, "reason": "Guardian blocked BUY due to Extreme Bearish sentiment (Falling Knife protection)."}

        # Rule 2b: Falling Knife (price). `market` is a core/market_guard.py reading prepared by the
        # tools layer. A BUY is blocked while the pair is still falling after a large drop, and - when
        # the operator requires the check - while the check cannot run.
        if side.lower() == "buy" and market:
            if market.get("falling_knife"):
                return {"allowed": False, "reason": _knife_reason(symbol, market)}
            if market.get("required") and market.get("status") not in ("ok", "disabled"):
                return {
                    "allowed": False,
                    "reason": (
                        f"Falling Knife check could not run for {symbol} "
                        f"({market.get('detail') or market.get('status')}); BUYs are blocked until it can. "
                        "Set MARKET_GUARD_ON_DATA_ERROR=allow to override."
                    ),
                }

        # Rule 3: Price Collar (Fat-finger protection - SEC Rule 15c3-5)
        if last_close_price and price:
            deviation = abs(price - last_close_price) / last_close_price
            if deviation > 0.05:  # 5% collar
                return {"allowed": False, "reason": f"Price collar violation: {deviation:.2%} deviation from last close exceeds 5% limit."}

        # Rule 4: PDT (Pattern Day Trader) Check
        if day_trades_count >= 3 and portfolio_value < 25000:
            return {"allowed": False, "reason": "Pattern Day Trader protection: >3 day trades in account under $25k."}

        # Rule 5: Large Trade Confirmation
        # Any trade > $5000 requires manual approval even if allowed by logic
        needs_confirmation = False
        if amount_usd > 5000.0:
            needs_confirmation = True

        return {
            "allowed": True,
            "needs_confirmation": needs_confirmation,
            "reason": "Trade looks safe but requires manual confirmation." if needs_confirmation else "Trade looks safe.",
        }


def _knife_reason(symbol: str, market: Dict[str, Any]) -> str:
    drop = market.get("drop_pct") or 0.0
    peak = market.get("peak_close")
    last = market.get("last_close")
    window = (market.get("rule") or {}).get("window_bars", 4)
    return (
        f"Guardian blocked BUY: {symbol} is down {drop:.1%} from its highest close of the last "
        f"{window} days ({peak:.5f} -> {last:.5f}) and is still at the lowest close of that window "
        "(Falling Knife protection, price)."
    )
