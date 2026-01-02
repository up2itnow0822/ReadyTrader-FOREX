import os
import time
from typing import Any, Dict, Optional

import requests

# Optional imports for Real APIs
try:
    import tweepy
except ImportError:
    tweepy = None

try:
    import praw
except ImportError:
    praw = None

try:
    from newsapi import NewsApiClient
except ImportError:
    NewsApiClient = None

try:
    import feedparser
except ImportError:
    feedparser = None


def get_dxy_trend() -> str:
    """
    Fetch US Dollar Index (DXY) trend using yfinance.
    """
    try:
        import yfinance as yf

        ticker = yf.Ticker("DX-Y.NYB")  # Yahoo Finance ticker for DXY
        hist = ticker.history(period="5d")
        if hist.empty:
            return "DXY Trend: Data unavailable."

        last = hist.iloc[-1]["Close"]
        start = hist.iloc[0]["Close"]
        pct = ((last - start) / start) * 100

        direction = "Bullish" if pct > 0 else "Bearish"
        return f"DXY Trend (5d): {direction} ({pct:.2f}%). Last: {last:.2f}"
    except Exception as e:
        return f"DXY Trend: Error fetching data: {str(e)}"


def get_economic_calendar() -> str:
    """
    Fetch High Impact Economic Events from ForexFactory RSS.
    """
    if not feedparser:
        return "Economic Calendar: feedparser not installed. Using mock: No High Impact events scheduled."

    url = "https://www.forexfactory.com/ff_calendar_thisweek.xml"
    try:
        feed = feedparser.parse(url)
        events = []
        for entry in feed.entries[:8]:
            impact = getattr(entry, "impact", "Low")
            if impact.lower() in ["high", "critical"]:
                events.append(f"{entry.title} ({entry.get('country', 'N/A')}) - {impact} Impact")

        if not events:
            return "Economic Calendar: No High Impact events scheduled for today (via ForexFactory)."
        return "High Impact Economic Events:\n" + "\n".join(events)
    except Exception as e:
        return f"Economic Calendar Error: {str(e)}"


def get_market_sentiment() -> str:
    """
    Aggregated Forex Sentiment.
    Combines DXY Trend and simulated Calendar.
    """
    dxy = get_dxy_trend()
    cal = get_economic_calendar()
    return f"Forex Sentiment:\n{dxy}\n{cal}"


def get_volatility_status(symbol: str) -> float:
    """
    Calculate volatility multiplier (Current ATR / Avg ATR).
    Returns 1.0 if normal, > 3.0 if extreme.
    """
    # For now, we return 1.0 (Normal) unless mocked.
    # In production, this would calculate TA.
    return 1.0


def get_news_status() -> bool:
    """
    Check if we are in a High Impact news window.
    """
    # For now, False unless mocked
    return False


def get_market_news() -> str:
    """
    Fetch aggregated equity market news using Alpha Vantage.
    """
    api_key = os.getenv("ALPHAVANTAGE_API_KEY")
    if not api_key:
        return "Market News: ALPHAVANTAGE_API_KEY missing. News unavailable."

    try:
        # Alpha Vantage News Sentiment endpoint
        url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&apikey={api_key}"
        response = requests.get(url, timeout=10)
        data = response.json()

        if "feed" in data:
            headlines = [f"{i + 1}. {p['title']} ({p['source']})" for i, p in enumerate(data["feed"][:5])]
            return "Alpha Vantage news:\n" + "\n".join(headlines)
        return "Error: No news found via Alpha Vantage."
    except Exception as e:
        return f"Error fetching news: {str(e)}"


