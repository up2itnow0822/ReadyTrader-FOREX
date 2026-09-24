# Falling Knife (price) and the volatility halt

Every trade check and every order — `validate_trade_risk`, `place_forex_order`,
`place_market_order`, `place_limit_order`, `place_stock_order` — reads the pair's recent daily
bars and applies two rules:

- **Volatility halt** (Rule 0.6): while today's move is more than 4.5x the pair's 20-day norm,
  **every** trade on the pair is refused, BUY or SELL, as an exchange circuit breaker would.
- **Falling Knife** (Rule 2b): a **BUY** is refused while the pair is still falling after a 5%
  drop over four days. A SELL is never refused by this rule, because a SELL may be the exit from a
  long.

## The rules

Only daily closes are used. FX highs and lows carry bad provider prints (in the study data 0.24%
of bars had a high more than 3% above the open-close body), and a phantom spike would otherwise
read as a crash. During the session "today's close" is the current rate, from today's partial bar.

```
Falling Knife
  drop = (highest of the last four closes - today's close) / highest of the last four closes
  BUY blocked  when  drop >= 5%  AND  today's close is at or below each of the three earlier closes

Volatility halt
  ratio = |ln(today's close / yesterday's close)| / mean of the same move over the 20 days before
  every trade blocked  when  ratio > 4.5
```

**Direction.** The Falling Knife rule protects the currency being bought. A BUY of USDTRY buys
dollars, so a lira collapse (USDTRY rising) does not block it. Buying the lira is a SELL of USDTRY,
which this rule does not check; the volatility halt is what stops trading into that kind of
dislocation, in either direction.

## How it runs

- **Data**: `global_container.exchange_provider.fetch_ohlcv(symbol, "1d", limit=40)` — the same
  yfinance-backed provider as the `fetch_ohlcv` tool (`EURUSD` and `EUR/USD` are read as
  `EURUSD=X`), cached for `OHLCV_CACHE_TTL_SEC` (60 s by default, never past the next daily
  boundary). At most one network call per pair per minute.
- **Code**: `core/market_guard.py` is pure (bars in, reading out). `app/tools/trading.py`
  (`_market_context`) fetches the bars and applies the policy below; `core/risk.py` turns the
  reading into a verdict. `intelligence.core.get_volatility_status(symbol)` returns the same ratio,
  or `None` when it cannot be computed — never a made-up "normal".
- **Response**: `validate_trade_risk` returns a `market` block — `status`, `falling_knife`,
  `drop_pct`, `peak_close`, `last_close`, `still_falling`, `volatility_ratio`, `bars`, `as_of`,
  `detail`, the `rule` thresholds and the data-error policy. A blocked order returns the same
  block in its error data. `inactive_rules` lists any rule that cannot fire (the news guard is
  still a stub; both rules here appear if `MARKET_GUARD_ENABLED=false`).

### When the bars cannot be read

`status` is `ok`, `insufficient_data` (fewer than 4 usable bars), `stale` (latest bar more than
5 days old — a weekend plus a holiday is fine), `unavailable` (the provider raised), or `disabled`.
The volatility ratio needs 22 bars; with fewer it is `null` and the halt cannot fire.

| `MARKET_GUARD_ON_DATA_ERROR` | A BUY whose check could not run |
| :--- | :--- |
| unset, live mode | **blocked** — a missed buy is recoverable, a buy into a collapse may not be |
| unset, paper mode | allowed, with the `market` block saying why the check did not run |
| `block` | blocked |
| `allow` | allowed, with the `market` block saying why |
| anything else | blocked (an unrecognised value fails closed) |

A SELL is never blocked for missing data.

### Settings

| Variable | Default | Effect |
| :--- | :--- | :--- |
| `MARKET_GUARD_ENABLED` | `true` | `false` turns off both rules; they are then listed in `inactive_rules` |
| `MARKET_GUARD_ON_DATA_ERROR` | unset | see the table above |
| `OHLCV_CACHE_TTL_SEC` | `60` | cache lifetime for the daily bars |

`CIRCUIT_BREAKER_PCT` is not read by any check; it predates these rules and is kept only so
existing configurations still load.

## Why these numbers

The thresholds were chosen on daily history and then tested on data the choice never saw. The full
protocol, the scripts and their raw output are in [`research/falling_knife/`](../research/falling_knife/);
this is the summary. Every pair was scored in both directions (EURUSD and USDEUR), since either
leg can be the one bought.

### Falling Knife

**Question asked:** if you had bought at the close on a day the rule fires, how often did the
bought currency fall a *further* 3% within ten days, compared with buying on any day?

**Selection** (2003-2016, 19 pairs): among rules firing on 0.3%-1.0% of pair-days, the highest
lift. That was 5% over four closes; it was frozen, with its hash, before any scoring.

