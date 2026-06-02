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


def should_trigger_deep_analysis(score: float, matched_keywords: list[str], significance: float = 0.0) -> bool:
    if not matched_keywords:
        return False
    for sub in deps.active_subscriptions.values():
        if score <= sub.threshold:
            return True
    if significance >= 0.7:
        return True
    return False


async def run_deep_analysis_from_state(initial_state: dict, retries: int = MAX_DEEP_RETRIES) -> str | None:
    """Run LangGraph analysis with a pre-populated state including knowledge data."""
    from app.analysis.langgraph_flow import get_compiled_graph

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
                if report:
                    return report
                last_error = result.get("error", "empty report")
            except asyncio.TimeoutError:
                last_error = "timeout"
                logger.warning("Deep analysis timed out (attempt %d/%d): %s", attempt + 1, retries + 1, initial_state.get("news_title", "")[:40])
            except Exception as e:
                last_error = str(e)
                logger.error("Deep analysis error (attempt %d/%d): %s", attempt + 1, retries + 1, e)

            if attempt < retries:
                await asyncio.sleep(2 * (attempt + 1))

        logger.error("Deep analysis failed after %d attempts for: %s (last error: %s)", retries + 1, initial_state.get("news_title", "")[:40], last_error)
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

            # --- Always run intelligent analysis regardless of subscriptions ---
            entities = []
            multi_sentiment_result = None
            cluster = None
            relations = []
            causal_chain = None

            # Step 1: Entity extraction
            if sentiment.news_db_id:
                try:
                    from app.analysis.entity_extractor import extract_and_save
                    entities = await extract_and_save(
                        sentiment.news_db_id,
                        sentiment.news_item.title,
                        sentiment.news_item.content_snippet,
                        sentiment.news_item.title_hash,
                    )
                except Exception as e:
                    logger.warning("Entity extraction failed: %s", e)

            # Step 2: Multi-dimensional sentiment
            if sentiment.news_db_id:
                try:
                    from app.analysis.multi_sentiment import analyze_and_save as ms_analyze
                    multi_sentiment_result = await ms_analyze(
                        sentiment.news_db_id,
                        sentiment.news_item.title,
                        sentiment.news_item.content_snippet,
                        entities,
                    )
                except Exception as e:
                    logger.warning("Multi-sentiment analysis failed: %s", e)

            # Step 3: Event clustering
            if sentiment.news_db_id and entities:
                try:
                    from app.analysis.event_cluster import try_cluster
                    cluster = await try_cluster(
                        sentiment.news_db_id,
                        sentiment.news_item.title,
                        entities,
                        sentiment.score,
                        sentiment.label,
                    )
                except Exception as e:
                    logger.warning("Event clustering failed: %s", e)

            # Step 4: Knowledge graph (only for new clusters)
            if cluster and len(cluster.entities) >= 2:
                try:
                    from app.analysis.knowledge_graph import extract_relations_and_infer
                    relations, causal_chain = await extract_relations_and_infer(
                        cluster,
                        sentiment.news_item.title,
                        sentiment.news_item.content_snippet,
                    )
                except Exception as e:
                    logger.warning("Knowledge graph extraction failed: %s", e)

            # Broadcast entity/event/momentum updates via WebSocket
            if entities:
                try:
                    from app.ws.connection_manager import get_manager
                    mgr = get_manager()
                    await mgr.broadcast({
                        "type": "entity_update",
                        "payload": {
                            "news_id": sentiment.news_db_id,
                            "entities": [{"name": e.name, "type": e.type} for e in entities],
                        },
                    })
                except Exception:
                    pass

            if cluster:
                try:
                    from app.ws.connection_manager import get_manager
                    mgr = get_manager()
                    await mgr.broadcast({
                        "type": "event_update",
                        "payload": {
                            "cluster_id": cluster.cluster_id,
                            "title": cluster.title,
                            "news_count": len(cluster.news_ids),
                            "significance": cluster.significance,
                        },
                    })
                except Exception:
                    pass

            if multi_sentiment_result and multi_sentiment_result.momentum_shift:
                try:
                    from app.ws.connection_manager import get_manager
                    mgr = get_manager()
                    await mgr.broadcast({
                        "type": "momentum_shift",
                        "payload": {
                            "news_id": sentiment.news_db_id,
                            "entity": multi_sentiment_result.entity_name,
                            "momentum": multi_sentiment_result.momentum,
                            "dominant": multi_sentiment_result.dominant,
                        },
                    })
                except Exception:
                    pass

            # --- Subscription matching and alerting (only if subscribed) ---
            matched = match_subscriptions(alert)
            if not matched:
                continue

            # Assign alert level based on sentiment score
            if sentiment.score <= -0.7:
                alert.alert_level = "critical"
            elif sentiment.score <= -0.3:
                alert.alert_level = "warning"
            else:
                alert.alert_level = "info"

            triggered_keywords = []
            for sub, keywords in matched:
                triggered_keywords.extend(keywords)
            alert.triggered_keywords = list(set(triggered_keywords))

            # Step 5: Deep analysis (enhanced with knowledge)
            if should_trigger_deep_analysis(sentiment.score, triggered_keywords, cluster.significance if cluster else 0.0):
                # Inject knowledge into LangGraph initial state
                initial_state = {
                    "news_title": sentiment.news_item.title,
                    "news_snippet": sentiment.news_item.content_snippet,
                    "news_url": sentiment.news_item.url,
                    "sentiment_score": sentiment.score,
                    "sentiment_label": sentiment.label,
                    "keywords_matched": triggered_keywords,
                    "context_summary": "",
                    "risk_assessment": "",
                    "final_report": "",
                    "error": None,
                }
                if entities:
                    initial_state["entities"] = [{"name": e.name, "type": e.type} for e in entities]
                if multi_sentiment_result:
                    initial_state["multi_sentiment"] = {
                        "fear": multi_sentiment_result.fear,
                        "greed": multi_sentiment_result.greed,
                        "optimism": multi_sentiment_result.optimism,
                        "uncertainty": multi_sentiment_result.uncertainty,
                        "dominant": multi_sentiment_result.dominant,
                    }
                if cluster:
                    initial_state["event_context"] = {
                        "cluster_title": cluster.title,
                        "news_count": len(cluster.news_ids),
                        "significance": cluster.significance,
                    }
                if relations:
                    initial_state["relations"] = [
                        {"source": r.source, "target": r.target, "relation": r.relation, "context": r.context}
                        for r in relations
                    ]
                if causal_chain:
                    initial_state["causal_chain"] = {
                        "trigger": causal_chain.trigger,
                        "path": causal_chain.path,
                        "impact": causal_chain.impact,
                        "confidence": causal_chain.confidence,
                    }
                report = await run_deep_analysis_from_state(initial_state)
                alert.deep_analysis = report

            # Persist alert
            if sentiment.news_db_id and sentiment.sentiment_db_id:
                await save_alert(sentiment.news_db_id, sentiment.sentiment_db_id, alert)

            # Store report for later followup/export
            await store_report(alert)

            await deps.alert_queue.put(alert)
            logger.info(
                "Alert queued: score=%.3f level=%s keywords=%s entities=%d - %s",
                sentiment.score, alert.alert_level, triggered_keywords,
                len(entities), sentiment.news_item.title[:40],
            )

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Slow track error: %s", e, exc_info=True)
            await asyncio.sleep(1)
