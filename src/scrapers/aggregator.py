import asyncio
import logging
from datetime import date
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from src.database import cache_occupancy_blocks, get_cached_occupancy_blocks
from src.models import OccupancyBlock, Room
from src.scrapers.base import RoomSourceAdapter, ScraperResult
from src.scrapers.libcal import LibCalScraper
from src.scrapers.su_events import SUEventsScraper
from src.scrapers.timetable import TimetableScraper

logger = logging.getLogger(__name__)


class AggregatorResult(BaseModel):
    blocks: List[OccupancyBlock] = Field(default_factory=list)
    health_status: Dict[str, bool] = Field(default_factory=dict)
    errors: Dict[str, Optional[str]] = Field(default_factory=dict)
    is_cached_fallback: bool = False


class ScrapeAggregator:
    """Manages concurrent scraping across all DCU data adapters with caching and fallback."""

    def __init__(self, adapters: Optional[List[RoomSourceAdapter]] = None):
        if adapters is None:
            self.adapters: List[RoomSourceAdapter] = [
                TimetableScraper(),
                LibCalScraper(),
                SUEventsScraper(),
            ]
        else:
            self.adapters = adapters

    async def fetch_all(
        self,
        rooms: List[Room],
        target_date: date,
        db_path: Optional[str] = None,
        timeout_seconds: float = 4.0,
    ) -> AggregatorResult:
        """Concurrently query all room occupancy adapters and return consolidated results."""
        tasks = [
            adapter.fetch_safe(rooms, target_date, timeout_seconds=timeout_seconds)
            for adapter in self.adapters
        ]

        results: List[ScraperResult] = await asyncio.gather(*tasks, return_exceptions=False)

        all_blocks: List[OccupancyBlock] = []
        health_status: Dict[str, bool] = {}
        errors: Dict[str, Optional[str]] = {}
        any_failed = False

        for res in results:
            health_status[res.source_name] = res.success
            errors[res.source_name] = res.error_message

            if res.success:
                all_blocks.extend(res.blocks)
            else:
                any_failed = True

        # Cache successfully scraped blocks into SQLite database
        if db_path and all_blocks:
            try:
                cache_occupancy_blocks(db_path, all_blocks)
            except Exception as e:
                logger.error(f"Failed to cache occupancy blocks: {e}")

        # Fallback logic: if any adapter failed and db_path provided, retrieve cached blocks
        is_cached_fallback = False
        if any_failed and db_path:
            try:
                cached = get_cached_occupancy_blocks(db_path, room_ids=[r.id for r in rooms])
                if cached:
                    is_cached_fallback = True
                    # Merge cached blocks for failed sources
                    existing_keys = {
                        (b.room_id, b.start_time.isoformat(), b.end_time.isoformat())
                        for b in all_blocks
                    }
                    for cb in cached:
                        key = (cb.room_id, cb.start_time.isoformat(), cb.end_time.isoformat())
                        if key not in existing_keys:
                            all_blocks.append(cb)
                            existing_keys.add(key)
            except Exception as e:
                logger.error(f"Failed to load cached fallback occupancy: {e}")

        return AggregatorResult(
            blocks=all_blocks,
            health_status=health_status,
            errors=errors,
            is_cached_fallback=is_cached_fallback,
        )
