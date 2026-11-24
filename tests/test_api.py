import pytest
from httpx import ASGITransport, AsyncClient

from src.database import init_db, seed_rooms
from src.main import app, DB_PATH, SEED_PATH


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_api_dcu_rooms.db")
    init_db(test_db)
    seed_rooms(test_db, "data/rooms_seed.json")
    monkeypatch.setattr("src.main.DB_PATH", test_db)


@pytest.mark.asyncio
async def test_health_check_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database_connected"] is True
        assert data["registered_rooms_count"] > 0


@pytest.mark.asyncio
async def test_campuses_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/campuses")
        assert response.status_code == 200
        campuses = response.json()
        assert "All Campuses" in campuses
        assert "Glasnevin" in campuses
        assert "Library GSRs" in campuses


@pytest.mark.asyncio
async def test_search_rooms_endpoint_default():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Use force_refresh=false to query database cache quickly
        response = await client.get("/api/rooms/search?force_refresh=false")
        assert response.status_code == 200
        data = response.json()
        assert "timestamp" in data
        assert "available_rooms_count" in data
        assert "rooms" in data
        assert isinstance(data["rooms"], list)


@pytest.mark.asyncio
async def test_search_rooms_endpoint_campus_filter():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/rooms/search?campus=Library+GSRs&force_refresh=false")
        assert response.status_code == 200
        data = response.json()
        for r in data["rooms"]:
            assert r["room"]["campus"] == "Library GSRs"


@pytest.mark.asyncio
async def test_search_rooms_endpoint_duration_filter():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/rooms/search?min_duration=120&force_refresh=false")
        assert response.status_code == 200
        data = response.json()
        for r in data["rooms"]:
            assert r["remaining_minutes"] >= 120


@pytest.mark.asyncio
async def test_search_rooms_endpoint_date_parameter():
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    dublin_now = datetime.now(ZoneInfo("Europe/Dublin"))
    today = dublin_now.date()
    tomorrow = today + timedelta(days=1)
    out_of_range = today + timedelta(days=10)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Valid future date within 7-day rolling window
        resp_valid = await client.get(f"/api/rooms/search?date={tomorrow.isoformat()}&force_refresh=false")
        assert resp_valid.status_code == 200
        data_valid = resp_valid.json()
        assert data_valid["date"] == tomorrow.isoformat()
        assert data_valid["is_today"] is False

        # Invalid date format
        resp_invalid = await client.get("/api/rooms/search?date=invalid-date")
        assert resp_invalid.status_code == 400
        assert "Invalid date format" in resp_invalid.json()["detail"]

        # Out-of-range date (> +6 days)
        resp_out = await client.get(f"/api/rooms/search?date={out_of_range.isoformat()}")
        assert resp_out.status_code == 400
        assert "Date out of range" in resp_out.json()["detail"]


@pytest.mark.asyncio
async def test_serve_ui_homepage():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert "DCU Room Finder" in response.text
