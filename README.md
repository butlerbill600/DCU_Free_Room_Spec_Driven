# DCU Room Finder 📍 — macOS Native Desktop Utility

**DCU Room Finder** is a zero-terminal, single-click macOS desktop application designed to live in the macOS Dock or `/Applications` folder. When launched, it concurrently queries Dublin City University (DCU) room scheduling and booking endpoints across **Glasnevin**, **St. Patrick's**, and **All Hallows** campuses plus **Library Group Study Rooms (GSRs)**, filters out currently occupied rooms, and renders a clean real-time view of available spaces between **07:00 and 22:00** (`Europe/Dublin`).

---

## 🌟 Key Features

* **Zero-Terminal Experience:** Double-click launch directly from the macOS Dock or `/Applications`. Embedded local server lifecycle is managed automatically on an ephemeral localhost port.
* **Multi-Source Aggregation:** Normalizes room occupancy across:
  * **DCU Open Timetable (`opentimetable.dcu.ie`):** Scheduled lectures, labs, and tutorials.
  * **DCU Library LibCal (`dcu-ie.libcal.com`):** O'Reilly & Cregan Library Group Study Rooms.
  * **DCU SU / Events (`dcusu.ie` / `rooms.rb.dcu.ie`):** Society meetings and public events.
* **07:00–22:00 Daily Availability Engine:**
  * **Strict Occupancy Exclusion:** Excludes rooms currently in use (`start_time <= now < end_time`).
  * **Continuous Free Window Calculation:** Calculates `free_until` timestamp and remaining minutes.
  * **Visual Timeline Bar:** Hourly block indicators (07:00–22:00) showing green free blocks vs muted gray booked blocks.
* **Resilient & Fast:** Asynchronous concurrent scrapers with rate-limit protection and SQLite caching fallback if a portal times out.

---

## 🏗 Architecture & Stack

* **Backend Engine:** Python 3.12 + FastAPI + `httpx` + `BeautifulSoup4` / `selectolax` + `SQLite` (`aiosqlite`).
* **Desktop UI:** Single-page desktop interface built with HTML5, Tailwind CSS, and Inter font.
* **Native macOS Window:** `pywebview` Cocoa `WKWebView` wrapper for zero-terminal launch.
* **macOS Bundling:** PyInstaller configured for macOS `.app` bundle with custom `.icns` Dock icon.

```text
dcu-room-finder/
├── SPEC.md                  # Complete technical specification
├── IMPLEMENTATION_PLAN.md   # Project phase task list
├── README.md                # Usage, setup, architecture
├── pyproject.toml           # Project dependencies & pytest configuration
├── DCU Room Finder.spec     # PyInstaller macOS .app spec
├── generate_assets.py       # macOS icon asset generator
├── build_app.py             # One-click macOS app builder script
├── assets/
│   ├── icon.png
│   └── dcu_rooms.icns       # Custom macOS Dock icon
├── data/
│   └── rooms_seed.json      # Master room registry
├── src/
│   ├── main.py              # Entry point: FastAPI backend + pywebview native window
│   ├── models.py            # Pydantic domain models
│   ├── database.py          # SQLite database cache & room registry manager
│   ├── engine.py            # 07:00–22:00 availability engine & timeline generator
│   ├── scrapers/
│   │   ├── base.py          # Abstract RoomSourceAdapter
│   │   ├── timetable.py     # DCU Open Timetable adapter
│   │   ├── libcal.py        # DCU Library LibCal adapter
│   │   ├── su_events.py     # SU & Society events adapter
│   │   └── aggregator.py   # Concurrent async gather & fallback aggregator
│   └── ui/
│       └── index.html       # Desktop UI interface
└── tests/
    ├── test_engine.py       # Availability engine unit tests
    ├── test_scrapers.py     # Scraper parsing & fallback tests
    ├── test_api.py          # FastAPI endpoint tests
    └── test_main.py         # Lifecycle and port finder tests
```

---

## 🚀 Quickstart & Development

### 1. Prerequisites
* macOS 12+ (Apple Silicon or Intel)
* Python 3.12+

### 2. Setup Virtual Environment
```bash
git clone https://github.com/butlerbill600/DCU_Free_Room_Spec_Driven.git
cd DCU_Free_Room_SSD

python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

### 3. Run Development Server / Desktop App
```bash
# Launch Native macOS Window App
python3 src/main.py

# Or launch FastAPI Server Only (for browser access at http://127.0.0.1:8000)
python3 src/main.py --server-only --port 8000
```

---

## 📦 Building macOS `.app` Bundle for Applications & Dock

To compile a stand-alone single-click `DCU Room Finder.app` bundle:

```bash
python3 build_app.py
```

Upon completion, your native bundle is generated at:
`dist/DCU Room Finder.app`

### Installation to macOS Dock:
1. Open Finder and navigate to `dist/`.
2. Drag `DCU Room Finder.app` into `/Applications`.
3. Drag `DCU Room Finder.app` from `/Applications` onto your **macOS Dock**.
4. Single-click the app icon anytime to open DCU Room Finder with **zero terminal windows**.

---

## 🧪 Running Tests

To run the full unit and integration test suite:

```bash
pytest
```
