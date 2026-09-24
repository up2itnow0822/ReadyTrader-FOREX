"""
Price-based Falling Knife check and volatility ratio, from daily bars. Pure: no network, no clock
unless given.

A BUY of a pair is a falling knife when, over the latest daily close and the KNIFE_WINDOW closes
before it:

    drop = (highest close in the window - latest close) / highest close  >=  KNIFE_MIN_DROP
    and the latest close is at or below every earlier close in the window (still falling)

Only closes are used, here and in the volatility ratio. FX daily highs and lows carry bad provider
prints (in the study data 0.24% of bars had a high more than 3% above the open-close body), and a
phantom spike would otherwise read as a crash. During the session the latest bar is today's
partial candle, so "latest close" is the current rate.

KNIFE_WINDOW = 3 (today plus three prior days) and KNIFE_MIN_DROP = 5% were chosen on 2003-2016
daily history of 19 pairs, each also scored inverted (EURUSD and USDEUR), frozen, and then scored
once on 24 pairs that had never been downloaded (docs/FALLING_KNIFE.md). On those, over 2000-2026,
the rule fired on 0.17% of pair-days; a buy on those days fell a further 3% within ten days 40.6%
of the time, against 11.6% on all days, and its worst-decile drawdown was -7.8% against -3.2%. Its
median outcome was not worse: this is tail protection, not a forecast.

The rule protects the currency being bought. A BUY of USDTRY buys dollars, so a lira collapse
(USDTRY rising) does not block it. Buying the lira is a SELL of USDTRY, and SELLs are never
checked by this rule because a SELL may be the exit from a long; the volatility halt below is what
stops trading into that kind of dislocation.

volatility_ratio = |ln(latest close / previous close)| / the mean of that same move over the
VOLATILITY_BASELINE days before it. The Risk Guardian halts every trade above VOLATILITY_HALT_RATIO
(4.5). On the development years that fired on 0.80% of pair-days (the frequency of the 3x
true-range halt it replaces) and on 1.0% of the never-seen pairs; after a halt day a 3% move within
five days happened 15.4% of the time on those pairs, against 5.6% on all days. It caught the SNB
floor removal (508x), the Aug 2018 lira crash (17.7x), Brexit (12.6x), the 2016 GBP and 2019 JPY
flash crashes (5.6x, 6.2x) and the 2022 UK mini-budget (7.7x).
"""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

KNIFE_WINDOW = 3
KNIFE_MIN_DROP = 0.05
VOLATILITY_BASELINE = 20
VOLATILITY_HALT_RATIO = 4.5

# How many daily bars to request. The window needs KNIFE_WINDOW + 1; the rest is headroom for
# holidays and for bars a provider drops.
BARS_REQUESTED = 40
TIMEFRAME = "1d"

# A latest bar older than this is not "now": FX trades five days a week, so Friday's bar is 2-3 days
# old over a weekend and a holiday adds one more.
MAX_STALENESS_DAYS = 5

STATUS_OK = "ok"
STATUS_INSUFFICIENT = "insufficient_data"
STATUS_STALE = "stale"
STATUS_UNAVAILABLE = "unavailable"
STATUS_DISABLED = "disabled"


@dataclass(frozen=True)
class MarketReading:
    status: str
    falling_knife: bool = False
    drop_pct: Optional[float] = None
    peak_close: Optional[float] = None
    last_close: Optional[float] = None
    still_falling: Optional[bool] = None
    volatility_ratio: Optional[float] = None
    bars: int = 0
    as_of: Optional[str] = None
    detail: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Session:
    """
    A trading session, for the freshness check: once today's session has opened, the provider must
    already have today's daily bar, or the check would be reading yesterday's closes while missing a
    move happening now. Daily bars are stamped at midnight of their session date in the exchange's
    time zone (yfinance), which is how a bar is matched to a date.
    """

    tz: str
    open_hhmm: str = "00:00"
    weekdays: Tuple[int, ...] = (0, 1, 2, 3, 4)  # Monday..Friday

    def open_date(self, now_ms: int) -> Optional[date]:
        """Today's date in `tz` if today is a session day and the session has opened, else None."""
        local = datetime.fromtimestamp(now_ms / 1000, ZoneInfo(self.tz))
        hour, minute = (int(part) for part in self.open_hhmm.split(":"))
        if local.weekday() in self.weekdays and (local.hour, local.minute) >= (hour, minute):
            return local.date()
        return None

    def bar_date(self, ts_ms: int) -> date:
        return datetime.fromtimestamp(ts_ms / 1000, ZoneInfo(self.tz)).date()