| Data | Fires on | Fell a further 3% within 10 days | Worst-decile 10-day drawdown | Median 10-day return |
| :--- | ---: | :--- | :--- | :--- |
| Development: 19 pairs, 2003-2016 | 0.36% of days | 47.8% vs 16.9% on all days (2.8x) | -10.4% vs -3.8% | +1.0% vs 0.0% |
| **Never-seen: 24 other pairs, 2000-2026** | 0.17% | **40.6% vs 11.6% (3.5x)** | -7.8% vs -3.2% | +1.3% vs 0.0% |
| Never-seen pairs, 2017-2026 only | 0.06% | 36.8% vs 8.8% (4.2x) | -8.9% vs -2.9% | +1.2% vs 0.0% |
| Development pairs, 2017-2026 (already used once, to test the first version) | 0.13% | 44.6% vs 10.7% (4.2x) | -15.2% vs -3.1% | +1.9% vs 0.0% |

### Volatility halt

The threshold was set on the development years to fire as often as the true-range halt it replaces
(0.8% of pair-days), then scored the same way: after a halt day, how often did the pair move 3% or
more (either way) within five days?

| Data | Halted on | 3%+ move within 5 days |
| :--- | ---: | :--- |
| Development, 2003-2016 | 0.80% of days | 20.0% vs 10.0% on all days (2.0x) |
| Development pairs, 2017-2026 | 0.96% | 14.2% vs 5.1% (2.8x) |
| **Never-seen pairs, 2000-2026** | 1.00% | **15.4% vs 5.6% (2.7x)** |

It caught the SNB floor removal (508x the norm), the August 2018 lira crash (17.7x), the Brexit
vote (12.6x), the December 2021 lira reversal (8.8x), the 2022 UK mini-budget (7.7x) and the 2016
GBP and 2019 JPY flash crashes (5.6x, 6.2x). It did not halt EURUSD in March 2020 (4.2x), the
October 2022 yen intervention (4.4x), the November 2021 lira collapse (4.3x — the Falling Knife
rule blocked buying the lira that day) or the August 2024 carry unwind (3.2x).

The shipped `core/market_guard.py` was checked against the research implementation on all 517,544
pair-days above, using only the 40 bars it sees at runtime: 100% agreement on both rules.

**Real episodes pinned by the tests** (`tests/fixtures/market_guard_real_bars.json`; dates are the
UTC dates of Yahoo's bars, which stamp many FX days at 23:00 the day before):

| Pair, bar | Reading |
| :--- | :--- |
| EURCHF 2015-01-16 (SNB) | EUR down 17%: **halted** (508x) and a Falling Knife for a buy of EURCHF |
| CHFEUR, same bar | **halted**; not a Falling Knife (CHF rose) |
| TRYUSD 2021-11-25 (buying the lira) | down 7.4%: **Falling Knife**; 4.3x, under the halt. The lira fell a further 14% within ten days |
| USDTRY, same bar (buying dollars) | not a Falling Knife |
| GBPUSD 2016-10-06 (flash crash) | **halted** (5.6x); only 3.5% down, under the Falling Knife floor |
| EURUSD 2024-06-12 | an ordinary day: allowed |

## What it is not

- **Not a forecast.** On days the Falling Knife rule fires the *median* ten-day return was slightly
  positive: some collapses bounce. The rule trades those bounces away for protection against the
  tail. That matches this project's rule that nothing should make an unrecoverable move; if you
  disagree for your strategy, set `MARKET_GUARD_ENABLED=false`.
- **The halt also stops exits made through this server.** That is deliberate — fills during a
  dislocation are where the damage is done — but if you must close a position during a halt, close
  it with the broker directly.
- **Not independent evidence hundreds of times over.** Fires cluster in crises, so the effective
  number of independent episodes is far smaller than the day counts.
- **Only as good as the bars.** A bad close from the provider can cause a false block. The study
  removed obvious single-bar bad ticks; the live check does not, so a bad tick can halt a pair for
  as long as it is the latest close.
- **Separate from the sentiment rule.** `sentiment_score` (your own reading of the crowd, below
  -0.5) still blocks a BUY on its own; see [SENTIMENT.md](SENTIMENT.md).

## History

Before these rules the volatility halt and the Falling Knife protection were wired into the Risk
Guardian but never fired: `get_volatility_status` was a stub returning 1.0, and the sentiment score
could not be measured (see SENTIMENT.md). A first version measured drops from intraday highs and
used a true-range halt (3x); it was replaced by the close-based rules above before release because
bad high/low prints in FX data made it fire on phantom spikes. A price rule for crypto was tested
the same way and failed on data it had not seen, so ReadyTrader-Crypto does not ship one.
