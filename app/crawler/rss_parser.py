from __future__ import annotations

import hashlib
import logging
import xml.etree.ElementTree as ET

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
            # Atom: <feed><entry>
            ns = "{http://www.w3.org/2005/Atom}"
            for entry in root.findall(f"{ns}entry"):
                title_el = entry.find(f"{ns}title")
                link_el = entry.find(f"{ns}link")
                summary_el = entry.find(f"{ns}summary")
                updated_el = entry.find(f"{ns}updated")

                title = title_el.text.strip() if title_el is not None and title_el.text else ""
                if not title:
                    continue
                link = link_el.get("href", "") if link_el is not None else ""
                snippet = summary_el.text[:500] if summary_el is not None and summary_el.text else ""

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
