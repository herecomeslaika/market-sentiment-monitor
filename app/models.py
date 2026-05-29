from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class NewsItem(BaseModel):
    source: str
    title: str
    url: str = ""
    published_at: datetime = Field(default_factory=datetime.now)
    content_snippet: str = ""
    title_hash: str = ""


class SentimentResult(BaseModel):
    news_item: NewsItem
    score: float = Field(ge=-1.0, le=1.0)
    label: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    processed_at: datetime = Field(default_factory=datetime.now)
    news_db_id: int | None = None
    sentiment_db_id: int | None = None


class AlertPayload(BaseModel):
    news_item: NewsItem
    sentiment: SentimentResult
    deep_analysis: str | None = None
    triggered_keywords: list[str] = Field(default_factory=list)
    alert_level: str = "warning"
    created_at: datetime = Field(default_factory=datetime.now)


class Subscription(BaseModel):
    user_id: str
    keywords: list[str]
    threshold: float = -0.5


class WSMessage(BaseModel):
    type: str  # "alert" | "sentiment_update" | "status"
    payload: dict
    timestamp: datetime = Field(default_factory=datetime.now)


class SubscriptionCommand(BaseModel):
    action: str  # "subscribe" | "unsubscribe"
    keywords: list[str] = Field(default_factory=list)
    threshold: float = -0.5
