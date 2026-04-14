"""
peering_intelligence_cache.py
─────────────────────────────────────────────────────────────────────────────
Helper untuk cache hasil enrichment dari BGPView / PeeringDB / ip-api.com
di MongoDB collection `peering_intelligence_cache`.

Skema dokumen:
{
  "key":        "asn:7713",         # cache key
  "data":       { ... },            # payload hasil API
  "fetched_at": "2026-03-26T...",   # timestamp pengambilan
  "ttl_seconds": 21600              # default 6 jam
}
─────────────────────────────────────────────────────────────────────────────
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Any

logger = logging.getLogger(__name__)


async def cache_get(db, key: str) -> Optional[Any]:
    """Return cached value jika masih valid, atau None."""
    try:
        doc = await db.peering_intelligence_cache.find_one({"key": key})
        if not doc:
            return None
        fetched_at = datetime.fromisoformat(doc["fetched_at"])
        ttl = doc.get("ttl_seconds", 21600)
        if datetime.now(timezone.utc) - fetched_at > timedelta(seconds=ttl):
            return None   # expired
        return doc["data"]
    except Exception as e:
        logger.warning(f"[PeeringCache] cache_get error ({key}): {e}")
        return None


async def cache_set(db, key: str, data: Any, ttl_seconds: int = 21600):
    """Simpan / update cache entry."""
    try:
        await db.peering_intelligence_cache.update_one(
            {"key": key},
            {"$set": {
                "key": key,
                "data": data,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "ttl_seconds": ttl_seconds,
            }},
            upsert=True,
        )
    except Exception as e:
        logger.warning(f"[PeeringCache] cache_set error ({key}): {e}")
