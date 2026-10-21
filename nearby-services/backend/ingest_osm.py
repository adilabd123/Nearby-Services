import os
import json
import time
import requests
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_DSN = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:adil123@localhost:5432/nearby_services"
)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

HEADERS = {
    "User-Agent": "NearbyServicesGISApp/1.0 (Contact: student@example.com)"
}

CATEGORY_MAPPINGS = [
    {"osm_tag": '["amenity"="hospital"]', "cat": "hospital", "subcat": "govt_hospital"},
    {"osm_tag": '["amenity"="pharmacy"]', "cat": "pharmacy", "subcat": "retail_pharmacy"},
    {"osm_tag": '["amenity"="police"]', "cat": "police", "subcat": "police_station"},
    {"osm_tag": '["amenity"="atm"]', "cat": "atm", "subcat": "bank_atm"},
    {"osm_tag": '["amenity"="bank"]', "cat": "atm", "subcat": "bank_branch"},
    {"osm_tag": '["amenity"="school"]', "cat": "school", "subcat": "primary_school"},
    {"osm_tag": '["amenity"="fuel"]', "cat": "fuel", "subcat": "petrol"},
    {"osm_tag": '["leisure"="park"]', "cat": "park", "subcat": "public_park"},
]

def fetch_and_store_pois(lat: float = 18.5204, lng: float = 73.8567, radius_meters: int = 10000):
    print(f"📡 Fetching live OpenStreetMap facilities around ({lat}, {lng}) within {radius_meters/1000}km...\n")
    
    try:
        conn = psycopg2.connect(DB_DSN)
        cur = conn.cursor()
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return

    total_inserted = 0

    for item in CATEGORY_MAPPINGS:
        # Overpass query searching for nodes within search radius
        query = f"""
        [out:json][timeout:25];
        node{item['osm_tag']}(around:{radius_meters},{lat},{lng});
        out center;
        """
        
        try:
            response = requests.post(OVERPASS_URL, data={"data": query}, headers=HEADERS, timeout=30)
            if response.status_code != 200:
                print(f"⚠️ Skipping '{item['cat']}': Overpass HTTP {response.status_code}")
                time.sleep(1)
                continue
                
            elements = response.json().get("elements", [])
            print(f" Found {len(elements)} items for category '{item['cat']}'")

            cat_inserted = 0
            for elem in elements:
                tags = elem.get("tags", {})
                name = tags.get("name") or f"Unnamed {item['cat'].title()}"
                address = tags.get("addr:street") or tags.get("addr:suburb") or tags.get("address") or "Local Area"
                phone = tags.get("phone") or tags.get("contact:phone")
                opening_hours = tags.get("opening_hours")
                
                # Extract coordinates
                node_lat = elem.get("lat") or elem.get("center", {}).get("lat")
                node_lng = elem.get("lon") or elem.get("center", {}).get("lon")

                if not node_lat or not node_lng:
                    continue

                extra_info = json.dumps({
                    "osm_id": elem["id"],
                    "brand": tags.get("brand"),
                    "operator": tags.get("operator")
                })

                sql = """
                INSERT INTO service (name, category_code, subcategory_code, address, phone, opening_hours, extra_info, geom)
                VALUES (%s, %s, %s, %s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography);
                """
                
                try:
                    cur.execute(sql, (
                        name, item["cat"], item["subcat"], address,
                        phone, opening_hours, extra_info, node_lng, node_lat
                    ))
                    cat_inserted += cur.rowcount
                except psycopg2.Error:
                    conn.rollback()
                    continue
                else:
                    conn.commit()

            total_inserted += cat_inserted
            time.sleep(1)
        except Exception as e:
            print(f"❌ Error fetching '{item['cat']}': {e}")

    cur.close()
    conn.close()
    print(f"\n Finished! Added {total_inserted} new facilities into your PostGIS database.")

if __name__ == "__main__":
    fetch_and_store_pois()