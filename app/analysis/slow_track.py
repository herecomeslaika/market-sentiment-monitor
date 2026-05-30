from __future__ import annotations

import asyncio
import logging

from app import deps
from app.models import AlertPayload

logger = logging.getLogger(__name__)

# Limit concurrent DeepSeek API calls (created lazily)
_semaphore: asyncio.Semaphore | None = None
MAX_DEEP_RETRIES = 2


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(3)
    return _semaphore


def should_trigger_deep_analysis(score: float, matched_keywords: list[str]) -> bool:
    if not matched_keywords:
        return False
    for sub in deps.active_subscriptions.values():
        if score <= sub.threshold:
            return True
    return False


async def run_deep_analysis(sentiment, retries: int = MAX_DEEP_RETRIES) -> str | None:
    from app.analysis.langgraph_flow import get_compiled_graph

    initial_state = {
        "news_title": sentiment.news_item.title,
        "news_snippet": sentiment.news_item.content_snippet,
        "sentiment_score": sentiment.score,
        "sentiment_label": sentiment.label,
        "keywords_matched": [],
        "context_summary": "",
        "risk_assessment": "",
        "final_report": "",
        "error": None,
    }
    async with _get_semaphore():
        last_error = None
        for attempt in range(retries + 1):
            try:
                result = await asyncio.wait_for(
                    get_compiled_graph().ainvoke(initial_state),
                    timeout=90,
                )
                report = result.get("final_report")
                if report and not result.get("error"):
                    return report
                # Partial report is still useful
                if report:
                    return report
                last_error = result.get("error", "empty report")
            except asyncio.TimeoutError:
                last_error = "timeout"
                logger.warning("Deep analysis timed out (attempt %d/%d): %s", attempt + 1, retries + 1, sentiment.news_item.title[:40])
            except Exception as e:
                last_error = str(e)
                logger.error("Deep analysis error (attempt %d/%d): %s", attempt + 1, retries + 1, e)

            if attempt < retries:
                await asyncio.sleep(2 * (attempt + 1))

        logger.error("Deep analysis failed after %d attempts for: %s (last error: %s)", retries + 1, sentiment.news_item.title[:40], last_error)
        return None


async def slow_track_consumer():
    from app.subscription.matcher import match_subscriptions
    from app.repository import save_alert
    from app.analysis.report_service import store_report

    logger.info("Slow track consumer started")
    while True:
        try:
            sentiment = await deps.scored_queue.get()

            alert = AlertPayload(
                news_item=sentiment.news_item,
                sentiment=sentiment,
            )
            matched = match_subscriptions(alert)
            if not matched:
                continue

            triggered_keywords = []
            for sub, keywords in matched:
                triggered_keywords.extend(keywords)
            alert.triggered_keywords = list(set(triggered_keywords))

            if sentiment.score <= -0.7:
                alert.alert_level = "critical"
            elif sentiment.score <= -0.4:
                alert.alert_level = "warning"
            else:
                alert.alert_level = "info"

            if should_trigger_deep_analysis(sentiment.score, triggered_keywords):
                report = await run_deep_analysis(sentiment)
                alert.deep_analysis = report

            # Persist alert
            if sentiment.news_db_id and sentiment.sentiment_db_id:
                await save_alert(sentiment.news_db_id, sentiment.sentiment_db_id, alert)

            # Store report for later followup/export
            await store_report(alert)

            await deps.alert_queue.put(alert)
            logger.info(
                "Alert queued: score=%.3f level=%s keywords=%s - %s",
                sentiment.score, alert.alert_level, triggered_keywords,
                sentiment.news_item.title[:40],
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Slow track error: %s", e, exc_info=True)
            await asyncio.sleep(1)
