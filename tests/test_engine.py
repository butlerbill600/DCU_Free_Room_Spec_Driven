import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pytest

from src.database import (
    cache_occupancy_blocks,
    get_all_rooms,
    get_cached_occupancy_blocks,
    get_room_by_id,
    init_db,
    seed_rooms,
)
from src.engine import (
    DUBLIN_TZ,
    calculate_room_availability,
    ensure_dublin_tz,
    filter_available_rooms,
)
from src.models import (
    Campus,
    OccupancyBlock,
    OccupancyStatus,
    Room,
    RoomType,
)


@pytest.fixture
def sample_room() -> Room:
    return Room(
        id="glasnevin-l-lg25",
        code="LG25",
        name="McNulty Lecture Theatre",
        campus=Campus.GLASNEVIN,
        building_code="L",
        building_name="McNulty Building",
        capacity=120,
        room_type=RoomType.LECTURE_HALL,
        source_ids={"timetable": "L_LG25"},
    )


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_dcu_rooms.db"
    init_db(db_file)
    return db_file


def test_seed_and_database_operations(temp_db, tmp_path):
    seed_file = tmp_path / "rooms_seed.json"
    seed_data = [
        {
            "id": "glasnevin-l-lg25",
            "code": "LG25",
            "name": "McNulty Lecture Theatre",
            "campus": "Glasnevin",
            "building_code": "L",
            "building_name": "McNulty Building",
            "capacity": 120,
            "room_type": "Lecture Hall",
            "source_ids": {"timetable": "L_LG25"},
        },
        {
            "id": "lib-oreilly-gsr01",
            "code": "GSR 1",
            "name": "O'Reilly Library GSR 1",
            "campus": "Library GSRs",
            "building_code": "LIB_OREILLY",
            "building_name": "O'Reilly Library",
            "capacity": 6,
            "room_type": "Group Study Room",
            "source_ids": {"libcal": "oreilly_gsr_1"},
        },
    ]
    seed_file.write_text(json.dumps(seed_data))

    rooms = seed_rooms(temp_db, seed_file)
    assert len(rooms) == 2

    all_rooms = get_all_rooms(temp_db)
    assert len(all_rooms) == 2

    glasnevin_rooms = get_all_rooms(temp_db, campus_filter="Glasnevin")
    assert len(glasnevin_rooms) == 1
    assert glasnevin_rooms[0].code == "LG25"

    single_room = get_room_by_id(temp_db, "lib-oreilly-gsr01")
    assert single_room is not None
    assert single_room.code == "GSR 1"

    now = datetime.now(DUBLIN_TZ)
    block = OccupancyBlock(
        room_id="glasnevin-l-lg25",
        start_time=now,
        end_time=now + timedelta(hours=1),
        source="timetable",
        status=OccupancyStatus.BOOKED,
        summary="Lecture CA101",
    )
    cache_occupancy_blocks(temp_db, [block])

    cached = get_cached_occupancy_blocks(temp_db, room_ids=["glasnevin-l-lg25"])
    assert len(cached) == 1
    assert cached[0].summary == "Lecture CA101"


def test_ensure_dublin_tz():
    naive_dt = datetime(2026, 11, 23, 10, 0, 0)
    localized = ensure_dublin_tz(naive_dt)
    assert localized.tzinfo == DUBLIN_TZ

    utc_dt = datetime(2026, 11, 23, 10, 0, 0, tzinfo=ZoneInfo("UTC"))
    converted = ensure_dublin_tz(utc_dt)
    assert converted.tzinfo == DUBLIN_TZ


def test_operating_hours_window(sample_room):
    base_date = datetime(2026, 11, 23, tzinfo=DUBLIN_TZ)

    # 06:59 — Before 07:00
    before_7 = base_date.replace(hour=6, minute=59)
    avail_before = calculate_room_availability(sample_room, [], now=before_7)
    assert avail_before.is_within_operating_hours is False
    assert avail_before.is_available_now is False

    # 07:00 — Operating start boundary
    at_7 = base_date.replace(hour=7, minute=0)
    avail_at_7 = calculate_room_availability(sample_room, [], now=at_7)
    assert avail_at_7.is_within_operating_hours is True
    assert avail_at_7.is_available_now is True

    # 12:00 — Midday
    at_12 = base_date.replace(hour=12, minute=0)
    avail_at_12 = calculate_room_availability(sample_room, [], now=at_12)
    assert avail_at_12.is_within_operating_hours is True
    assert avail_at_12.is_available_now is True

    # 21:59 — Last minute of operating window
    at_21_59 = base_date.replace(hour=21, minute=59)
    avail_at_21_59 = calculate_room_availability(sample_room, [], now=at_21_59)
    assert avail_at_21_59.is_within_operating_hours is True
    assert avail_at_21_59.is_available_now is True

    # 22:00 — Closing boundary
    at_22 = base_date.replace(hour=22, minute=0)
    avail_at_22 = calculate_room_availability(sample_room, [], now=at_22)
    assert avail_at_22.is_within_operating_hours is False
    assert avail_at_22.is_available_now is False


