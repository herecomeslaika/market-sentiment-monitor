"""Tests for entity extraction module."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.models import Entity


class TestExtractAndSave:
    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_extract_parses_valid_json(self, db):
        mock_client = AsyncMock()
        mock_client.analyze.return_value = '[{"name":"工商银行","type":"company","aliases":["ICBC"]},{"name":"降息","type":"policy","aliases":[]}]'

        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.entity_extractor.deps") as mock_deps, \
             patch("app.repository.get_db", return_value=db):
            mock_deps.settings = MagicMock()
            from app.analysis.entity_extractor import extract_and_save
            result = await extract_and_save(1, "工商银行受益降息", "LPR下调利好银行", "h1")
            assert len(result) == 2
            assert result[0].name == "工商银行"
            assert result[0].type == "company"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_extract_handles_malformed_json(self, db):
        mock_client = AsyncMock()
        mock_client.analyze.return_value = "这不是JSON"
        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.entity_extractor.deps") as mock_deps, \
             patch("app.repository.get_db", return_value=db):
            mock_deps.settings = MagicMock()
            from app.analysis.entity_extractor import extract_and_save
            result = await extract_and_save(1, "测试", "测试", "h2")
            assert result == []

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_extract_handles_timeout(self, db):
        mock_client = AsyncMock()
        mock_client.analyze.side_effect = TimeoutError()
        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.entity_extractor.deps") as mock_deps, \
             patch("app.repository.get_db", return_value=db):
            mock_deps.settings = MagicMock()
            from app.analysis.entity_extractor import extract_and_save
            result = await extract_and_save(1, "测试", "测试", "h3")
            assert result == []

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_extract_skips_empty_name(self, db):
        mock_client = AsyncMock()
        mock_client.analyze.return_value = '[{"name":"","type":"policy"},{"name":"有效实体","type":"company"}]'
        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.entity_extractor.deps") as mock_deps, \
             patch("app.repository.get_db", return_value=db):
            mock_deps.settings = MagicMock()
            from app.analysis.entity_extractor import extract_and_save
            result = await extract_and_save(1, "测试", "测试", "h4")
            assert all(e.name.strip() for e in result)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_extract_handles_markdown_wrapped_json(self, db):
        mock_client = AsyncMock()
        mock_client.analyze.return_value = '```json\n[{"name":"央行","type":"policy"}]\n```'
        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client), \
             patch("app.analysis.entity_extractor.deps") as mock_deps, \
             patch("app.repository.get_db", return_value=db):
            mock_deps.settings = MagicMock()
            from app.analysis.entity_extractor import extract_and_save
            result = await extract_and_save(1, "央行降息", "央行宣布降息", "h5")
            assert len(result) == 1
            assert result[0].name == "央行"
