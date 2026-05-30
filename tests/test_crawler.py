"""Tests for the crawler module."""
import json

import pytest

from app.crawler.sources import (
    compute_title_hash, parse_sina, parse_cls, parse_eastmoney, parse_jin10, parse_kr36, _clean_html,
    SourceConfig, SourceHealth, default_sources, get_source_health, _PARSERS,
)
from app.crawler.dedup import check_and_register
from app import deps
from config.settings import Settings
from collections import OrderedDict


class TestComputeTitleHash:
    def test_same_title_same_hash(self):
        assert compute_title_hash("test") == compute_title_hash("test")

    def test_different_title_different_hash(self):
        assert compute_title_hash("hello") != compute_title_hash("world")

    def test_whitespace_trimmed(self):
        assert compute_title_hash("  hello  ") == compute_title_hash("hello")


class TestCleanHtml:
    def test_strips_tags(self):
        assert _clean_html("<p>Hello <b>world</b></p>") == "Hello world"

    def test_collapses_whitespace(self):
        assert _clean_html("a   b") == "a b"

    def test_truncates(self):
        assert len(_clean_html("x" * 1000)) == 500


class TestParseSina:
    def test_parse_valid(self):
        data = json.dumps({
            "result": {
                "data": [
                    {"title": "测试标题", "url": "https://example.com", "intro": "摘要"},
                    {"title": "标题2", "url": "https://example.com/2", "intro": ""},
                ]
            }
        })
        items = parse_sina(data, "新浪财经-A股")
        assert len(items) == 2
        assert items[0].title == "测试标题"
        assert items[0].source == "新浪财经-A股"

    def test_parse_empty(self):
        items = parse_sina("{}", "新浪财经")
        assert items == []

    def test_parse_no_title_skipped(self):
        data = json.dumps({"result": {"data": [{"title": "", "url": ""}]}})
        items = parse_sina(data, "新浪财经")
        assert items == []


class TestParseCls:
    def test_parse_roll_data(self):
        data = json.dumps({
            "data": {
                "roll_data": [
                    {"title": "财联社新闻", "content": "内容", "id": "123"},
                ]
            }
        })
        items = parse_cls(data, "财联社")
        assert len(items) == 1
        assert items[0].source == "财联社"

    def test_parse_direct_list(self):
        data = json.dumps({"data": [{"title": "直接列表", "content": "c", "id": "1"}]})
        items = parse_cls(data, "财联社")
        assert len(items) == 1

    def test_content_as_title_fallback(self):
        data = json.dumps({"data": {"roll_data": [{"content": "这是一条没有标题的新闻", "id": "99"}]}})
        items = parse_cls(data, "财联社")
        assert len(items) == 1
        assert items[0].title.startswith("这是一条")


class TestParseEastMoney:
    def test_parse_valid(self):
        data = json.dumps({
            "data": {
                "list": [
                    {"title": "东方财富新闻", "url": "https://example.com", "digest": "摘要"},
                ]
            }
        })
        items = parse_eastmoney(data, "东方财富")
        assert len(items) == 1
        assert items[0].source == "东方财富"

    def test_parse_empty_list(self):
        data = json.dumps({"data": {"list": []}})
        items = parse_eastmoney(data, "东方财富")
        assert items == []

    def test_parse_null_data(self):
        items = parse_eastmoney('{"data": null}', "东方财富")
        assert items == []


class TestParseJin10:
    def test_parse_valid(self):
        data = json.dumps({
            "data": [
                {"content": "金十快讯内容", "id": "abc123"},
            ]
        })
        items = parse_jin10(data, "金十数据")
        assert len(items) == 1
        assert items[0].source == "金十数据"
        assert "abc123" in items[0].url

    def test_parse_empty(self):
        items = parse_jin10('{"data": []}', "金十数据")
        assert items == []


class TestParseKr36:
    def test_parse_items(self):
        data = json.dumps({
            "data": {
                "items": [
                    {"title": "36氪新闻标题", "id": "123", "web_url": "https://36kr.com/p/123"},
                ]
            }
        })
        items = parse_kr36(data, "36氪")
        assert len(items) == 1
        assert items[0].source == "36氪"
        assert items[0].title == "36氪新闻标题"

    def test_parse_entity_fallback(self):
        data = json.dumps({
            "data": {
                "items": [
                    {"entity": {"title": "实体标题", "content": "内容"}, "id": "456"},
                ]
            }
        })
        items = parse_kr36(data, "36氪")
        assert len(items) == 1
        assert items[0].title == "实体标题"

    def test_parse_empty(self):
        items = parse_kr36('{"data": {"items": []}}', "36氪")
        assert items == []


class TestSourceConfig:
    def test_default_sources(self):
        sources = default_sources()
        assert "sina_stock" in sources
        assert "sina_hk" in sources
        assert "sina_us" in sources
        assert "eastmoney" in sources
        assert "cls" in sources
        assert "jin10" in sources
        assert "kr36" in sources
        assert len(sources) == 7

    def test_source_config_fields(self):
        sources = default_sources()
        sina = sources["sina_stock"]
        assert sina.name == "新浪财经-A股"
        assert sina.parser == "sina"
        assert sina.enabled is True
        assert sina.retries >= 1

    def test_all_parsers_registered(self):
        sources = default_sources()
        for key, src in sources.items():
            assert src.parser in _PARSERS, f"Parser {src.parser} not registered for {key}"


class TestSourceHealth:
    def test_health_init(self):
        h = SourceHealth()
        assert h.consecutive_failures == 0
        assert h.is_healthy is True

    def test_health_unhealthy(self):
        h = SourceHealth()
        h.consecutive_failures = 5
        assert h.is_healthy is False

    def test_get_source_health(self):
        health = get_source_health()
        assert isinstance(health, dict)


class TestDedup:
    def test_new_item_not_duplicate(self):
        deps.dedup_cache = OrderedDict()
        deps.settings = Settings(deepseek_api_key="test")
        result = check_and_register("hash1")
        assert result is False

    def test_same_item_is_duplicate(self):
        deps.dedup_cache = OrderedDict()
        deps.settings = Settings(deepseek_api_key="test")
        check_and_register("hash1")
        result = check_and_register("hash1")
        assert result is True

    def test_cache_eviction(self):
        deps.dedup_cache = OrderedDict()
        deps.settings = Settings(deepseek_api_key="test", dedup_cache_max_size=3)
        check_and_register("h1")
        check_and_register("h2")
        check_and_register("h3")
        check_and_register("h4")
        assert len(deps.dedup_cache) == 3
        assert "h1" not in deps.dedup_cache