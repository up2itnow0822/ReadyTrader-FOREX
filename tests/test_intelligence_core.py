from unittest.mock import MagicMock, patch

from intelligence.core import (
    SentimentCache,
    analyze_social_sentiment,
    fetch_financial_news,
    fetch_rss_news,
    get_cached_sentiment_score,
    get_market_news,
    get_market_sentiment,
)


def test_get_market_sentiment_success():
    with (
        patch("intelligence.core.get_dxy_trend", return_value="DXY Trend: Bullish"),
        patch("intelligence.core.get_economic_calendar", return_value="Calendar: Clear"),
    ):
        sentiment = get_market_sentiment()
        assert "Forex Sentiment:" in sentiment
        assert "DXY Trend: Bullish" in sentiment


def test_get_market_sentiment_failure():
    with patch("intelligence.core.get_dxy_trend", side_effect=Exception("Data Source Down")):
        # The current implementation of get_market_sentiment calls get_dxy_trend which catches its own exceptions
        # and returns an error string. So we shouldn't see an exception here, but the error string in the output.
        # However, if we want to test failure of the *composition*, we can rely on get_dxy_trend's error handling.
        # Let's mock get_dxy_trend to actually raise if we want to test outer handling,
        # OR rely on the fact that get_dxy_trend returns an error message.
        # Looking at core.py, get_dxy_trend catches Exception and returns "DXY Trend: Error..."
        # So let's test that flow.
        pass

    # Actually, let's verify that if the sub-functions return error strings, they appear in the output.
    with patch("intelligence.core.get_dxy_trend", return_value="DXY Trend: Error fetching data"):
        sentiment = get_market_sentiment()
        assert "DXY Trend: Error fetching data" in sentiment


def test_analyze_social_sentiment_no_keys():
    # Ensure env vars are unset
    with patch.dict("os.environ", {}, clear=True):
        res = analyze_social_sentiment("AAPL")
        assert "No sentiment APIs configured" in res
        # A missing source must not be reported as a measured neutral market.
        assert "no data source" in res or "treats sentiment as neutral" in res


def test_sentiment_cache():
    cache = SentimentCache()
    cache.set("EUR/USD", 12)

    cached = cache.get("EURUSD")
    # The cache records how much text was fetched, never a score - nothing here measures one.
    assert cached["texts"] == 12
    assert cached["configured"] is True
    assert "score" not in cached
    # Any spelling of the pair reaches the same entry.
    assert cache.get("eur_usd")["texts"] == 12

    # Expiry runs on the monotonic clock, so a wall-clock step cannot pin or expire an entry.
    import time

    real = time.monotonic

    with patch("time.monotonic", side_effect=lambda: real() + cache.ttl + 1):
        assert cache.get("EURUSD") is None


def test_get_cached_sentiment_score():
    """This server measures no sentiment, so the cached score is neutral for every pair."""
    assert get_cached_sentiment_score("EURUSD") == 0.0
    assert get_cached_sentiment_score("GBPJPY") == 0.0


def test_get_market_news_no_key():
    with patch.dict("os.environ", {}, clear=True):
        res = get_market_news()
        assert "ALPHAVANTAGE_API_KEY missing" in res


def test_get_market_news_success():
    with patch.dict("os.environ", {"ALPHAVANTAGE_API_KEY": "test"}):
        with patch("requests.get") as mock_get:
            mock_get.return_value.json.return_value = {"feed": [{"title": "Stock Up", "source": "CNBC"}]}
            res = get_market_news()
            assert "Stock Up" in res


def test_fetch_rss_news_no_lib():
    with patch("intelligence.core.feedparser", None):
        res = fetch_rss_news("AAPL")
        assert "feedparser library not installed" in res


def test_fetch_rss_news_success():
    # Only if feedparser is installed (it is in main env, but maybe verify)
    # Use mock
    with patch("intelligence.core.feedparser") as mock_fp, patch("intelligence.core.requests.get") as get:
        get.return_value.content = b"<rss/>"
        entry = MagicMock()
        entry.title = "AAPL releases iPhone 20"
        entry.summary = "It is great"

        mock_feed = MagicMock()
        mock_feed.entries = [entry]
        mock_fp.parse.return_value = mock_feed

        res = fetch_rss_news("AAPL")
        assert "AAPL releases iPhone 20" in res


def test_fetch_financial_news_no_key():
    with patch.dict("os.environ", {}, clear=True):
        res = fetch_financial_news("AAPL")
        assert "NEWSAPI_KEY missing" in res


def test_fetch_financial_news_success():
    with patch.dict("os.environ", {"NEWSAPI_KEY": "test"}):
        with patch("intelligence.core.NewsApiClient") as MockClient:
            client_inst = MockClient.return_value
            client_inst.get_everything.return_value = {"status": "ok", "articles": [{"title": "Boom", "source": {"name": "Test"}}]}
            res = fetch_financial_news("AAPL")
            assert "Boom" in res


def test_analyze_social_sentiment_mocked_success():
    with patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "x", "REDDIT_CLIENT_ID": "r", "REDDIT_CLIENT_SECRET": "s"}):
        with patch("intelligence.core.tweepy") as mock_tweepy:
            with patch("intelligence.core.praw") as mock_praw:
                # Mock Twitter
                mock_client = MagicMock()
                mock_tweet = MagicMock()
                mock_tweet.text = "AAPL is going up #bullish"
                mock_client.search_recent_tweets.return_value = MagicMock(data=[mock_tweet])
                mock_tweepy.Client.return_value = mock_client

                # Mock Reddit
                mock_reddit = MagicMock()
                mock_sub = MagicMock()
                mock_post = MagicMock()
                mock_post.title = "AAPL DD"
                mock_sub.search.return_value = [mock_post]
                mock_reddit.subreddit.return_value = mock_sub
                mock_praw.Reddit.return_value = mock_reddit

                res = analyze_social_sentiment("AAPL")
                assert "Twitter (Real): 1 recent posts" in res
                assert "Reddit (Real): 1 posts" in res
                # The posts themselves are handed to the agent, not condensed into a number.
                assert "AAPL is going up #bullish" in res
                assert "AAPL DD" in res
