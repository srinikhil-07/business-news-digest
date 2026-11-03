from datetime import datetime, timedelta, timezone
from html import escape
import unittest
from unittest.mock import patch

from scripts.news_digest import (
    PUBLISHER_DOMAINS, RSS_FEEDS, collect, fetch_feed, parse_feed, publish, publisher_url,
)


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
            publisher_url("https://www.wsj.com/a", "wsj.com"),
            "https://www.wsj.com/a",
        )
        for url in (
            "https://wsj.com.evil.test/a", "https://notwsj.com/a", "javascript:alert(1)",
            "https://www.bing.com/news/apiclick.aspx?url=https%3A%2F%2Fwww.wsj.com%2Fa",
        ):
            self.assertIsNone(publisher_url(url, "wsj.com"))

    def test_barrons_google_news_links(self):
        link = "https://news.google.com/rss/articles/article-id?oc=5"
        for source, expected in (
            ('<source url="https://www.barrons.com">Barrons</source>', 1),
            ('<source url="https://barrons.com.evil.test">Barrons</source>', 0),
            ('<source url="https://wsj.com">WSJ</source>', 0),
            ("", 0),
        ):
            with self.subTest(source=source):
                data = feed([("story", link, "Sun, 01 Nov 2026 05:00:00 GMT")])
                data = data.replace(b"</item>", source.encode() + b"</item>")
                articles, rejected = parse_feed(data, "barrons.com", NOW - timedelta(hours=24), NOW)
                self.assertEqual(len(articles), expected)
                self.assertEqual(rejected, 1 - expected)
                if articles:
                    self.assertEqual(articles[0].url, link)
                other_articles, _ = parse_feed(data, "wsj.com", NOW - timedelta(hours=24), NOW)
                self.assertFalse(other_articles)

    def test_dublin_core_dates(self):
        data = (
            b'<rss xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><item>'
            b'<title>story</title><link>https://www.economist.com/business/story</link>'
            b'<dc:date>2026-11-01T05:00:00Z</dc:date></item></channel></rss>'
        )
        articles, rejected = parse_feed(data, "economist.com", NOW - timedelta(hours=24), NOW)
        self.assertEqual(len(articles), 1)
        self.assertEqual(rejected, 0)
        self.assertEqual(articles[0].published, NOW - timedelta(minutes=30))

    @patch("scripts.news_digest.urlopen")
    def test_fetch_uses_configured_feed_urls(self, open_url):
        open_url.return_value.__enter__.return_value.read.return_value = feed([])
        for url in RSS_FEEDS.values():
            fetch_feed(url)
            self.assertEqual(open_url.call_args.args[0].full_url, url)
            self.assertEqual(open_url.call_args.kwargs["timeout"], 40)
        self.assertEqual(len(RSS_FEEDS), 12)
        self.assertEqual(RSS_FEEDS.keys(), PUBLISHER_DOMAINS.keys())

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
        for name in RSS_FEEDS:
            self.assertIn("## " + name, body)
        self.assertIn("2026-11-01 11:00:00", body)
        self.assertEqual([call.args[0] for call in fetch.call_args_list], list(RSS_FEEDS.values()))
        self.assertNotIn("Bing", body)

    @patch("scripts.news_digest.fetch_feed", side_effect=TimeoutError("unavailable"))
    def test_failures_are_visible(self, fetch):
        body, failures = collect(NOW)
        self.assertEqual(len(failures), 12)
        self.assertEqual(body.count("**Collection failed.**"), 12)

    @patch("scripts.news_digest.fetch_feed")
    def test_successful_feeds_survive_partial_failure(self, fetch):
        fetch.side_effect = [
            TimeoutError("unavailable"),
            feed([("economy story", "https://nytimes.com/story", "Sun, 01 Nov 2026 05:00:00 GMT")]),
        ] + [feed([])] * 10
        body, failures = collect(NOW)
        self.assertEqual(len(failures), 1)
        self.assertIn("[economy story](<https://nytimes.com/story>)", body)
        self.assertEqual(body.count("**Collection failed.**"), 1)

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
