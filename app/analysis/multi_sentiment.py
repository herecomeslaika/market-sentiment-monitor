"""Multi-dimensional sentiment analysis with momentum detection."""
from __future__ import annotations

import asyncio
import json
import logging

from app import deps
from app.models import Entity, MultiSentiment

logger = logging.getLogger(__name__)

MULTI_SENTIMENT_PROMPT = (
    "你是一个金融市场情绪分析专家。分析以下金融新闻，从四个维度评估情绪强度（0到1的浮点数）：\n"
    "- fear: 恐惧程度（市场恐慌、避险情绪、利空信号）\n"
    "- greed: 贪婪程度（追涨情绪、过度乐观、泡沫信号）\n"
    "- optimism: 乐观程度（积极预期、增长信号、利好因素）\n"
    "- uncertainty: 不确定性（模糊信号、矛盾信息、政策不明确）\n\n"
    "返回JSON，包含 fear, greed, optimism, uncertainty 四个0-1的数值，"
    "以及 dominant（最突出的情绪维度，如无突出则填neutral）。"
    "只返回JSON。例如：{\"fear\": 0.2, \"greed\": 0.7, \"optimism\": 0.6, \"uncertainty\": 0.3, \"dominant\": \"greed\"}"
)

MOMENTUM_THRESHOLD = 0.3


def _parse_multi_sentiment(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            return None
        for key in ("fear", "greed", "optimism", "uncertainty"):
            if key not in data:
                return None
            data[key] = max(0.0, min(1.0, float(data[key])))
        if "dominant" not in data:
            scores = {k: data[k] for k in ("fear", "greed", "optimism", "uncertainty")}
            max_dim = max(scores, key=scores.get)
            data["dominant"] = max_dim if scores[max_dim] > 0.5 else "neutral"
        if data["dominant"] not in ("fear", "greed", "optimism", "uncertainty", "neutral"):
            data["dominant"] = "neutral"
        return data
    except (json.JSONDecodeError, ValueError):
        return None


async def analyze_sentiment(title: str, snippet: str = "") -> MultiSentiment | None:
    """Analyze multi-dimensional sentiment for a news item."""
    from app.analysis.deepseek_client import DeepSeekClient
    client = DeepSeekClient(deps.settings)

    text = title
    if snippet:
        text += f"\n{snippet[:300]}"

    try:
        result = await asyncio.wait_for(
            client.analyze(MULTI_SENTIMENT_PROMPT, text),
            timeout=15,
        )
        parsed = _parse_multi_sentiment(result)
        if not parsed:
            return None
        return MultiSentiment(
            news_id=0,
            fear=parsed["fear"],
            greed=parsed["greed"],
            optimism=parsed["optimism"],
            uncertainty=parsed["uncertainty"],
            dominant=parsed["dominant"],
        )
    except (asyncio.TimeoutError, Exception) as e:
        logger.warning("Multi-sentiment analysis failed: %s", e)
        return None


async def compute_momentum(entity_name: str, current: MultiSentiment) -> tuple[float, bool]:
    """Compute sentiment momentum for an entity compared to its last measurement.

    Returns (momentum_value, is_shift).
    """
    from app.repository import load_last_multi_sentiment
    last = await load_last_multi_sentiment(entity_name)
    if not last:
        return 0.0, False

    # Average absolute change across dimensions
    dims = ("fear", "greed", "optimism", "uncertainty")
    changes = [abs(getattr(current, d) - last.get(d, 0.0) if isinstance(last, dict) else getattr(current, d) - getattr(last, d)) for d in dims]
    momentum = round(sum(changes) / len(changes), 3)

    # Detect if any single dimension had a large shift
    is_shift = any(c > MOMENTUM_THRESHOLD for c in changes)
    return momentum, is_shift


async def analyze_and_save(
    news_id: int,
    title: str,
    snippet: str = "",
    entities: list[Entity] | None = None,
) -> MultiSentiment | None:
    """Analyze multi-sentiment, compute momentum, and persist to DB."""
    ms = await analyze_sentiment(title, snippet)
    if not ms:
        return None

    ms.news_id = news_id

    # Compute momentum for each entity
    if entities:
        primary = entities[0].name
        ms.entity_name = primary
        momentum, is_shift = await compute_momentum(primary, ms)
        ms.momentum = momentum
        ms.momentum_shift = is_shift

    from app.repository import save_multi_sentiment
    await save_multi_sentiment(ms)
    return ms
