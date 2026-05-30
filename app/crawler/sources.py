from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field

import aiohttp

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
    retries: int = 2


@dataclass
class SourceHealth:
    """Track health of each source for auto-disable."""
    consecutive_failures: int = 0
    last_success: float = 0.0
    last_failure: float = 0.0
    total_fetched: int = 0
    total_failures: int = 0

    @property
    def is_healthy(self) -> bool:
        if self.consecutive_failures >= 5:
            return False
        return True


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
        "sina_stock": SourceConfig(
            name="新浪财经-A股",
            url="https://feed.mix.sina.com.cn/api/roll/get",
            params={"pageid": "153", "lid": "2516", "num": "50", "page": "1"},
            headers={**BROWSER_HEADERS, "Referer": "https://finance.sina.com.cn/"},
            parser="sina",
        ),
        "sina_hk": SourceConfig(
            name="新浪财经-港股",
            url="https://feed.mix.sina.com.cn/api/roll/get",
            params={"pageid": "153", "lid": "2517", "num": "30", "page": "1"},
            headers={**BROWSER_HEADERS, "Referer": "https://finance.sina.com.cn/"},
            parser="sina",
        ),
        "sina_us": SourceConfig(
            name="新浪财经-美股",
            url="https://feed.mix.sina.com.cn/api/roll/get",
            params={"pageid": "153", "lid": "2518", "num": "30", "page": "1"},
            headers={**BROWSER_HEADERS, "Referer": "https://finance.sina.com.cn/"},
            parser="sina",
        ),
        "eastmoney": SourceConfig(
            name="东方财富",
            url="https://np-listapi.eastmoney.com/comm/web/getNewsByColumns",
            params={
                "client": "web", "biz": "web_news_col", "column": "250",
                "order": "1", "needInteractData": "0", "page_index": "1",
                "page_size": "20", "req_trace": "",
            },
            headers={**BROWSER_HEADERS, "Referer": "https://finance.eastmoney.com/"},
            parser="eastmoney",
            retries=1,
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
            retries=1,
        ),
        "jin10": SourceConfig(
            name="金十数据",
            url="https://flash-api.jin10.com/get_flash_list",
            params={"channel": "-8200", "vip": "1", "num": "20"},
            headers={**BROWSER_HEADERS, "Referer": "https://www.jin10.com/", "x-appid": "basic"},
            parser="jin10",
            retries=1,
        ),
        "kr36": SourceConfig(
            name="36氪",
            url="https://36kr.com/api/newsflash",
            params={"per_page": "20", "page": "1"},
            headers={**BROWSER_HEADERS, "Referer": "https://36kr.com/newsflashes"},
            parser="kr36",
        ),
    }


# ---------- Source Health Tracker ----------

_source_health: dict[str, SourceHealth] = {}


def get_source_health() -> dict[str, dict]:
    return {
        k: {
            "healthy": v.is_healthy,
            "consecutive_failures": v.consecutive_failures,
            "total_fetched": v.total_fetched,
            "total_failures": v.total_failures,
        }
        for k, v in _source_health.items()
    }


def _record_success(key: str, count: int):
    h = _source_health.setdefault(key, SourceHealth())
    h.consecutive_failures = 0
    h.last_success = time.time()
    h.total_fetched += count


