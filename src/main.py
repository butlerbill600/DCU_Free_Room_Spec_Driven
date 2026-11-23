import argparse
import logging
import socket
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from src.database import (
    get_all_rooms,
    get_cached_occupancy_blocks,
    init_db,
    seed_rooms,
)
from src.engine import (
    DUBLIN_TZ,
    calculate_room_availability,
    filter_available_rooms,
)
from src.models import Campus, RoomAvailability
from src.scrapers.aggregator import ScrapeAggregator

logger = logging.getLogger("dcu_room_finder")
DB_PATH = "dcu_rooms.db"
SEED_PATH = "data/rooms_seed.json"
UI_DIR = Path(__file__).parent / "ui"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager to initialize database and seed room registry."""
    init_db(DB_PATH)
    try:
        existing_rooms = get_all_rooms(DB_PATH)
        if not existing_rooms and Path(SEED_PATH).exists():
            seed_rooms(DB_PATH, SEED_PATH)
            logger.info("Seeded initial rooms database successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize rooms database: {e}")
    yield


app = FastAPI(
    title="DCU Room Finder API",
    description="Real-time DCU free room search backend",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/api/health")
async def health_check():
    """Health status check endpoint."""
    now_dublin = datetime.now(DUBLIN_TZ)
    rooms = get_all_rooms(DB_PATH)
    return {
        "status": "healthy",
        "timestamp": now_dublin.isoformat(),
        "database_connected": True,
        "registered_rooms_count": len(rooms),
    }


@app.get("/api/campuses")
async def get_campuses():
    """Returns available campus filter options."""
    return [
        "All Campuses",
        Campus.GLASNEVIN.value,
        Campus.ST_PATRICKS.value,
        Campus.ALL_HALLOWS.value,
        Campus.LIBRARY_GSRS.value,
    ]


@app.get("/api/rooms/search")
async def search_rooms(
    campus: str = Query("All Campuses", description="Campus filter pill"),
    min_duration: int = Query(0, description="Minimum free duration in minutes (e.g. 0, 30, 60, 120)"),
    date_str: Optional[str] = Query(None, alias="date", description="Target search date (YYYY-MM-DD)"),
    force_refresh: bool = Query(True, description="Query live scrapers if true; use SQLite cache if false"),
):
    """Search for currently available rooms across DCU campuses."""
    now_dublin = datetime.now(DUBLIN_TZ)

    if date_str:
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    else:
        target_date = now_dublin.date()

    rooms = get_all_rooms(DB_PATH)
    if not rooms and Path(SEED_PATH).exists():
        rooms = seed_rooms(DB_PATH, SEED_PATH)

    health_status: Dict[str, bool] = {"timetable": True, "libcal": True, "su_events": True}
    is_cached_fallback = False

    if force_refresh and target_date == now_dublin.date():
        aggregator = ScrapeAggregator()
        agg_result = await aggregator.fetch_all(
            rooms=rooms,
            target_date=target_date,
            db_path=DB_PATH,
            timeout_seconds=4.0,
        )
        occupancy_blocks = agg_result.blocks
        health_status = agg_result.health_status
        is_cached_fallback = agg_result.is_cached_fallback
    else:
        occupancy_blocks = get_cached_occupancy_blocks(DB_PATH)
        is_cached_fallback = True

    # Compute availability for each room
    all_availabilities: List[RoomAvailability] = []
    for room in rooms:
        avail = calculate_room_availability(room, occupancy_blocks, now=now_dublin)
        all_availabilities.append(avail)

    # Filter available rooms by campus and duration
    filtered = filter_available_rooms(
        all_availabilities,
        min_duration_minutes=min_duration,
        campus_filter=campus,
    )

    day_start = now_dublin.replace(hour=7, minute=0, second=0, microsecond=0)
    day_end = now_dublin.replace(hour=22, minute=0, second=0, microsecond=0)
    outside_operating_hours = not (day_start <= now_dublin < day_end)

    return {
        "timestamp": now_dublin.isoformat(),
        "date": target_date.isoformat(),
        "operating_hours_banner": outside_operating_hours,
        "is_cached_fallback": is_cached_fallback,
        "health_status": health_status,
        "total_rooms": len(rooms),
        "available_rooms_count": len(filtered),
        "rooms": [ra.model_dump() for ra in filtered],
    }


@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    """Serve desktop UI single-page application."""
    index_file = UI_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h2>DCU Room Finder UI loading...</h2>")
    return FileResponse(index_file)


if UI_DIR.exists():
    app.mount("/static", StaticFiles(directory=UI_DIR), name="static")


def find_free_port() -> int:
    """Bind to an ephemeral port to locate a free port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class UvicornServerThread(threading.Thread):
    """Background thread running Uvicorn FastAPI server."""

    def __init__(self, host: str, port: int):
        super().__init__(daemon=True)
        config = uvicorn.Config(app, host=host, port=port, log_level="warning")
        self.server = uvicorn.Server(config)

    def run(self):
        self.server.run()

    def stop(self):
        self.server.should_exit = True


def start_desktop_app():
    """Launch native macOS pywebview window connected to ephemeral FastAPI backend server."""
    port = find_free_port()
    server_thread = UvicornServerThread("127.0.0.1", port)
    server_thread.start()

    # Wait briefly for FastAPI server socket to bind
    time.sleep(0.4)

    url = f"http://127.0.0.1:{port}"

    try:
        import webview

        window = webview.create_window(
            title="DCU Room Finder",
            url=url,
            width=1150,
            height=820,
            min_size=(800, 600),
            resizable=True,
        )
        webview.start()
    except Exception as e:
        logger.error(f"pywebview failed to launch: {e}. Defaulting to browser.", exc_info=True)
        import webbrowser
        webbrowser.open(url)
        try:
            while server_thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    finally:
        server_thread.stop()


def main():
    parser = argparse.ArgumentParser(description="DCU Room Finder Desktop App")
    parser.add_argument("--server-only", action="store_true", help="Run FastAPI server only (no desktop window)")
    parser.add_argument("--port", type=int, default=8000, help="Port for server-only mode")
    args = parser.parse_args()

    if args.server_only:
        uvicorn.run(app, host="127.0.0.1", port=args.port)
    else:
        start_desktop_app()


if __name__ == "__main__":
    main()
