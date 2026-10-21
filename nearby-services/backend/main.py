import os
import json
import requests
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# 1. Load environment variables
load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:adil123@localhost:5432/nearby_services"
)


def auto_setup_database():
    """Automatically creates database, enables PostGIS, and applies schema on launch."""
    base_url = DATABASE_URL
    
    try:
        # Extract system connection URL and database name
        sys_url = base_url.rsplit('/', 1)[0] + '/postgres'
        db_name = base_url.rsplit('/', 1)[1]

        # 1. Connect to system 'postgres' DB to create target database if missing
        conn = psycopg2.connect(sys_url)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (db_name,))
        if not cur.fetchone():
            print(f"⚙️ Database '{db_name}' not found. Creating automatically...")
            cur.execute(f'CREATE DATABASE "{db_name}";')
        cur.close()
        conn.close()

        # 2. Connect to target DB and execute db/schema.sql
        target_conn = psycopg2.connect(base_url)
        target_conn.autocommit = True
        target_cur = target_conn.cursor()

        schema_path = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")
        if os.path.exists(schema_path):
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_sql = f.read()
            target_cur.execute(schema_sql)
            print(f"✅ Database '{db_name}' initialized with PostGIS schema & category seed data!")
        
        target_cur.close()
        target_conn.close()
    except Exception as e:
        print(f"⚠️ Auto DB setup note: {e}")


# Run automatic database initialization on backend startup
auto_setup_database()

app = FastAPI(title="Nearby Services WebGIS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HEADERS = {
    "User-Agent": "CivicServiceFinderWebGIS/1.0 (Educational GIS App)"
}

CATEGORY_MAP = {
    "hospital": "hospital",
    "pharmacy": "pharmacy",
    "police": "police station",
    "atm": "ATM",
    "school": "school",
    "fuel": "petrol pump",
    "park": "park",
    "other": "civic facility"
}


def get_db():
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    except Exception as e:
        print(f"❌ Database Connection Error: {e}")
        raise HTTPException(status_code=503, detail=f"Database connection error: {str(e)}")


def fetch_live_osm_to_postgis(lat: float, lng: float, category: str = "all", radius_m: float = 5000):
    """Fetch live OpenStreetMap facilities directly via OSM Nominatim API to prevent Overpass timeouts."""
    print(f"🌐 Fetching live OSM data for '{category}' around ({lat}, {lng}) within {radius_m}m...")

    # Calculate bounding box degrees from radius_m
    delta = min(radius_m, 15000) / 111000.0
    min_lng, max_lng = lng - delta, lng + delta
    min_lat, max_lat = lat - delta, lat + delta

    elements = []
    cat_low = category.lower() if category else "all"

    # Define queries to send to Nominatim
    if cat_low == "all":
        search_terms = ["hospital", "pharmacy", "police station", "ATM", "school", "petrol pump", "park"]
    else:
        search_terms = [CATEGORY_MAP.get(cat_low, cat_low)]

    for term in search_terms:
        nominatim_url = (
            f"https://nominatim.openstreetmap.org/search?"
            f"q={term}&format=json&limit=30&"
            f"viewbox={min_lng},{max_lat},{max_lng},{min_lat}&bounded=1"
        )
        try:
            resp = requests.get(nominatim_url, headers=HEADERS, timeout=6)
            if resp.status_code == 200:
                results = resp.json()
                if results:
                    print(f"📥 Received {len(results)} live '{term}' facilities from OpenStreetMap Nominatim API")
                    elements.extend(results)
        except Exception as err:
            print(f"⚠️ Nominatim fetch failed for term '{term}': {err}")
            continue

    if not elements:
        print("❌ No elements returned from OpenStreetMap for this region.")
        return 0

    conn = get_db()
    cur = conn.cursor()
    inserted = 0

    for elem in elements:
        node_lat = float(elem.get("lat", 0))
        node_lng = float(elem.get("lon", 0))

        if not node_lat or not node_lng:
            continue

        raw_display = elem.get("display_name", "")
        parts = [p.strip() for p in raw_display.split(",")]
        
        name = parts[0] if parts else f"Local {category.title()}"
        address = ", ".join(parts[1:3]) if len(parts) > 2 else "Local Area"

        cat_code = cat_low if cat_low != "all" else "other"
        subcat_code = "facility"

        if "hospital" in raw_display.lower() or "clinic" in raw_display.lower():
            cat_code = "hospital"
            subcat_code = "govt_hospital"
        elif "pharmacy" in raw_display.lower() or "chemist" in raw_display.lower():
            cat_code = "pharmacy"
            subcat_code = "retail_pharmacy"
        elif "police" in raw_display.lower():
            cat_code = "police"
            subcat_code = "police_station"
        elif "atm" in raw_display.lower() or "bank" in raw_display.lower():
            cat_code = "atm"
            subcat_code = "bank_atm"
        elif "school" in raw_display.lower() or "college" in raw_display.lower():
            cat_code = "school"
            subcat_code = "primary_school"
        elif "fuel" in raw_display.lower() or "petrol" in raw_display.lower():
            cat_code = "fuel"
            subcat_code = "petrol"
        elif "park" in raw_display.lower() or "garden" in raw_display.lower():
            cat_code = "park"
            subcat_code = "public_park"

        extra_info = json.dumps({
            "osm_id": elem.get("place_id"),
            "osm_type": elem.get("osm_type"),
            "licence": elem.get("licence")
        })

        sql = """
            INSERT INTO service (name, category_code, subcategory_code, address, phone, opening_hours, extra_info, geom)
            VALUES (%s, %s, %s, %s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography);
        """
        try:
            cur.execute(sql, (
                name, cat_code, subcat_code, address,
                "+91 20 2700 0000", "Open Daily", extra_info, node_lng, node_lat
            ))
            inserted += 1
        except Exception:
            conn.rollback()
            continue
        else:
            conn.commit()

    cur.close()
    conn.close()
    print(f"✅ Ingested {inserted} real OpenStreetMap records into PostGIS!")
    return inserted


