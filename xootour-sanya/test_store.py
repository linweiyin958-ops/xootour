"""Quick test: crawl a few Sanya stores to verify the pipeline works."""
import os, sys, json, logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

from scraper.config import OUTPUT_DIR, DATA_DIR, SANYA_CITY_ID, SANYA_DISTRICTS, AMAP_API_KEY
from scraper.store_scraper import StoreScraper
from scraper.rule_extractor import RuleExtractor
from scraper.sqlite_writer import SQLiteWriter

# Verify config loaded
logger.info(f"SANYA_CITY_ID={SANYA_CITY_ID}")
logger.info(f"Districts: {len(SANYA_DISTRICTS)}")
logger.info(f"AMAP_API_KEY={'SET' if AMAP_API_KEY else 'MISSING'}")

# Load categories
with open(os.path.join(DATA_DIR, "store_categories.json"), "r", encoding="utf-8") as f:
    categories = json.load(f)
logger.info(f"Loaded {len(categories)} categories")

# Init SQLite
sdb = SQLiteWriter()
if not sdb.connect():
    logger.error("SQLite connection failed")
    sys.exit(1)
sdb.init_schema()

# Get next store ID
next_id = sdb.conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM store").fetchone()[0]
logger.info(f"Next store ID: {next_id}")

store_api = StoreScraper()
rule_ext = RuleExtractor()

# Test: search POIs for category 1 (food) with 1 keyword
cat = categories[0]
logger.info(f"\n=== Testing category: {cat['category_name_zh']} ===")

if AMAP_API_KEY:
    pois = store_api.search_pois_by_keyword(cat["amap_keywords"][0], max_count=3)
    logger.info(f"Found {len(pois)} POIs for '{cat['amap_keywords'][0]}'")

    for i, poi in enumerate(pois[:3]):
        logger.info(f"\n--- POI {i+1}: {poi.get('name_zh', 'N/A')} ---")
        logger.info(f"  lat={poi.get('lat')}, lng={poi.get('lng')}")
        logger.info(f"  address={poi.get('address_zh', '')[:60]}")
        logger.info(f"  district={poi.get('district', '')}")

        # Extract structured data
        data = rule_ext.extract_store(poi, {"shop": None, "products": [], "reviews": [], "source": "dianping"}, cat)
        l1 = data.get("L1_base_and_info", {})
        l1["category_id"] = cat["category_id"]
        l1["city_id"] = SANYA_CITY_ID

        # Save JSON
        json_path = os.path.join(OUTPUT_DIR, f"store_{next_id}_{poi.get('name_zh', 'unknown')[:20]}.json")
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"  JSON saved: {json_path}")

        # Write SQLite
        data.setdefault("L5_quality_control", {})["data_quality_score"] = 0.67
        data["L5_quality_control"]["source_platform"] = "Amap"
        try:
            sdb.write_store_data(next_id, data)
            logger.info(f"  SQLite written: store_id={next_id}")
        except Exception as e:
            logger.error(f"  SQLite error: {e}")

        next_id += 1
else:
    logger.error("AMAP_API_KEY not set! Cannot search POIs.")

# Verify data
count = sdb.conn.execute("SELECT COUNT(*) FROM store").fetchone()[0]
logger.info(f"\n=== Done. Total stores in DB: {count} ===")
sdb.close()
