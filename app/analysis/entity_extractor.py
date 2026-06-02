"""Extract structured entities from news using LLM."""
from __future__ import annotations

import asyncio
import json
import logging
from collections import OrderedDict

from app import deps
from app.models import Entity

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = (
    "你是一个金融实体识别专家。从以下新闻中提取关键实体，包括：\n"
    "- company: 公司/机构名称\n"
    "- industry: 行业/板块\n"
    "- policy: 政策/法规/事件\n"
    "- indicator: 经济指标/数据\n"
    "- person: 重要人物\n\n"
    "返回JSON数组，每个元素含 name, type, aliases 字段。aliases 是该实体的其他称呼。\n"
    "只返回JSON，不要其他内容。例如：\n"
    '[{"name": "工商银行", "type": "company", "aliases": ["ICBC", "工行"]}]'
)

# Cache: title_hash -> list[Entity] to avoid re-extraction
_extraction_cache: OrderedDict[str, list[Entity]] = {}
_CACHE_MAX = 2000

# Semaphore to limit concurrent LLM calls
_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(3)
    return _semaphore


def _parse_entities(text: str) -> list[Entity]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        items = json.loads(text)
        if not isinstance(items, list):
            return []
        entities = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("name", "").strip()
            etype = item.get("type", "").strip()
            if not name or etype not in ("company", "industry", "policy", "indicator", "person"):
                continue
            aliases = item.get("aliases", [])
            if not isinstance(aliases, list):
                aliases = []
            entities.append(Entity(name=name, type=etype, aliases=[str(a).strip() for a in aliases if str(a).strip()]))
        return entities
    except json.JSONDecodeError:
        return []


async def extract_entities(title: str, snippet: str = "", title_hash: str = "") -> list[Entity]:
    """Extract entities from a single news item."""
    if title_hash and title_hash in _extraction_cache:
        return _extraction_cache[title_hash]

    from app.analysis.deepseek_client import DeepSeekClient
    client = DeepSeekClient(deps.settings)

    text = title
    if snippet:
        text += f"\n{snippet[:200]}"

    async with _get_semaphore():
        try:
            result = await asyncio.wait_for(
                client.analyze(EXTRACTION_PROMPT, text),
                timeout=15,
            )
            entities = _parse_entities(result)
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning("Entity extraction failed: %s", e)
            entities = []

    if title_hash and entities:
        _extraction_cache[title_hash] = entities
        if len(_extraction_cache) > _CACHE_MAX:
            _extraction_cache.popitem(last=False)

    return entities


async def extract_entities_batch(items: list[dict]) -> dict[int, list[Entity]]:
    """Extract entities from multiple news items in batch (5 per LLM call)."""
    from app.analysis.deepseek_client import DeepSeekClient
    client = DeepSeekClient(deps.settings)

    results: dict[int, list[Entity]] = {}
    batch_size = 5

    for start in range(0, len(items), batch_size):
        batch = items[start:start + batch_size]
        # Check cache first
        uncached = []
        for i, item in enumerate(batch):
            idx = start + i
            th = item.get("title_hash", "")
            if th and th in _extraction_cache:
                results[idx] = _extraction_cache[th]
            else:
                uncached.append((idx, item))

        if not uncached:
            continue

        # Build combined prompt for uncached items
        news_text = "\n---\n".join(
            f"新闻{ j + 1}: {item.get('title', '')}"
            + (f"\n摘要: {item.get('content_snippet', '')[:150]}" if item.get("content_snippet") else "")
            for j, (_, item) in enumerate(uncached)
        )

        batch_prompt = (
            "你是一个金融实体识别专家。从以下多条新闻中分别提取关键实体。\n"
            "实体类型: company(公司), industry(行业), policy(政策), indicator(指标), person(人物)\n"
            "返回JSON数组，每个元素含 news_index(从1开始), name, type, aliases。\n"
            "只返回JSON。例如：\n"
            '[{"news_index": 1, "name": "工商银行", "type": "company", "aliases": ["ICBC"]}]'
        )

        async with _get_semaphore():
            try:
                result = await asyncio.wait_for(
                    client.analyze(batch_prompt, news_text),
                    timeout=20,
                )
                parsed = _parse_batch_result(result)
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning("Batch entity extraction failed: %s", e)
                parsed = {}

        for j, (idx, item) in enumerate(uncached):
            entities = parsed.get(j + 1, [])
            results[idx] = entities
            th = item.get("title_hash", "")
            if th and entities:
                _extraction_cache[th] = entities
                if len(_extraction_cache) > _CACHE_MAX:
                    _extraction_cache.popitem(last=False)

    return results


def _parse_batch_result(text: str) -> dict[int, list[Entity]]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        items = json.loads(text)
        if not isinstance(items, list):
            return {}
        result: dict[int, list[Entity]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            idx = item.get("news_index", 0)
            if not isinstance(idx, int) or idx < 1:
                continue
            name = item.get("name", "").strip()
            etype = item.get("type", "").strip()
            if not name or etype not in ("company", "industry", "policy", "indicator", "person"):
                continue
            aliases = item.get("aliases", [])
            if not isinstance(aliases, list):
                aliases = []
            entity = Entity(name=name, type=etype, aliases=[str(a).strip() for a in aliases if str(a).strip()])
            result.setdefault(idx, []).append(entity)
        return result
    except json.JSONDecodeError:
        return {}


async def extract_and_save(news_id: int, title: str, snippet: str = "", title_hash: str = "") -> list[Entity]:
    """Extract entities and persist to DB."""
    entities = await extract_entities(title, snippet, title_hash)
    if entities and news_id:
        from app.repository import save_entities
        await save_entities(news_id, entities)
    return entities
