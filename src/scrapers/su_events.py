import logging
from datetime import date, datetime
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo
import httpx
from bs4 import BeautifulSoup

from src.models import OccupancyBlock, OccupancyStatus, Room
from src.scrapers.base import RoomSourceAdapter

logger = logging.getLogger(__name__)
DUBLIN_TZ = ZoneInfo("Europe/Dublin")


class SUEventsScraper(RoomSourceAdapter):
    """Adapter for DCU SU Events & Society room allocations (dcusu.ie / rooms.rb.dcu.ie)."""

    def __init__(self, base_url: str = "https://dcusu.ie"):
        self._base_url = base_url.rstrip("/")

    @property
    def source_name(self) -> str:
        return "su_events"

    async def fetch_occupancy_blocks(
        self, rooms: List[Room], target_date: date
    ) -> List[OccupancyBlock]:
        """Fetch society events and SU room bookings."""
        su_rooms: Dict[str, Room] = {}
        for r in rooms:
            source_id = r.source_ids.get("su_events")
            if source_id:
                su_rooms[source_id] = r

        if not su_rooms:
            return []

        blocks: List[OccupancyBlock] = []

        async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client:
            url = f"{self._base_url}/api/events"
            params = {
                "date": target_date.isoformat(),
            }

            try:
                response = await client.get(url, params=params)
                if response.status_code == 200:
                    content_type = response.headers.get("content-type", "")
                    if "application/json" in content_type:
                        data = response.json()
                        blocks.extend(self._parse_events_json(data, su_rooms, target_date))
                    else:
                        blocks.extend(self._parse_events_html(response.text, su_rooms, target_date))
                else:
                    logger.warning(f"SU Events endpoint returned HTTP {response.status_code}")
            except httpx.HTTPError as err:
                logger.warning(f"SU Events HTTP error: {err}")

        return blocks

    def _parse_events_json(
        self, data: dict, room_map: Dict[str, Room], target_date: date
    ) -> List[OccupancyBlock]:
        """Parse structured JSON events payload."""
        blocks: List[OccupancyBlock] = []
        events = data.get("events", []) if isinstance(data, dict) else []

        for ev in events:
            loc_id = ev.get("room_id") or ev.get("location")
            room = room_map.get(loc_id)
            if not room:
                continue

            start_str = ev.get("start_time")
            end_str = ev.get("end_time")

            if start_str and end_str:
                st = self._parse_datetime(start_str, target_date)
                et = self._parse_datetime(end_str, target_date)

                if st and et and st < et:
                    blocks.append(
                        OccupancyBlock(
                            room_id=room.id,
                            start_time=st,
                            end_time=et,
                            source=self.source_name,
                            status=OccupancyStatus.BOOKED,
                            summary=ev.get("title") or ev.get("society") or "SU Event / Society Booking",
                        )
                    )

        return blocks

    def _parse_events_html(
        self, html_text: str, room_map: Dict[str, Room], target_date: date
    ) -> List[OccupancyBlock]:
        """Parse HTML event list markup."""
        blocks: List[OccupancyBlock] = []
        soup = BeautifulSoup(html_text, "html.parser")

        event_items = soup.find_all(class_=["su-event-item", "society-booking"])

        for item in event_items:
            loc_id = item.get("data-room-id") or item.get("data-location")
            room = room_map.get(loc_id) if loc_id else None

            start_attr = item.get("data-start")
            end_attr = item.get("data-end")

            if room and start_attr and end_attr:
                st = self._parse_datetime(start_attr, target_date)
                et = self._parse_datetime(end_attr, target_date)
                if st and et and st < et:
                    blocks.append(
                        OccupancyBlock(
                            room_id=room.id,
                            start_time=st,
                            end_time=et,
                            source=self.source_name,
                            status=OccupancyStatus.BOOKED,
                            summary=item.get_text(strip=True) or "Society Event",
                        )
                    )

        return blocks

    def _parse_datetime(self, time_val: str, target_date: date) -> Optional[datetime]:
        """Convert ISO string or 'HH:MM' string to datetime in Europe/Dublin timezone."""
        try:
            if "T" in time_val:
                dt = datetime.fromisoformat(time_val)
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=DUBLIN_TZ)
                return dt.astimezone(DUBLIN_TZ)

            parts = time_val.strip().split(":")
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
