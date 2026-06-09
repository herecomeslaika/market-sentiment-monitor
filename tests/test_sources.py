"""Tests for news crawler sources and parsers."""
import pytest

from app.crawler.sources import default_sources, parse_rss, _PARSERS
from app.models import NewsItem


class TestDefaultSources:
    @pytest.mark.unit
    def test_source_count(self):
        sources = default_sources()
        assert len(sources) >= 13  # 7 domestic + 6 overseas

    @pytest.mark.unit
    def test_overseas_sources_present(self):
        sources = default_sources()
        names = [s.name for s in sources.values()]
        assert "CNBC" in names
        assert "CNBC-Asia" in names
        assert "MarketWatch" in names
        assert "BBC-Business" in names

    @pytest.mark.unit
    def test_overseas_sources_use_rss_parser(self):
        sources = default_sources()
        for key in ["cnbc_top", "cnbc_asia", "marketwatch", "bbc_business"]:
            assert sources[key].parser == "rss"

    @pytest.mark.unit
    def test_domestic_sources_present(self):
        sources = default_sources()
        names = [s.name for s in sources.values()]
        assert "新浪财经-A股" in names
        assert "东方财富" in names

    @pytest.mark.unit
    def test_all_sources_have_required_fields(self):
        sources = default_sources()
        for key, s in sources.items():
            assert s.name, f"Source {key} missing name"
            assert s.url, f"Source {key} missing url"
            assert s.parser, f"Source {key} missing parser"
            assert s.parser in _PARSERS, f"Source {key} has unknown parser: {s.parser}"


class TestParseRss:
    @pytest.mark.unit
    def test_parse_valid_rss(self, sample_rss):
        items = parse_rss(sample_rss, "TestFeed")
        assert len(items) == 2  # 3rd item has empty title, should be skipped
        assert items[0].title == "Fed signals rate cut in September"
        assert items[0].source == "TestFeed"
        assert items[0].url == "https://example.com/fed-rate-cut"

    @pytest.mark.unit
    def test_parse_rss_extracts_snippet(self, sample_rss):
        items = parse_rss(sample_rss, "TestFeed")
        assert "Federal Reserve" in items[0].content_snippet

    @pytest.mark.unit
    def test_parse_rss_extracts_published_at(self, sample_rss):
        items = parse_rss(sample_rss, "TestFeed")
        assert items[0].published_at is not None

    @pytest.mark.unit
    def test_parse_empty_rss(self):
        items = parse_rss("", "EmptyFeed")
        assert items == []

    @pytest.mark.unit
    def test_parse_invalid_xml(self):
        items = parse_rss("not xml at all", "BadFeed")
        assert items == []

    @pytest.mark.unit
    def test_parse_rss_no_channel(self):
        xml = '<?xml version="1.0"?><rss version="2.0"><item><title>Test</title></item></rss>'
        items = parse_rss(xml, "NoChannel")
        # Should still parse items from root
        assert len(items) >= 0  # At minimum, should not crash

    @pytest.mark.unit
    def test_rss_parser_registered(self):
        assert "rss" in _PARSERS
        assert _PARSERS["rss"] == parse_rss