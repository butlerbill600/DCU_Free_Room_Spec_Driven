import logging
from datetime import date, datetime, time
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo
import httpx
from bs4 import BeautifulSoup

from src.models import OccupancyBlock, OccupancyStatus, Room
from src.scrapers.base import RoomSourceAdapter

logger = logging.getLogger(__name__)
DUBLIN_TZ = ZoneInfo("Europe/Dublin")


class TimetableScraper(RoomSourceAdapter):
    """Adapter for DCU Open Timetable (opentimetable.dcu.ie / Scientia Syllabus+)."""

    def __init__(self, base_url: str = "https://opentimetable.dcu.ie"):
        self._base_url = base_url.rstrip("/")

    @property
    def source_name(self) -> str:
        return "timetable"

    async def fetch_occupancy_blocks(
        self, rooms: List[Room], target_date: date
    ) -> List[OccupancyBlock]:
        """Fetch and parse scheduled lectures, labs, and tutorials from DCU Open Timetable."""
        # Filter rooms that have a timetable source_id
        timetable_rooms: Dict[str, Room] = {}
        for r in rooms:
            source_id = r.source_ids.get("timetable")
            if source_id:
                timetable_rooms[source_id] = r

        if not timetable_rooms:
            return []

        blocks: List[OccupancyBlock] = []

        async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client:
            url = f"{self._base_url}/api/timetable"
            params = {
                "date": target_date.isoformat(),
                "locations": ",".join(timetable_rooms.keys()),
            }

            try:
                response = await client.get(url, params=params)
                if response.status_code == 200:
                    content_type = response.headers.get("content-type", "")
                    if "application/json" in content_type:
                        data = response.json()
                        blocks.extend(self._parse_json_response(data, timetable_rooms, target_date))
                    else:
                        blocks.extend(self._parse_html_response(response.text, timetable_rooms, target_date))
                else:
                    logger.warning(f"Timetable scraper endpoint returned HTTP {response.status_code}")
            except httpx.HTTPError as err:
                logger.warning(f"Timetable HTTP error: {err}")

        return blocks

    def _parse_json_response(
        self, data: dict, room_map: Dict[str, Room], target_date: date
    ) -> List[OccupancyBlock]:
        """Parse structured JSON timetable response."""
        blocks: List[OccupancyBlock] = []
        events = data.get("events", []) if isinstance(data, dict) else []

        for ev in events:
            loc_id = ev.get("location") or ev.get("room_id")
            room = room_map.get(loc_id)
            if not room:
                continue

            start_str = ev.get("start_time")  # e.g. "09:00" or "2026-11-23T09:00:00"
            end_str = ev.get("end_time")  # e.g. "11:00" or "2026-11-23T11:00:00"
            if not start_str or not end_str:
                continue

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
                        summary=ev.get("description") or ev.get("module") or "Lecture/Tutorial",
                    )
                )

        return blocks

    def _parse_html_response(
        self, html_text: str, room_map: Dict[str, Room], target_date: date
    ) -> List[OccupancyBlock]:
        """Parse HTML timetable response grid."""
        blocks: List[OccupancyBlock] = []
        soup = BeautifulSoup(html_text, "html.parser")

        # Search for elements with class 'timetable-event' or 'event-slot'
        event_nodes = soup.find_all(class_=["timetable-event", "event-slot", "booking-slot"])

        for node in event_nodes:
            loc_id = node.get("data-room") or node.get("data-location")
            room = room_map.get(loc_id) if loc_id else None

            start_attr = node.get("data-start")
            end_attr = node.get("data-end")

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
                            summary=node.get_text(strip=True) or "Scheduled Class",
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

            # HH:MM format
            parts = time_val.strip().split(":")
            h, m = int(parts[0]), int(parts[1])
            return datetime(
                target_date.year,
                target_date.month,
                target_date.day,
                h,
                m,
                0,
                tzinfo=DUBLIN_TZ,
            )
        except Exception:
            return None
