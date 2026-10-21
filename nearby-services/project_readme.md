# Nearby — Civic Service Finder

A WebGIS application to locate hospitals, pharmacies, police stations, ATMs, schools, fuel stations, parks, and other facilities anywhere in the world. Features radius and nearest-N searches, distance-sorted results synced to Leaflet map markers, and on-demand live OpenStreetMap (Nominatim) ingestion into PostGIS.

## Architecture

```
┌────────────────────┐      HTTP/JSON       ┌──────────────────────┐      SQL (psycopg2)     ┌───────────────────┐
│  Leaflet frontend   │ ───────────────────▶ │   FastAPI backend    │ ───────────────────────▶ │  PostgreSQL+PostGIS │
│  frontend/index.html│ ◀─────────────────── │   backend/main.py    │ ◀─────────────────────── │  db/schema.sql    │
└────────────────────┘                       └──────────────────────┘                          └───────────────────┘
        │                                                │                                               ▲
        │ optional WMS overlay                           │ Live Dynamic OSM Fetch                        │
        ▼                                                ▼                                               │
┌────────────────────┐                       ┌──────────────────────┐                                    │
│      GeoServer     │                       │ OpenStreetMap API    │ ── (Ingested into PostGIS) ───────┘
│  geoserver/        │                       │ (Nominatim Engine)   │
└────────────────────┘                       └──────────────────────┘
```

- **PostGIS:** Stores facilities as `geography(Point,4326)` for metric-based spatial queries (`ST_DWithin` and KNN `<->`) without manual CRS projection transforms.
- **FastAPI:** Executes spatial distance queries, auto-initializes the PostGIS database schema on launch, and dynamically fetches live POIs from OpenStreetMap if local cached data is sparse.
- **Leaflet.js:** Interactive client featuring city address search (geocoding), map click coordinate picking, category/subcategory filtering, radius/nearest-N search toggles, and sync between map markers and result cards.
- **Dynamic Ingestion Engine:** Connects to the OpenStreetMap Nominatim API on demand, automatically downloading and storing live regional points into PostGIS as users explore new locations worldwide.

## Project Layout

```
nearby-services/
├── run.bat                 -- 1-Click launcher for Windows (Automates DB, dependencies, & server)
├── run.sh                  -- 1-Click launcher for macOS / Linux
├── db/
│   └── schema.sql          -- PostGIS spatial tables, GiST indexes, and category seed data
├── backend/
│   ├── main.py             -- FastAPI server with auto DB bootstrapper & OSM ingestion
│   ├── requirements.txt    -- Python dependencies (FastAPI, Uvicorn, psycopg2-binary, requests)
│   └── .env.example        -- Environment variable template
├── frontend/
│   └── index.html          -- Single-file Leaflet WebGIS dashboard
└── geoserver/
    └── PUBLISHING.md       -- Layer publication and SLD styling guide
```

## Quick Start for Evaluators

### Option 1: 1-Click Automatic Startup (Recommended)

1. Ensure PostgreSQL is running on your machine.
2. Double-click **`run.bat`** (Windows) or execute `bash run.sh` (macOS/Linux).

> **Note:** The backend automatically connects to PostgreSQL, creates the `nearby_services` database if missing, enables PostGIS, applies `db/schema.sql`, seeds categories, starts the Uvicorn server on port `8000`, and opens the dashboard in your browser.

---

### Option 2: Manual Setup

#### 1. Environment & Database Configuration
Create a `.env` file inside the `backend/` directory (or use default fallback settings):
```env
DATABASE_URL=postgresql://postgres:your_password@localhost:5432/nearby_services
```

#### 2. Start Backend Server
```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```
*The database and PostGIS tables will be initialized automatically upon server startup.*

#### 3. Open Frontend Dashboard
Open `frontend/index.html` directly in any web browser or serve via Live Server at `http://127.0.0.1:5500/frontend/index.html`.

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/categories` | `GET` | Fetches categories and subcategories for dynamic UI filters |
| `/api/services/nearby` | `GET` | Executes spatial search (`lat`, `lng`, `category`, `subcategory`, `mode`, `radius_m`, `n`). Triggers live OSM ingestion if no local points exist nearby. |

## Key Features & Error Handling

- **Automatic PostGIS Bootstrapping:** Ensures zero manual SQL imports are required before running.
- **Dynamic OSM Ingestion:** Queries global OpenStreetMap facilities on demand and caches them in PostGIS.
- **Fail-Safe Spatial Queries:** Handles empty search results gracefully with HTTP 200 responses and clear dashboard notifications.
- **Input Validation:** Validates coordinate bounds (`-90..90` lat, `-180..180` lng) both on client and server.