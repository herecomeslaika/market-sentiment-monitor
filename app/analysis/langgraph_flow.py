from __future__ import annotations

import asyncio
import logging
from typing import TypedDict

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
RETRY_DELAY = 2.0


class AnalysisState(TypedDict, total=False):
    news_title: str
    news_snippet: str
    sentiment_score: float
    sentiment_label: str
    keywords_matched: list[str]
    web_context: str
    context_summary: str
    risk_assessment: str
    final_report: str
    error: str | None
    retry_count: int


SYSTEM_PROMPT = (
    "你是一位专业的金融市场分析师。请基于提供的财经新闻和情绪数据，"
    "进行深入的市场影响分析。使用中文回答。"
)

_cached_client = None


def _get_client():
    global _cached_client
    if _cached_client is None:
        from app.analysis.deepseek_client import DeepSeekClient
        from app import deps
        _cached_client = DeepSeekClient(deps.settings)
    return _cached_client


async def _retry_analyze(client, system_prompt: str, user_prompt: str, timeout: int = 30, retries: int = MAX_RETRIES) -> str:
    """Call DeepSeek with retry logic."""
    last_error = None
    for attempt in range(retries + 1):
        try:
            result = await asyncio.wait_for(
                client.analyze(system_prompt, user_prompt),
                timeout=timeout,
            )
            return result
        except asyncio.TimeoutError:
            last_error = "timeout"
            logger.warning("DeepSeek call timed out (attempt %d/%d)", attempt + 1, retries + 1)
        except Exception as e:
            last_error = str(e)
            logger.warning("DeepSeek call failed (attempt %d/%d): %s", attempt + 1, retries + 1, e)

        if attempt < retries:
            await asyncio.sleep(RETRY_DELAY * (attempt + 1))

    raise RuntimeError(f"DeepSeek call failed after {retries + 1} attempts: {last_error}")


async def search_web_context(state: AnalysisState) -> dict:
    """Search the web for related context using DuckDuckGo HTML search."""
    keywords = state.get("keywords_matched", [])
    title = state.get("news_title", "")
    query = title if title else " ".join(keywords[:3])

    import aiohttp

    for attempt in range(MAX_RETRIES + 1):
        try:
            async with aiohttp.ClientSession() as session:
                params = {"q": f"{query} 财经", "kl": "cn-zh"}
                headers = {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                    ),
                }
                async with session.get(
                    "https://html.duckduckgo.com/html/",
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        if attempt < MAX_RETRIES:
                            await asyncio.sleep(1)
                            continue
                        return {"web_context": ""}
                    html = await resp.text()

                    import re
                    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
                    snippets = [re.sub(r"<[^>]+>", "", s).strip() for s in snippets[:5]]
                    web_context = "\n".join(f"- {s}" for s in snippets if s)
                    return {"web_context": web_context}
        except Exception as e:
            logger.warning("Web search failed (attempt %d/%d): %s", attempt + 1, MAX_RETRIES + 1, e)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(1)

    return {"web_context": ""}


async def gather_context(state: AnalysisState) -> dict:
    client = _get_client()
    web_ctx = state.get("web_context", "")
    web_section = f"\n网络搜索参考：\n{web_ctx}" if web_ctx else ""

    user_prompt = (
        f"新闻标题：{state.get('news_title', '')}\n"
        f"新闻摘要：{state.get('news_snippet', '')}\n"
        f"情绪得分：{state.get('sentiment_score', 0)} ({state.get('sentiment_label', '')})\n"
        f"匹配关键词：{', '.join(state.get('keywords_matched', []))}\n"
        f"{web_section}\n\n"
        "请总结这条新闻的市场背景和潜在影响。"
    )
    try:
        result = await _retry_analyze(client, SYSTEM_PROMPT, user_prompt)
        return {"context_summary": result}
    except Exception as e:
        logger.error("gather_context failed: %s", e)
        return {"context_summary": f"背景分析不可用: {e}", "error": str(e)}


async def assess_risk(state: AnalysisState) -> dict:
    if state.get("error"):
        return {}

    client = _get_client()
    user_prompt = (
        f"市场背景：{state.get('context_summary', '')}\n"
        f"情绪得分：{state.get('sentiment_score', 0)}\n\n"
        "请评估风险等级（高/中/低），并提供可操作的交易建议。"
    )
    try:
        result = await _retry_analyze(client, SYSTEM_PROMPT, user_prompt)
        return {"risk_assessment": result}
    except Exception as e:
        logger.error("assess_risk failed: %s", e)
        return {"risk_assessment": f"风险评估不可用: {e}", "error": str(e)}


async def compose_report(state: AnalysisState) -> dict:
    client = _get_client()
    has_error = state.get("error")
    error_note = "\n注意：部分分析步骤未完成，研报可能不完整。" if has_error else ""

    user_prompt = (
        f"新闻：{state.get('news_title', '')}\n"
        f"情绪：{state.get('sentiment_score', 0)} ({state.get('sentiment_label', '')})\n"
        f"市场背景：{state.get('context_summary', '（不可用）')}\n"
        f"风险评估：{state.get('risk_assessment', '（不可用）')}\n"
        f"{error_note}\n\n"
        "请将以上内容整合为一份简洁的研报，包含：1) 事件概述 2) 市场影响 3) 风险等级 4) 操作建议。"
    )
    try:
        result = await _retry_analyze(client, SYSTEM_PROMPT, user_prompt)
        return {"final_report": result}
    except Exception as e:
        logger.error("compose_report failed: %s", e)
        return {"final_report": f"研报生成失败: {e}", "error": str(e)}


def _should_continue(state: AnalysisState) -> str:
    if state.get("error"):
        return "compose_report"
    return "next"


def build_graph():
    from langgraph.graph import END, StateGraph

    graph = StateGraph(AnalysisState)
    graph.add_node("search_web_context", search_web_context)
    graph.add_node("gather_context", gather_context)
    graph.add_node("assess_risk", assess_risk)
    graph.add_node("compose_report", compose_report)

    graph.set_entry_point("search_web_context")
    graph.add_edge("search_web_context", "gather_context")
    graph.add_conditional_edges(
        "gather_context",
        _should_continue,
        {"next": "assess_risk", "compose_report": "compose_report"},
    )
    graph.add_conditional_edges(
        "assess_risk",
        _should_continue,
        {"next": "compose_report", "compose_report": "compose_report"},
    )
    graph.add_edge("compose_report", END)

    return graph


_compiled_graph = None


def get_compiled_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph().compile()
    return _compiled_graph
