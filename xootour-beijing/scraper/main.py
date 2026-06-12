import json
import logging
import os
import sys
from datetime import datetime
import argparse

from .config import DATA_DIR, OUTPUT_DIR, BEIJING_CITY_ID, AMAP_API_KEY
from .amap_web_scraper import AmapWebScraper
from .amap_client import AmapClient
from .mafengwo_scraper import MafengwoScraper
from .ctrip_scraper import CtripScraper
from .tripadvisor_scraper import TripAdvisorScraper
from .rule_extractor import RuleExtractor
from .ai_extractor import FreeLLMExtractor
from .sql_generator import SQLGenerator
from .db_writer import DBWriter
from .sqlite_writer import SQLiteWriter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.join(OUTPUT_DIR, f"scraper_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger(__name__)


def load_spots(spots_file: str = None) -> list:
    if not spots_file:
        spots_file = os.path.join(DATA_DIR, "spots.json")
    with open(spots_file, "r", encoding="utf-8") as f:
        return json.load(f)


def calculate_quality_score(data: dict) -> float:
    score = 0.0
    l1 = data.get("L1_base_and_info", {})
    l2 = data.get("L2_operations", {})
    l3 = data.get("L3_ugc_trends", {})
    sub = data.get("sub_tables", {})

    if l1.get("name_zh") and l1.get("name_en"):
        score += 0.15
    if l1.get("lat") and l1.get("lng"):
        score += 0.1
    if l1.get("summary_zh") and l1.get("summary_en"):
        score += 0.15
    if l2.get("open_hours"):
        score += 0.1
    if l2.get("transportation"):
        score += 0.1
    if l3.get("photo_spots"):
        score += 0.05
    if sub.get("tour_spot_banner") and len(sub["tour_spot_banner"]) >= 5:
        score += 0.15
    elif sub.get("tour_spot_banner"):
        score += 0.05
    if sub.get("tour_spot_feature") and len(sub["tour_spot_feature"]) >= 3:
        score += 0.1
    elif sub.get("tour_spot_feature"):
        score += 0.03
    if sub.get("tour_spot_route"):
        score += 0.05
    if sub.get("tour_spot_facility"):
        score += 0.05

    return round(min(score, 1.0), 2)


def merge_supplement(rule_data: dict, supplement: dict) -> dict:
    if not supplement:
        return rule_data

    for key in ("L1_base_and_info", "L2_operations", "L3_ugc_trends"):
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


def run_pipeline(spots: list, start_id: int = 1,
                 skip_geo: bool = False, skip_mafengwo: bool = False,
                 skip_ctrip: bool = False, skip_tripadvisor: bool = False,
                 skip_ai: bool = False, write_db: bool = False,
                 write_sqlite: bool = False, output_dir: str = None):
    amap_web = AmapWebScraper()
    amap_api = AmapClient() if AMAP_API_KEY else None
    mafengwo = MafengwoScraper()
    ctrip = CtripScraper()
    tripadvisor = TripAdvisorScraper()
    rule_ext = RuleExtractor()
    llm = FreeLLMExtractor() if not skip_ai else None
    sql_gen = SQLGenerator(output_dir=output_dir)
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
        results = []

        for idx, spot in enumerate(spots):
            spot_id = start_id + idx
            name_zh = spot.get("name_zh", "")
            name_en = spot.get("name_en", "")
            keywords = spot.get("keywords", name_zh)

            logger.info(f"\n{'='*60}")
            logger.info(f"Processing: {name_zh} ({name_en}) -- spot_id={spot_id}")
            logger.info(f"{'='*60}")

            geo_data = None
            if not skip_geo:
                if amap_api:
                    logger.info(f"[Step 1/4] Fetching geo data from Amap API...")
                    geo_data = amap_api.get_spot_geo(name_zh, keywords)
                else:
                    logger.info(f"[Step 1/4] Fetching geo data from AmapWeb/Nominatim...")
                    geo_data = amap_web.search_geo(name_zh, keywords)
                if geo_data:
                    logger.info(f"  -> lat={geo_data.get('lat')}, lng={geo_data.get('lng')}, district={geo_data.get('district')}")
                else:
                    logger.warning(f"  -> No geo data found")

            mafengwo_data = {"spot": None, "notes": [], "source": "mafengwo"}
            if not skip_mafengwo:
                logger.info(f"[Step 2/4] Scraping MaFengWo...")
                mafengwo_data = mafengwo.scrape_spot(keywords, max_notes=5)
                logger.info(f"  -> Spot: {'[OK]' if mafengwo_data.get('spot') else '[--]'}")
                logger.info(f"  -> Notes: {len(mafengwo_data.get('notes', []))}")

            ctrip_data = {"spot": None, "packages": [], "source": "ctrip"}
            if not skip_ctrip:
                logger.info(f"[Step 3/4] Scraping Ctrip...")
                ctrip_data = ctrip.scrape_spot(name_zh)
                logger.info(f"  -> Spot: {'[OK]' if ctrip_data.get('spot') else '[--]'}")
                logger.info(f"  -> Packages: {len(ctrip_data.get('packages', []))}")

            ta_data = {"spot": None, "reviews": [], "source": "tripadvisor"}
            if not skip_tripadvisor:
                logger.info(f"[Step 4/4] Scraping TripAdvisor...")
                ta_data = tripadvisor.scrape_spot(name_en, max_reviews=10)
                logger.info(f"  -> Spot: {'[OK]' if ta_data.get('spot') else '[--]'}")

            logger.info(f"[Rule] Extracting structured data via rules...")
            structured_data = rule_ext.extract_spot(spot, geo_data, mafengwo_data, ctrip_data, ta_data)

            if llm:
                logger.info(f"[LLM] Supplementing AI-generated fields...")
                raw_data = {
                    "mafengwo": mafengwo_data,
                    "ctrip": ctrip_data,
                    "tripadvisor": ta_data,
                }
                supplement = llm.supplement_spot(structured_data, raw_data)
                if supplement:
                    merge_supplement(structured_data, supplement)
                    logger.info(f"  -> LLM supplement applied")
                else:
                    logger.warning(f"  -> LLM supplement failed, using rule-only data")

            structured_data["L1_base_and_info"]["city_id"] = BEIJING_CITY_ID

            quality_score = calculate_quality_score(structured_data)
            structured_data.setdefault("L5_quality_control", {})["data_quality_score"] = quality_score
            structured_data["L5_quality_control"]["is_ai_generated"] = llm is not None
            structured_data["L5_quality_control"]["data_collected_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            source_platforms = []
            source_urls = []
            if geo_data:
                source_platforms.append(geo_data.get("source", "Amap"))
            if mafengwo_data.get("spot"):
                source_platforms.append("Mafengwo")
                source_urls.append(mafengwo_data["spot"].get("poi_url", ""))
            if ctrip_data.get("spot"):
                source_platforms.append("Ctrip")
                source_urls.append(ctrip_data["spot"].get("sight_url", ""))
            if ta_data.get("spot"):
                source_platforms.append("TripAdvisor")
                source_urls.append(ta_data["spot"].get("attraction_url", ""))

            structured_data["L5_quality_control"]["source_platform"] = ",".join(source_platforms)
            structured_data["L5_quality_control"]["source_note_ids"] = [u for u in source_urls if u]

            logger.info(f"  -> Data quality score: {quality_score}")

            json_path = os.path.join(OUTPUT_DIR, f"spot_{spot_id}_{name_zh}.json")
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(structured_data, f, ensure_ascii=False, indent=2)
            logger.info(f"  -> JSON saved: {json_path}")

            sql_path = sql_gen.generate(spot_id, structured_data)
            logger.info(f"  -> SQL saved: {sql_path}")

            if write_db and db:
                try:
                    db.write_spot_data(spot_id, structured_data)
                    logger.info(f"  -> DB written: spot_id={spot_id}")
                except Exception as e:
                    logger.error(f"  -> DB write error: {e}")

            if write_sqlite and sdb:
                try:
                    sdb.write_spot_data(spot_id, structured_data)
                    logger.info(f"  -> SQLite written: spot_id={spot_id}")
                except Exception as e:
                    logger.error(f"  -> SQLite write error: {e}")

            results.append({
                "spot_id": spot_id,
                "name_zh": name_zh,
                "name_en": name_en,
                "quality_score": quality_score,
            })

        logger.info(f"\n{'='*60}")
        logger.info("Pipeline Summary")
        logger.info(f"{'='*60}")
        for r in results:
            logger.info(f"  {r['spot_id']}: {r['name_zh']} ({r['name_en']}) -- score={r['quality_score']}")

        return results
    finally:
        if db:
            db.close()
        if sdb:
            sdb.close()


def main():
    parser = argparse.ArgumentParser(description="XOOTOUR Beijing Tourist Spots Data Scraper")
    parser.add_argument("--spots-file", type=str, help="Path to spots JSON file")
    parser.add_argument("--start-id", type=int, default=1, help="Starting spot_id (default: 1)")
    parser.add_argument("--output-dir", type=str, help="Output directory")
    parser.add_argument("--skip-geo", action="store_true", help="Skip geo lookup")
    parser.add_argument("--skip-mafengwo", action="store_true", help="Skip MaFengWo scraping")
    parser.add_argument("--skip-ctrip", action="store_true", help="Skip Ctrip scraping")
    parser.add_argument("--skip-tripadvisor", action="store_true", help="Skip TripAdvisor scraping")
    parser.add_argument("--skip-ai", action="store_true", help="Skip LLM supplement (rule-only)")
    parser.add_argument("--write-db", action="store_true", help="Write data directly to MySQL database")
    parser.add_argument("--sqlite", action="store_true", help="Write data to SQLite .db file")
    parser.add_argument("--init-schema", action="store_true", help="Initialize database schema before scraping")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.init_schema:
        db = DBWriter()
        if db.connect():
            db.init_schema()
            db.close()
            logger.info("Database schema initialized")

    spots = load_spots(args.spots_file)
    logger.info(f"Loaded {len(spots)} spots to process")

    run_pipeline(
        spots=spots,
        start_id=args.start_id,
        skip_geo=args.skip_geo,
        skip_mafengwo=args.skip_mafengwo,
        skip_ctrip=args.skip_ctrip,
        skip_tripadvisor=args.skip_tripadvisor,
        skip_ai=args.skip_ai,
        write_db=args.write_db,
        write_sqlite=args.sqlite,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
