# Market Intelligence & Sentiment Guide (ReadyTrader-FOREX)

ReadyTrader-FOREX gives AI agents both "Hands" (execution) and "Eyes" (intelligence). This document explains how to configure the feeds, and what the Risk Guardian's Falling Knife rule does and does not know.

## Overview of Sentiment Sources

| Source | Level | Cost | Required Credentials | Feature |
| :--- | :--- | :--- | :--- | :--- |
| **Forex RSS News** | Basic | Free | None | Investing.com, FXStreet, DailyFX, ForexLive, Reuters. |
| **DXY Trend** | Basic | Free | None | Dollar-index direction over five sessions (yfinance). |
| **Economic Calendar** | Basic | Free | None | High-impact releases from ForexFactory. |
| **X (Twitter)** | Social | Free (Limited) | Bearer Token | Recent posts about a pair. |
| **Reddit** | Community | Free | Client ID + Secret | r/forex and r/wallstreetbets discussion. |
| **NewsAPI** | Financial | Free (Trial) | API Key | Reporting from major financial outlets. |

______________________________________________________________________

## Configuration Instructions

### 1. Free news, DXY and calendar

These work **out of the box** with no configuration.

### 2. X / Twitter (social volume)

1. Sign up for a Developer Account at [X Developer Portal](https://developer.x.com/).
1. Create a **Project** and an **App**.
1. Generate an **App-only Bearer Token**.
1. Add it to your `.env`:
   ```bash
   TWITTER_BEARER_TOKEN=your_bearer_token_here
   ```

### 3. Reddit

1. Go to [Reddit App Preferences](https://www.reddit.com/prefs/apps).
1. Click "Create another app..." and select **script**.
1. Redirect URI can be `http://localhost:8080`.
1. Copy your **Client ID** (under the name) and **Client Secret**.
1. Add them to your `.env`:
   ```bash
   REDDIT_CLIENT_ID=your_client_id
   REDDIT_CLIENT_SECRET=your_client_secret
   ```

### 4. NewsAPI (institutional news)

1. Get a key at [NewsAPI.org](https://newsapi.org/).
1. Add it to your `.env`:
   ```bash
   NEWSAPI_KEY=your_newsapi_key_here
   ```

______________________________________________________________________

## 🤖 Agent Tool Reference

AI Agents can query these feeds using the following tools:

- `get_forex_market_brief(symbol)`: One call for price, DXY trend, calendar and news.
- `get_forex_news(limit)`: Aggregated headlines from five free Forex feeds.
- `get_market_sentiment()`: DXY trend plus the high-impact calendar. Not pair-specific.
- `get_economic_calendar()`: High-impact releases from ForexFactory.
- `get_social_sentiment(symbol)`: Returns recent X and Reddit posts about a pair **for you to read**. Returns text, not a score — see "The Falling Knife rule" below.
- `get_financial_news(symbol)`: Queries NewsAPI.
- `fetch_custom_feed(url, keyword)`: Headlines from any RSS or Atom feed you supply.

> [!TIP]
> When keys are missing, the tools say so and explain which keys are needed, rather than returning a simulated value. Nothing here fabricates a score — see below.

______________________________________________________________________

## The Falling Knife rule, and why this server does not score sentiment

`get_social_sentiment(symbol)` returns **posts, not a number**. That is a deliberate decision, and this section records the evidence behind it so it can be revisited rather than rediscovered.

### What was broken

`analyze_social_sentiment` added a flat `+0.2` for each configured source. The score therefore measured *how many API keys were set*, not what anyone was saying: a panicking feed and a euphoric feed both scored `+0.4`, and the only reachable values were `0.0`, `0.2` and `0.4`. The Risk Guardian's Falling Knife rule blocks a BUY below `-0.5`, so it could never fire. A second defect made this moot anyway — the order path passed a hardcoded `0.0`.

### What was tried

A deterministic replacement was built: VADER's rule engine (negation, intensifiers, capitals) over a market-only vocabulary instead of general-English sentiment, scoring the bull-bear spread over directional texts. The same design is in production in the crypto sibling of this repo, where it works.

It was then measured against simulated pair searches written by a model that had never seen its vocabulary, with the configuration frozen before scoring, and hardened through two rounds of adversarial review.

### What the measurement showed (FX)

On 30 simulated pair searches written blind to the vocabulary: **0 of 8 currency crashes blocked, and 1 false block.** The failure is structural, not a matter of tuning.

1. **The polarity inverts on quote-convention pairs.** `USDTRY +10.94%` is the lira collapsing, but the *pair* is rising, so a naive reader scores it bullish. On an emerging-market currency collapse a text scorer would nudge toward buying.
1. **"Falling knife" is not well defined for a pair.** Every FX pair is long one currency and short another, while the Guardian takes a single `side` for a single `symbol`. The premise the rule rests on does not hold here the way it does for a single asset.
1. **FX panic is written in liquidity and credibility terms**, outside any direction vocabulary: "no bid", "the offer disappeared", "an air pocket", "close only", "spreads from 2 cents to 14", "margin call". A thirteen-post feed of unmistakable panic scored two bearish texts.

Shipping a mirror of the crypto scorer here would have installed a gate that never fires and occasionally points the wrong way — worse than a broken one, because it would look fixed.

### What ships instead

- **The order path is no longer a bypass.** It reads the same sentiment value as the validation tool, and now passes daily loss and drawdown, which it never did — so those two rules apply to real orders for the first time.
- **Nothing fabricates a number.** The cache stores how much text was fetched, never a score.
- **The absence of a measurement is visible.** Every verdict carries a `sentiment` block whose `source` is `unmeasured` or `agent_supplied` — never a measurement by this server — plus a `hint` saying what to do about it.
- **The agent can supply its own reading.** `validate_trade_risk(..., sentiment_score=...)` and every order entry point accept a score on `[-1, +1]`. You are an LLM reading the actual posts, which is a far better judge of them than any word list, and the response records that the judgement was yours.

### The durable fix

Drive the Falling Knife rule from **price and volume**, which this repo already fetches (`fetch_ohlcv`, `intelligence/regime.py` computes ATR). A gap-down-plus-volume-spike test catches the feeds above directly, instead of inferring them from chatter. That is a larger change than repairing a broken scorer, and is deliberately left as follow-up rather than smuggled into this one.

The benchmark corpora used above are simulations, not market data. They are preserved outside the repo so that any future scorer can be compared against the same feeds.
