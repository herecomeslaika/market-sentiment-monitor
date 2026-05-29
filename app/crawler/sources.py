from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field

import aiohttp

from app import deps
from app.models import NewsItem

logger = logging.getLogger(__name__)


def compute_title_hash(title: str) -> str:
    return hashlib.md5(title.strip().encode()).hexdigest()


@dataclass
class SourceConfig:
    name: str
    url: str
    method: str = "GET"
    headers: dict = field(default_factory=dict)
    params: dict = field(default_factory=dict)
    parser: str = ""
    enabled: bool = True


BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&\w+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:500]


def default_sources() -> dict[str, SourceConfig]:
    return {
        "sina": SourceConfig(
            name="新浪财经",
            url="https://feed.mix.sina.com.cn/api/roll/get",
            params={"pageid": "153", "lid": "2516", "k": "", "num": "20", "page": "1"},
            headers={**BROWSER_HEADERS, "Referer": "https://finance.sina.com.cn/"},
            parser="sina",
        ),
        "cls": SourceConfig(
            name="财联社",
            url="https://www.cls.cn/nodeapi/updateTelegraph",
            params={"last_time": "", "refresh_type": "1", "rn": "20"},
            headers={
                **BROWSER_HEADERS,
                "Referer": "https://www.cls.cn/telegraph",
                "Accept": "application/json, text/plain, */*",
            },
            parser="cls",
        ),
        "eastmoney_info": SourceConfig(
            name="东方财富-要闻",
            url="https://np-listapi.eastmoney.com/comm/web/getNewsByColumns",
            params={
                "client": "web",
                "biz": "web_news_col",
                "column": "250",
                "order": "1",
                "needInteractData": "0",
                "page_index": "1",
                "page_size": "20",
                "req_trace": "",
            },
            headers={**BROWSER_HEADERS, "Referer": "https://finance.eastmoney.com/"},
            parser="eastmoney",
        ),
        "jin10": SourceConfig(
            name="金十数据",
            url="https://flash-api.jin10.com/get_flash_list",
            params={
                "channel": "-8200",
                "vip": "1",
                "num": "20",
            },
            headers={
                **BROWSER_HEADERS,
                "Referer": "https://www.jin10.com/",
                "x-appid": "basic",
                "x-version": "1.0.0",
            },
            parser="jin10",
        ),
    }


# ---------- Parsers ----------

def parse_sina(text: str, source_name: str) -> list[NewsItem]:
    items = []
    try:
        data = json.loads(text)
        news_list = data.get("result", {}).get("data", [])
        for entry in news_list:
            title = entry.get("title", "").strip()
            if not title:
                continue
            content = entry.get("intro", "") or entry.get("summary", "")
            url = entry.get("url", "") or entry.get("wapurl", "")
            items.append(NewsItem(
                source="新浪财经", title=title, url=url,
                content_snippet=_clean_html(content),
                title_hash=compute_title_hash(title),
            ))
    except Exception as e:
        logger.warning("Sina parse error: %s", e)
    return items


def parse_cls(text: str, source_name: str) -> list[NewsItem]:
    items = []
    try:
        data = json.loads(text)
        payload = data.get("data", [])
        if isinstance(payload, dict):
            roll_data = payload.get("roll_data", [])
            if not roll_data:
                roll_data = payload.get("list", payload.get("items", []))
        elif isinstance(payload, list):
            roll_data = payload
        else:
            roll_data = []
        for entry in roll_data:
            if not isinstance(entry, dict):
                continue
            title = entry.get("title", "").strip() or entry.get("content", "").strip()[:80]
            if not title:
                continue
            content = entry.get("content", "")
            url = entry.get("shareurl", "") or entry.get("url", "")
            if not url and entry.get("id"):
                url = f"https://www.cls.cn/detail/{entry['id']}"
            items.append(NewsItem(
                source="财联社", title=title, url=url,
                content_snippet=_clean_html(content),
                title_hash=compute_title_hash(title),
            ))
    except Exception as e:
        logger.warning("CLS parse error: %s", e)
    return items


def parse_eastmoney(text: str, source_name: str) -> list[NewsItem]:
    items = []
    try:
        data = json.loads(text)
        news_list = data.get("data", {}).get("list", [])
        if not news_list:
            return items
        for entry in news_list:
            if not isinstance(entry, dict):
                continue
            title = entry.get("title", "").strip()
            if not title:
                continue
            content = entry.get("digest", "") or entry.get("content", "")
            url = entry.get("url", "")
            items.append(NewsItem(
                source="东方财富", title=title, url=url,
                content_snippet=_clean_html(content),
                title_hash=compute_title_hash(title),
            ))
    except Exception as e:
        logger.warning("EastMoney parse error: %s", e)
    return items


def parse_jin10(text: str, source_name: str) -> list[NewsItem]:
    items = []
    try:
        data = json.loads(text)
        news_list = data.get("data", [])
        if not news_list:
            return items
        for entry in news_list:
            if not isinstance(entry, dict):
                continue
            title = entry.get("content", "").strip()
            if not title:
                title = entry.get("title", "").strip()
            if not title:
                continue
            content = entry.get("content", "")
            url = ""
            if entry.get("id"):
                url = f"https://www.jin10.com/flash/{entry['id']}.html"
            items.append(NewsItem(
                source="金十数据", title=title[:200], url=url,
                content_snippet=_clean_html(content)[:500],
                title_hash=compute_title_hash(title[:200]),
            ))
    except Exception as e:
        logger.warning("Jin10 parse error: %s", e)
    return items


_PARSERS = {
    "sina": parse_sina,
    "cls": parse_cls,
    "eastmoney": parse_eastmoney,
    "jin10": parse_jin10,
}


async def fetch_source(
    session: aiohttp.ClientSession,
    source: SourceConfig,
) -> list[NewsItem]:
    if not source.enabled:
        return []
    timeout = aiohttp.ClientTimeout(total=15)
    try:
        async with session.request(
            source.method, source.url,
            params=source.params, headers=source.headers, timeout=timeout,
        ) as response:
            if response.status != 200:
                logger.warning("%s returned status %d", source.name, response.status)
                return []
            text = await response.text()
            parser = _PARSERS.get(source.parser)
            if parser:
                return parser(text, source.name)
            # Fallback: try RSS
            from app.crawler.rss_parser import parse_rss_xml
            return parse_rss_xml(text, source.name)
    except aiohttp.ClientError as e:
        logger.warning("Fetch failed for %s: %s", source.name, e)
    except Exception as e:
        logger.error("Unexpected error fetching %s: %s", source.name, e, exc_info=True)
    return []


async def fetch_all_sources(session: aiohttp.ClientSession) -> list[NewsItem]:
    sources = deps.sources if deps.sources else default_sources()
    tasks = [fetch_source(session, src) for src in sources.values() if src.enabled]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    items = []
    for result in results:
        if isinstance(result, list):
            items.extend(result)
        else:
            logger.error("Source error: %s", result)
    return items
