"""Backfill missing district field via Amap reverse geocoding (multithreaded)."""
import logging, os, sqlite3, sys, time, random, requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scraper.config import AMAP_API_KEY

log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "_backfill_district.log")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "xootour_chengdu.db")
AMAP_REGEO_URL = "https://restapi.amap.com/v3/geocode/regeo"


def regeocode(lng, lat):
    params = {
        "key": AMAP_API_KEY,
        "location": f"{lng},{lat}",
        "output": "JSON",
        "extensions": "base",
    }
    try:
        resp = requests.get(AMAP_REGEO_URL, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "1" and data.get("regeocode"):
            comp = data["regeocode"].get("addressComponent", {})
            district = comp.get("district", "")
            if district:
                return district
        return None
    except Exception:
        return None


def main():
    if not AMAP_API_KEY:
        logger.error("AMAP_API_KEY not configured. Set in .env file.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")

    rows = conn.execute(
        "SELECT si.store_id, si.lat, si.lng, s.name_zh "
        "FROM store_info si "
        "JOIN store s ON s.id = si.store_id "
        "WHERE (si.district IS NULL OR si.district = '') "
        "AND si.lat IS NOT NULL AND si.lng IS NOT NULL"
    ).fetchall()

    if not rows:
        logger.info("No stores missing district with valid coordinates.")
        conn.close()
        return

    logger.info(f"Stores missing district with geo: {len(rows)}")
    total = len(rows)
    updated = 0
    lock = Lock()

    def process_one(row):
        nonlocal updated
        store_id, lat, lng, name = row
        district = regeocode(lng, lat)
        if district:
            with lock:
                conn.execute("UPDATE store_info SET district=? WHERE store_id=?", (district, store_id))
                conn.commit()
                updated += 1
            return store_id, name, district
        return None

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(process_one, row): row for row in rows}
        for future in as_completed(futures):
            result = future.result()
            if result:
                logger.info(f"  [{result[0]}] {result[1]} -> {result[2]}")

    logger.info(f"\nDone. Updated {updated}/{total} stores with district.")
    conn.close()


if __name__ == "__main__":
    main()
