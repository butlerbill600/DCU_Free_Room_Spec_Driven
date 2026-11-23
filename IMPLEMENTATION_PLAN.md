# DCU Room Finder Implementation Plan

## Phase 1: Core Engine & Seed Data (`feat/core-engine-and-seed`)
- [ ] Create project configuration (`pyproject.toml`) and `.gitignore`
- [ ] Create `data/rooms_seed.json` master registry for DCU rooms across campuses
- [ ] Implement `src/models.py` for `Room`, `OccupancyBlock`, `RoomAvailability`, `Campus`, `RoomType`
- [ ] Implement `src/database.py` for SQLite database operations and seed loading
- [ ] Implement `src/engine.py` availability engine (07:00–22:00 Europe/Dublin timezone window, strict current occupancy exclusion, free_until, timeline blocks)
- [ ] Implement unit tests in `tests/test_engine.py` testing operating hours, occupancy overlaps, boundary conditions, and filtering logic
- [ ] Execute `pytest` to verify all Phase 1 tests pass

## Phase 2: Live Data Scrapers (`feat/dcu-live-scrapers`)
- [ ] Implement `src/scrapers/base.py` standard `RoomSourceAdapter` interface
- [ ] Implement `src/scrapers/timetable.py` for DCU Open Timetable / Scientia adapter
- [ ] Implement `src/scrapers/libcal.py` for O'Reilly & Cregan Library LibCal adapter
- [ ] Implement `src/scrapers/su_events.py` for SU / Events adapter
- [ ] Write tests in `tests/test_scrapers.py` with mocked data
- [ ] Verify concurrent scraping and graceful fallback logic

## Phase 3: FastAPI Backend & Desktop UI (`feat/fastapi-and-ui`)
- [ ] Implement `src/main.py` FastAPI server & API endpoints (`/api/rooms/search`, `/api/health`, `/api/campuses`)
- [ ] Build desktop UI in `src/ui/index.html` (Search control, campus filter pills, minimum duration filter, timeline visualizer)
- [ ] Connect frontend to FastAPI backend with real-time updates and fallback badges
- [ ] Verify backend & frontend integration

## Phase 4: macOS Dock App Bundle (`feat/macos-dock-app-bundle`)
- [ ] Integrate `pywebview` for native macOS window lifecycle management in `src/main.py`
- [ ] Generate app assets (`assets/dcu_rooms.icns`)
- [ ] Configure PyInstaller build script/spec for `DCU Room Finder.app`
- [ ] Build and test native macOS `.app` bundle launch
