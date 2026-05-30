from __future__ import annotations

import asyncio
import logging

from langchain_deepseek import ChatDeepSeek

from config.settings import Settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
RETRY_DELAY = 1.0


class DeepSeekClient:
    def __init__(self, settings: Settings):
        self.llm = ChatDeepSeek(
            model=settings.deepseek_model,
            temperature=settings.deepseek_temperature,
            max_tokens=settings.deepseek_max_tokens,
            api_key=settings.deepseek_api_key,
        )

    async def analyze(self, system_prompt: str, user_prompt: str, retries: int = MAX_RETRIES) -> str:
        messages = [
            ("system", system_prompt),
            ("human", user_prompt),
        ]
        last_error = None
        for attempt in range(retries + 1):
            try:
                response = await self.llm.ainvoke(messages)
                return response.content
            except asyncio.TimeoutError:
                last_error = "timeout"
                logger.warning("DeepSeek API timeout (attempt %d/%d)", attempt + 1, retries + 1)
            except Exception as e:
                last_error = str(e)
                logger.warning("DeepSeek API error (attempt %d/%d): %s", attempt + 1, retries + 1, e)

            if attempt < retries:
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))

        logger.error("DeepSeek API failed after %d attempts: %s", retries + 1, last_error)
        raise RuntimeError(f"DeepSeek API failed: {last_error}")
