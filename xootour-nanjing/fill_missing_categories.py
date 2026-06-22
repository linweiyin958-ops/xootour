import json
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

from scraper.config import OUTPUT_DIR, NANJING_CITY_ID
from scraper.store_scraper import StoreScraper
from scraper.rule_extractor import RuleExtractor
from scraper.ai_extractor import FreeLLMExtractor
from scraper.sqlite_writer import SQLiteWriter


def main():
    store_api = StoreScraper()
    rule_ext = RuleExtractor()
    llm = FreeLLMExtractor()

    sdb = SQLiteWriter()
    if not sdb.connect():
        logger.error("SQLite connection failed")
        return

    store_id_counter = sdb.conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM store").fetchone()[0]
    logger.info(f"Starting store_id_counter from: {store_id_counter}")

    categories_file = os.path.join(os.path.dirname(OUTPUT_DIR), "data", "store_categories.json")
    with open(categories_file, "r", encoding="utf-8") as f:
        missing_categories = json.load(f)

    known_names = set(r["name_zh"] for r in sdb.conn.execute("SELECT name_zh FROM store").fetchall())
    logger.info(f"Existing stores: {len(known_names)}")

    results = []
    for cat in missing_categories:
        logger.info(f"\n{'='*40}\nSearching category: {cat['category_name_zh']}\n{'='*40}")
        pois = store_api.batch_search_by_category(cat, max_per_keyword=25)

        for poi in pois:
            name_zh = poi.get("name_zh", "")
            if name_zh in known_names:
                continue

            logger.info(f"Processing: {name_zh}")
            data = rule_ext.extract_store(poi, {"shop": None, "products": [], "reviews": [], "source": "dianping"}, cat)
            l1 = data.setdefault("L1_base_and_info", {})
            l1["category_id"] = cat["category_id"]
            l1["city_id"] = NANJING_CITY_ID

            if llm:
                supplement = llm.supplement_store(data, {"dianping": {"shop": None, "products": [], "reviews": []}})
                if supplement:
                    for key in ("L1_base_and_info", "L2_operations"):
                        if key in supplement:
                            target = data.setdefault(key, {})
                            for k, v in supplement[key].items():
                                if v and not target.get(k):
                                    target[k] = v
                    if "sub_tables" in supplement:
                        sub = data.setdefault("sub_tables", {})
                        for k, v in supplement["sub_tables"].items():
                            if v and not sub.get(k):
                                sub[k] = v

            data.setdefault("L5_quality_control", {})["data_quality_score"] = 0.5
            data["L5_quality_control"]["source_platform"] = "Amap"
            data["L5_quality_control"]["data_collected_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            sdb.write_store_data(store_id_counter, data)
            logger.info(f"  -> Written: store_id={store_id_counter}")
            known_names.add(name_zh)
            results.append((store_id_counter, name_zh, cat["category_name_zh"]))
            store_id_counter += 1

    logger.info(f"\n{'='*40}\n Summary: {len(results)} new stores\n{'='*40}")
    for sid, name, cat_name in results:
        logger.info(f"  {sid}: [{cat_name}] {name}")
    sdb.close()


if __name__ == "__main__":
    main()
