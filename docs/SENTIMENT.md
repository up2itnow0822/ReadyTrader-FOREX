# Market Intelligence & Sentiment Guide

ReadyTrader-Crypto empowers AI agents with both "Hands" (execution) and "Eyes" (intelligence). This document explains how to configure and use the various sentiment and news feeds available.

## 🌟 Overview of Sentiment Sources

| Source | Level | Cost | Required Credentials | Feature |
| :--- | :--- | :--- | :--- | :--- |
| **RSS Market News** | Basic | Free | None | General market awareness from CoinDesk/Cointelegraph. |
| **Fear & Greed Index** | Basic | Free | None | Overall market sentiment (Alternative.me). |
| **CryptoPanic** | Pro | Free/Paid | API Key | Aggregated hot news across the industry. |
| **X (Twitter)** | Social | Free (Limited) | Bearer Token | Real-time social buzz for specific tokens. |
| **Reddit** | Community | Free | Client ID + Secret | Deep-dives into subreddit discussions. |
| **NewsAPI** | Financial | Free (Trial) | API Key | High-tier financial reporting (Bloomberg, Reuters). |

______________________________________________________________________

## 🛠️ Configuration Instructions

### 1. Free RSS News & Fear/Greed

These work **out-of-the-box** with zero configuration. AI agents will automatically fallback to these if no paid keys are found.

### 2. CryptoPanic (Highly Recommended)

CryptoPanic is the gold standard for aggregated crypto news.

1. Sign up at [CryptoPanic Developers](https://cryptopanic.com/developers/api/).
1. Copy your **API Token**.
1. Add it to your `.env`:
   ```bash
   CRYPTOPANIC_API_KEY=your_token_here
   ```

### 3. X / Twitter (Social Volume)

To see what people are saying about a specific token ($BTC, $SOL):

1. Sign up for a Developer Account at [X Developer Portal](https://developer.x.com/).
1. Create a **Project** and an **App**.
1. Generate an **App-only Bearer Token**.
1. Add it to your `.env`:
   ```bash
   TWITTER_BEARER_TOKEN=your_bearer_token_here
   ```

### 4. Reddit Sentiment

Great for detecting "FOMO" or "FUD" in `/r/cryptocurrency`.

1. Go to [Reddit App Preferences](https://www.reddit.com/prefs/apps).
1. Click "Create another app..." at the bottom.
1. Select **script**. Name it "ReadyTraderAgent".
1. Redirect URI can be `http://localhost:8080`.
1. Save and copy your **Client ID** (under the name) and **Client Secret**.
1. Add them to your `.env`:
   ```bash
   REDDIT_CLIENT_ID=your_client_id
   REDDIT_CLIENT_SECRET=your_client_secret
   ```

### 5. NewsAPI (Institutional News)

For high-signal news from major financial outlets.

1. Get a key at [NewsAPI.org](https://newsapi.org/).
1. Add it to your `.env`:
   ```bash
   NEWSAPI_KEY=your_newsapi_key_here
   ```

______________________________________________________________________

## 🤖 Agent Tool Reference

AI Agents can query these feeds using the following tools:

- `get_free_news(symbol="")`: Aggregates RSS feeds. Best for overall context.
- `get_sentiment()`: Returns the Fear & Greed Index.
- `get_social_sentiment(symbol)`: Queries X and Reddit.
- `get_financial_news(symbol)`: Queries NewsAPI.
- `get_news()`: Queries CryptoPanic.

> [!TIP]
> When multiple keys are missing, the system will provide a **Simulated Score** but also include instructions on which keys are needed. This allows for rapid prototyping without immediate expense.
