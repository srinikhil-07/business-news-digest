"""Collect public news-index links and publish a daily GitHub issue."""

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import json
import os
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo


PUBLICATIONS = (
    ("Barron's", "barrons.com"),
    ("MarketWatch", "marketwatch.com"),
    ("Investor's Business Daily", "investors.com"),
    ("The Wall Street Journal", "wsj.com"),
)
IST = ZoneInfo("Asia/Kolkata")
MAX_BODY_BYTES = 60_000


@dataclass(frozen=True)
class Article:
    title: str
    url: str
    published: datetime


def publisher_url(link, domain):
    """Unwrap Bing's tracking URL without requesting subscription pages."""
    parsed = urlsplit(link)
    if parsed.hostname in ("bing.com", "www.bing.com"):
        values = parse_qs(parsed.query)
        link = values.get("url", [""])[0]
        parsed = urlsplit(link)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https"):
        return None
    if host != domain and not host.endswith("." + domain):
        return None
    return link


def parse_feed(data, domain, start, end):
    root = ET.fromstring(data)
    if root.tag != "rss" or root.find("channel") is None:
        raise ValueError("Response is not a news RSS feed")
    articles = {}
    rejected = 0
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        date = item.findtext("pubDate")
        url = publisher_url(link, domain)
        try:
            published = parsedate_to_datetime(date) if date else None
        except (TypeError, ValueError, OverflowError):
            published = None
        if not title or not url or published is None or published.tzinfo is None:
            rejected += 1
            continue
        published = published.astimezone(timezone.utc)
        if start <= published <= end:
            key = urlsplit(url)._replace(query="", fragment="").geturl()
            article = Article(title, url, published)
            if key not in articles or published > articles[key].published:
                articles[key] = article
    return sorted(articles.values(), key=lambda a: a.published, reverse=True), rejected


def fetch_feed(domain):
    query = urlencode({
        "q": f"site:{domain}",
        "qft": 'interval="9"',
        "format": "rss",
        "sortby": "date",
        "setlang": "en-US",
    })
    request = Request(
        "https://www.bing.com/news/search?" + query,
        headers={"User-Agent": "BusinessNewsDigest/1.0", "Accept": "application/rss+xml"},
    )
    for attempt in range(3):
        try:
            with urlopen(request, timeout=40) as response:
                return response.read(5_000_001)
        except (HTTPError, URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def markdown_text(text):
    text = " ".join(text.split())
    for char in ("\\", "[", "]", "*", "_", "`", "<", ">"):
        text = text.replace(char, "\\" + char)
    return text


def collect(now):
    start = now - timedelta(hours=24)
    lines = [
        "# Business news links",
        "",
        f"Window: **{start.astimezone(IST):%Y-%m-%d %H:%M:%S}** to "
        f"**{now.astimezone(IST):%Y-%m-%d %H:%M:%S} IST** (preceding 24 hours).",
        "",
        "Public Bing News index results only; coverage is not exhaustive. "
        "Times are index-provided publication timestamps, which can reflect updates. "
        "No subscription pages or credentials are accessed.",
    ]
    failures = []
    for name, domain in PUBLICATIONS:
        lines.extend(["", f"## {name}", ""])
        try:
            data = fetch_feed(domain)
            if len(data) > 5_000_000:
                raise ValueError("Feed exceeds the 5 MB response limit")
            articles, rejected = parse_feed(data, domain, start, now)
        except (HTTPError, URLError, TimeoutError, ET.ParseError, ValueError) as error:
            message = f"{name}: {type(error).__name__}: {error}"
            failures.append(message)
            print(message, file=sys.stderr)
            lines.append("**Collection failed.** " + markdown_text(str(error)))
            continue
        if not articles:
            lines.append("No verified links found in this window. This does not prove no articles were published.")
        for article in articles:
            url = article.url.replace("<", "%3C").replace(">", "%3E")
            lines.append(
                f"- [{markdown_text(article.title)}](<{url}>) "
                f"— {article.published.astimezone(IST):%d %b, %H:%M} IST"
            )
        if rejected:
            lines.extend(["", f"Excluded {rejected} entries with missing/invalid dates or non-publisher URLs."])
    lines.extend([
        "",
        "---",
        "Generated automatically. Open the publisher links using your own subscriptions.",
    ])
    body = "\n".join(lines) + "\n"
    if len(body.encode()) > MAX_BODY_BYTES:
        raise ValueError("Digest exceeds issue body budget; refusing to silently truncate links")
    return body, failures


def gh_api(endpoint, method="GET", payload=None, paginate=False):
    command = ["gh", "api", endpoint, "--method", method]
    if paginate:
        command.extend(["--paginate", "--slurp"])
    if payload is not None:
        command.extend(["--input", "-"])
    result = subprocess.run(
        command,
        input=json.dumps(payload) if payload is not None else None,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def publish(repo, title, body):
    pages = gh_api(f"repos/{repo}/issues?state=all&per_page=100", paginate=True)
    existing = next(
        (issue for page in pages for issue in page
         if "pull_request" not in issue and issue["title"] == title),
        None,
    )
    if existing:
        issue = gh_api(
            f"repos/{repo}/issues/{existing['number']}", "PATCH", {"body": body}
        )
    else:
        issue = gh_api(f"repos/{repo}/issues", "POST", {"title": title, "body": body})
    print(issue["html_url"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    body, failures = collect(now)
    if args.publish:
        repo = os.environ["GITHUB_REPOSITORY"]
        publish(repo, f"Business news — {now.astimezone(IST):%Y-%m-%d} (IST)", body)
    else:
        print(body)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
