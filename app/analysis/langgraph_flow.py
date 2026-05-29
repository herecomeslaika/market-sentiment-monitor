from __future__ import annotations

import asyncio
import logging
from typing import TypedDict

logger = logging.getLogger(__name__)


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


async def search_web_context(state: AnalysisState) -> dict:
    """Search the web for related context using aiohttp to query a search API."""
    keywords = state.get("keywords_matched", [])
    title = state.get("news_title", "")
    query = title if title else " ".join(keywords[:3])

    import aiohttp
    from app import deps

    try:
        async with aiohttp.ClientSession() as session:
            # Use DuckDuckGo HTML search as a free search source
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
                    return {"web_context": ""}
                html = await resp.text()

                # Extract result snippets from HTML
                import re
                snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
                snippets = [re.sub(r"<[^>]+>", "", s).strip() for s in snippets[:5]]
                web_context = "\n".join(f"- {s}" for s in snippets if s)
                return {"web_context": web_context}
    except Exception as e:
        logger.warning("Web search failed: %s", e)
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
        result = await asyncio.wait_for(
            client.analyze(SYSTEM_PROMPT, user_prompt),
            timeout=30,
        )
        return {"context_summary": result}
    except asyncio.TimeoutError:
        return {"context_summary": "分析超时", "error": "gather_context timeout"}
    except Exception as e:
        return {"context_summary": f"分析失败: {e}", "error": str(e)}


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
        result = await asyncio.wait_for(
            client.analyze(SYSTEM_PROMPT, user_prompt),
            timeout=30,
        )
        return {"risk_assessment": result}
    except asyncio.TimeoutError:
        return {"risk_assessment": "风险评估超时", "error": "assess_risk timeout"}
    except Exception as e:
        return {"risk_assessment": f"风险评估失败: {e}", "error": str(e)}


async def compose_report(state: AnalysisState) -> dict:
    if state.get("error"):
        return {"final_report": f"分析不完整: {state.get('error', 'unknown error')}"}

    client = _get_client()
    user_prompt = (
        f"新闻：{state.get('news_title', '')}\n"
        f"情绪：{state.get('sentiment_score', 0)} ({state.get('sentiment_label', '')})\n"
        f"市场背景：{state.get('context_summary', '')}\n"
        f"风险评估：{state.get('risk_assessment', '')}\n\n"
        "请将以上内容整合为一份简洁的研报，包含：1) 事件概述 2) 市场影响 3) 风险等级 4) 操作建议。"
    )
    try:
        result = await asyncio.wait_for(
            client.analyze(SYSTEM_PROMPT, user_prompt),
            timeout=30,
        )
        return {"final_report": result}
    except asyncio.TimeoutError:
        return {"final_report": "研报生成超时", "error": "compose_report timeout"}
    except Exception as e:
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
