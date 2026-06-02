"""Knowledge graph construction and causal chain inference."""
from __future__ import annotations

import asyncio
import json
import logging

from app import deps
from app.models import CausalChain, Entity, EntityRelation, EventCluster

logger = logging.getLogger(__name__)

RELATION_EXTRACTION_PROMPT = (
    "你是一个金融知识图谱构建专家。从以下新闻和实体中提取实体间的关系。\n"
    "关系类型：\n"
    "- affects: A影响B（如利率影响银行利润）\n"
    "- belongs_to: A属于B（如工商银行属于银行业）\n"
    "- causes: A导致B（如降息导致房贷需求上升）\n"
    "- correlates: A与B相关（如金价与美元指数负相关）\n\n"
    "返回JSON数组，每个元素含 source, target, relation, context, confidence(0-1)。\n"
    "只返回JSON。例如：\n"
    '[{"source": "央行降息", "target": "银行利润", "relation": "affects", "context": "降息压缩银行利差", "confidence": 0.8}]'
)

CAUSAL_CHAIN_PROMPT = (
    "你是一个金融因果推理专家。基于以下实体关系和新闻背景，推理事件的影响传播链。\n"
    "输出一条因果链，包含：\n"
    "- trigger: 触发事件\n"
    "- path: 传播路径（从原因到结果的实体序列）\n"
    "- impact: 最终影响\n"
    "- confidence: 置信度(0-1)\n\n"
    "返回JSON。例如：\n"
    '{"trigger": "央行降息", "path": ["央行降息", "银行利差收窄", "房贷利率下降", "房贷需求上升"], '
    '"impact": "房地产板块利好", "confidence": 0.75}\n'
    "只返回JSON。"
)


def _parse_relations(text: str) -> list[EntityRelation]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        items = json.loads(text)
        if not isinstance(items, list):
            return []
        relations = []
        for item in items:
            if not isinstance(item, dict):
                continue
            source = item.get("source", "").strip()
            target = item.get("target", "").strip()
            relation = item.get("relation", "").strip()
            if not source or not target or relation not in ("affects", "belongs_to", "causes", "correlates"):
                continue
            context = item.get("context", "").strip()
            confidence = item.get("confidence", 0.5)
            try:
                confidence = max(0.0, min(1.0, float(confidence)))
            except (ValueError, TypeError):
                confidence = 0.5
            relations.append(EntityRelation(
                source=source, target=target, relation=relation,
                context=context, confidence=confidence,
            ))
        return relations
    except json.JSONDecodeError:
        return []


def _parse_causal_chain(text: str) -> CausalChain | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            return None
        trigger = data.get("trigger", "").strip()
        path = data.get("path", [])
        impact = data.get("impact", "").strip()
        confidence = data.get("confidence", 0.5)
        if not trigger or not isinstance(path, list) or not path:
            return None
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (ValueError, TypeError):
            confidence = 0.5
        return CausalChain(
            trigger=trigger,
            path=[str(p).strip() for p in path if str(p).strip()],
            impact=impact,
            confidence=confidence,
        )
    except json.JSONDecodeError:
        return None


async def extract_relations(
    title: str,
    snippet: str = "",
    entities: list[Entity] | None = None,
    news_id: int | None = None,
) -> list[EntityRelation]:
    """Extract entity relations from news text."""
    if not entities or len(entities) < 2:
        return []

    from app.analysis.deepseek_client import DeepSeekClient
    client = DeepSeekClient(deps.settings)

    entity_names = ", ".join(f"{e.name}({e.type})" for e in entities[:8])
    text = f"新闻: {title}"
    if snippet:
        text += f"\n摘要: {snippet[:300]}"
    text += f"\n涉及的实体: {entity_names}"

    try:
        result = await asyncio.wait_for(
            client.analyze(RELATION_EXTRACTION_PROMPT, text),
            timeout=15,
        )
        relations = _parse_relations(result)
    except (asyncio.TimeoutError, Exception) as e:
        logger.warning("Relation extraction failed: %s", e)
        return []

    # Persist relations
    if relations and news_id:
        from app.repository import save_relations
        await save_relations(relations, news_id)

    return relations


async def infer_causal_chain(
    entities: list[Entity],
    relations: list[EntityRelation],
    news_context: str,
) -> CausalChain | None:
    """Infer a causal chain from entities and their relations."""
    if not entities or not relations:
        return None

    from app.analysis.deepseek_client import DeepSeekClient
    client = DeepSeekClient(deps.settings)

    entity_text = ", ".join(e.name for e in entities[:8])
    relation_text = "\n".join(
        f"- {r.source} --[{r.relation}]--> {r.target} (依据: {r.context})"
        for r in relations[:10]
    )

    user_prompt = (
        f"新闻背景: {news_context[:300]}\n\n"
        f"相关实体: {entity_text}\n\n"
        f"实体关系:\n{relation_text}\n\n"
        "请推理最关键的一条因果传播链。"
    )

    try:
        result = await asyncio.wait_for(
            client.analyze(CAUSAL_CHAIN_PROMPT, user_prompt),
            timeout=20,
        )
        return _parse_causal_chain(result)
    except (asyncio.TimeoutError, Exception) as e:
        logger.warning("Causal chain inference failed: %s", e)
        return None


async def extract_relations_and_infer(
    cluster: EventCluster,
    news_title: str = "",
    news_snippet: str = "",
) -> tuple[list[EntityRelation], CausalChain | None]:
    """Extract relations from an event cluster and infer causal chain."""
    relations = await extract_relations(
        title=cluster.title or news_title,
        snippet=news_snippet,
        entities=cluster.entities,
    )

    causal_chain = None
    if relations:
        context = cluster.title
        if news_snippet:
            context += f" {news_snippet[:200]}"
        causal_chain = await infer_causal_chain(cluster.entities, relations, context)

    return relations, causal_chain
