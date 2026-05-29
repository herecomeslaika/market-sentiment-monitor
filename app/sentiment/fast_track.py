from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from app import deps
from app.models import SentimentResult
from app.sentiment.finbert_worker import score_text

logger = logging.getLogger(__name__)


async def process_news_item(item) -> SentimentResult:
    loop = asyncio.get_running_loop()
    score, label, confidence = await loop.run_in_executor(
        deps.finbert_pool, score_text, item.title
    )
    return SentimentResult(
        news_item=item,
        score=score,
        label=label,
        confidence=confidence,
        processed_at=datetime.now(),
    )


async def fast_track_consumer():
    from app.repository import save_news, save_sentiment

    logger.info("Fast track consumer started")
    while True:
        try:
            item = await deps.news_queue.get()
            result = await process_news_item(item)

            # Persist to database
            news_id = await save_news(item)
            sentiment_db_id = None
            if news_id:
                sentiment_db_id = await save_sentiment(news_id, result)

            result.news_db_id = news_id
            result.sentiment_db_id = sentiment_db_id

            await deps.scored_queue.put(result)
            logger.debug("Scored: %.3f (%s) - %s", result.score, result.label, item.title[:40])
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Fast track error: %s", e, exc_info=True)
            await asyncio.sleep(1)
