import argparse
import json
import logging
import os
import sys
from datetime import datetime

from .config import DATA_DIR, OUTPUT_DIR, BEIJING_CITY_ID, AMAP_API_KEY
from .amap_web_scraper import AmapWebScraper
from .store_scraper import StoreScraper
from .dianping_scraper import DianpingScraper
from .rule_extractor import RuleExtractor
from .ai_extractor import FreeLLMExtractor
from .store_sql_generator import StoreSQLGenerator
from .db_writer import DBWriter
from .sqlite_writer import SQLiteWriter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.join(OUTPUT_DIR, f"store_scraper_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger(__name__)


def load_categories(categories_file: str = None) -> list:
    if not categories_file:
        categories_file = os.path.join(DATA_DIR, "store_categories.json")
    with open(categories_file, "r", encoding="utf-8") as f:
        return json.load(f)


def calculate_store_quality_score(data: dict) -> float:
    score = 0.0
    l1 = data.get("L1_base_and_info", {})
    l2 = data.get("L2_operations", {})
    sub = data.get("sub_tables", {})

    if l1.get("name_zh") and l1.get("name_en"):
        score += 0.15
    if l1.get("lat") and l1.get("lng"):
        score += 0.1
    if l1.get("summary_zh") and l1.get("summary_en"):
        score += 0.15
    if l2.get("open_hours"):
        score += 0.1
    if l2.get("phone"):
        score += 0.05
    if l2.get("signature_items") and len(l2["signature_items"]) >= 3:
        score += 0.15
    elif l2.get("signature_items"):
        score += 0.05
    if sub.get("store_banner") and len(sub["store_banner"]) >= 3:
        score += 0.1
    elif sub.get("store_banner"):
        score += 0.03
    if sub.get("store_product") and len(sub["store_product"]) >= 3:
        score += 0.1
    elif sub.get("store_product"):
        score += 0.03
    if sub.get("store_facility"):
        score += 0.07

    return round(min(score, 1.0), 2)


def merge_store_supplement(rule_data: dict, supplement: dict) -> dict:
    if not supplement:
        return rule_data

    for key in ("L1_base_and_info", "L2_operations"):
        if key in supplement:
            target = rule_data.setdefault(key, {})
            for k, v in supplement[key].items():
                if v and not target.get(k):
                    target[k] = v

    if "sub_tables" in supplement:
        sub = rule_data.setdefault("sub_tables", {})
        for k, v in supplement["sub_tables"].items():
            if v and not sub.get(k):
                sub[k] = v

    return rule_data


def run_store_pipeline(
    categories: list,
    max_per_category: int = 80,
    skip_dianping: bool = False,
    skip_ai: bool = False,
    write_db: bool = False,
    write_sqlite: bool = False,
    output_dir: str = None,
):
    amap_web = AmapWebScraper()
    store_api = StoreScraper() if AMAP_API_KEY else None
    dianping = DianpingScraper()
    rule_ext = RuleExtractor()
    llm = FreeLLMExtractor() if not skip_ai else None
    sql_gen = StoreSQLGenerator(output_dir=output_dir)
    db = None
    sdb = None

    if write_db:
        db = DBWriter()
        if not db.connect():
            logger.error("Database connection failed, falling back to SQL file output")
            db = None
            write_db = False

    if write_sqlite:
        sdb = SQLiteWriter()
        if not sdb.connect():
            logger.error("SQLite connection failed")
            sdb = None
            write_sqlite = False
        else:
            sdb.init_schema()

    try:
        known_names = set()
        if sdb:
            store_id_counter = sdb.conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM store").fetchone()[0]
            rows = sdb.conn.execute("SELECT name_zh FROM store").fetchall()
            known_names = set(r["name_zh"] for r in rows)
        elif db:
            result = db.query_one("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM store")
            store_id_counter = result["next_id"] if result else 1
            rows = db.query_all("SELECT name_zh FROM store")
            known_names = set(r["name_zh"] for r in rows)
        else:
            store_id_counter = 1
        logger.info(f"Loaded {len(known_names)} existing store names for dedup")

        if sdb or db:
            skip_duplicates = True
        else:
            skip_duplicates = False
        results = []

        for cat_config in categories:
            cat_id = cat_config["category_id"]
            cat_name = cat_config["category_name_zh"]

            logger.info(f"\n{'='*60}")
            logger.info(f"Processing category: {cat_name} (id={cat_id})")
            logger.info(f"{'='*60}")

            if store_api:
                logger.info(f"Using Amap API for POI search...")
                pois = store_api.batch_search_by_category(cat_config, max_per_keyword=max_per_category)
            else:
                logger.info(f"Using AmapWeb for POI search (no API Key)...")
                pois = amap_web.batch_search_by_category(cat_config, max_per_keyword=max_per_category)
            logger.info(f"Found {len(pois)} POIs for {cat_name}")

            for poi in pois:
                name_zh = poi.get("name_zh", "")
                if skip_duplicates and name_zh in known_names:
                    logger.info(f"  Skipping (already exists): {name_zh}")
                    continue
                logger.info(f"\n--- Processing store: {name_zh} (store_id={store_id_counter}) ---")

                dianping_data = {"shop": None, "products": [], "reviews": [], "source": "dianping"}
                if not skip_dianping:
                    logger.info(f"  [Step 1/2] Scraping Dianping...")
                    dianping_data = dianping.scrape_shop(name_zh, category=cat_name)
                    logger.info(f"  -> Shop: {'[OK]' if dianping_data.get('shop') else '[--]'}")
                    logger.info(f"  -> Products: {len(dianping_data.get('products', []))}")

                logger.info(f"  [Step 2/2] Rule extracting...")
                structured_data = rule_ext.extract_store(poi, dianping_data, cat_config)

                if llm:
                    logger.info(f"  [LLM] Supplementing AI-generated fields...")
                    raw_data = {"dianping": dianping_data}
                    supplement = llm.supplement_store(structured_data, raw_data)
                    if supplement:
                        merge_store_supplement(structured_data, supplement)
                        logger.info(f"  -> LLM supplement applied")
                    else:
                        logger.warning(f"  -> LLM supplement failed, using rule-only data")

                l1 = structured_data.setdefault("L1_base_and_info", {})
                l1["category_id"] = cat_id
                l1["city_id"] = BEIJING_CITY_ID

                quality_score = calculate_store_quality_score(structured_data)
                l5 = structured_data.setdefault("L5_quality_control", {})
                l5["data_quality_score"] = quality_score
                l5["is_ai_generated"] = llm is not None
                l5["data_collected_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                source_platforms = ["Amap"]
                source_urls = []
                if dianping_data.get("shop"):
                    source_platforms.append("Dianping")
                    source_urls.append(dianping_data["shop"].get("shop_url", ""))
                l5["source_platform"] = ",".join(source_platforms)
                l5["source_urls"] = [u for u in source_urls if u]

                logger.info(f"  -> Quality score: {quality_score}")

                json_path = os.path.join(OUTPUT_DIR, f"store_{store_id_counter}_{name_zh}.json")
                os.makedirs(OUTPUT_DIR, exist_ok=True)
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(structured_data, f, ensure_ascii=False, indent=2)
                logger.info(f"  -> JSON saved: {json_path}")

                sql_path = sql_gen.generate(store_id_counter, structured_data)
                logger.info(f"  -> SQL saved: {sql_path}")

                if write_db and db:
                    try:
                        l2 = structured_data.get("L2_operations", {})
                        l5 = structured_data.get("L5_quality_control", {})
                        sid = db.insert_store({
                            "id": store_id_counter,
                            "name_zh": l1.get("name_zh"),
                            "name_en": l1.get("name_en"),
                            "category_id": cat_id,
                            "city_id": BEIJING_CITY_ID,
                            "cover_img": l1.get("cover_img"),
                            "seo_desc": l1.get("seo_desc"),
                            "price_range": l2.get("price_range"),
                            "rating": l2.get("rating", 0.0),
                            "review_count": l2.get("review_count", 0),
                            "ranking_desc": l2.get("ranking_desc"),
                            "cuisine_tags": l2.get("cuisine_tags"),
                            "michelin_status": l2.get("michelin_status", 0),
                            "source_platform": l5.get("source_platform"),
                            "data_quality_score": l5.get("data_quality_score", 0.0),
                            "is_ai_generated": l5.get("is_ai_generated", True),
                        })
                        if sid:
                            db.write_store_data(sid, structured_data)
                            logger.info(f"  -> DB written: store_id={sid}")
                            known_names.add(name_zh)
                    except Exception as e:
                        logger.error(f"  -> DB write error: {e}")

                if write_sqlite and sdb:
                    try:
                        sdb.write_store_data(store_id_counter, structured_data)
                        logger.info(f"  -> SQLite written: store_id={store_id_counter}")
                        known_names.add(name_zh)
                    except Exception as e:
                        logger.error(f"  -> SQLite write error: {e}")

                results.append({
                    "store_id": store_id_counter,
                    "name_zh": name_zh,
                    "category": cat_name,
                    "quality_score": quality_score,
                })
                store_id_counter += 1

        logger.info(f"\n{'='*60}")
        logger.info("Store Pipeline Summary")
        logger.info(f"{'='*60}")
        for r in results:
            logger.info(f"  {r['store_id']}: [{r['category']}] {r['name_zh']} -- score={r['quality_score']}")
        logger.info(f"\nTotal stores processed: {len(results)}")

        return results
    finally:
        if db:
            db.close()
        if sdb:
            sdb.close()


def main():
    parser = argparse.ArgumentParser(description="XOOTOUR Beijing Store Data Scraper")
    parser.add_argument("--categories-file", type=str, help="Path to store categories JSON file")
    parser.add_argument("--max-per-category", type=int, default=80, help="Max stores per category (default: 80)")
    parser.add_argument("--output-dir", type=str, help="Output directory")
    parser.add_argument("--skip-dianping", action="store_true", help="Skip Dianping scraping")
    parser.add_argument("--skip-ai", action="store_true", help="Skip LLM supplement")
    parser.add_argument("--write-db", action="store_true", help="Write data directly to MySQL database")
    parser.add_argument("--sqlite", action="store_true", help="Write data to SQLite .db file")
    parser.add_argument("--init-schema", action="store_true", help="Initialize database schema before scraping")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    categories = load_categories(args.categories_file)
    logger.info(f"Loaded {len(categories)} categories")

    if args.init_schema:
        db = DBWriter()
        if db.connect():
            db.init_schema()
            db.close()
            logger.info("Database schema initialized")

    run_store_pipeline(
        categories=categories,
        max_per_category=args.max_per_category,
        skip_dianping=args.skip_dianping,
        skip_ai=args.skip_ai,
        write_db=args.write_db,
        write_sqlite=args.sqlite,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
