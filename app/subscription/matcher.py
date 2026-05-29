from __future__ import annotations

from app import deps
from app.models import AlertPayload, Subscription


def match_subscriptions(alert: AlertPayload) -> list[tuple[Subscription, list[str]]]:
    """Match alert against all active subscriptions by keyword + threshold.

    Returns list of (subscription, matched_keywords) tuples.
    """
    results = []
    title = alert.news_item.title.lower()
    score = alert.sentiment.score

    for sub in deps.active_subscriptions.values():
        # Check keyword match
        matched_kw = [kw for kw in sub.keywords if kw.lower() in title]
        if not matched_kw:
            continue

        # Check threshold: alert if score is at or below the subscription's threshold
        if score <= sub.threshold:
            results.append((sub, matched_kw))

    return results