def fetch_rss_news(symbol: str = "") -> str:
    """
    Fetch free market news from RSS feeds.
    """
    if not feedparser:
        return "Error: feedparser library not installed. Cannot fetch RSS news."

    feeds = [("MarketWatch", "https://www.marketwatch.com/rss/marketupdate"), ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex")]

    all_headlines = []

    for name, url in feeds:
        try:
            feed = feedparser.parse(url)
            # Take top 3 from each
            count = 0
            for entry in feed.entries:
                if count >= 3:
                    break
                # If symbol is provided, check if it's in the title/summary (case-insensitive)
                if symbol and symbol.lower() not in entry.title.lower() and symbol.lower() not in (getattr(entry, "summary", "")).lower():
                    continue

                all_headlines.append(f"{entry.title} ({name})")
                count += 1
        except Exception as e:
            all_headlines.append(f"Error fetching {name} feed: {str(e)}")

    if not all_headlines:
        return f"No RSS news found matching '{symbol}' or feeds unavailable."

    return "Market News (Free RSS):\n" + "\n".join([f"{i + 1}. {h}" for i, h in enumerate(all_headlines[:6])])


# Curated Forex-specific RSS feeds (all free, no API key required)
FOREX_RSS_FEEDS = [
    ("Investing.com Forex", "https://www.investing.com/rss/news_14.rss"),
    ("FXStreet News", "https://www.fxstreet.com/rss/news"),
    ("DailyFX", "https://www.dailyfx.com/feeds/market-news"),
    ("ForexLive", "https://www.forexlive.com/feed/news"),
    ("Reuters Forex", "https://www.reutersagency.com/feed/?best-topics=forex"),
]


def get_forex_news(limit: int = 10) -> str:
    """
    Fetch aggregated Forex news from multiple free RSS sources.
    Returns headlines from Investing.com, FXStreet, DailyFX, ForexLive, and Reuters.
    """
    if not feedparser:
        return "Error: feedparser library not installed. Cannot fetch Forex news."

    all_headlines = []
    source_status = []

    for name, url in FOREX_RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            count = 0
            for entry in feed.entries:
                if count >= 2:  # Take 2 from each source for variety
                    break
                title = entry.title.strip()
                # Skip if title is too short or looks like an error
                if len(title) < 10:
                    continue
                all_headlines.append({"title": title, "source": name, "link": entry.get("link", ""), "published": entry.get("published", "")})
                count += 1
            source_status.append(f"✓ {name}")
        except Exception as e:
            source_status.append(f"✗ {name}: {str(e)[:30]}")

    if not all_headlines:
        return f"No Forex news available. Source status: {', '.join(source_status)}"

    # Format output
    output_lines = ["📰 Forex News (Free Feeds):"]
    output_lines.append(f"Sources: {', '.join(source_status)}\n")

    for i, h in enumerate(all_headlines[:limit]):
        output_lines.append(f"{i + 1}. {h['title']} ({h['source']})")

    return "\n".join(output_lines)


def get_forex_market_brief(symbol: str = "EURUSD") -> str:
    """
    One-call comprehensive Forex market overview.
    Combines: price, DXY trend, economic calendar, and recent news.
    """
    from marketdata.exchange_provider import ExchangeProvider

    sections = []

    # 1. Current Price
    try:
        provider = ExchangeProvider()
        ticker = provider.fetch_ticker(symbol)
        price = ticker.get("last", "N/A")
        bid = ticker.get("bid", "N/A")
        ask = ticker.get("ask", "N/A")
        sections.append(f"📊 {symbol}: {price:.5f} (Bid: {bid:.5f}, Ask: {ask:.5f})")
    except Exception as e:
        sections.append(f"📊 {symbol}: Price unavailable ({str(e)[:30]})")

    # 2. DXY Trend
    dxy = get_dxy_trend()
    sections.append(f"\n💵 {dxy}")

    # 3. Economic Calendar
    cal = get_economic_calendar()
    sections.append(f"\n📅 {cal}")

    # 4. Recent News (condensed)
    news = get_forex_news(limit=5)
    sections.append(f"\n{news}")

    return "\n".join(sections)


class SentimentCache:
    def __init__(self, ttl: int = 3600):
        self.cache = {}
        self.ttl = ttl

    def get(self, symbol: str) -> Optional[Dict[str, Any]]:
        if symbol in self.cache:
            entry = self.cache[symbol]
            if time.time() - entry["time"] < self.ttl:
                return entry
        return None

    def set(self, symbol: str, score: float, rationales: list[str]):
        self.cache[symbol] = {
            "time": time.time(),
            "score": round(score, 2),
            "rationales": rationales,
            "explainability_string": f"AI Sentiment of {round(score, 2)} based on: {'; '.join(rationales)}",
        }


_sentiment_cache = SentimentCache()


def get_cached_sentiment_score(symbol: str) -> float:
    """Return cached sentiment score or 0.0 if missing."""
    entry = _sentiment_cache.get(symbol)
    if entry:
        return entry["score"]
    return 0.0


def analyze_social_sentiment(symbol: str) -> str:
    """
    Analyze social sentiment using Tweepy (X) or PRAW (Reddit) if configured.
    """
    # Check cache first (optional, but good for speed)
    # But usually this tool is called explicitly to Refresh.
    # Let's refresh every time this tool is CALLED, but get_cached_sentiment_score uses what's there.

    score = 0.0
    rationales = []

    # 1. Twitter / X Analysis
    twitter_bearer = os.getenv("TWITTER_BEARER_TOKEN")
    twitter_result = "Twitter: Not Configured."

    if twitter_bearer and tweepy:
        try:
            client = tweepy.Client(bearer_token=twitter_bearer)
            # Simple search for recent tweets (read-only)
            query = f"{symbol} -is:retweet lang:en"
            tweets = client.search_recent_tweets(query=query, max_results=10)
            if tweets.data:
                texts = [t.text for t in tweets.data]
                preview = " | ".join([t[:50] + "..." for t in texts[:2]])
                twitter_result = f"Twitter: Found {len(texts)} recent tweets. Preview: {preview}"
                rationales.append(f"Twitter volume alert for {symbol}")
                score += 0.2
            else:
                twitter_result = "Twitter: No recent tweets found."
        except Exception as e:
            twitter_result = f"Twitter Error: {str(e)}"

    # 2. Reddit Analysis
    reddit_id = os.getenv("REDDIT_CLIENT_ID")
    reddit_secret = os.getenv("REDDIT_CLIENT_SECRET")
    reddit_result = "Reddit: Not Configured."

    if reddit_id and reddit_secret and praw:
        try:
            reddit = praw.Reddit(client_id=reddit_id, client_secret=reddit_secret, user_agent="readytrader_forex/1.0")
            # Search r/forex or r/wallstreetbets
            subreddit = reddit.subreddit("forex+wallstreetbets")
            posts = subreddit.search(symbol, limit=5, time_filter="day")
            titles = [p.title for p in posts]
            if titles:
                preview = " | ".join(titles[:2])
                reddit_result = f"Reddit: Found {len(titles)} posts. Preview: {preview}"
                rationales.append("Reddit active discussion in r/forex")
                score += 0.2
            else:
                reddit_result = "Reddit: No recent posts found."
        except Exception as e:
            reddit_result = f"Reddit Error: {str(e)}"

    # Combine
    final_output = f"{twitter_result}\n{reddit_result}"

    if "Not Configured" in twitter_result and "Not Configured" in reddit_result:
        return "Social Sentiment: No providers configured (Twitter/Reddit API keys missing). (Zero-Mock Policy)."

    # Update Cache
    _sentiment_cache.set(symbol, score, rationales)

    return final_output


def fetch_financial_news(symbol: str) -> str:
    """
    Fetch financial news using NewsAPI.
    """
    api_key = os.getenv("NEWSAPI_KEY")
    if not api_key or not NewsApiClient:
        return "Financial News: NEWSAPI_KEY missing or NewsApiClient not installed. (Zero-Mock Policy)."

    try:
        newsapi = NewsApiClient(api_key=api_key)
        # Search for symbol + forex or finance
        articles = newsapi.get_everything(q=f"{symbol} stock", language="en", sort_by="relevancy", page_size=3)

        if articles["status"] == "ok" and articles["articles"]:
            headlines = [f"{i + 1}. {a['title']} ({a['source']['name']})" for i, a in enumerate(articles["articles"])]
            return "Financial Headlines (NewsAPI):\n" + "\n".join(headlines)
        return "NewsAPI: No articles found."
    except Exception as e:
        return f"NewsAPI Error: {str(e)}"


def fetch_custom_feed(url: str, keyword: Optional[str] = None) -> str:
    """
    Fetch headlines from a user-provided RSS or Atom feed.
    """
    if not feedparser:
        return "Error: feedparser not installed."

    try:
        feed = feedparser.parse(url)
        headlines = []
        for entry in feed.entries[:10]:
            if keyword and keyword.lower() not in entry.title.lower():
                continue
            headlines.append(f"{entry.title} ({feed.feed.title if 'title' in feed.feed else 'RSS'})")

        if not headlines:
            return f"No headlines found in feed: {url}"
        return f"Custom Feed ({url}):\n" + "\n".join(headlines)
    except Exception as e:
        return f"Error fetching custom feed: {str(e)}"
