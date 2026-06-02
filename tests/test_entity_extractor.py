"""Tests for entity extraction module."""
import pytest
from unittest.mock import AsyncMock, patch

from app import deps
from app.models import Entity
from config.settings import Settings


@pytest.fixture(autouse=True)
def setup_deps():
    deps.settings = Settings(deepseek_api_key="test-key")
    deps.active_subscriptions = {}
    yield
    deps.active_subscriptions.clear()


class TestParseEntities:
    def test_valid_json(self):
        from app.analysis.entity_extractor import _parse_entities
        text = '[{"name": "工商银行", "type": "company", "aliases": ["ICBC"]}]'
        result = _parse_entities(text)
        assert len(result) == 1
        assert result[0].name == "工商银行"
        assert result[0].type == "company"
        assert result[0].aliases == ["ICBC"]

    def test_invalid_type_skipped(self):
        from app.analysis.entity_extractor import _parse_entities
        text = '[{"name": "xxx", "type": "unknown_type"}]'
        result = _parse_entities(text)
        assert len(result) == 0

    def test_markdown_wrapped_json(self):
        from app.analysis.entity_extractor import _parse_entities
        text = '```json\n[{"name": "央行", "type": "policy", "aliases": []}]\n```'
        result = _parse_entities(text)
        assert len(result) == 1
        assert result[0].name == "央行"

    def test_empty_name_skipped(self):
        from app.analysis.entity_extractor import _parse_entities
        text = '[{"name": "", "type": "company"}]'
        result = _parse_entities(text)
        assert len(result) == 0

    def test_invalid_json(self):
        from app.analysis.entity_extractor import _parse_entities
        result = _parse_entities("not json")
        assert result == []


class TestExtractEntities:
    @pytest.mark.asyncio
    async def test_extract_with_mock_client(self):
        from app.analysis.entity_extractor import extract_entities
        import app.analysis.entity_extractor as mod

        mock_client = AsyncMock()
        mock_client.analyze.return_value = '[{"name": "工商银行", "type": "company", "aliases": ["ICBC"]}]'

        with patch.object(mod, "_get_semaphore", return_value=AsyncMock()):
            with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client):
                entities = await extract_entities("工商银行发布财报", "银行利润增长")
                assert len(entities) == 1
                assert entities[0].name == "工商银行"

    @pytest.mark.asyncio
    async def test_extract_cached(self):
        from app.analysis.entity_extractor import extract_entities, _extraction_cache
        import app.analysis.entity_extractor as mod

        cached_entities = [Entity(name="测试", type="company")]
        _extraction_cache["hash123"] = cached_entities

        result = await extract_entities("title", "snippet", "hash123")
        assert result == cached_entities

        # Clean up
        _extraction_cache.pop("hash123", None)

    @pytest.mark.asyncio
    async def test_extract_handles_failure(self):
        from app.analysis.entity_extractor import extract_entities
        import app.analysis.entity_extractor as mod

        mock_client = AsyncMock()
        mock_client.analyze.side_effect = RuntimeError("API unavailable")

        with patch.object(mod, "_get_semaphore", return_value=AsyncMock()):
            with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client):
                entities = await extract_entities("测试标题")
                assert entities == []


class TestBatchResult:
    def test_parse_batch_result(self):
        from app.analysis.entity_extractor import _parse_batch_result
        text = '[{"news_index": 1, "name": "央行", "type": "policy", "aliases": []}, {"news_index": 2, "name": "A股", "type": "industry", "aliases": []}]'
        result = _parse_batch_result(text)
        assert 1 in result
        assert 2 in result
        assert result[1][0].name == "央行"
        assert result[2][0].name == "A股"