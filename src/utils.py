import sys
from pathlib import Path


def get_default_db_path() -> Path:
    """Get writable SQLite database path in user Application Support directory on macOS."""
    app_support = Path.home() / "Library" / "Application Support" / "DCU Room Finder"
    app_support.mkdir(parents=True, exist_ok=True)
    return app_support / "dcu_rooms.db"


def get_resource_path(relative_path: str) -> Path:
    """Resolve file path for normal runtime or PyInstaller bundled environment (_MEIPASS)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_path = Path(sys._MEIPASS)
    else:
        # Base directory is workspace root (parent of src/)
        base_path = Path(__file__).resolve().parent.parent
    return base_path / relative_path
