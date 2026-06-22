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

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "xootour_nanjing.db")
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
            return comp.get("district", "")
    except Exception:
        pass
    return None


def main():
    if not AMAP_API_KEY:
        logger.error("AMAP_API_KEY not set.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT store_id, lat, lng FROM store_info "
        "WHERE (district IS NULL OR district = '') AND lat IS NOT NULL AND lng IS NOT NULL"
    ).fetchall()
    total = len(rows)
    logger.info(f"Stores missing district: {total}")

    if total == 0:
        logger.info("All stores have district.")
        conn.close()
        return

    updated = 0
    failed = 0
    write_lock = Lock()

    def process(row):
        sid, lat, lng = row["store_id"], row["lat"], row["lng"]
        time.sleep(random.uniform(0.3, 0.6))
        district = regeocode(lng, lat)
        return sid, district

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(process, row): row for row in rows}
        for i, future in enumerate(as_completed(futures), 1):
            sid, district = future.result()
            if district:
                with write_lock:
                    conn.execute("UPDATE store_info SET district=? WHERE store_id=?", (district, sid))
                    conn.commit()
                    updated += 1
            else:
                failed += 1
            if i % 200 == 0:
                with write_lock:
                    conn.commit()
                logger.info(f"Progress: {i}/{total} (ok={updated}, fail={failed})")

    logger.info(f"\n=== Backfill district complete: {updated} updated, {failed} failed ===")
    conn.close()


if __name__ == "__main__":
    main()
