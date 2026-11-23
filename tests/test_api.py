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
async def test_serve_ui_homepage():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert "DCU Room Finder" in response.text
