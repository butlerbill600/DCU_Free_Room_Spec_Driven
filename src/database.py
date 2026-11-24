import json
import sqlite3
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional, Union

from src.models import Campus, OccupancyBlock, OccupancyStatus, Room, RoomType
from src.utils import get_default_db_path, get_resource_path


def _resolve_db_path(db_path: Optional[Union[str, Path]] = None) -> Union[str, Path]:
    """Resolve database path, creating parent directories for file paths."""
    if db_path is None:
        db_path = get_default_db_path()

    db_str = str(db_path)
    if db_str == ":memory:":
        return ":memory:"

    path_obj = Path(db_path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    return path_obj


def init_db(db_path: Optional[Union[str, Path]] = None) -> None:
    """Initialize SQLite database tables for rooms and occupancy cache."""
    resolved_path = _resolve_db_path(db_path)
    conn = sqlite3.connect(resolved_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rooms (
            id TEXT PRIMARY KEY,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            campus TEXT NOT NULL,
            building_code TEXT NOT NULL,
            building_name TEXT NOT NULL,
            capacity INTEGER NOT NULL,
            room_type TEXT NOT NULL,
            source_ids TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS occupancy_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            source TEXT NOT NULL,
            status TEXT NOT NULL,
            summary TEXT,
            fetched_at TEXT NOT NULL,
            target_date TEXT,
            FOREIGN KEY (room_id) REFERENCES rooms (id)
        )
    """)

    # Ensure target_date column exists for upgraded existing databases
    cursor.execute("PRAGMA table_info(occupancy_cache)")
    columns = [col[1] for col in cursor.fetchall()]
    if "target_date" not in columns:
        cursor.execute("ALTER TABLE occupancy_cache ADD COLUMN target_date TEXT")

    conn.commit()
    conn.close()


def seed_rooms(
    db_path: Optional[Union[str, Path]] = None,
    seed_file: Optional[Union[str, Path]] = None,
) -> List[Room]:
    """Seed database with master room registry from JSON file."""
    if seed_file is None:
        seed_path = get_resource_path("data/rooms_seed.json")
    else:
        seed_path = Path(seed_file)

    if not seed_path.exists():
        raise FileNotFoundError(f"Seed file not found at {seed_path}")

    resolved_db_path = _resolve_db_path(db_path)
    init_db(resolved_db_path)

    with open(seed_path, "r", encoding="utf-8") as f:
        rooms_data = json.load(f)

    rooms: List[Room] = []
    conn = sqlite3.connect(resolved_db_path)
    cursor = conn.cursor()

    for item in rooms_data:
        room = Room(**item)
        rooms.append(room)
        cursor.execute(
            """
            INSERT OR REPLACE INTO rooms (
                id, code, name, campus, building_code, building_name, capacity, room_type, source_ids
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                room.id,
                room.code,
                room.name,
                room.campus.value if isinstance(room.campus, Enum) else str(room.campus),
                room.building_code,
                room.building_name,
                room.capacity,
                room.room_type.value if isinstance(room.room_type, Enum) else str(room.room_type),
                json.dumps(room.source_ids),
            ),
        )

    conn.commit()
    conn.close()
    return rooms


def get_all_rooms(
    db_path: Optional[Union[str, Path]] = None,
    campus_filter: Optional[str] = None,
) -> List[Room]:
    """Retrieve all rooms from database, optionally filtered by campus."""
    resolved_db_path = _resolve_db_path(db_path)
    conn = sqlite3.connect(resolved_db_path)
    cursor = conn.cursor()

    if campus_filter and campus_filter != "All Campuses":
        cursor.execute(
            "SELECT id, code, name, campus, building_code, building_name, capacity, room_type, source_ids FROM rooms WHERE campus = ?",
            (campus_filter,),
        )
    else:
        cursor.execute(
            "SELECT id, code, name, campus, building_code, building_name, capacity, room_type, source_ids FROM rooms"
        )

    rows = cursor.fetchall()
    conn.close()

    rooms: List[Room] = []
    for row in rows:
        rooms.append(
            Room(
                id=row[0],
                code=row[1],
                name=row[2],
                campus=Campus(row[3]),
                building_code=row[4],
                building_name=row[5],
                capacity=row[6],
                room_type=RoomType(row[7]),
                source_ids=json.loads(row[8]),
            )
        )
    return rooms


def get_room_by_id(
    db_path: Optional[Union[str, Path]] = None,
    room_id: str = "",
) -> Optional[Room]:
    """Retrieve a single room by its unique ID."""
    resolved_db_path = _resolve_db_path(db_path)
    conn = sqlite3.connect(resolved_db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, code, name, campus, building_code, building_name, capacity, room_type, source_ids FROM rooms WHERE id = ?",
        (room_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return Room(
        id=row[0],
        code=row[1],
        name=row[2],
        campus=Campus(row[3]),
        building_code=row[4],
        building_name=row[5],
        capacity=row[6],
        room_type=RoomType(row[7]),
        source_ids=json.loads(row[8]),
    )


def cache_occupancy_blocks(
    db_path: Optional[Union[str, Path]] = None,
    blocks: Optional[List[OccupancyBlock]] = None,
    target_date: Optional[date] = None,
) -> None:
    """Save scraped occupancy blocks into SQLite cache, keyed by target_date."""
    if not blocks:
        return

    resolved_db_path = _resolve_db_path(db_path)
    init_db(resolved_db_path)
    conn = sqlite3.connect(resolved_db_path)
    cursor = conn.cursor()
    fetched_at = datetime.now(timezone.utc).isoformat()

    target_date_str = target_date.isoformat() if target_date else blocks[0].start_time.date().isoformat()

    # Clear existing cached blocks for this target_date to avoid duplicates upon re-cache
    cursor.execute("DELETE FROM occupancy_cache WHERE target_date = ?", (target_date_str,))

    for block in blocks:
        b_status = block.status.value if isinstance(block.status, Enum) else str(block.status)
        cursor.execute(
            """
            INSERT INTO occupancy_cache (
                room_id, start_time, end_time, source, status, summary, fetched_at, target_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                block.room_id,
                block.start_time.isoformat(),
                block.end_time.isoformat(),
                block.source,
                b_status,
                block.summary,
                fetched_at,
                target_date_str,
            ),
        )

    conn.commit()
    conn.close()


def get_cached_occupancy_blocks(
    db_path: Optional[Union[str, Path]] = None,
    room_ids: Optional[List[str]] = None,
    target_date: Optional[date] = None,
) -> List[OccupancyBlock]:
    """Retrieve stored occupancy blocks from SQLite cache, optionally filtered by room_ids and target_date."""
    resolved_db_path = _resolve_db_path(db_path)
    conn = sqlite3.connect(resolved_db_path)
    cursor = conn.cursor()

    query = "SELECT room_id, start_time, end_time, source, status, summary FROM occupancy_cache WHERE 1=1"
    params: List[Union[str, int]] = []

    if room_ids:
        placeholders = ",".join("?" for _ in room_ids)
        query += f" AND room_id IN ({placeholders})"
        params.extend(room_ids)

    if target_date:
        t_str = target_date.isoformat()
        query += " AND (target_date = ? OR (target_date IS NULL AND start_time LIKE ?))"
        params.extend([t_str, f"{t_str}%"])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    blocks: List[OccupancyBlock] = []
    for row in rows:
        blocks.append(
            OccupancyBlock(
                room_id=row[0],
                start_time=datetime.fromisoformat(row[1]),
                end_time=datetime.fromisoformat(row[2]),
                source=row[3],
                status=OccupancyStatus(row[4]),
                summary=row[5],
            )
        )
    return blocks
