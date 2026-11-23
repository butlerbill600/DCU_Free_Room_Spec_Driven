import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import date
from typing import List, Optional
from pydantic import BaseModel, Field

from src.models import OccupancyBlock, Room

logger = logging.getLogger(__name__)


class ScraperResult(BaseModel):
    source_name: str
    success: bool
    blocks: List[OccupancyBlock] = Field(default_factory=list)
    error_message: Optional[str] = None


class RoomSourceAdapter(ABC):
    """Abstract Base Class for DCU room occupancy data scrapers and connectors."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Unique identifier for the data source (e.g., 'timetable', 'libcal', 'su_events')."""
        pass

    @abstractmethod
    async def fetch_occupancy_blocks(
        self, rooms: List[Room], target_date: date
    ) -> List[OccupancyBlock]:
        """Fetch and parse live occupancy blocks for the given rooms on target_date."""
        pass

    async def fetch_safe(
        self, rooms: List[Room], target_date: date, timeout_seconds: float = 5.0
    ) -> ScraperResult:
        """Safely execute scraper with timeout protection and error handling."""
        try:
            blocks = await asyncio.wait_for(
                self.fetch_occupancy_blocks(rooms, target_date),
                timeout=timeout_seconds,
            )
            return ScraperResult(
                source_name=self.source_name,
                success=True,
                blocks=blocks,
            )
        except asyncio.TimeoutError:
            err = f"Scraper '{self.source_name}' timed out after {timeout_seconds}s"
            logger.warning(err)
            return ScraperResult(
                source_name=self.source_name,
                success=False,
                blocks=[],
                error_message=err,
            )
        except Exception as e:
            err = f"Scraper '{self.source_name}' failed: {str(e)}"
            logger.error(err, exc_info=True)
            return ScraperResult(
                source_name=self.source_name,
                success=False,
                blocks=[],
                error_message=err,
            )