# Yahoo's FX daily bars are London days, Monday to Friday, stamped at London midnight; the current
# day's bar exists from midnight London, while the pair is trading.
FX_SESSION = Session(tz="Europe/London")


def _clean(ohlcv: Sequence[Sequence[Any]]) -> List[List[float]]:
    """Keep rows with a timestamp and finite, positive, consistent OHLC; sort and de-duplicate by time."""
    rows: Dict[int, List[float]] = {}
    for row in ohlcv or []:
        try:
            ts, o, h, low, c = int(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4])
        except (TypeError, ValueError, IndexError):
            continue
        values = (o, h, low, c)
        if not all(math.isfinite(v) and v > 0 for v in values) or h < low:
            continue
        rows[ts] = [ts, o, h, low, c]
    return [rows[k] for k in sorted(rows)]


def volatility_ratio(bars: Sequence[Sequence[float]], baseline: int = VOLATILITY_BASELINE) -> Optional[float]:
    """Latest |log close-to-close move| over the mean of the `baseline` moves before it; None if too short."""
    if len(bars) < baseline + 2:
        return None
    moves = [abs(math.log(bars[i][4] / bars[i - 1][4])) for i in range(len(bars) - baseline - 1, len(bars))]
    mean = sum(moves[:-1]) / baseline
    return round(moves[-1] / mean, 4) if mean > 0 else None


def _now_ms() -> int:
    """The clock `assess` uses when no `now_ms` is given (tests replace it)."""
    return int(time.time() * 1000)


def _iso(ts_ms: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts_ms / 1000))


def assess(
    ohlcv: Sequence[Sequence[Any]],
    *,
    min_drop: float = KNIFE_MIN_DROP,
    window: int = KNIFE_WINDOW,
    now_ms: Optional[int] = None,
    max_staleness_days: float = MAX_STALENESS_DAYS,
    session: Optional[Session] = None,
) -> MarketReading:
    """
    Evaluate the latest bar of `ohlcv` ([[ts_ms, open, high, low, close, volume], ...]).

    With a `session`, a latest bar older than today's session is stale once that session has
    opened: neither rule can then see today's move, so neither may pass for checked.
    """
    bars = _clean(ohlcv)
    if len(bars) < window + 1:
        return MarketReading(
            status=STATUS_INSUFFICIENT,
            bars=len(bars),
            detail=f"need {window + 1} daily bars, got {len(bars)}",
        )

    last_ts = int(bars[-1][0])
    now = _now_ms() if now_ms is None else int(now_ms)
    age_days = (now - last_ts) / 86_400_000
    if age_days > max_staleness_days:
        return MarketReading(
            status=STATUS_STALE,
            bars=len(bars),
            as_of=_iso(last_ts),
            detail=f"latest daily bar is {age_days:.1f} days old",
        )
    if session is not None:
        today = session.open_date(now)
        latest = session.bar_date(last_ts)
        if today is not None and latest < today:
            return MarketReading(
                status=STATUS_STALE,
                bars=len(bars),
                as_of=_iso(last_ts),
                detail=(
                    f"no daily bar yet for today's session ({today.isoformat()}, {session.tz}); "
                    f"the latest is {latest.isoformat()}"
                ),
            )

    closes = [b[4] for b in bars[-(window + 1):]]
    peak_close = max(closes)
    last_close = closes[-1]
    drop = (peak_close - last_close) / peak_close
    still_falling = last_close <= min(closes[:-1])
    return MarketReading(
        status=STATUS_OK,
        falling_knife=bool(drop >= min_drop and still_falling),
        drop_pct=round(drop, 6),
        peak_close=peak_close,
        last_close=last_close,
        still_falling=bool(still_falling),
        volatility_ratio=volatility_ratio(bars),
        bars=len(bars),
        as_of=_iso(last_ts),
    )
