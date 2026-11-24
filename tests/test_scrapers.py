import asyncio
from datetime import date, datetime, timedelta
from typing import List
from zoneinfo import ZoneInfo
import pytest
import httpx

from src.database import cache_occupancy_blocks, init_db
from src.engine import DUBLIN_TZ
from src.models import Campus, OccupancyBlock, OccupancyStatus, Room, RoomType
from src.scrapers.aggregator import ScrapeAggregator
from src.scrapers.base import RoomSourceAdapter, ScraperResult
from src.scrapers.libcal import LibCalScraper
from src.scrapers.su_events import SUEventsScraper
from src.scrapers.timetable import TimetableScraper


@pytest.fixture
def sample_rooms() -> List[Room]:
    return [
        Room(
            id="glasnevin-l-lg25",
            code="LG25",
            name="McNulty Lecture Theatre",
            campus=Campus.GLASNEVIN,
            building_code="L",
            building_name="McNulty Building",
            capacity=120,
            room_type=RoomType.LECTURE_HALL,
            source_ids={"timetable": "L_LG25", "su_events": "L_LG25"},
        ),
        Room(
            id="lib-oreilly-gsr01",
            code="GSR 1",
            name="O'Reilly Library GSR 1",
            campus=Campus.LIBRARY_GSRS,
            building_code="LIB_OREILLY",
            building_name="O'Reilly Library",
            capacity=6,
            room_type=RoomType.GROUP_STUDY_ROOM,
            source_ids={"libcal": "oreilly_gsr_1"},
        ),
    ]


@pytest.mark.asyncio
async def test_timetable_scraper_json(sample_rooms, monkeypatch):
    target_date = date(2026, 11, 23)
    scraper = TimetableScraper(base_url="https://mock-timetable.dcu.ie")

    mock_json_data = {
        "events": [
            {
                "location": "L_LG25",
                "start_time": "09:00",
                "end_time": "11:00",
                "description": "CA101 Programming Fundamentals",
            }
        ]
    }

    class MockResponse:
        status_code = 200
        headers = {"content-type": "application/json"}

        def json(self):
            return mock_json_data

        @property
        def text(self):
            return ""

    async def mock_get(self, url, params=None):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    blocks = await scraper.fetch_occupancy_blocks(sample_rooms, target_date)
    assert len(blocks) == 1
    assert blocks[0].room_id == "glasnevin-l-lg25"
    assert blocks[0].summary == "CA101 Programming Fundamentals"
    assert blocks[0].start_time == datetime(2026, 11, 23, 9, 0, tzinfo=DUBLIN_TZ)
    assert blocks[0].end_time == datetime(2026, 11, 23, 11, 0, tzinfo=DUBLIN_TZ)


@pytest.mark.asyncio
async def test_timetable_scraper_html(sample_rooms, monkeypatch):
    target_date = date(2026, 11, 23)
    scraper = TimetableScraper(base_url="https://mock-timetable.dcu.ie")

    mock_html = """
    <div class="timetable-grid">
        <div class="timetable-event" data-room="L_LG25" data-start="14:00" data-end="16:00">
            Lecture EE202 Digital Logic
        </div>
    </div>
    """

    class MockResponse:
        status_code = 200
        headers = {"content-type": "text/html"}

        def json(self):
            return {}

        @property
        def text(self):
            return mock_html

    async def mock_get(self, url, params=None):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    blocks = await scraper.fetch_occupancy_blocks(sample_rooms, target_date)
    assert len(blocks) == 1
    assert blocks[0].room_id == "glasnevin-l-lg25"
    assert "EE202 Digital Logic" in blocks[0].summary
    assert blocks[0].start_time == datetime(2026, 11, 23, 14, 0, tzinfo=DUBLIN_TZ)


@pytest.mark.asyncio
async def test_libcal_scraper(sample_rooms, monkeypatch):
    target_date = date(2026, 11, 23)
    scraper = LibCalScraper(base_url="https://mock-libcal.dcu.ie")

    mock_libcal_grid = {
        "slots": [
            {
                "item_id": "oreilly_gsr_1",
                "start": "2026-11-23T10:00:00+00:00",
                "end": "2026-11-23T11:00:00+00:00",
                "is_available": False,
                "className": "s-lc-eq-checkout",
            },
            {
                "item_id": "oreilly_gsr_1",
                "start": "2026-11-23T11:00:00+00:00",
                "end": "2026-11-23T12:00:00+00:00",
                "is_available": True,
                "className": "s-lc-eq-avail",
            },
        ]
    }

    class MockResponse:
        status_code = 200
        headers = {"content-type": "application/json"}

        def json(self):
            return mock_libcal_grid

    async def mock_get(self, url, params=None):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    blocks = await scraper.fetch_occupancy_blocks(sample_rooms, target_date)
    assert len(blocks) == 1
    assert blocks[0].room_id == "lib-oreilly-gsr01"
    assert blocks[0].source == "libcal"


