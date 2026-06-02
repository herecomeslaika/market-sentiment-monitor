"""On-demand report generation from user intent.

Flow:
1. Extract search keywords from user intent via LLM
2. Search recent news from DB matching keywords
3. Crawl fresh news if DB results are insufficient
4. Run LangGraph analysis to generate deep report
5. Store and return the report
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app import deps
from app.models import AlertPayload, NewsItem, SentimentResult

logger = logging.getLogger(__name__)

KEYWORD_EXTRACTION_PROMPT = (
    "你是一个金融新闻搜索助手。用户会输入一个中文投资意图或研究主题，"
    "你需要从中提取搜索关键词，包含中文和英文，用于在新闻数据库中匹配中英文文章。\n\n"
    "要求：\n"
    "- 提取3-5个中文关键词（精确词）\n"
    "- 同时提取对应的3-5个英文关键词（使用金融领域常用术语，尽量宽泛以便匹配更多海外新闻）\n"
    "- 例如用户输入「降息对银行的影响」，应返回：\n"
    "  [\"降息\", \"银行\", \"LPR\", \"rate cut\", \"interest rate\", \"bank\", \"Fed\"]\n"
    "- 又如「美联储加息对黄金的影响」，应返回：\n"
    "  [\"美联储\", \"加息\", \"黄金\", \"Fed\", \"rate hike\", \"gold\", \"interest rate\"]\n\n"
    "只返回JSON数组，不要其他内容。"
)


async def extract_keywords(intent: str) -> list[str]:
    """Use LLM to extract search keywords from user intent."""
    from app.analysis.deepseek_client import DeepSeekClient

    client = DeepSeekClient(deps.settings)
    try:
        result = await asyncio.wait_for(
            client.analyze(KEYWORD_EXTRACTION_PROMPT, intent),
            timeout=15,
        )
        # Parse JSON array from response
        text = result.strip()
        # Handle cases where LLM wraps in markdown code block
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        keywords = json.loads(text)
        if isinstance(keywords, list):
            return [str(k).strip() for k in keywords if str(k).strip()]
    except (json.JSONDecodeError, asyncio.TimeoutError, Exception) as e:
        logger.warning("Keyword extraction failed, using fallback: %s", e)

    # Fallback: simple split
    return [w for w in intent.replace("的", " ").split() if len(w) >= 2][:5]


async def search_recent_news(keywords: list[str], hours: int = 24) -> list[dict]:
    """Search recent news from DB matching any keyword."""
    from app.repository import get_db

    db = await get_db()
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")

    # Build LIKE conditions for each keyword
    conditions = []
    params: list = []
    for kw in keywords:
        conditions.append("(n.title LIKE ? OR n.content_snippet LIKE ?)")
        params.extend([f"%{kw}%", f"%{kw}%"])

    where = " OR ".join(conditions) if conditions else "1=1"
    params.append(since)

    rows = await db.execute_fetchall(
        f"""SELECT n.id, n.title, n.source, n.url, n.content_snippet, n.created_at,
                   s.score, s.label, s.confidence
            FROM news n
            LEFT JOIN sentiment s ON s.news_id = n.id
            WHERE ({where}) AND n.created_at >= ?
            ORDER BY n.created_at DESC LIMIT 20""",
        params,
    )
    return [dict(r) for r in rows]


async def crawl_fresh_news(keywords: list[str]) -> list[dict]:
    """Crawl fresh news matching keywords to supplement DB results."""
    import aiohttp
    from app.crawler.sources import fetch_all_sources

    try:
        async with aiohttp.ClientSession() as session:
            all_items = await asyncio.wait_for(fetch_all_sources(session), timeout=30)
    except Exception as e:
        logger.warning("Crawl failed during intent report: %s", e)
        return []

    # Filter by keyword match (case-insensitive for English)
    lower_keywords = [k.lower() for k in keywords]
    matched = []
    for item in all_items:
        title = item.title if hasattr(item, "title") else item.get("title", "")
        if not title:
            continue
        title_lower = title.lower()
        if any(kw in title_lower for kw in lower_keywords):
            matched.append({
                "title": title,
                "source": item.source if hasattr(item, "source") else item.get("source", ""),
                "url": item.url if hasattr(item, "url") else item.get("url", ""),
                "content_snippet": item.content_snippet if hasattr(item, "content_snippet") else item.get("content_snippet", ""),
            })
    return matched


async def generate_analysis(intent: str, news_items: list[dict]) -> str | None:
    """Run LangGraph-style analysis on the gathered news, enriched with entity/relation data."""
    from app.analysis.deepseek_client import DeepSeekClient

    client = DeepSeekClient(deps.settings)

    # Build context from news items (with numbered references and links)
    news_context = ""
    for i, n in enumerate(news_items[:8], 1):
        title = n.get("title", "")
        source = n.get("source", "")
        url = n.get("url", "")
        snippet = n.get("content_snippet", "")
        news_context += f"[{i}] 【{source}】{title}\n"
        if url:
            news_context += f"    链接: {url}\n"
        if snippet:
            news_context += f"    摘要: {snippet[:200]}\n"
        news_context += "\n"

    # Look up entities and relations for related news
    entity_info = ""
    relation_info = ""
    causal_info = ""
    try:
        from app.repository import load_entities_for_news_items, load_relations_for_context
        news_ids = [n.get("id") for n in news_items if n.get("id")]
        if news_ids:
            all_entities = await load_entities_for_news_items(news_ids)
            if all_entities:
                entity_lines = [f"- {e['name']}({e['type']})" for e in all_entities[:10]]
                entity_info = "\n相关实体:\n" + "\n".join(entity_lines)
            relations = await load_relations_for_context([e['name'] for e in (all_entities or [])[:5]])
            if relations:
                relation_lines = [f"- {r['source']} --[{r['relation']}]--> {r['target']}" for r in relations[:8]]
                relation_info = "\n实体关系:\n" + "\n".join(relation_lines)
            if all_entities and relations:
                causal_prompt = (
                    f"相关实体: {', '.join(e['name'] for e in all_entities[:5])}\n"
                    f"关系: {', '.join(f'{r['source']}->{r['target']}' for r in relations[:5])}\n"
                    f"新闻背景: {intent}\n\n"
                    "请推理最关键的一条因果传导链，格式：触发→路径→影响。简要回答。"
                )
                try:
                    causal_result = await asyncio.wait_for(
                        client.analyze("你是金融因果推理专家。", causal_prompt),
                        timeout=15,
                    )
                    causal_info = f"\n因果推理: {causal_result.strip()}"
                except Exception:
                    pass
    except Exception as e:
        logger.warning("Knowledge lookup for intent report failed: %s", e)

    # Step 1: Background analysis
    system_prompt = (
        "你是一位专业的金融市场分析师。用户提出了一个投资研究意图，"
        "你需要在以下新闻的基础上，分析该主题的市场背景和现状。使用中文回答，要有深度。"
    )
    user_prompt = f"研究意图：{intent}\n\n相关新闻：\n{news_context}{entity_info}{relation_info}{causal_info}"

    try:
        background = await asyncio.wait_for(
            client.analyze(system_prompt, user_prompt),
            timeout=30,
        )
    except Exception as e:
        logger.error("Background analysis failed: %s", e)
        return None

    # Step 2: Risk assessment
    risk_prompt = (
        f"研究意图：{intent}\n"
        f"背景分析：{background}\n\n"
        "请基于以上分析，评估该主题相关的投资风险和不确定性因素。"
        "包括政策风险、市场情绪风险、行业竞争等。使用中文回答。"
    )
    try:
        risk = await asyncio.wait_for(
            client.analyze(system_prompt, risk_prompt),
            timeout=30,
        )
    except Exception as e:
        logger.warning("Risk assessment failed: %s", e)
        risk = "风险评估未能生成。"

    # Step 3: Synthesize final report
    final_prompt = (
        f"研究意图：{intent}\n"
        f"相关新闻：\n{news_context}\n\n"
        f"{entity_info}{relation_info}{causal_info}\n\n"
        f"背景分析：{background}\n\n"
        f"风险评估：{risk}\n\n"
        "请综合以上信息，撰写一份结构完整的深度研报。"
        "包含：1) 核心观点 2) 涉及实体及关系 3) 因果传导路径 4) 风险提示 5) 行动建议。使用中文。"
    )
    try:
        report = await asyncio.wait_for(
            client.analyze(system_prompt, final_prompt),
            timeout=45,
        )
        return report
    except Exception as e:
        logger.error("Final report generation failed: %s", e)
        return None


async def run(intent: str, hours: int = 168) -> dict | None:
    """Full pipeline: extract keywords → search news → generate report → store."""
    # Step 1: Extract bilingual keywords
    keywords = await extract_keywords(intent)
    logger.info("Intent '%s' → keywords: %s", intent, keywords)

    # Step 2: Search DB for recent matching news (Chinese + English keywords)
    db_news = await search_recent_news(keywords, hours)

    # Step 3: Always crawl fresh news to get overseas sources
    crawled = await crawl_fresh_news(keywords)

    # Merge and deduplicate by title
    news_items = list(db_news)
    seen_titles = {n.get("title") for n in db_news}
    for item in crawled:
        if item["title"] not in seen_titles:
            news_items.append(item)
            seen_titles.add(item["title"])

    if not news_items:
        return {"error": "未找到与该意图相关的最近新闻，请尝试换一个主题或稍后再试"}

    # Step 4: Generate analysis
    deep_analysis = await generate_analysis(intent, news_items)
    if not deep_analysis:
        return {"error": "研报生成失败，请稍后重试"}

    # Step 5: Build and store report
    report_id = f"r_{uuid4().hex[:12]}"
    # Use first news item for metadata, or intent itself
    primary = news_items[0]
    alert = AlertPayload(
        news_item=NewsItem(
            source=primary.get("source", "on-demand"),
            title=intent,
            url=primary.get("url", ""),
            content_snippet=primary.get("content_snippet", ""),
        ),
        sentiment=SentimentResult(
            news_item=NewsItem(source="on-demand", title=intent),
            score=primary.get("score", 0.0) or 0.0,
            label=primary.get("label", "neutral") or "neutral",
            confidence=primary.get("confidence", 0.0) or 0.0,
        ),
        alert_level="info",
        triggered_keywords=keywords,
        deep_analysis=deep_analysis,
    )

    # Build referenced news list with links
    referenced_news = [
        {"title": n.get("title", ""), "source": n.get("source", ""), "url": n.get("url", "")}
        for n in news_items
    ]

    from app.repository import save_report
    await save_report(report_id, alert, referenced_news=referenced_news)

    return {
        "report_id": report_id,
        "news_count": len(news_items),
        "keywords": keywords,
        "deep_analysis": deep_analysis,
        "alert_level": "info",
        "news_title": intent,
        "news_source": "on-demand",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "referenced_news": referenced_news,
    }
