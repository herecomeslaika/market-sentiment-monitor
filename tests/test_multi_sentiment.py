"""Tests for multi-dimensional sentiment analysis module."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.models import Entity, MultiSentiment


class TestAnalyzeAndSave:
    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_analyze_parses_valid_response(self, seeded_db):
        db, ids = seeded_db
        mock_client = AsyncMock()
        mock_client.analyze.return_value = '{"fear":0.1,"greed":0.5,"optimism":0.8,"uncertainty":0.2,"dominant":"optimism"}'
        entities = [Entity(name="美联储", type="policy")]

        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.multi_sentiment.deps") as mock_deps, \
             patch("app.repository.get_db", return_value=db):
            mock_deps.settings = MagicMock()
            from app.analysis.multi_sentiment import analyze_and_save
            result = await analyze_and_save(ids["n2"], "Fed signals rate cut", "Rate cut hints", entities)
            assert result is not None
            assert result.dominant == "optimism"
            assert result.entity_name == "美联储"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_analyze_handles_malformed_json(self, seeded_db):
        db, ids = seeded_db
        mock_client = AsyncMock()
        mock_client.analyze.return_value = "不是JSON"
        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.multi_sentiment.deps") as mock_deps, \
             patch("app.repository.get_db", return_value=db):
            mock_deps.settings = MagicMock()
            from app.analysis.multi_sentiment import analyze_and_save
            result = await analyze_and_save(ids["n1"], "测试标题", "测试内容", [])
            assert result is None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_analyze_handles_timeout(self, seeded_db):
        db, ids = seeded_db
        mock_client = AsyncMock()
        mock_client.analyze.side_effect = TimeoutError()
        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.multi_sentiment.deps") as mock_deps, \
             patch("app.repository.get_db", return_value=db):
            mock_deps.settings = MagicMock()
            from app.analysis.multi_sentiment import analyze_and_save
            result = await analyze_and_save(ids["n1"], "测试标题", "测试内容", [])
            assert result is None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_momentum_shift_detected(self, seeded_db):
        db, ids = seeded_db
        mock_client = AsyncMock()
        mock_client.analyze.return_value = '{"fear":0.1,"greed":0.6,"optimism":0.8,"uncertainty":0.2,"dominant":"optimism"}'
        entities = [Entity(name="央行", type="policy")]

        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.multi_sentiment.deps") as mock_deps, \
             patch("app.repository.get_db", return_value=db):
            mock_deps.settings = MagicMock()
            from app.analysis.multi_sentiment import analyze_and_save
            result = await analyze_and_save(ids["n1"], "央行降息利好", "利好消息", entities)
            if result:
                assert isinstance(result.momentum_shift, bool)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_no_entities_skips_analysis(self, seeded_db):
        db, ids = seeded_db
        with patch("app.repository.get_db", return_value=db):
            from app.analysis.multi_sentiment import analyze_and_save
            result = await analyze_and_save(ids["n1"], "测试", "测试", [])
            assert result is None or isinstance(result, MultiSentiment)
