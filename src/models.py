from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class Campus(str, Enum):
    GLASNEVIN = "Glasnevin"
    ST_PATRICKS = "St. Patrick's"
    ALL_HALLOWS = "All Hallows"
    LIBRARY_GSRS = "Library GSRs"


class RoomType(str, Enum):
    LECTURE_HALL = "Lecture Hall"
    COMPUTER_LAB = "Computer Lab"
    GROUP_STUDY_ROOM = "Group Study Room"
    MEETING_ROOM = "Meeting Room"
    CLASSROOM = "Classroom"


class OccupancyStatus(str, Enum):
    BOOKED = "booked"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class Room(BaseModel):
    id: str
    code: str
    name: str
    campus: Campus
    building_code: str
    building_name: str
    capacity: int
    room_type: RoomType
    source_ids: Dict[str, str] = Field(default_factory=dict)


class OccupancyBlock(BaseModel):
    room_id: str
    start_time: datetime
    end_time: datetime
    source: str
    status: OccupancyStatus = OccupancyStatus.BOOKED
    summary: Optional[str] = None


class TimelineBlock(BaseModel):
    hour: int
    start_time_str: str
    end_time_str: str
    status: str  # "free" or "booked"


class RoomAvailability(BaseModel):
    room: Room
    is_available_now: bool
    is_within_operating_hours: bool = True
    free_until: Optional[datetime] = None
    free_until_str: Optional[str] = None
    remaining_minutes: int = 0
    timeline: List[TimelineBlock] = Field(default_factory=list)
    occupancy_blocks: List[OccupancyBlock] = Field(default_factory=list)
