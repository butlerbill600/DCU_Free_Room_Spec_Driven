from pathlib import Path

from src.utils import get_default_db_path, get_resource_path


def test_get_default_db_path():
    db_path = get_default_db_path()
    assert isinstance(db_path, Path)
    assert db_path.name == "dcu_rooms.db"
    assert "Application Support" in str(db_path)
    assert db_path.parent.exists()


def test_get_resource_path():
    seed_path = get_resource_path("data/rooms_seed.json")
    assert isinstance(seed_path, Path)
    assert seed_path.exists()
    assert seed_path.name == "rooms_seed.json"

    ui_path = get_resource_path("src/ui/index.html")
    assert ui_path.exists()
    assert ui_path.name == "index.html"