@pytest.mark.asyncio
async def test_libcal_scraper_dom_html_fallback(sample_rooms, monkeypatch):
    target_date = date(2026, 11, 23)
    scraper = LibCalScraper(base_url="https://mock-libcal.dcu.ie")

    mock_html = """
    <div class="fc-timeline flex-container">
        <div class="fc-timeline-event s-lc-eq-period-unavailable" title="14:00 - 15:00 - GSR 1 - Unavailable">
            14:00 - 15:00 - GSR 1 - Unavailable
        </div>
    </div>
    """

    class MockResponse:
        status_code = 200
        headers = {"content-type": "text/html"}

        def json(self):
            return {}

        @property
        def text(self):
            return mock_html

    async def mock_get(self, url, params=None):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    blocks = await scraper.fetch_occupancy_blocks(sample_rooms, target_date)
    assert len(blocks) == 1
    assert blocks[0].room_id == "lib-oreilly-gsr01"
    assert blocks[0].start_time == datetime(2026, 11, 23, 14, 0, tzinfo=DUBLIN_TZ)
    assert blocks[0].end_time == datetime(2026, 11, 23, 15, 0, tzinfo=DUBLIN_TZ)


@pytest.mark.asyncio
async def test_libcal_scraper_error_handling(sample_rooms, monkeypatch):
    target_date = date(2026, 11, 23)
    scraper = LibCalScraper(base_url="https://mock-libcal.dcu.ie")

    class MockResponse500:
        status_code = 500
        headers = {"content-type": "text/html"}
        text = "Internal Server Error"

    async def mock_get(self, url, params=None):
        return MockResponse500()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    res = await scraper.fetch_safe(sample_rooms, target_date)
    assert res.success is False
    assert "HTTP 500" in res.error_message


@pytest.mark.asyncio
async def test_su_events_scraper(sample_rooms, monkeypatch):
    target_date = date(2026, 11, 23)
    scraper = SUEventsScraper(base_url="https://mock-su.dcu.ie")

    mock_su_json = {
        "events": [
            {
                "location": "L_LG25",
                "start_time": "18:00",
                "end_time": "20:00",
                "title": "Redbreak Soc Weekly Meetup",
            }
        ]
    }

    class MockResponse:
        status_code = 200
        headers = {"content-type": "application/json"}

        def json(self):
            return mock_su_json

    async def mock_get(self, url, params=None):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    blocks = await scraper.fetch_occupancy_blocks(sample_rooms, target_date)
    assert len(blocks) == 1
    assert blocks[0].room_id == "glasnevin-l-lg25"
    assert blocks[0].summary == "Redbreak Soc Weekly Meetup"


class DummyFailingScraper(RoomSourceAdapter):
    @property
    def source_name(self) -> str:
        return "failing_source"

    async def fetch_occupancy_blocks(self, rooms: List[Room], target_date: date) -> List[OccupancyBlock]:
        raise RuntimeError("Endpoint connection refused")


class DummySlowScraper(RoomSourceAdapter):
    @property
    def source_name(self) -> str:
        return "slow_source"

    async def fetch_occupancy_blocks(self, rooms: List[Room], target_date: date) -> List[OccupancyBlock]:
        await asyncio.sleep(2.0)
        return []


@pytest.mark.asyncio
async def test_aggregator_resiliency_and_fallback(sample_rooms, tmp_path):
    db_file = str(tmp_path / "test_aggregator.db")
    init_db(db_file)

    # Seed cached block into db
    cached_block = OccupancyBlock(
        room_id="glasnevin-l-lg25",
        start_time=datetime(2026, 11, 23, 9, 0, tzinfo=DUBLIN_TZ),
        end_time=datetime(2026, 11, 23, 10, 0, tzinfo=DUBLIN_TZ),
        source="cached_timetable",
        summary="Cached Lecture",
    )
    cache_occupancy_blocks(db_file, [cached_block])

    failing = DummyFailingScraper()
    slow = DummySlowScraper()

    aggregator = ScrapeAggregator(adapters=[failing, slow])
    res = await aggregator.fetch_all(
        sample_rooms, date(2026, 11, 23), db_path=db_file, timeout_seconds=0.1
    )

    # Check health status flags
    assert res.health_status["failing_source"] is False
    assert res.health_status["slow_source"] is False
    assert "timed out" in res.errors["slow_source"]

    # Check that fallback to cached SQLite data occurred
    assert res.is_cached_fallback is True
    assert len(res.blocks) == 1
    assert res.blocks[0].summary == "Cached Lecture"
