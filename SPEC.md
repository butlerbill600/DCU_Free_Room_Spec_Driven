# SPEC.md — DCU Room Finder (macOS Native Desktop Utility)

## 1. Overview & Vision
**DCU Room Finder** is a zero-terminal, single-click macOS desktop application designed to live in the macOS Dock. When launched and triggered via a top-bar **Search** action, it concurrently queries Dublin City University (DCU) scheduling and room-booking endpoints across Glasnevin, St. Patrick's, and All Hallows campuses, filters out currently occupied rooms, and renders a clean, real-time view of available spaces between **07:00 and 22:00** (Europe/Dublin).

### Core Design Goals
* **Zero-CLI Experience:** Double-click launch from the macOS Dock/Applications folder; embedded local server lifecycle managed automatically in the background.
* **Multi-Source Aggregation:** Normalizes room occupancy across lectures, library study spaces, and student society bookings into a single source of truth.
* **Resilient & Fast:** Asynchronous concurrent scraping with local SQLite caching, rate-limit protection, and graceful fallback if a single DCU portal is slow or undergoing maintenance.

---

## 2. Target Data Sources & Architecture

### 2.1 Master Room Registry (`rooms.json` / SQLite `rooms` table)
A pre-seeded, extensible catalog of DCU rooms across campuses, tagged with building code, room code, campus, capacity, room type (lecture hall, computer lab, group study room, meeting room), and source identifiers:
* **Academic & Lecture Rooms:** McNulty Building (`L`), Stokes (`S`/`SG`/`SA`), Henry Grattan (`CG`/`C`), Albert College (`AG`), Nursing (`HG`), Business School (`Q`), St. Patrick's (`E`/`F`/`G`), All Hallows.
* **Library Group Study Rooms (GSRs):**
  * *O'Reilly Library (Glasnevin):* Ground Floor (`GSR 1`), First Floor (`GSR 6, 7, 9, 10`), Second Floor (`GSR 13, 14, 15, 16`) + standard rooms (`3, 4, 5, 8, 12, 17, 18`).
  * *Cregan Library (St. Patrick's):* `G215`, `G315`.
* **Student Union & Clubs/Socs Spaces:** U Building (`U` rooms), Clubs & Socs allocated rooms.

### 2.2 Live Data Connectors (Scrapers / API Clients)
Each connector implements a unified `RoomSourceAdapter` interface returning normalized `OccupancyBlock` objects (`room_id`, `start_time`, `end_time`, `source`, `status`):

1. **DCU Open Timetable (`opentimetable.dcu.ie` / Scientia Syllabus+):**
   * Queries location/room timetables for the current academic week and day of week.
   * Extracts scheduled lectures, labs, and tutorials between `07:00` and `22:00`.
2. **DCU Library LibCal (`dcu-ie.libcal.com`):**
   * Queries the public availability grid endpoints (`/spaces/availability/grid`) for both **O'Reilly Library** and **Cregan Library** Group Study Rooms (1-hour and 2-hour slots).
   * Parses `Unavailable/Padding` vs. `Available` slot timestamps.
3. **DCU Web Room Booking & Clubs/Socs (`rooms.rb.dcu.ie` / Registry Web Room Booking):**
   * Checks public society/event room allocations and supplementary campus bookings where accessible without privileged admin credentials.
4. **DCU Events / SU Calendar (`dcusu.ie` / `dcu.ie/events`):**
   * Scrapes public event listings specifying room locations in The U or campus venues to prevent false positives on non-academic bookings.

---

## 3. Functional Requirements

### 3.1 Availability & Filtering Rules
* **Operating Window:** `07:00` to `22:00` daily (`Europe/Dublin` timezone, handling GMT/IST automatically).
* **7-Day Rolling Date Selector:**
  * Allows selecting any date within a 7-day window (`[today, today + 6 days]`).
  * **When `selected_date == today`:**
    * **Current Occupancy Rule (Strict Exclusion):** Captures `now = current_local_time()`. If a room has an active `OccupancyBlock` where `start_time <= now < end_time`, the room is marked **In Use** and excluded from the default results list.
    * If `now < 07:00` or `now >= 22:00`, displays an operating hours banner while rendering the full `07:00–22:00` schedule.
    * Calculate `free_until` and `remaining_minutes` from `now`.
  * **When `selected_date > today` (Tomorrow through +6 days):**
    * Evaluates availability across the full `07:00–22:00` window for that target date.
    * Includes rooms that have available free windows during `07:00–22:00` on that day.
    * Calculates total free minutes and longest continuous free block across the operating hours.
    * Renders full `07:00–22:00` hourly timeline bar (green = free, gray = booked) so the user can see exact free slots for future days.
* **Free Window Calculation:**
  * For every room that is free during the target window, calculate `free_until` (or next booking start) and `remaining_minutes`.
  * Render an interactive `07:00–22:00` visual timeline bar per room showing free blocks (green) vs. booked blocks (muted gray) so the user can see if a room is free for 20 minutes or 4 hours.

### 3.2 User Interface Specification
* **Top Control Bar:**
  * Primary **`Search`** button (triggers live concurrent fetch across all connectors with a progress indicator).
  * **7-Day Rolling Date Selector Bar:** Horizontal scrollable/sliding date pills showing `Today`, `Tomorrow`, and formatted day pills (`Thu 26 Nov` through `+6 days`).
  * **Campus Filter Pills:** `All Campuses` | `Glasnevin` | `St. Patrick's` | `All Hallows` | `Library GSRs`.
  * **Minimum Free Duration Filter:** `Any` | `30m+` | `1h+` | `2h+`.
  * **Last Updated Timestamp** & source health status dots (e.g., `Timetable ✓`, `Library ✓`, `SU/Events ✓`).
* **Main Results View (Clean Card/Table Layout):**
  * Displays **only currently available rooms** sorted by longest available window first (`free_until` descending).
  * Each room row/card shows:
    * **Room Code & Building** (e.g., `LG25 — McNulty Building`)
    * **Status Badge** (e.g., `Free until 14:00 (2h 15m left)`)
    * **Capacity & Type** (e.g., `60 seats • Lecture Room` or `6 seats • Library GSR`)
    * **07:00–22:00 Timeline Bar** (visual hourly blocks from `07:00` to `22:00`)
* **Empty / Loading States:**
  * Clean skeleton loaders during the ~2–4 second concurrent scrape.
  * Graceful warning banner if a DCU endpoint times out, displaying cached results from SQLite with a `(Cached)` badge.

---

## 4. Technical Stack & macOS Packaging

### 4.1 Recommended Architecture (Zero-Terminal Native App)
* **Backend & Scraping Engine:** Python 3.12 + `FastAPI` + `httpx` (async HTTP) + `BeautifulSoup4` / `selectolax` + `SQLite` (`aiosqlite`).
* **Frontend UI:** Lightweight, zero-build single-page UI (HTML5 + Tailwind CSS + Alpine.js or vanilla JS) served locally by FastAPI on an ephemeral localhost port (`127.0.0.1:0`).
* **Native macOS Window & Dock Integration:** **`pywebview`** (wraps the local FastAPI UI inside a native macOS `WKWebView` Cocoa window—no external browser tab required, cleanly closes the server when the window quits).
* **macOS `.app` Bundling:** **`PyInstaller`** (`--windowed --onedir --icon=assets/dcu_rooms.icns`) generating `DCU Room Finder.app`.
  * Dragging `DCU Room Finder.app` into `/Applications` and onto the **macOS Dock** allows single-click launch with zero Terminal windows.

### 4.2 Repository Structure
```text
dcu-room-finder/
├── SPEC.md                  # This architectural specification
├── README.md                # Setup, screenshots, architecture overview
├── pyproject.toml           # Dependencies (fastapi, uvicorn, httpx, pywebview, pyinstaller)
├── assets/
│   └── dcu_rooms.icns       # Custom macOS Dock icon
├── data/
│   └── rooms_seed.json      # Master registry of DCU rooms, buildings, and IDs
├── src/
│   ├── main.py              # Entry point: starts FastAPI thread + pywebview native window
│   ├── models.py            # Pydantic models (Room, OccupancyBlock, RoomAvailability)
│   ├── database.py          # SQLite cache & room registry loader
│   ├── engine.py            # Availability calculator (07:00–22:00 window & current-time filter)
│   ├── scrapers/
│   │   ├── base.py          # Abstract RoomSourceAdapter
│   │   ├── timetable.py     # DCU Open Timetable / Scientia adapter
│   │   ├── libcal.py        # O'Reilly & Cregan Library LibCal adapter
│   │   └── su_events.py     # Clubs & Socs / SU public room & event adapter
│   └── ui/
│       └── index.html       # Clean single-page desktop interface
└── tests/
    ├── test_engine.py       # Unit tests for 07:00–22:00 filtering & overlap logic
    └── test_scrapers.py     # Mocked HTML/JSON parser tests