def test_strict_current_occupancy_exclusion(sample_room):
    now = datetime(2026, 11, 23, 10, 30, tzinfo=DUBLIN_TZ)

    # Active booking: 10:00 to 11:30
    active_block = OccupancyBlock(
        room_id=sample_room.id,
        start_time=now.replace(hour=10, minute=0),
        end_time=now.replace(hour=11, minute=30),
        source="timetable",
        status=OccupancyStatus.BOOKED,
    )

    avail = calculate_room_availability(sample_room, [active_block], now=now)
    assert avail.is_available_now is False
    assert avail.remaining_minutes == 0

    # Boundary test: Booking ended exactly at 10:30 (end_time == now) -> Room is free now
    ended_block = OccupancyBlock(
        room_id=sample_room.id,
        start_time=now.replace(hour=9, minute=30),
        end_time=now.replace(hour=10, minute=30),
        source="timetable",
        status=OccupancyStatus.BOOKED,
    )
    avail_ended = calculate_room_availability(sample_room, [ended_block], now=now)
    assert avail_ended.is_available_now is True

    # Boundary test: Booking starting exactly at 10:30 (start_time == now) -> Room is occupied now
    starting_block = OccupancyBlock(
        room_id=sample_room.id,
        start_time=now.replace(hour=10, minute=30),
        end_time=now.replace(hour=11, minute=30),
        source="timetable",
        status=OccupancyStatus.BOOKED,
    )
    avail_starting = calculate_room_availability(sample_room, [starting_block], now=now)
    assert avail_starting.is_available_now is False


def test_free_window_calculation(sample_room):
    now = datetime(2026, 11, 23, 10, 0, tzinfo=DUBLIN_TZ)

    # Next booking starts at 12:30 (2h 30m = 150m from now)
    next_block = OccupancyBlock(
        room_id=sample_room.id,
        start_time=now.replace(hour=12, minute=30),
        end_time=now.replace(hour=14, minute=0),
        source="timetable",
        status=OccupancyStatus.BOOKED,
    )

    avail = calculate_room_availability(sample_room, [next_block], now=now)
    assert avail.is_available_now is True
    assert avail.free_until == now.replace(hour=12, minute=30)
    assert avail.free_until_str == "12:30"
    assert avail.remaining_minutes == 150

    # No future bookings -> free until 22:00 (12h = 720m from 10:00)
    avail_no_bookings = calculate_room_availability(sample_room, [], now=now)
    assert avail_no_bookings.is_available_now is True
    assert avail_no_bookings.free_until == now.replace(hour=22, minute=0)
    assert avail_no_bookings.free_until_str == "22:00"
    assert avail_no_bookings.remaining_minutes == 720


def test_timeline_blocks(sample_room):
    now = datetime(2026, 11, 23, 10, 0, tzinfo=DUBLIN_TZ)

    # Booking from 11:00 to 13:00
    block = OccupancyBlock(
        room_id=sample_room.id,
        start_time=now.replace(hour=11, minute=0),
        end_time=now.replace(hour=13, minute=0),
        source="timetable",
        status=OccupancyStatus.BOOKED,
    )

    avail = calculate_room_availability(sample_room, [block], now=now)
    assert len(avail.timeline) == 15  # 07:00 through 21:00 (15 hours)

    # 11:00-12:00 and 12:00-13:00 should be booked
    timeline_dict = {t.hour: t.status for t in avail.timeline}
    assert timeline_dict[7] == "free"
    assert timeline_dict[10] == "free"
    assert timeline_dict[11] == "booked"
    assert timeline_dict[12] == "booked"
    assert timeline_dict[13] == "free"


def test_filtering_and_sorting(sample_room):
    now = datetime(2026, 11, 23, 10, 0, tzinfo=DUBLIN_TZ)

    room_b = Room(
        id="lib-oreilly-gsr01",
        code="GSR 1",
        name="O'Reilly Library GSR 1",
        campus=Campus.LIBRARY_GSRS,
        building_code="LIB_OREILLY",
        building_name="O'Reilly Library",
        capacity=6,
        room_type=RoomType.GROUP_STUDY_ROOM,
    )

    # Room A (sample_room): free until 12:00 (120 min left)
    block_a = OccupancyBlock(
        room_id=sample_room.id,
        start_time=now.replace(hour=12, minute=0),
        end_time=now.replace(hour=14, minute=0),
        source="timetable",
    )
    avail_a = calculate_room_availability(sample_room, [block_a], now=now)

    # Room B (room_b): free until 16:00 (360 min left)
    block_b = OccupancyBlock(
        room_id=room_b.id,
        start_time=now.replace(hour=16, minute=0),
        end_time=now.replace(hour=17, minute=0),
        source="libcal",
    )
    avail_b = calculate_room_availability(room_b, [block_b], now=now)

    avails = [avail_a, avail_b]

    # Filter all campuses, min duration 60m
    results = filter_available_rooms(avails, min_duration_minutes=60)
    assert len(results) == 2
    # Sorted by free_until descending -> Room B (16:00) before Room A (12:00)
    assert results[0].room.id == room_b.id
    assert results[1].room.id == sample_room.id

    # Filter by campus: Library GSRs
    lib_results = filter_available_rooms(avails, campus_filter="Library GSRs")
    assert len(lib_results) == 1
    assert lib_results[0].room.id == room_b.id

    # Filter min duration 180m -> Only Room B qualifies (360 min)
    long_results = filter_available_rooms(avails, min_duration_minutes=180)
    assert len(long_results) == 1
    assert long_results[0].room.id == room_b.id