def _record_failure(key: str):
    h = _source_health.setdefault(key, SourceHealth())
    h.consecutive_failures += 1
    h.last_failure = time.time()
    h.total_failures += 1
    if h.consecutive_failures >= 5:
        logger.warning("Source %s auto-disabled after %d consecutive failures", key, h.consecutive_failures)


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
                source=source_name, title=title, url=url,
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
                source=source_name, title=title, url=url,
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
        d = data.get("data") or {}
        news_list = d.get("list", []) if isinstance(d, dict) else []
        for entry in news_list:
            if not isinstance(entry, dict):
                continue
            title = entry.get("title", "").strip()
            if not title:
                continue
            content = entry.get("digest", "") or entry.get("content", "")
            url = entry.get("url", "")
            items.append(NewsItem(
                source=source_name, title=title, url=url,
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
        for entry in news_list:
            if not isinstance(entry, dict):
                continue
            title = entry.get("content", "").strip() or entry.get("title", "").strip()
            if not title:
                continue
            content = entry.get("content", "")
            url = ""
            if entry.get("id"):
                url = f"https://www.jin10.com/flash/{entry['id']}.html"
            items.append(NewsItem(
                source=source_name, title=title[:200], url=url,
                content_snippet=_clean_html(content)[:500],
                title_hash=compute_title_hash(title[:200]),
            ))
    except Exception as e:
        logger.warning("Jin10 parse error: %s", e)
    return items


def parse_kr36(text: str, source_name: str) -> list[NewsItem]:
    items = []
    try:
        data = json.loads(text)
        d = data.get("data") or {}
        news_list = d.get("items", d.get("newsflashes", [])) if isinstance(d, dict) else []
        for entry in news_list:
            if not isinstance(entry, dict):
                continue
            title = entry.get("title", "").strip()
            if not title:
                entity = entry.get("entity")
                if isinstance(entity, dict):
                    title = entity.get("title", "").strip()
            if not title:
                continue
            content = entry.get("description", "")
            entity = entry.get("entity")
            if isinstance(entity, dict) and not content:
                content = entity.get("content", "")
            url = entry.get("web_url", "") or entry.get("news_url", "")
            if not url and entry.get("id"):
                url = f"https://36kr.com/newsflashes/{entry['id']}"
            items.append(NewsItem(
                source=source_name, title=title, url=url,
                content_snippet=_clean_html(content),
                title_hash=compute_title_hash(title),
            ))
    except Exception as e:
        logger.warning("36kr parse error: %s", e)
    return items


_PARSERS = {
    "sina": parse_sina,
    "cls": parse_cls,
    "eastmoney": parse_eastmoney,
    "jin10": parse_jin10,
    "kr36": parse_kr36,
}


async def fetch_source(
    session: aiohttp.ClientSession,
    key: str,
    source: SourceConfig,
) -> list[NewsItem]:
    if not source.enabled:
        return []

    # Check health - auto-disable unhealthy sources temporarily
    health = _source_health.get(key)
    if health and not health.is_healthy:
        # Re-check every 5 minutes
        if time.time() - health.last_failure < 300:
            return []
        logger.info("Re-attempting unhealthy source: %s", source.name)

    timeout = aiohttp.ClientTimeout(total=15)

    for attempt in range(source.retries + 1):
        try:
            async with session.request(
                source.method, source.url,
                params=source.params, headers=source.headers, timeout=timeout,
            ) as response:
                if response.status == 200:
                    text = await response.text()
                    parser = _PARSERS.get(source.parser)
                    if parser:
                        result = parser(text, source.name)
                        _record_success(key, len(result))
                        return result
                    return []
                logger.warning(
                    "%s returned status %d (attempt %d/%d)",
                    source.name, response.status, attempt + 1, source.retries + 1,
                )
        except aiohttp.ClientError as e:
            logger.warning(
                "Fetch failed for %s: %s (attempt %d/%d)",
                source.name, e, attempt + 1, source.retries + 1,
            )
        except Exception as e:
            logger.error("Unexpected error fetching %s: %s", source.name, e, exc_info=True)
            return []

        if attempt < source.retries:
            await asyncio.sleep(1 * (attempt + 1))

    _record_failure(key)
    return []


async def fetch_all_sources(session: aiohttp.ClientSession) -> list[NewsItem]:
    from app import deps
    sources = deps.sources if deps.sources else default_sources()
    enabled = {k: v for k, v in sources.items() if v.enabled}
    tasks = [fetch_source(session, k, v) for k, v in enabled.items()]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    items = []
    for key, result in zip(enabled.keys(), results):
        if isinstance(result, list):
            items.extend(result)
        else:
            logger.error("Source %s error: %s", key, result)
            _record_failure(key)
    return items
