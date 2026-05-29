from __future__ import annotations

import time
from collections import OrderedDict

from app import deps


def check_and_register(title_hash: str) -> bool:
    """Returns True if the item is a duplicate (already seen)."""
    if title_hash in deps.dedup_cache:
        # Move to end (most recently used)
        deps.dedup_cache.move_to_end(title_hash)
        return True

    # Register new item
    deps.dedup_cache[title_hash] = time.time()
    deps.dedup_cache.move_to_end(title_hash)

    # Evict oldest if over capacity
    max_size = deps.settings.dedup_cache_max_size if deps.settings else 10000
    while len(deps.dedup_cache) > max_size:
        deps.dedup_cache.popitem(last=False)

    return False
