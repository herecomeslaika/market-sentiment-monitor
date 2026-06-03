"""Fed monetary policy tracker.

Collects Fed-related news (prioritizing English-language sources) and distills
the current policy stance via LLM.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from app import deps

logger = logging.getLogger(__name__)

# English keywords take priority — Fed policy is primarily communicated in English
FED_KEYWORDS_EN = [
    "Fed", "Federal Reserve", "rate cut", "rate hike", "interest rate",
    "federal funds rate", "QE", "QT", "quantitative tightening",
    "quantitative easing", "Powell", "FOMC", "monetary policy", "balance sheet",
    "tapering", "forward guidance", "basis points", "bps",
]

# Chinese keywords as secondary supplement
FED_KEYWORDS_CN = ["美联储", "降息", "加息", "缩表", "扩表", "鲍威尔", "FOMC"]

# English-language source names for priority filtering
EN_SOURCE_PATTERNS = ["CNBC", "MarketWatch", "Yahoo", "BBC", "Investing", "Reuters", "Bloomberg"]

POLICY_SYSTEM_PROMPT = (
    "You are a Federal Reserve monetary policy analyst. Based on the following news "
    "(primarily from English-language sources), distill the current Fed policy stance.\n"
    "Output strictly in this JSON format, with nothing else:\n"
    "{\n"
    '  "rate_trend": "hiking" | "cutting" | "holding",\n'
    '  "policy_stance": "hawkish" | "dovish" | "neutral",\n'
    '  "qt_qe_status": "QT ongoing" | "QE ongoing" | "paused" | "unclear",\n'
    '  "rate_level": "current rate level description",\n'
    '  "summary": "policy summary in under 200 words, in Chinese",\n'
    '  "key_events": ["event 1", "event 2", ...],\n'
    '  "outlook": "forward policy outlook, in Chinese",\n'
    '  "sources": ["source 1", "source 2", ...]\n'
    "}\n"
)

POLICY_USER_PROMPT_TEMPLATE = (
    "Below are recent Fed-related news articles (English sources listed first):\n\n"
    "{news_text}\n\n"
    "Distill the current Fed monetary policy stance. "
    "Write summary and outlook in Chinese, events and sources in English."
)


def _is_english_source(source_name: str) -> bool:
    return any(pat.lower() in (source_name or "").lower() for pat in EN_SOURCE_PATTERNS)


async def search_fed_news(hours: int = 168) -> list[dict]:
    """Search DB for Fed-related news, English sources first."""
    from app.repository import get_db

    db = await get_db()
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")

    # Search English keywords first (broader match), then Chinese
    conditions = []
    params: list = []
    for kw in FED_KEYWORDS_EN:
        conditions.append("(n.title LIKE ? OR n.content_snippet LIKE ?)")
        params.extend([f"%{kw}%", f"%{kw}%"])
    for kw in FED_KEYWORDS_CN:
        conditions.append("(n.title LIKE ? OR n.content_snippet LIKE ?)")
        params.extend([f"%{kw}%", f"%{kw}%"])

    where = " OR ".join(conditions)
    params.append(since)

    rows = await db.execute_fetchall(
        f"""SELECT n.id, n.title, n.source, n.url, n.content_snippet, n.created_at,
                   s.score, s.label
            FROM news n
            LEFT JOIN sentiment s ON s.news_id = n.id
            WHERE ({where}) AND n.created_at >= ?
            ORDER BY n.created_at DESC LIMIT 40""",
        params,
    )
    results = [dict(r) for r in rows]

    # Sort: English sources first
    results.sort(key=lambda r: (0 if _is_english_source(r.get("source", "")) else 1, r.get("created_at", "")), reverse=False)
    # Re-sort by time within each group
    en = [r for r in results if _is_english_source(r.get("source", ""))]
    cn = [r for r in results if not _is_english_source(r.get("source", ""))]
    en.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    cn.sort(key=lambda r: r.get("created_at", ""), reverse=True)

    # Return up to 20 EN + 5 CN
    return en[:20] + cn[:5]


async def crawl_fed_news() -> list[dict]:
    """Crawl fresh Fed-related news, English sources prioritized."""
    import aiohttp
    from app.crawler.sources import fetch_all_sources

    try:
        async with aiohttp.ClientSession() as session:
            all_items = await asyncio.wait_for(fetch_all_sources(session), timeout=30)
    except Exception as e:
        logger.warning("Crawl failed for Fed policy: %s", e)
        return []

    # Match using English + Chinese keywords
    lower_keywords = [kw.lower() for kw in FED_KEYWORDS_EN + FED_KEYWORDS_CN]
    en_matched = []
    cn_matched = []
    for item in all_items:
        title = item.title if hasattr(item, "title") else ""
        if not title:
            continue
        title_lower = title.lower()
        if any(kw in title_lower for kw in lower_keywords):
            entry = {
                "title": title,
                "source": item.source if hasattr(item, "source") else "",
                "url": item.url if hasattr(item, "url") else "",
                "content_snippet": item.content_snippet if hasattr(item, "content_snippet") else "",
            }
            if _is_english_source(entry["source"]):
                en_matched.append(entry)
            else:
                cn_matched.append(entry)

    # English first, limit Chinese
    return en_matched[:15] + cn_matched[:3]


def _format_news_text(news_items: list[dict]) -> str:
    """Format news for LLM, English sources first."""
    lines = []
    for i, n in enumerate(news_items[:18], 1):
        source = n.get("source", "")
        title = n.get("title", "")
        snippet = n.get("content_snippet", "")[:150]
        lines.append(f"[{i}] [{source}] {title}")
        if snippet:
            lines.append(f"    {snippet}")
    return "\n".join(lines)


async def generate_policy_summary(news_items: list[dict]) -> dict | None:
    """Use LLM to distill the current Fed policy stance from news."""
    if not news_items:
        return None

    from app.analysis.deepseek_client import DeepSeekClient
    client = DeepSeekClient(deps.settings)

    news_text = _format_news_text(news_items)
    user_prompt = POLICY_USER_PROMPT_TEMPLATE.format(news_text=news_text)

    try:
        result = await asyncio.wait_for(
            client.analyze(POLICY_SYSTEM_PROMPT, user_prompt),
            timeout=45,
        )
    except Exception as e:
        logger.error("Fed policy summary generation failed: %s", e)
        return None

    text = result.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Fed policy summary: LLM returned non-JSON, storing as raw text")
        parsed = {
            "rate_trend": "unclear",
            "policy_stance": "unclear",
            "qt_qe_status": "unclear",
            "rate_level": "",
            "summary": text[:500],
            "key_events": [],
            "outlook": "",
            "sources": [],
        }

    return parsed


async def get_fed_policy(refresh: bool = False) -> dict | None:
    """Get the current Fed policy summary.

    Returns cached summary if fresh (< 1 hour), unless refresh=True.
    """
    from app.repository import load_latest_fed_policy, save_fed_policy_summary

    if not refresh:
        cached = await load_latest_fed_policy(max_age_hours=1)
        if cached:
            return cached

    # Gather news from DB + fresh crawl (English prioritized)
    db_news = await search_fed_news(hours=168)
    crawled = await crawl_fed_news()

    # Merge and deduplicate
    all_news = list(db_news)
    seen_titles = {n.get("title") for n in db_news}
    for item in crawled:
        if item["title"] not in seen_titles:
            all_news.append(item)
            seen_titles.add(item["title"])

    if not all_news:
        return {
            "rate_trend": "no data",
            "policy_stance": "no data",
            "qt_qe_status": "no data",
            "rate_level": "",
            "summary": "未找到近期美联储相关新闻，请稍后再试。",
            "key_events": [],
            "outlook": "",
            "sources": [],
            "news_count": 0,
        }

    summary = await generate_policy_summary(all_news)
    if not summary:
        return None

    summary["news_count"] = len(all_news)

    # Persist
    await save_fed_policy_summary(summary)

    return summary
