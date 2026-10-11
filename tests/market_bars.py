"""Synthetic daily bars for Falling Knife and volatility-halt tests. Rows are [ts_ms, o, h, l, c, v]."""

import time

DAY_MS = 86_400_000


def series(closes, *, end_ms=None, spread=0.001):
    """Daily bars ending at `end_ms` (default: now) whose closes follow `closes`."""
    end = int(time.time() * 1000) if end_ms is None else end_ms
    start = end - (len(closes) - 1) * DAY_MS
    rows, prev = [], closes[0]
    for i, c in enumerate(closes):
        o = prev
        rows.append([start + i * DAY_MS, o, max(o, c) * (1 + spread), min(o, c) * (1 - spread), c, 0.0])
        prev = c
    return rows


def _choppy(n, price, noise):
    return [price * (1 + (noise if i % 2 else -noise)) for i in range(n)]


def calm(n=40, price=1.10, noise=0.004, **kw):
    """A quiet tape: small alternating moves around `price`."""
    return series(_choppy(n, price, noise), **kw)


def collapse(n=40, price=1.10, drop=0.08, days=3, noise=0.01, **kw):
    """
    A choppy tape, then a steady fall of `drop` over the last `days` bars, closing on the low.
    The chop keeps each day's move ordinary next to the 20-day norm, so this is a falling knife
    without being a volatility halt.
    """
    head = _choppy(n - days, price, noise)
    base = head[-1]
    tail = [base * (1 - drop * (i + 1) / days) for i in range(days)]
    return series(head + tail, **kw)


def spike(n=40, price=1.10, move=0.06, noise=0.004, **kw):
    """A quiet tape whose last close jumps by `move`: a volatility halt, not a falling knife."""
    closes = _choppy(n - 1, price, noise)
    return series(closes + [closes[-1] * (1 + move)], **kw)
