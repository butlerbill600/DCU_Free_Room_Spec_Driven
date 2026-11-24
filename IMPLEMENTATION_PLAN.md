# DCU Room Finder Implementation Plan

## Phase 1: Core Engine & Seed Data (`feat/core-engine-and-seed`)
- [x] Create project configuration (`pyproject.toml`) and `.gitignore`
- [x] Create `data/rooms_seed.json` master registry for DCU rooms across campuses
- [x] Implement `src/models.py` for `Room`, `OccupancyBlock`, `RoomAvailability`, `Campus`, `RoomType`
- [x] Implement `src/database.py` for SQLite database operations and seed loading
- [x] Implement `src/engine.py` availability engine (07:00–22:00 Europe/Dublin timezone window, strict current occupancy exclusion, free_until, timeline blocks)
- [x] Implement unit tests in `tests/test_engine.py` testing operating hours, occupancy overlaps, boundary conditions, and filtering logic
- [x] Execute `pytest` to verify all Phase 1 tests pass

## Phase 2: Live Data Scrapers (`feat/dcu-live-scrapers`)
- [x] Implement `src/scrapers/base.py` standard `RoomSourceAdapter` interface
- [x] Implement `src/scrapers/timetable.py` for DCU Open Timetable / Scientia adapter
- [x] Implement `src/scrapers/libcal.py` for O'Reilly & Cregan Library LibCal adapter
- [x] Implement `src/scrapers/su_events.py` for SU / Events adapter
- [x] Write tests in `tests/test_scrapers.py` with mocked data
- [x] Verify concurrent scraping and graceful fallback logic

## Phase 3: FastAPI Backend & Desktop UI (`feat/fastapi-and-ui`)
- [x] Implement `src/main.py` FastAPI server & API endpoints (`/api/rooms/search`, `/api/health`, `/api/campuses`)
- [x] Build desktop UI in `src/ui/index.html` (Search control, campus filter pills, minimum duration filter, timeline visualizer)
- [x] Connect frontend to FastAPI backend with real-time updates and fallback badges
- [x] Verify backend & frontend integration

## Phase 4: macOS Dock App Bundle (`feat/macos-dock-app-bundle`)
- [x] Integrate `pywebview` for native macOS window lifecycle management in `src/main.py`
- [x] Generate app assets (`assets/dcu_rooms.icns`)
- [x] Configure PyInstaller build script/spec for `DCU Room Finder.app`
- [x] Build and test native macOS `.app` bundle launch

## Phase 5: 7-Day Rolling Date Selector (`feat/7-day-availability-bar`)
- [x] Document 7-day rolling date selector feature rules in `SPEC.md` and add Phase 5 to `IMPLEMENTATION_PLAN.md`
- [x] Update SQLite cache (`src/database.py`) and scrapers (`src/scrapers/`) to support date-keyed caching and date parameter
- [x] Update engine (`src/engine.py`) to calculate availability for future dates (`selected_date > today`) across 07:00–22:00 window
- [x] Update FastAPI endpoint (`src/main.py`) to accept optional `date` query parameter (validated in range `[today, today + 6 days]`)
- [x] Implement responsive 7-day horizontal selector bar in frontend (`src/ui/index.html`) with day pills (`Today`, `Tomorrow`, +5 days)
- [x] Write unit tests in `tests/` covering future-date availability calculations, date-keyed caching, and API date parameter validation
- [x] Rebuild native macOS app bundle with `build_app.py`
- [x] Open clean Pull Request into `main`
