from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import deps
from app.models import Subscription
from app.subscription import manager as sub_manager

router = APIRouter(tags=["api"])


# ---------- Health & Status ----------

@router.get("/health")
async def health():
    return {
        "status": "ok",
        "news_queue_size": deps.news_queue.qsize() if deps.news_queue else 0,
        "scored_queue_size": deps.scored_queue.qsize() if deps.scored_queue else 0,
        "alert_queue_size": deps.alert_queue.qsize() if deps.alert_queue else 0,
        "active_connections": len(deps.active_connections),
        "active_subscriptions": len(deps.active_subscriptions),
        "dedup_cache_size": len(deps.dedup_cache),
    }


@router.get("/status")
async def status():
    from app.crawler.sources import get_source_health
    sources_info = {}
    for key, src in deps.sources.items():
        sources_info[key] = {"name": src.name, "url": src.url, "enabled": src.enabled, "parser": src.parser}
    return {
        "settings": {
            "rss_poll_interval": deps.settings.rss_poll_interval_seconds if deps.settings else 30,
            "process_pool_size": deps.settings.process_pool_size if deps.settings else 2,
        },
        "queues": {
            "news": deps.news_queue.qsize() if deps.news_queue else 0,
            "scored": deps.scored_queue.qsize() if deps.scored_queue else 0,
            "alert": deps.alert_queue.qsize() if deps.alert_queue else 0,
        },
        "connections": len(deps.active_connections),
        "subscriptions": {uid: sub.model_dump() for uid, sub in deps.active_subscriptions.items()},
        "sources": sources_info,
        "source_health": get_source_health(),
    }


# ---------- Subscriptions ----------

@router.post("/subscriptions", response_model=Subscription)
async def create_subscription(sub: Subscription):
    result = await sub_manager.add_subscription(sub.user_id, sub.keywords, sub.threshold)
    return result


@router.delete("/subscriptions/{user_id}")
async def delete_subscription(user_id: str):
    await sub_manager.remove_subscription(user_id)
    return {"status": "removed"}


@router.get("/subscriptions", response_model=list[Subscription])
async def list_subscriptions():
    return list(sub_manager.list_subscriptions().values())


@router.get("/subscriptions/{user_id}", response_model=Subscription | None)
async def get_subscription(user_id: str):
    return sub_manager.get_subscription(user_id)


# ---------- Source Management ----------

class SourceCreate(BaseModel):
    key: str
    name: str
    url: str
    parser: str = "rss"
    enabled: bool = True


class SourceUpdate(BaseModel):
    enabled: bool | None = None
    url: str | None = None


@router.get("/sources")
async def list_sources():
    result = {}
    for key, src in deps.sources.items():
        result[key] = {"name": src.name, "url": src.url, "parser": src.parser, "enabled": src.enabled}
    return result


@router.post("/sources")
async def add_source(body: SourceCreate):
    from app.crawler.sources import SourceConfig, BROWSER_HEADERS
    src = SourceConfig(
        name=body.name,
        url=body.url,
        headers=BROWSER_HEADERS,
        parser=body.parser,
        enabled=body.enabled,
    )
    deps.sources[body.key] = src
    return {"status": "added", "key": body.key}


@router.patch("/sources/{key}")
async def update_source(key: str, body: SourceUpdate):
    src = deps.sources.get(key)
    if not src:
        raise HTTPException(404, f"Source '{key}' not found")
    if body.enabled is not None:
        src.enabled = body.enabled
    if body.url is not None:
        src.url = body.url
    return {"status": "updated", "key": key}


@router.delete("/sources/{key}")
async def delete_source(key: str):
    if key not in deps.sources:
        raise HTTPException(404, f"Source '{key}' not found")
    del deps.sources[key]
    return {"status": "removed", "key": key}


# ---------- History & Stats ----------

@router.get("/news/history")
async def news_history(limit: int = 50, offset: int = 0, source: str | None = None):
    from app.repository import query_news
    return await query_news(limit, offset, source)


@router.get("/sentiment/trend")
async def sentiment_trend(hours: int = 24):
    from app.repository import query_sentiment_trend
    return await query_sentiment_trend(hours)


@router.get("/sentiment/history")
async def sentiment_history(hours: int = 24):
    from app.repository import query_sentiment_history
    return await query_sentiment_history(hours)


@router.get("/alerts/history")
async def alert_history(limit: int = 50, offset: int = 0, level: str | None = None):
    from app.repository import query_alert_history
    return await query_alert_history(limit, offset, level)


@router.get("/stats/keywords")
async def keyword_stats(hours: int = 24):
    from app.repository import query_keyword_stats
    return await query_keyword_stats(hours)


@router.post("/cleanup")
async def cleanup_data(days: int = 30):
    from app.repository import cleanup_old_data
    await cleanup_old_data(days)
    return {"status": "cleaned", "older_than_days": days}


# ---------- Report Service ----------

class FollowupRequest(BaseModel):
    question: str


@router.get("/reports")
async def list_reports(limit: int = 20, offset: int = 0, level: str | None = None):
    from app.repository import query_reports
    return await query_reports(limit, offset, level)


@router.get("/reports/{report_id}")
async def get_report(report_id: str):
    from app.analysis.report_service import get_report as _get_report
    report = await _get_report(report_id)
    if not report:
        raise HTTPException(404, "Report not found")
    return report


@router.post("/reports/{report_id}/followup")
async def followup(report_id: str, body: FollowupRequest):
    from app.analysis.report_service import followup_question
    result = await followup_question(report_id, body.question)
    if result is None:
        raise HTTPException(404, "Report not found or no analysis available")
    return {"question": body.question, "answer": result}


@router.get("/reports/{report_id}/markdown")
async def export_report_markdown(report_id: str):
    from app.analysis.report_service import get_report as _get_report, export_markdown
    from fastapi.responses import PlainTextResponse
    report = await _get_report(report_id)
    md = export_markdown(report)
    if md is None:
        raise HTTPException(404, "Report not found")
    return PlainTextResponse(content=md, media_type="text/markdown")


@router.post("/reports/{report_id}/compare")
async def compare_models(report_id: str):
    from app.analysis.report_service import multi_model_compare
    result = await multi_model_compare(report_id)
    if result is None:
        raise HTTPException(404, "Report not found")
    return result


# ---------- Notification Preferences ----------

class NotificationPrefsBody(BaseModel):
    email: str | None = None
    dingtalk_webhook: str | None = None
    feishu_webhook: str | None = None
    silence_minutes: int = 0
    min_level: str = "info"


@router.get("/notifications/{user_id}")
async def get_notification_prefs(user_id: str):
    from app.notification.dispatcher import get_notification_prefs as _get
    return _get(user_id)


@router.put("/notifications/{user_id}")
async def set_notification_prefs(user_id: str, body: NotificationPrefsBody):
    from app.notification.dispatcher import set_notification_prefs as _set
    prefs = {
        "email": body.email,
        "dingtalk_webhook": body.dingtalk_webhook,
        "feishu_webhook": body.feishu_webhook,
        "silence_minutes": body.silence_minutes,
        "min_level": body.min_level,
    }
    _set(user_id, prefs)
    return {"status": "updated", "user_id": user_id}
