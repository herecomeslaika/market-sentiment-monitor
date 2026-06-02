"""Tests for source parsers including RSS."""
from app.crawler.sources import parse_rss, default_sources


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>Fed signals rate cut in September</title>
      <link>https://example.com/fed-rate-cut</link>
      <description>The Federal Reserve hinted at a possible rate cut amid slowing inflation.</description>
      <pubDate>Mon, 02 Jun 2026 14:30:00 GMT</pubDate>
    </item>
    <item>
      <title>Nvidia stock hits all-time high</title>
      <link>https://example.com/nvidia-ath</link>
      <description>Nvidia shares surged after announcing new AI chip lineup.</description>
      <pubDate>Mon, 02 Jun 2026 13:00:00 GMT</pubDate>
    </item>
    <item>
      <title></title>
      <link>https://example.com/empty</link>
      <description>Should be skipped</description>
    </item>
  </channel>
</rss>"""


class TestParseRss:
    def test_parses_valid_rss(self):
        items = parse_rss(SAMPLE_RSS, "TestSource")
        assert len(items) == 2
        assert items[0].title == "Fed signals rate cut in September"
        assert items[0].source == "TestSource"
        assert items[0].url == "https://example.com/fed-rate-cut"
        assert "Federal Reserve" in items[0].content_snippet
        assert items[1].title == "Nvidia stock hits all-time high"

    def test_skips_empty_titles(self):
        items = parse_rss(SAMPLE_RSS, "TestSource")
        assert all(item.title for item in items)

    def test_handles_malformed_xml(self):
        items = parse_rss("not xml at all", "BadSource")
        assert items == []

    def test_published_at_parsed(self):
        items = parse_rss(SAMPLE_RSS, "TestSource")
        assert items[0].published_at is not None
        assert items[0].published_at.year == 2026

    def test_default_sources_includes_overseas(self):
        sources = default_sources()
        assert "cnbc_top" in sources
        assert "cnbc_asia" in sources
        assert "marketwatch" in sources
        assert "yahoo_finance" in sources
        assert "bbc_business" in sources
        assert "investing_crypto" in sources

    def test_overseas_sources_use_rss_parser(self):
        sources = default_sources()
        for key in ("cnbc_top", "cnbc_asia", "marketwatch", "yahoo_finance", "bbc_business", "investing_crypto"):
            assert sources[key].parser == "rss", f"{key} should use rss parser"
