from datetime import datetime, timedelta, timezone
from html import escape
import unittest
from unittest.mock import patch

from scripts.news_digest import Article, collect, parse_feed, publish, publisher_url


NOW = datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc)


def feed(items):
    return ("<rss><channel>" + "".join(
        f"<item><title>{escape(title)}</title><link>{escape(url)}</link>"
        f"<pubDate>{escape(date)}</pubDate></item>"
        for title, url, date in items
    ) + "</channel></rss>").encode()


class DigestTests(unittest.TestCase):
    def test_publisher_links(self):
        self.assertEqual(
            publisher_url("https://www.bing.com/news/apiclick.aspx?url=https%3A%2F%2Fwww.wsj.com%2Fa", "wsj.com"),
            "https://www.wsj.com/a",
        )
        for url in ("https://wsj.com.evil.test/a", "https://notwsj.com/a", "javascript:alert(1)"):
            self.assertIsNone(publisher_url(url, "wsj.com"))

    def test_exact_window_and_invalid_entries(self):
        data = feed([
            ("boundary", "https://wsj.com/boundary", "Sat, 31 Oct 2026 05:30:00 GMT"),
            ("too old", "https://wsj.com/old", "Sat, 31 Oct 2026 05:29:59 GMT"),
            ("now", "https://wsj.com/now", "Sun, 01 Nov 2026 05:30:00 GMT"),
            ("future", "https://wsj.com/future", "Sun, 01 Nov 2026 05:30:01 GMT"),
            ("invalid", "https://wsj.com/invalid", "bad date"),
            ("wrong site", "https://example.com/a", "Sun, 01 Nov 2026 05:00:00 GMT"),
            ("no timezone", "https://wsj.com/nozone", "Sun, 01 Nov 2026 05:00:00"),
        ])
        articles, rejected = parse_feed(data, "wsj.com", NOW - timedelta(hours=24), NOW)
        self.assertEqual([a.title for a in articles], ["now", "boundary"])
        self.assertEqual(rejected, 3)

    def test_deduplication(self):
        data = feed([
            ("old", "https://wsj.com/a?tracking=1", "Sun, 01 Nov 2026 04:00:00 GMT"),
            ("new", "https://wsj.com/a?tracking=2", "Sun, 01 Nov 2026 05:00:00 GMT"),
        ])
        articles, _ = parse_feed(data, "wsj.com", NOW - timedelta(hours=24), NOW)
        self.assertEqual([a.title for a in articles], ["new"])

    def test_html_is_not_empty_success(self):
        with self.assertRaises(ValueError):
            parse_feed(b"<html>blocked</html>", "wsj.com", NOW - timedelta(hours=24), NOW)

    @patch("scripts.news_digest.fetch_feed", return_value=feed([]))
    def test_publication_sections_and_ist(self, fetch):
        body, failures = collect(NOW)
        self.assertFalse(failures)
        for name in ("Barron's", "MarketWatch", "Investor's Business Daily", "The Wall Street Journal"):
            self.assertIn("## " + name, body)
        self.assertIn("2026-11-01 11:00:00", body)
        self.assertEqual(fetch.call_count, 4)

    @patch("scripts.news_digest.fetch_feed", side_effect=TimeoutError("unavailable"))
    def test_failures_are_visible(self, fetch):
        body, failures = collect(NOW)
        self.assertEqual(len(failures), 4)
        self.assertEqual(body.count("**Collection failed.**"), 4)

    @patch("scripts.news_digest.gh_api")
    def test_rerun_updates_daily_issue(self, api):
        api.side_effect = [
            [[{"title": "daily", "number": 7}]],
            {"html_url": "https://github.com/o/r/issues/7"},
        ]
        publish("o/r", "daily", "body")
        self.assertEqual(api.call_args.args, ("repos/o/r/issues/7", "PATCH", {"body": "body"}))

    @patch("scripts.news_digest.gh_api")
    def test_new_daily_issue(self, api):
        api.side_effect = [[[]], {"html_url": "https://github.com/o/r/issues/1"}]
        publish("o/r", "daily", "body")
        self.assertEqual(api.call_args.args, ("repos/o/r/issues", "POST", {"title": "daily", "body": "body"}))


if __name__ == "__main__":
    unittest.main()
