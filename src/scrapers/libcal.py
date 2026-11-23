import logging
from datetime import date, datetime
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo
import httpx

from src.models import OccupancyBlock, OccupancyStatus, Room
from src.scrapers.base import RoomSourceAdapter

logger = logging.getLogger(__name__)
DUBLIN_TZ = ZoneInfo("Europe/Dublin")


class LibCalScraper(RoomSourceAdapter):
    """Adapter for DCU Library LibCal space availability (O'Reilly & Cregan Library GSRs)."""

    def __init__(self, base_url: str = "https://dcu-ie.libcal.com"):
        self._base_url = base_url.rstrip("/")

    @property
    def source_name(self) -> str:
        return "libcal"

    async def fetch_occupancy_blocks(
        self, rooms: List[Room], target_date: date
    ) -> List[OccupancyBlock]:
        """Fetch and parse Group Study Room availability grid slots from LibCal."""
        libcal_rooms: Dict[str, Room] = {}
        for r in rooms:
            source_id = r.source_ids.get("libcal")
            if source_id:
                libcal_rooms[source_id] = r

        if not libcal_rooms:
            return []

        blocks: List[OccupancyBlock] = []

        async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client:
            url = f"{self._base_url}/spaces/availability/grid"
            params = {
                "date": target_date.isoformat(),
            }

            try:
                response = await client.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    blocks.extend(self._parse_libcal_grid(data, libcal_rooms, target_date))
                else:
                    logger.warning(f"LibCal endpoint returned HTTP {response.status_code}")
            except httpx.HTTPError as err:
                logger.warning(f"LibCal HTTP error: {err}")

        return blocks

    def _parse_libcal_grid(
        self, data: dict, room_map: Dict[str, Room], target_date: date
    ) -> List[OccupancyBlock]:
        """Parse LibCal grid slot JSON payload."""
        blocks: List[OccupancyBlock] = []
        slots = data.get("slots", []) if isinstance(data, dict) else []

        for slot in slots:
            item_id = str(slot.get("item_id") or slot.get("itemId") or slot.get("space_id"))
            room = room_map.get(item_id)
            if not room:
                continue

            # Check if slot is marked unavailable / booked / checked-out / padding
            is_available = slot.get("is_available")
            class_name = str(slot.get("className") or slot.get("status") or "").lower()

            if is_available is False or any(
                term in class_name for term in ["unavailable", "checkout", "booked", "padding", "reserved"]
            ):
                start_str = slot.get("start")
                end_str = slot.get("end")

                if start_str and end_str:
                    st = self._parse_iso_datetime(start_str, target_date)
                    et = self._parse_iso_datetime(end_str, target_date)

                    if st and et and st < et:
                        blocks.append(
                            OccupancyBlock(
                                room_id=room.id,
                                start_time=st,
                                end_time=et,
                                source=self.source_name,
                                status=OccupancyStatus.BOOKED,
                                summary="Library GSR Booking",
                            )
                        )

        return blocks

    def _parse_iso_datetime(self, iso_str: str, target_date: date) -> Optional[datetime]:
        """Parse ISO datetime string and convert to Europe/Dublin timezone."""
        try:
            if "T" in iso_str:
                dt = datetime.fromisoformat(iso_str)
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=DUBLIN_TZ)
                return dt.astimezone(DUBLIN_TZ)

            parts = iso_str.strip().split(":")
            return datetime(
                target_date.year,
                target_date.month,
                target_date.day,
                int(parts[0]),
                int(parts[1]),
                0,
                tzinfo=DUBLIN_TZ,
            )
        except Exception:
            return None
