# business-news-digest

Daily links from **Barron's, MarketWatch, Investor's Business Daily, and The Wall Street Journal**, grouped by publication in a GitHub issue.

## Schedule and delivery

GitHub Actions runs daily at **11:00 AM IST** (`30 5 * * *`, 05:30 UTC).
GitHub scheduled jobs are best-effort and can be delayed or skipped under load.
Each run uses the preceding 24 hours relative to its actual start time.
An issue is created for the current IST date; rerunning that day updates the same issue
with the newly collected window instead of creating duplicates.
Earlier issues are retained. Watch this repository's issues to receive notifications.

To run immediately, select **Actions > Daily business news > Run workflow**.

## Sources and limitations

The collector queries public Bing News RSS search results separately for each publisher,
requests the past day's results, and then strictly filters timezone-aware publication
timestamps to the last 24 hours. It unwraps index tracking links and accepts only URLs
on the specified publisher's domain. Duplicate article URLs are collapsed.

Only titles, links, and publication times are collected. There is no article scraping,
paywall bypass, subscription login, paid API, or external secret to configure.
Open links with your own subscriptions.

**This is an indexed-news digest, not a complete publisher archive.** Search indexes
can omit or delay articles, cap result sets, or report updated rather than original
publication times. Invalid dates and non-publisher links are excluded and counted.
An empty section means no verified indexed links were found, not that the publisher
published nothing.

Feed errors appear in the issue and cause the workflow to fail, while successful
publications still appear. A malformed/blocked response is not treated as an empty feed.
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
