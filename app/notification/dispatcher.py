from __future__ import annotations

import asyncio
import json
import logging
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from typing import TypedDict

import aiohttp

from app import deps
from app.models import AlertPayload

logger = logging.getLogger(__name__)


# ---------- Notification Preferences ----------

class NotificationPrefs(TypedDict, total=False):
    email: str | None
    dingtalk_webhook: str | None
    feishu_webhook: str | None
    silence_minutes: int  # Default: 0 (no silence)
    last_alert_time: datetime | None
    min_level: str  # "critical", "warning", "info"


# Per-user notification preferences
_notification_prefs: dict[str, NotificationPrefs] = {}


def set_notification_prefs(user_id: str, prefs: NotificationPrefs):
    _notification_prefs[user_id] = prefs


def get_notification_prefs(user_id: str) -> NotificationPrefs:
    return _notification_prefs.get(user_id, {"silence_minutes": 0, "min_level": "info"})


def is_in_silence_period(user_id: str) -> bool:
    prefs = _notification_prefs.get(user_id)
    if not prefs:
        return False
    silence_minutes = prefs.get("silence_minutes", 0)
    if silence_minutes <= 0:
        return False
    last_time = prefs.get("last_alert_time")
    if not last_time:
        return False
    now = datetime.now()
    if now - last_time < timedelta(minutes=silence_minutes):
        return True
    return False


def should_send_alert(alert: AlertPayload, user_id: str) -> bool:
    """Check if an alert should be sent to a user based on level and silence."""
    prefs = _notification_prefs.get(user_id)
    if not prefs:
        return True

    # Check minimum level
    min_level = prefs.get("min_level", "info")
    level_order = {"critical": 0, "warning": 1, "info": 2}
    if level_order.get(alert.alert_level, 2) > level_order.get(min_level, 2):
        return False

    # Critical alerts bypass silence period
    if alert.alert_level == "critical":
        return True

    # Check silence period
    if is_in_silence_period(user_id):
        return False

    return True


def mark_alert_sent(user_id: str):
    prefs = _notification_prefs.get(user_id)
    if prefs:
        prefs["last_alert_time"] = datetime.now()


# ---------- Email Channel ----------

async def send_email(to: str, alert: AlertPayload):
    if not deps.settings:
        return
    smtp_host = getattr(deps.settings, "smtp_host", "")
    smtp_port = getattr(deps.settings, "smtp_port", 465)
    smtp_user = getattr(deps.settings, "smtp_user", "")
    smtp_pass = getattr(deps.settings, "smtp_pass", "")
    from_addr = getattr(deps.settings, "smtp_from", smtp_user)

    if not smtp_host or not to:
        return

    subject = f"[{alert.alert_level}] 市场情绪预警: {alert.news_item.title[:50]}"
    body = (
        f"新闻标题: {alert.news_item.title}\n"
        f"来源: {alert.news_item.source}\n"
        f"情绪得分: {alert.sentiment.score:.3f} ({alert.sentiment.label})\n"
        f"告警级别: {alert.alert_level}\n"
        f"触发关键词: {', '.join(alert.triggered_keywords)}\n\n"
    )
    if alert.deep_analysis:
        body += f"深度研报:\n{alert.deep_analysis}\n"

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to

    try:
        # Run SMTP in executor to avoid blocking event loop
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _smtp_send, smtp_host, smtp_port, smtp_user, smtp_pass, msg)
        logger.info("Email sent to %s", to)
    except Exception as e:
        logger.warning("Email send failed: %s", e)


def _smtp_send(host: str, port: int, user: str, pass_: str, msg: MIMEText):
    with smtplib.SMTP_SSL(host, port) as server:
        if user:
            server.login(user, pass_)
        server.send_message(msg)


# ---------- DingTalk Channel ----------

async def send_dingtalk(webhook: str, alert: AlertPayload):
    if not webhook:
        return

    title = f"[{alert.alert_level}] {alert.news_item.title[:50]}"
    text = (
        f"**新闻**: {alert.news_item.title}\n"
        f"**来源**: {alert.news_item.source}\n"
        f"**情绪**: {alert.sentiment.score:.3f} ({alert.sentiment.label})\n"
        f"**关键词**: {', '.join(alert.triggered_keywords)}\n\n"
    )
    if alert.deep_analysis:
        text += f"**研报**:\n{alert.deep_analysis[:500]}\n"

    payload = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": text},
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    logger.info("DingTalk notification sent")
                else:
                    logger.warning("DingTalk returned %d", resp.status)
    except Exception as e:
        logger.warning("DingTalk send failed: %s", e)


# ---------- Feishu/Lark Channel ----------

async def send_feishu(webhook: str, alert: AlertPayload):
    if not webhook:
        return

    title = f"[{alert.alert_level}] 市场情绪预警"
    text = (
        f"**新闻**: {alert.news_item.title}\n"
        f"**来源**: {alert.news_item.source}\n"
        f"**情绪得分**: {alert.sentiment.score:.3f} ({alert.sentiment.label})\n"
        f"**触发关键词**: {', '.join(alert.triggered_keywords)}\n\n"
    )
    if alert.deep_analysis:
        text += f"**深度研报**:\n{alert.deep_analysis[:500]}\n"

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": title}},
            "elements": [{"tag": "markdown", "content": text}],
        },
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    logger.info("Feishu notification sent")
                else:
                    logger.warning("Feishu returned %d", resp.status)
    except Exception as e:
        logger.warning("Feishu send failed: %s", e)


# ---------- Unified Notification Dispatcher ----------

async def dispatch_notification(alert: AlertPayload, user_id: str):
    """Dispatch alert through all configured channels for a user."""
    if not should_send_alert(alert, user_id):
        logger.debug("Alert skipped for %s (silence/level filter)", user_id)
        return

    prefs = _notification_prefs.get(user_id, {})

    # WebSocket push is handled separately by alert_pusher

    # Email channel
    email = prefs.get("email")
    if email:
        await send_email(email, alert)

    # DingTalk channel
    dingtalk = prefs.get("dingtalk_webhook")
    if dingtalk:
        await send_dingtalk(dingtalk, alert)

    # Feishu channel
    feishu = prefs.get("feishu_webhook")
    if feishu:
        await send_feishu(feishu, alert)

    mark_alert_sent(user_id)