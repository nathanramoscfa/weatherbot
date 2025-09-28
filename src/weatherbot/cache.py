# src/weatherbot/cache.py
"""Simple file-based caching for API responses."""

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class APICache:
    """Enhanced file-based cache for API responses with performance optimizations."""

    def __init__(self, cache_dir: Path = Path("cache"), ttl_seconds: int = 21600):
        """Initialize cache.

        Args:
            cache_dir: Cache directory
            ttl_seconds: Time to live in seconds (default: 6 hours - matches NHC update schedule)
        """
        self.cache_dir = cache_dir
        self.ttl_seconds = ttl_seconds
        self.cache_dir.mkdir(exist_ok=True)

        # In-memory cache for frequently accessed data
        self._memory_cache: dict[str, dict[str, Any]] = {}
        self._memory_ttl = 300  # 5 minutes for memory cache

    def get(self, key: str) -> dict[str, Any] | None:
        """Get cached data with memory cache optimization.

        Args:
            key: Cache key

        Returns:
            Cached data or None if not found/expired
        """
        # Check memory cache first
        if key in self._memory_cache:
            memory_data = self._memory_cache[key]
            if time.time() - memory_data.get('timestamp', 0) <= self._memory_ttl:
                logger.debug(f"Memory cache hit for key: {key}")
                return memory_data.get('data')
            # Memory cache expired
            del self._memory_cache[key]

        # Check file cache
        cache_file = self.cache_dir / f"{key}.json"

        if not cache_file.exists():
            return None

        try:
            with open(cache_file, encoding='utf-8') as f:
                data = json.load(f)

            # Check if expired
            if time.time() - data.get('timestamp', 0) > self.ttl_seconds:
                logger.debug(f"Cache expired for key: {key}")
                cache_file.unlink(missing_ok=True)
                return None

            # Store in memory cache for faster access
            self._memory_cache[key] = {
                'timestamp': time.time(),
                'data': data.get('data')
            }

            logger.debug(f"File cache hit for key: {key}")
            return data.get('data')

        except Exception as e:
            logger.warning(f"Failed to read cache for key {key}: {e}")
            cache_file.unlink(missing_ok=True)
            return None

    def set(self, key: str, data: dict[str, Any]) -> None:
        """Set cached data with memory cache optimization.

        Args:
            key: Cache key
            data: Data to cache
        """
        cache_file = self.cache_dir / f"{key}.json"

        try:
            cache_data = {
                'timestamp': time.time(),
                'data': data
            }

            # Store in memory cache immediately
            self._memory_cache[key] = {
                'timestamp': time.time(),
                'data': data
            }

            # Also store in file cache
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, default=str)

            logger.debug(f"Cached data for key: {key}")

        except Exception as e:
            logger.warning(f"Failed to cache data for key {key}: {e}")

    def clear(self) -> None:
        """Clear all cached data."""
        try:
            # Clear memory cache
            self._memory_cache.clear()

            # Clear file cache
            for cache_file in self.cache_dir.glob("*.json"):
                cache_file.unlink()
            logger.info("Cleared API cache")
        except Exception as e:
            logger.warning(f"Failed to clear cache: {e}")

    def cleanup_expired(self) -> None:
        """Clean up expired cache entries."""
        try:
            current_time = time.time()

            # Clean memory cache
            expired_keys = [
                key for key, data in self._memory_cache.items()
                if current_time - data.get('timestamp', 0) > self._memory_ttl
            ]
            for key in expired_keys:
                del self._memory_cache[key]

            # Clean file cache
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    with open(cache_file, encoding='utf-8') as f:
                        data = json.load(f)

                    if current_time - data.get('timestamp', 0) > self.ttl_seconds:
                        cache_file.unlink()
                        logger.debug(f"Removed expired cache file: {cache_file.name}")

                except Exception as e:
                    logger.debug(f"Error checking cache file {cache_file.name}: {e}")
                    cache_file.unlink(missing_ok=True)

            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

        except Exception as e:
            logger.warning(f"Failed to cleanup expired cache: {e}")


# Global cache instance
api_cache = APICache()
