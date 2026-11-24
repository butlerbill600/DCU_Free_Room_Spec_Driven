import logging
import re
from datetime import date, datetime, time
from typing import Dict, List, Optional, Set
from zoneinfo import ZoneInfo
import httpx
from bs4 import BeautifulSoup

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
        room_map = self._build_room_map(rooms)
        if not room_map:
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
                    content_type = response.headers.get("content-type", "").lower()
                    if "application/json" in content_type:
                        data = response.json()
                        blocks.extend(self._parse_libcal_grid(data, room_map, target_date))
                    else:
                        blocks.extend(self._parse_libcal_html(response.text, room_map, target_date))
                else:
                    err_msg = f"LibCal endpoint returned HTTP {response.status_code}"
                    logger.warning(err_msg)
                    raise RuntimeError(err_msg)
            except httpx.HTTPError as err:
                err_msg = f"LibCal HTTP error: {err}"
                logger.warning(err_msg)
                raise RuntimeError(err_msg)

        return blocks

    def _build_room_map(self, rooms: List[Room]) -> Dict[str, Room]:
        """Build multi-key lookup map for library group study rooms."""
        room_map: Dict[str, Room] = {}
        for r in rooms:
            source_id = r.source_ids.get("libcal")
            if source_id:
                room_map[source_id.lower()] = r
                # Also map extracted numeric or code variations (e.g. oreilly_gsr_6 -> 6)
                num_match = re.search(r"\d+", source_id)
                if num_match:
                    room_map[num_match.group(0)] = r

            room_map[r.id.lower()] = r
            room_map[r.code.lower()] = r
            room_map[r.code.replace(" ", "").lower()] = r

        return room_map

    def _parse_libcal_grid(
        self, data: dict, room_map: Dict[str, Room], target_date: date
    ) -> List[OccupancyBlock]:
        """Parse LibCal grid slot JSON payload."""
        blocks: List[OccupancyBlock] = []
        slots = data.get("slots", []) if isinstance(data, dict) else []

        for slot in slots:
            item_id = str(slot.get("item_id") or slot.get("itemId") or slot.get("space_id") or "").lower()
            room = room_map.get(item_id)

            if not room:
                title_str = str(slot.get("title") or slot.get("name") or slot.get("text") or "").lower()
                for key, r_obj in room_map.items():
                    if key in title_str:
                        room = r_obj
                        break

            if not room:
                continue

            # Check if slot is marked unavailable / booked / checked-out / padding / reserved
            is_available = slot.get("is_available")
            class_name = str(slot.get("className") or slot.get("status") or "").lower()

            is_booked = (is_available is False) or any(
                term in class_name
                for term in ["unavailable", "checkout", "booked", "padding", "reserved", "s-lc-eq-period-booked", "s-lc-eq-period-unavailable"]
            )

            if is_booked:
                start_str = slot.get("start")
                end_str = slot.get("end")

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
                                summary="Library GSR Booking",
                            )
                        )

        return blocks

    def _parse_libcal_html(
        self, html_text: str, room_map: Dict[str, Room], target_date: date
    ) -> List[OccupancyBlock]:
        """DOM fallback selector parsing for LibCal timeline and period elements."""
        blocks: List[OccupancyBlock] = []
        soup = BeautifulSoup(html_text, "html.parser")

        # Select elements matching LibCal grid events and booked/unavailable slots
        selectors = [
            ".fc-timeline-event",
            ".s-lc-eq-period-booked",
            ".s-lc-eq-period-unavailable",
            ".s-lc-eq-event",
            "[data-original-title]",
        ]

        nodes = soup.select(", ".join(selectors))
        for node in nodes:
            title_text = node.get("title") or node.get("data-original-title") or node.get("aria-label") or node.get_text()
            if not title_text:
                continue

            # Regex match patterns like "14:00 - 15:00 - GSR 6 - Unavailable"
            time_match = re.search(r"(\d{1,2}:\d{2})\s*[-–to]+\s*(\d{1,2}:\d{2})", title_text)
            if not time_match:
                continue

            st_str, et_str = time_match.group(1), time_match.group(2)
            st = self._parse_datetime(st_str, target_date)
            et = self._parse_datetime(et_str, target_date)

            if not st or not et or st >= et:
                continue

            # Locate target room code from title text or data attributes
            room = None
            title_lower = title_text.lower()
            for key, r_obj in room_map.items():
                if key in title_lower:
                    room = r_obj
                    break

            if room:
                blocks.append(
                    OccupancyBlock(
                        room_id=room.id,
                        start_time=st,
                        end_time=et,
                        source=self.source_name,
                        status=OccupancyStatus.BOOKED,
                        summary=f"Library GSR Booking ({room.code})",
                    )
                )

        return blocks

    def _parse_datetime(self, time_val: str, target_date: date) -> Optional[datetime]:
        """Parse ISO string or 'HH:MM' string into Europe/Dublin datetime."""
        try:
            if "T" in time_val:
                dt = datetime.fromisoformat(time_val)
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=DUBLIN_TZ)
                return dt.astimezone(DUBLIN_TZ)

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