def test_future_date_availability_calculation(sample_room):
    now = datetime(2026, 11, 23, 10, 0, tzinfo=DUBLIN_TZ)
    future_date = (now + timedelta(days=2)).date()

    future_day_start = datetime(
        future_date.year, future_date.month, future_date.day, 7, 0, 0, tzinfo=DUBLIN_TZ
    )

    # Booking on future date from 09:00 to 11:00
    future_block = OccupancyBlock(
        room_id=sample_room.id,
        start_time=future_day_start.replace(hour=9, minute=0),
        end_time=future_day_start.replace(hour=11, minute=0),
        source="timetable",
        status=OccupancyStatus.BOOKED,
        summary="Future Lecture CA202",
    )

    avail = calculate_room_availability(
        sample_room, [future_block], now=now, target_date=future_date
    )

    assert avail.is_within_operating_hours is True
    assert avail.is_available_now is True
    assert avail.free_until_str == "09:00"
    # Total free time: 07:00-09:00 (120m) + 11:00-22:00 (660m) = 780m
    assert avail.remaining_minutes == 780

    timeline_dict = {t.hour: t.status for t in avail.timeline}
    assert timeline_dict[7] == "free"
    assert timeline_dict[8] == "free"
    assert timeline_dict[9] == "booked"
    assert timeline_dict[10] == "booked"
    assert timeline_dict[11] == "free"


def test_date_keyed_caching(temp_db):
    date_a = datetime(2026, 11, 24, tzinfo=DUBLIN_TZ).date()
    date_b = datetime(2026, 11, 25, tzinfo=DUBLIN_TZ).date()

    dt_a = datetime(2026, 11, 24, 10, 0, tzinfo=DUBLIN_TZ)
    dt_b = datetime(2026, 11, 25, 14, 0, tzinfo=DUBLIN_TZ)

    block_a = OccupancyBlock(
        room_id="glasnevin-l-lg25",
        start_time=dt_a,
        end_time=dt_a + timedelta(hours=2),
        source="timetable",
        summary="Day A Lecture",
    )

    block_b = OccupancyBlock(
        room_id="glasnevin-l-lg25",
        start_time=dt_b,
        end_time=dt_b + timedelta(hours=1),
        source="libcal",
        summary="Day B Study",
    )

    cache_occupancy_blocks(temp_db, [block_a], target_date=date_a)
    cache_occupancy_blocks(temp_db, [block_b], target_date=date_b)

    cached_a = get_cached_occupancy_blocks(temp_db, target_date=date_a)
    assert len(cached_a) == 1
    assert cached_a[0].summary == "Day A Lecture"

    cached_b = get_cached_occupancy_blocks(temp_db, target_date=date_b)
    assert len(cached_b) == 1
    assert cached_b[0].summary == "Day B Study"


def test_libcal_fail_closed_guard(sample_room):
    now = datetime(2026, 11, 23, 10, 0, tzinfo=DUBLIN_TZ)

    lib_room = Room(
        id="lib-oreilly-gsr06",
        code="GSR 6",
        name="O'Reilly Library GSR 6",
        campus=Campus.LIBRARY_GSRS,
        building_code="LIB_OREILLY",
        building_name="O'Reilly Library",
        capacity=8,
        room_type=RoomType.GROUP_STUDY_ROOM,
        source_ids={"libcal": "oreilly_gsr_6"},
    )

    # When LibCal scraper fails (health status False), room must be marked unavailable
    avail_failed = calculate_room_availability(
        lib_room, [], now=now, scraper_health={"libcal": False}
    )
    assert avail_failed.is_available_now is False
    assert avail_failed.remaining_minutes == 0
    assert avail_failed.free_until_str == "LIBCAL SCRAPE FAILED / UNAVAILABLE"

    # When LibCal scraper is healthy, room is evaluated normally
    avail_healthy = calculate_room_availability(
        lib_room, [], now=now, scraper_health={"libcal": True}
    )
    assert avail_healthy.is_available_now is True
    assert avail_healthy.remaining_minutes == 720  # 10:00 to 22:00


