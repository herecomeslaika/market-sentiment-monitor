from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import xml.etree.ElementTree as ET
from typing import Any

import aiohttp

from app import deps
from app.models import NewsItem

logger = logging.getLogger(__name__)


def compute_title_hash(title: str) -> str:
    return hashlib.md5(title.strip().encode("utf-8")).hexdigest()


def parse_rss_xml(xml_text: str, source: str) -> list[NewsItem]:
    items = []
    try:
        root = ET.fromstring(xml_text)
        # RSS 2.0: <rss><channel><item>
        channel = root.find("channel")
        if channel is None:
            # Try Atom: <feed><entry>
            entries = root.findall("{http://www.w3.org/2005/Atom}entry")
            for entry in entries:
                title_el = entry.find("{http://www.w3.org/2005/Atom}title")
                link_el = entry.find("{http://www.w3.org/2005/Atom}link")
                summary_el = entry.find("{http://www.w3.org/2005/Atom}summary")
                updated_el = entry.find("{http://www.w3.org/2005/Atom}updated")

                title = title_el.text.strip() if title_el is not None and title_el.text else ""
                if not title:
                    continue
                link = link_el.get("href", "") if link_el is not None else ""
                snippet = summary_el.text[:500] if summary_el is not None and summary_el.text else ""
                published = updated_el.text if updated_el is not None and updated_el.text else ""

                items.append(NewsItem(
                    source=source,
                    title=title,
                    url=link,
                    content_snippet=snippet,
                    title_hash=compute_title_hash(title),
                ))
            return items

        for item in channel.findall("item"):
            title_el = item.find("title")
            link_el = item.find("link")
            desc_el = item.find("description")
            pub_el = item.find("pubDate")

            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            if not title:
                continue
            link = link_el.text.strip() if link_el is not None and link_el.text else ""
            snippet = desc_el.text[:500] if desc_el is not None and desc_el.text else ""
            published = pub_el.text if pub_el is not None and pub_el.text else ""

            items.append(NewsItem(
                source=source,
                title=title,
                url=link,
                content_snippet=snippet,
                title_hash=compute_title_hash(title),
            ))
    except ET.ParseError as e:
        logger.warning("Failed to parse RSS XML from %s: %s", source, e)

    return items


async def fetch_rss(session: aiohttp.ClientSession, source_name: str, url: str) -> list[NewsItem]:
    timeout = aiohttp.ClientTimeout(total=deps.settings.rss_request_timeout_seconds)
    try:
        async with session.get(url, timeout=timeout) as response:
            if response.status != 200:
                logger.warning("RSS %s returned status %d", source_name, response.status)
                return []
            text = await response.text()
            return parse_rss_xml(text, source_name)
    except aiohttp.ClientError as e:
        logger.warning("RSS fetch failed for %s: %s", source_name, e)
        return []
    except Exception as e:
        logger.error("Unexpected error fetching %s: %s", source_name, e, exc_info=True)
        return []


async def fetch_all_sources(session: aiohttp.ClientSession) -> list[NewsItem]:
    if not deps.settings:
        return []
    tasks = [
        fetch_rss(session, name, url)
        for name, url in deps.settings.rss_urls.items()
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    items = []
    for result in results:
        if isinstance(result, list):
            items.extend(result)
        else:
            logger.error("RSS source error: %s", result)
    return items
