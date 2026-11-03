# business-news-digest

Daily links from **The New York Times, The Wall Street Journal, MarketWatch,
Barron's, Investor's Business Daily, Financial Times, and The Economist**,
grouped by RSS feed in a GitHub issue.

## Schedule and delivery

GitHub Actions runs daily at **11:00 AM IST** (`30 5 * * *`, 05:30 UTC).
GitHub scheduled jobs are best-effort and can be delayed or skipped under load.
Each run uses the preceding 24 hours relative to its actual start time.
An issue is created for the current IST date; rerunning that day updates the same issue
with the newly collected window instead of creating duplicates.
Earlier issues are retained. Watch this repository's issues to receive notifications.

To run immediately, select **Actions > Daily business news > Run workflow**.

## Sources and limitations

The collector fetches these public RSS feeds, then strictly filters timezone-aware
publication timestamps to the last 24 hours:

| Feed | URL |
|------|-----|
| NYT Business | https://rss.nytimes.com/services/xml/rss/nyt/Business.xml |
| NYT Economy | https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml |
| NYT Your Money | https://rss.nytimes.com/services/xml/rss/nyt/YourMoney.xml |
| WSJ Markets | https://feeds.content.dowjones.io/public/rss/RSSMarketsMain |
| MarketWatch | https://feeds.marketwatch.com/marketwatch/topstories |
| Barrons | https://news.google.com/rss/search?q=when:24h+site:barrons.com&hl=en-US&gl=US&ceid=US:en |
| IBD | https://www.investors.com/feed/ |
| FT Markets | https://www.ft.com/markets?format=rss |
| FT Global Economy | https://www.ft.com/global-economy?format=rss |
| Economist Finance & Economics | https://www.economist.com/finance-and-economics/rss.xml |
| Economist Business | https://www.economist.com/business/rss.xml |
| Economist US | https://www.economist.com/united-states/rss.xml |

Direct links must be on the specified publisher's domain. Barron's Google News RSS
redirect links are also accepted when the entry's source URL identifies barrons.com;
they are kept as Google News links rather than fetching subscription pages to resolve
them. Duplicate article URLs are collapsed within each feed.

Only titles, links, and publication times are collected. There is no article scraping,
paywall bypass, subscription login, paid API, or external secret to configure.
Open links with your own subscriptions.

**This is an RSS digest, not a complete publisher archive.** Feeds and Google News
can omit or delay articles, cap result sets, or report updated rather than original
publication times. Invalid titles, dates, and source links are excluded and counted.
An empty section means no verified feed links were found, not that the publisher
published nothing.

Feed errors appear in the issue and cause the workflow to fail, while successful
feeds still appear. A malformed/blocked response is not treated as an empty feed.
Issue-write errors also fail the workflow. No links are silently truncated if the
issue body becomes too large.

## Development

Python 3.12 and the GitHub CLI are used; there are no third-party Python dependencies.

```sh
python -m unittest discover -s tests -v
python scripts/news_digest.py
# Publish using a token with issue-write permission:
GH_TOKEN=... GITHUB_REPOSITORY=owner/repo python scripts/news_digest.py --publish
```

The workflow grants only repository-content read and issue-write permissions.
