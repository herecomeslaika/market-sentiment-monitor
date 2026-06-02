"""Tests for multi-dimensional sentiment analysis."""
import pytest
from unittest.mock import AsyncMock, patch

from app import deps
from app.models import MultiSentiment
from config.settings import Settings


@pytest.fixture(autouse=True)
def setup_deps():
    deps.settings = Settings(deepseek_api_key="test-key")
    deps.active_subscriptions = {}
    yield
    deps.active_subscriptions.clear()


class TestParseMultiSentiment:
    def test_valid_json(self):
        from app.analysis.multi_sentiment import _parse_multi_sentiment
        text = '{"fear": 0.2, "greed": 0.7, "optimism": 0.6, "uncertainty": 0.3, "dominant": "greed"}'
        result = _parse_multi_sentiment(text)
        assert result is not None
        assert result["fear"] == 0.2
        assert result["greed"] == 0.7
        assert result["dominant"] == "greed"

    def test_clamps_values(self):
        from app.analysis.multi_sentiment import _parse_multi_sentiment
        text = '{"fear": 1.5, "greed": -0.3, "optimism": 0.5, "uncertainty": 0.4, "dominant": "fear"}'
        result = _parse_multi_sentiment(text)
        assert result["fear"] == 1.0
        assert result["greed"] == 0.0

    def test_auto_dominant(self):
        from app.analysis.multi_sentiment import _parse_multi_sentiment
        text = '{"fear": 0.1, "greed": 0.2, "optimism": 0.3, "uncertainty": 0.1}'
        result = _parse_multi_sentiment(text)
        # No dominant > 0.5, should be neutral
        assert result["dominant"] == "neutral"

    def test_markdown_wrapped(self):
        from app.analysis.multi_sentiment import _parse_multi_sentiment
        text = '```json\n{"fear": 0.5, "greed": 0.3, "optimism": 0.2, "uncertainty": 0.4, "dominant": "fear"}\n```'
        result = _parse_multi_sentiment(text)
        assert result is not None
        assert result["fear"] == 0.5

    def test_invalid_json(self):
        from app.analysis.multi_sentiment import _parse_multi_sentiment
        result = _parse_multi_sentiment("not json")
        assert result is None

    def test_missing_keys(self):
        from app.analysis.multi_sentiment import _parse_multi_sentiment
        result = _parse_multi_sentiment('{"fear": 0.5}')
        assert result is None


class TestAnalyzeSentiment:
    @pytest.mark.asyncio
    async def test_analyze_with_mock(self):
        from app.analysis.multi_sentiment import analyze_sentiment

        mock_client = AsyncMock()
        mock_client.analyze.return_value = '{"fear": 0.1, "greed": 0.8, "optimism": 0.7, "uncertainty": 0.2, "dominant": "greed"}'

        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client):
            result = await analyze_sentiment("A股大涨", "市场情绪高涨")
            assert result is not None
            assert result.greed == 0.8
            assert result.dominant == "greed"

    @pytest.mark.asyncio
    async def test_analyze_handles_failure(self):
        from app.analysis.multi_sentiment import analyze_sentiment

        mock_client = AsyncMock()
        mock_client.analyze.side_effect = RuntimeError("API down")

        with patch("app.analysis.deepseek_client.DeepSeekClient", return_value=mock_client):
            result = await analyze_sentiment("测试")
            assert result is None


class TestMomentumDetection:
    @pytest.mark.asyncio
    async def test_momentum_shift_detected(self):
        from app.analysis.multi_sentiment import compute_momentum
        current = MultiSentiment(news_id=2, entity_name="银行", fear=0.8, greed=0.1, optimism=0.1, uncertainty=0.5, dominant="fear")

        with patch("app.repository.load_last_multi_sentiment", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = {"fear": 0.2, "greed": 0.7, "optimism": 0.6, "uncertainty": 0.3, "dominant": "greed"}
            momentum, is_shift = await compute_momentum("银行", current)
            assert momentum > 0
            assert is_shift is True  # fear changed from 0.2 to 0.8 > 0.3

    @pytest.mark.asyncio
    async def test_no_momentum_on_first_data(self):
        from app.analysis.multi_sentiment import compute_momentum
        current = MultiSentiment(news_id=1, entity_name="银行", fear=0.5, greed=0.3, optimism=0.2, uncertainty=0.4, dominant="fear")

        with patch("app.repository.load_last_multi_sentiment", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = None
            momentum, is_shift = await compute_momentum("银行", current)
            assert momentum == 0.0
            assert is_shift is False
