"""Tests for knowledge graph and causal chain inference."""
import pytest
from unittest.mock import AsyncMock, patch

from app import deps
from app.models import Entity, EntityRelation, CausalChain, EventCluster
from config.settings import Settings
from datetime import datetime, timezone


@pytest.fixture(autouse=True)
def setup_deps():
    deps.settings = Settings(deepseek_api_key="test-key")
    deps.active_subscriptions = {}
    yield
    deps.active_subscriptions.clear()


class TestParseRelations:
    def test_valid_json(self):
        from app.analysis.knowledge_graph import _parse_relations
        text = '[{"source": "央行降息", "target": "银行利润", "relation": "affects", "context": "降息压缩利差", "confidence": 0.8}]'
        result = _parse_relations(text)
        assert len(result) == 1
        assert result[0].source == "央行降息"
        assert result[0].target == "银行利润"
        assert result[0].relation == "affects"
        assert result[0].confidence == 0.8

    def test_invalid_relation_type_skipped(self):
        from app.analysis.knowledge_graph import _parse_relations
        text = '[{"source": "A", "target": "B", "relation": "invalid_type", "context": "", "confidence": 0.5}]'
        result = _parse_relations(text)
        assert len(result) == 0

    def test_clamps_confidence(self):
        from app.analysis.knowledge_graph import _parse_relations
        text = '[{"source": "A", "target": "B", "relation": "causes", "context": "", "confidence": 2.0}]'
        result = _parse_relations(text)
        assert result[0].confidence == 1.0

    def test_markdown_wrapped(self):
        from app.analysis.knowledge_graph import _parse_relations
        text = '```json\n[{"source": "A股", "target": "港股", "relation": "correlates", "context": "联动", "confidence": 0.6}]\n```'
        result = _parse_relations(text)
        assert len(result) == 1

    def test_invalid_json(self):
        from app.analysis.knowledge_graph import _parse_relations
        result = _parse_relations("bad json")
        assert result == []


class TestParseCausalChain:
    def test_valid_json(self):
        from app.analysis.knowledge_graph import _parse_causal_chain
        text = '{"trigger": "央行降息", "path": ["央行降息", "银行利差收窄", "房贷需求上升"], "impact": "房地产利好", "confidence": 0.75}'
        result = _parse_causal_chain(text)
        assert result is not None
        assert result.trigger == "央行降息"
        assert len(result.path) == 3
        assert result.impact == "房地产利好"
        assert result.confidence == 0.75

    def test_empty_path_rejected(self):
        from app.analysis.knowledge_graph import _parse_causal_chain
        text = '{"trigger": "test", "path": [], "impact": "none", "confidence": 0.5}'
        result = _parse_causal_chain(text)
        assert result is None

    def test_invalid_json(self):
        from app.analysis.knowledge_graph import _parse_causal_chain
        result = _parse_causal_chain("not json")
        assert result is None


class TestExtractRelations:
    @pytest.mark.asyncio
    async def test_extract_with_mock(self):
        from app.analysis.knowledge_graph import extract_relations

        mock_client = AsyncMock()
        mock_client.analyze.return_value = '[{"source": "央行", "target": "利率", "relation": "affects", "context": "央行决定利率", "confidence": 0.9}]'
        entities = [Entity(name="央行", type="policy"), Entity(name="利率", type="indicator")]

        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client):
            relations = await extract_relations("央行降息", "详情...", entities)
            assert len(relations) == 1
            assert relations[0].source == "央行"

    @pytest.mark.asyncio
    async def test_skips_single_entity(self):
        from app.analysis.knowledge_graph import extract_relations
        entities = [Entity(name="央行", type="policy")]
        relations = await extract_relations("标题", "", entities)
        assert relations == []

    @pytest.mark.asyncio
    async def test_handles_failure(self):
        from app.analysis.knowledge_graph import extract_relations

        mock_client = AsyncMock()
        mock_client.analyze.side_effect = RuntimeError("API error")
        entities = [Entity(name="A", type="company"), Entity(name="B", type="industry")]

        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client):
            relations = await extract_relations("测试", "", entities)
            assert relations == []


class TestInferCausalChain:
    @pytest.mark.asyncio
    async def test_infer_with_mock(self):
        from app.analysis.knowledge_graph import infer_causal_chain

        mock_client = AsyncMock()
        mock_client.analyze.return_value = '{"trigger": "降息", "path": ["降息", "利差收窄", "房贷上升"], "impact": "利好", "confidence": 0.8}'
        entities = [Entity(name="央行", type="policy"), Entity(name="银行", type="company")]
        relations = [EntityRelation(source="央行", target="银行", relation="affects")]

        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client):
            chain = await infer_causal_chain(entities, relations, "央行降息背景")
            assert chain is not None
            assert chain.trigger == "降息"
            assert len(chain.path) == 3

    @pytest.mark.asyncio
    async def test_returns_none_without_relations(self):
        from app.analysis.knowledge_graph import infer_causal_chain
        entities = [Entity(name="A", type="company")]
        result = await infer_causal_chain(entities, [], "context")
        assert result is None
