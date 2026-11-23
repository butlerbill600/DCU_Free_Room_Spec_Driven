import json
import sqlite3
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional, Union
from src.models import Campus, OccupancyBlock, OccupancyStatus, Room, RoomType


def init_db(db_path: Union[str, Path] = "dcu_rooms.db") -> None:
    """Initialize SQLite database tables for rooms and occupancy cache."""
    conn = sqlite3.connect(db_path)
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
            FOREIGN KEY (room_id) REFERENCES rooms (id)
        )
    """)

    conn.commit()
    conn.close()


def seed_rooms(
    db_path: Union[str, Path] = "dcu_rooms.db",
    seed_file: Union[str, Path] = "data/rooms_seed.json"
) -> List[Room]:
    """Seed database with master room registry from JSON file."""
    init_db(db_path)
    seed_path = Path(seed_file)
    if not seed_path.exists():
        raise FileNotFoundError(f"Seed file not found at {seed_file}")

    with open(seed_path, "r", encoding="utf-8") as f:
        rooms_data = json.load(f)

    rooms: List[Room] = []
    conn = sqlite3.connect(db_path)
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
    db_path: Union[str, Path] = "dcu_rooms.db",
    campus_filter: Optional[str] = None
) -> List[Room]:
    """Retrieve all rooms from database, optionally filtered by campus."""
    conn = sqlite3.connect(db_path)
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
    db_path: Union[str, Path] = "dcu_rooms.db",
    room_id: str = ""
) -> Optional[Room]:
    """Retrieve a single room by its unique ID."""
    conn = sqlite3.connect(db_path)
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
    db_path: Union[str, Path] = "dcu_rooms.db",
    blocks: List[OccupancyBlock] = None
) -> None:
    """Save scraped occupancy blocks into SQLite cache."""
    if not blocks:
        return

    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    fetched_at = datetime.now(timezone.utc).isoformat()

    for block in blocks:
        cursor.execute(
            """
            INSERT INTO occupancy_cache (
                room_id, start_time, end_time, source, status, summary, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                block.room_id,
                block.start_time.isoformat(),
                block.end_time.isoformat(),
                block.source,
                block.status.value,
                block.summary,
                fetched_at,
            ),
        )

    conn.commit()
    conn.close()


def get_cached_occupancy_blocks(
    db_path: Union[str, Path] = "dcu_rooms.db",
    room_ids: Optional[List[str]] = None
) -> List[OccupancyBlock]:
    """Retrieve stored occupancy blocks from SQLite cache."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if room_ids:
        placeholders = ",".join("?" for _ in room_ids)
        cursor.execute(
            f"SELECT room_id, start_time, end_time, source, status, summary FROM occupancy_cache WHERE room_id IN ({placeholders})",
            room_ids,
        )
    else:
        cursor.execute(
            "SELECT room_id, start_time, end_time, source, status, summary FROM occupancy_cache"
        )

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
