from datetime import datetime, time, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo

from src.models import (
    Campus,
    OccupancyBlock,
    OccupancyStatus,
    Room,
    RoomAvailability,
    TimelineBlock,
)

DUBLIN_TZ = ZoneInfo("Europe/Dublin")


def ensure_dublin_tz(dt: datetime) -> datetime:
    """Ensure a datetime object is localized to Europe/Dublin timezone."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=DUBLIN_TZ)
    return dt.astimezone(DUBLIN_TZ)


def calculate_room_availability(
    room: Room,
    occupancy_blocks: List[OccupancyBlock],
    now: Optional[datetime] = None,
) -> RoomAvailability:
    """Calculate real-time availability for a single room for the 07:00–22:00 window.

    - Operating window: 07:00 to 22:00 Europe/Dublin daily.
    - Strict Exclusion: If room has active occupancy at 'now', marked unavailable.
    - Free Until & Remaining Minutes: Calculates continuous free time from 'now' until next booking or 22:00.
    - Timeline: Generates 15 hourly blocks from 07:00 to 22:00.
    """
    if now is None:
        now = datetime.now(DUBLIN_TZ)
    else:
        now = ensure_dublin_tz(now)

    day_start = now.replace(hour=7, minute=0, second=0, microsecond=0)
    day_end = now.replace(hour=22, minute=0, second=0, microsecond=0)

    is_within_operating_hours = day_start <= now < day_end

    # Standardize occupancy block timezones and filter for current day
    room_blocks: List[OccupancyBlock] = []
    for block in occupancy_blocks:
        if block.room_id != room.id:
            continue
        st = ensure_dublin_tz(block.start_time)
        et = ensure_dublin_tz(block.end_time)
        # Check if block overlaps today's operating window
        if st < day_end and et > day_start:
            room_blocks.append(
                OccupancyBlock(
                    room_id=block.room_id,
                    start_time=st,
                    end_time=et,
                    source=block.source,
                    status=block.status,
                    summary=block.summary,
                )
            )

    # Check strict exclusion rule: active occupied block at 'now'
    is_currently_occupied = False
    for block in room_blocks:
        if block.status in (OccupancyStatus.BOOKED, OccupancyStatus.UNAVAILABLE):
            if block.start_time <= now < block.end_time:
                is_currently_occupied = True
                break

    is_available_now = is_within_operating_hours and not is_currently_occupied

    # Calculate free_until and remaining_minutes
    free_until: Optional[datetime] = None
    remaining_minutes = 0

    if is_available_now:
        # Find earliest upcoming booking starting after 'now' today
        next_booking_start: Optional[datetime] = None
        for block in room_blocks:
            if block.status in (OccupancyStatus.BOOKED, OccupancyStatus.UNAVAILABLE):
                if block.start_time > now:
                    if next_booking_start is None or block.start_time < next_booking_start:
                        next_booking_start = block.start_time

        if next_booking_start is not None and next_booking_start < day_end:
            free_until = next_booking_start
        else:
            free_until = day_end

        seconds_free = (free_until - now).total_seconds()
        remaining_minutes = max(0, int(seconds_free // 60))
    else:
        free_until = None
        remaining_minutes = 0

    free_until_str = free_until.strftime("%H:%M") if free_until else None

    # Generate 15 timeline blocks (07:00-08:00, 08:00-09:00, ..., 21:00-22:00)
    timeline: List[TimelineBlock] = []
    for h in range(7, 22):
        slot_start = day_start.replace(hour=h, minute=0)
        slot_end = slot_start + timedelta(hours=1)

        slot_booked = False
        for block in room_blocks:
            if block.status in (OccupancyStatus.BOOKED, OccupancyStatus.UNAVAILABLE):
                if block.start_time < slot_end and block.end_time > slot_start:
                    slot_booked = True
                    break

        status_str = "booked" if slot_booked else "free"
        timeline.append(
            TimelineBlock(
                hour=h,
                start_time_str=f"{h:02d}:00",
                end_time_str=f"{h+1:02d}:00",
                status=status_str,
            )
        )

    return RoomAvailability(
        room=room,
        is_available_now=is_available_now,
        is_within_operating_hours=is_within_operating_hours,
        free_until=free_until,
        free_until_str=free_until_str,
        remaining_minutes=remaining_minutes,
        timeline=timeline,
        occupancy_blocks=room_blocks,
    )


def filter_available_rooms(
    rooms_availability: List[RoomAvailability],
    min_duration_minutes: int = 0,
    campus_filter: Optional[str] = None,
) -> List[RoomAvailability]:
    """Filter rooms for current availability, campus, and minimum free duration.

    Returns available rooms sorted by longest remaining free window first.
    """
    filtered: List[RoomAvailability] = []

    for ra in rooms_availability:
        # Exclude currently occupied or outside operating hours
        if not ra.is_available_now:
            continue

        # Campus filter
        if campus_filter and campus_filter != "All Campuses":
            room_campus_val = (
                ra.room.campus.value
                if isinstance(ra.room.campus, Campus)
                else str(ra.room.campus)
            )
            if room_campus_val != campus_filter:
                continue

        # Minimum duration filter
        if ra.remaining_minutes < min_duration_minutes:
            continue

        filtered.append(ra)

    # Sort by free_until descending (longest free window first), then room code
    filtered.sort(
        key=lambda r: (
            r.free_until if r.free_until is not None else datetime.min.replace(tzinfo=DUBLIN_TZ),
            r.room.code,
        ),
        reverse=True,
    )

    return filtered
