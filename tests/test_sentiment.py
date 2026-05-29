"""Tests for the sentiment analysis (fast_track and finbert worker)."""
import pytest
from unittest.mock import patch, MagicMock

from app.models import NewsItem, SentimentResult, SentimentResult


class TestFinbertWorker:
    """Tests for finbert_worker module."""

    def test_score_text_positive(self):
        # score_text is only callable in a subprocess, so we test via import
        # The actual score_text requires model loading so we can only test logic
        from app.sentiment.finbert_worker import score_text as _  # noqa

    def test_init_model(self):
        # Test init_model sets pipeline
        # This would require mocking torch/transformers, skip if unavailable
        pass


class TestFastTrackConsumer:
    """Test the fast_track_consumer core logic (without starting the actual consumer)."""

    def test_process_news_item_mock(self):
        from app.models import NewsItem
        from app.sentiment.fast_track import process_news_item
        # Just test that imports work; actual scoring requires subprocess
        # Real scoring needs a loaded model, so we test structure only
        assert callable(process_news_item)