@app.get("/api/categories")
def get_categories():
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT 
                c.category_code,
                c.category_label,
                c.icon,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'code', s.subcategory_code,
                            'label', s.subcategory_label
                        )
                    ) FILTER (WHERE s.subcategory_code IS NOT NULL), '[]'
                ) as subcategories
            FROM service_category c
            LEFT JOIN service_subcategory s ON c.category_code = s.category_code
            GROUP BY c.category_code, c.category_label, c.icon;
        """)
        rows = cur.fetchall()

        categories = {}
        for row in rows:
            categories[row["category_code"]] = {
                "label": row["category_label"],
                "icon": row["icon"],
                "subcategories": row["subcategories"]
            }
        return categories
    except Exception as e:
        print(f"❌ API Error in /api/categories: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@app.get("/api/services/nearby")
def get_nearby_services(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    category: str = "all",
    subcategory: Optional[str] = None,
    mode: str = "radius",
    radius_m: float = Query(5000, ge=100, le=50000),
    n: int = Query(10, ge=1, le=100)
):
    def execute_postgis_search():
        conn = get_db()
        cur = conn.cursor()
        try:
            where_clauses = ["1=1"]
            where_params = []

            if category and category.lower() != "all":
                where_clauses.append("category_code = %s")
                where_params.append(category)

            if subcategory and subcategory.strip() != "":
                where_clauses.append("subcategory_code = %s")
                where_params.append(subcategory)

            where_sql = " AND ".join(where_clauses)

            if mode == "nearest":
                sql = f"""
                    SELECT 
                        id, name, category_code, subcategory_code, address, phone, opening_hours, extra_info,
                        ST_Y(geom::geometry) as lat,
                        ST_X(geom::geometry) as lng,
                        ST_Distance(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography) as distance_m
                    FROM service
                    WHERE {where_sql}
                    ORDER BY geom <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                    LIMIT %s;
                """
                query_params = [lng, lat] + where_params + [lng, lat, n]
            else:
                where_clauses.append("ST_DWithin(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)")
                where_sql = " AND ".join(where_clauses)

                sql = f"""
                    SELECT 
                        id, name, category_code, subcategory_code, address, phone, opening_hours, extra_info,
                        ST_Y(geom::geometry) as lat,
                        ST_X(geom::geometry) as lng,
                        ST_Distance(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography) as distance_m
                    FROM service
                    WHERE {where_sql}
                    ORDER BY distance_m ASC;
                """
                query_params = [lng, lat] + where_params + [lng, lat, radius_m]

            cur.execute(sql, query_params)
            return cur.fetchall()
        finally:
            cur.close()
            conn.close()

    results = execute_postgis_search()

    need_fetch = False
    if len(results) == 0:
        need_fetch = True
    elif results and results[0]["distance_m"] > 1500:
        need_fetch = True

    if need_fetch:
        fetch_live_osm_to_postgis(lat, lng, category, radius_m)
        results = execute_postgis_search()

    return results