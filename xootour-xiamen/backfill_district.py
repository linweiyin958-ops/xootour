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

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "xootour_xiamen.db")
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
        "AND si.lat IS NOT NULL AND si.lng IS NOT NULL "
        "AND si.lat != 0 AND si.lng != 0"
    ).fetchall()

    total = len(rows)
    logger.info(f"Stores missing district (with coords): {total}")

    if total == 0:
        logger.info("All stores have district data.")
        conn.close()
        return

    updated = 0
    failed = 0
    write_lock = Lock()
    results = []

    def process(row):
        store_id, lat, lng, name = row
        district = regeocode(lng, lat)
        return store_id, name, district, lat, lng

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(process, row): row for row in rows}

        for i, future in enumerate(as_completed(futures), 1):
            store_id, name, district, lat, lng = future.result()
            if district:
                with write_lock:
                    conn.execute("UPDATE store_info SET district=? WHERE store_id=?", (district, store_id))
                    updated += 1
            else:
                failed += 1
                if failed <= 5:
                    logger.warning(f"  [{store_id}] Failed: {name} ({lng},{lat})")

            if i % 200 == 0:
                with write_lock:
                    conn.commit()
                logger.info(f"  Progress: {i}/{total} (updated={updated}, failed={failed})")

    conn.commit()
    logger.info(f"\n=== District Backfill Results ===")
    logger.info(f"  Updated: {updated}")
    logger.info(f"  Failed: {failed}")
    logger.info(f"  Total processed: {total}")

    conn.close()


if __name__ == "__main__":
    main()

