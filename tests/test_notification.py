"""Tests for the notification dispatcher."""
import pytest
from unittest.mock import patch, MagicMock

from app.models import AlertPayload, NewsItem, SentimentResult
from app.notification.dispatcher import (
    should_send_alert,
    is_in_silence_period,
    set_notification_prefs,
    mark_alert_sent,
    _notification_prefs,
)


def _make_alert(level: str = "warning") -> AlertPayload:
    item = NewsItem(source="test", title="test", title_hash="x")
    sentiment = SentimentResult(news_item=item, score=-0.8, label="negative")
    return AlertPayload(news_item=item, sentiment=sentiment, alert_level=level)


class TestShouldSendAlert:
    def setup_method(self):
        _notification_prefs.clear()

    def test_no_prefs_allows_all(self):
        alert = _make_alert()
        assert should_send_alert(alert, "u1") is True

    def test_silence_period_blocks_warning(self):
        set_notification_prefs("u1", {"silence_minutes": 30})
        mark_alert_sent("u1")
        alert = _make_alert("warning")
        assert should_send_alert(alert, "u1") is False

    def test_critical_bypasses_silence(self):
        set_notification_prefs("u1", {"silence_minutes": 30})
        mark_alert_sent("u1")
        alert = _make_alert("critical")
        assert should_send_alert(alert, "u1") is True

    def test_min_level_filter(self):
        set_notification_prefs("u1", {"min_level": "warning", "silence_minutes": 0})
        info_alert = _make_alert("info")
        assert should_send_alert(info_alert, "u1") is False
        warning_alert = _make_alert("warning")
        assert should_send_alert(warning_alert, "u1") is True

    def test_min_level_critical(self):
        set_notification_prefs("u1", {"min_level": "critical", "silence_minutes": 0})
        warning_alert = _make_alert("warning")
        assert should_send_alert(warning_alert, "u1") is False
        critical_alert = _make_alert("critical")
        assert should_send_alert(critical_alert, "u1") is True


class TestIsInSilencePeriod:
    def setup_method(self):
        _notification_prefs.clear()

    def test_no_prefs_not_in_silence(self):
        assert is_in_silence_period("u1") is False

    def test_no_last_sent_not_in_silence(self):
        set_notification_prefs("u1", {"silence_minutes": 30})
        assert is_in_silence_period("u1") is False

    def test_after_mark_in_silence(self):
        set_notification_prefs("u1", {"silence_minutes": 30})
        mark_alert_sent("u1")
        assert is_in_silence_period("u1") is True

    def test_zero_silence_not_in_silence(self):
        set_notification_prefs("u1", {"silence_minutes": 0})
        mark_alert_sent("u1")
        assert is_in_silence_period("u1") is False


class TestSetNotificationPrefs:
    def setup_method(self):
        _notification_prefs.clear()

    def test_set_prefs(self):
        set_notification_prefs("u1", {"silence_minutes": 10, "min_level": "info"})
        assert _notification_prefs["u1"]["silence_minutes"] == 10
        assert _notification_prefs["u1"]["min_level"] == "info"

    def test_overwrite_prefs(self):
        set_notification_prefs("u1", {"silence_minutes": 10})
        set_notification_prefs("u1", {"silence_minutes": 60})
        assert _notification_prefs["u1"]["silence_minutes"] == 60
