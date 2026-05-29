from __future__ import annotations

import asyncio
import logging

import aiohttp

from app import deps
from app.crawler.dedup import check_and_register
from app.crawler.sources import default_sources, fetch_all_sources

logger = logging.getLogger(__name__)


async def crawl_cycle():
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=10, force_close=True)
    ) as session:
        items = await fetch_all_sources(session)

    new_count = 0
    for item in items:
        if check_and_register(item.title_hash):
            continue
        try:
            deps.news_queue.put_nowait(item)
            new_count += 1
        except asyncio.QueueFull:
            logger.warning("news_queue full, dropping item: %s", item.title[:50])
    logger.info("Crawl cycle: %d fetched, %d new", len(items), new_count)


async def start_crawler():
    # Initialize sources from settings or defaults
    if not deps.sources:
        deps.sources = default_sources()

    interval = deps.settings.rss_poll_interval_seconds if deps.settings else 30
    source_names = [s.name for s in deps.sources.values() if s.enabled]
    logger.info("Crawler started (interval=%ds, sources=%s)", interval, source_names)

    while True:
        try:
            await crawl_cycle()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Crawler cycle error: %s", e, exc_info=True)
        await asyncio.sleep(interval)
