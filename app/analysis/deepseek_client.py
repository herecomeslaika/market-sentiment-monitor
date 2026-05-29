from __future__ import annotations

import logging

from langchain_deepseek import ChatDeepSeek

from config.settings import Settings

logger = logging.getLogger(__name__)


class DeepSeekClient:
    def __init__(self, settings: Settings):
        self.llm = ChatDeepSeek(
            model=settings.deepseek_model,
            temperature=settings.deepseek_temperature,
            max_tokens=settings.deepseek_max_tokens,
            api_key=settings.deepseek_api_key,
        )

    async def analyze(self, system_prompt: str, user_prompt: str) -> str:
        messages = [
            ("system", system_prompt),
            ("human", user_prompt),
        ]
        try:
            response = await self.llm.ainvoke(messages)
            return response.content
        except Exception as e:
            logger.error("DeepSeek API error: %s", e, exc_info=True)
            raise
