import json, logging, os, sys, sqlite3
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

from scraper.ai_extractor import FreeLLMExtractor

import argparse


def process_one(llm, row):
    store_id, name, cat_name, district, address, open_hours, phone, price_range, rating = row
    district = district or ""
    address = address or ""
    open_hours = open_hours or ""
    phone = phone or ""
    price_range = price_range or ""

    supplement = llm.supplement_store(
        {"L1_base_and_info": {"name_zh": name, "district": district, "address_zh": address},
         "L2_operations": {"open_hours": open_hours, "phone": phone, "price_range": price_range,
                           "rating": rating or 0, "review_count": 0,
                           "cuisine_tags": ""}},
        {"dianping": {"shop": None, "products": [], "reviews": []}}
    )
    if not supplement:
        return None

    name_en = ""
    address_en = ""
    summary_zh = ""
    summary_en = ""
    visit_notice = ""
    tags = None
    sig = None
    facility_names = []
    ranking_desc = ""
    cuisine_tags = None
    subratings = None

    if "L1_base_and_info" in supplement:
        li = supplement["L1_base_and_info"]
        summary_zh = li.get("summary_zh", "")
        summary_en = li.get("summary_en", "")
        name_en = li.get("name_en", "")
        address_en = li.get("address_en", "")

    if "L2_operations" in supplement:
        lo = supplement["L2_operations"]
        visit_notice = lo.get("visit_notice", "")
        sig = lo.get("signature_items", [])
        tags = lo.get("tags", [])
        ranking_desc = lo.get("ranking_desc", "")
        cuisine_tags = lo.get("cuisine_tags", [])
        subratings = lo.get("subratings", [])

    if "sub_tables" in supplement:
        sub = supplement["sub_tables"]
        facility_names = sub.get("store_facility", [])

    return {
        "store_id": store_id,
        "summary_zh": summary_zh,
        "summary_en": summary_en,
        "name_en": name_en,
        "address_en": address_en,
        "visit_notice": visit_notice,
        "signature_items": json.dumps(sig, ensure_ascii=False) if sig else None,
        "tags": json.dumps(tags, ensure_ascii=False) if tags else None,
        "ranking_desc": ranking_desc,
        "cuisine_tags": json.dumps(cuisine_tags, ensure_ascii=False) if cuisine_tags else None,
        "subratings": json.dumps(subratings, ensure_ascii=False) if subratings else None,
        "facility_names": json.dumps(facility_names, ensure_ascii=False) if facility_names else None,
    }


def main():
    parser = argparse.ArgumentParser(description="Supplement store data via LLM")
    parser.add_argument("--db", type=str, default="output/xootour_nanjing.db", help="Database path")
    parser.add_argument("--limit", type=int, default=0, help="Limit stores to process")
    parser.add_argument("--workers", type=int, default=5, help="Thread workers")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    args = parser.parse_args()

    db_path = args.db
    if not os.path.isabs(db_path):
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), db_path)

    if not os.path.exists(db_path):
        logger.error(f"DB not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row

    query = (
        "SELECT s.id, s.name_zh, sc.name_zh, si.district, si.address_zh, "
        "si.open_hours, si.phone, s.price_range, s.rating "
        "FROM store s "
        "LEFT JOIN store_category sc ON sc.id = s.category_id "
        "LEFT JOIN store_info si ON si.store_id = s.id "
        "WHERE (si.summary_zh IS NULL OR si.summary_zh = '') "
        "ORDER BY s.id"
    )
    if args.limit > 0:
        query += f" LIMIT {args.limit}"
    rows = conn.execute(query).fetchall()
    total = len(rows)
    logger.info(f"Stores needing LLM supplement: {total}")

    if total == 0:
        logger.info("All stores have supplemental data.")
        conn.close()
        return

    if args.dry_run:
        logger.info("DRY RUN - first 10 stores:")
        for r in rows[:10]:
            logger.info(f"  {r['id']}: {r['name_zh'][:30]}")
        conn.close()
        return

    llm = FreeLLMExtractor()
    if not llm.client:
        logger.error("LLM client not initialized. Check API keys.")
        conn.close()
        return

    ok = 0
    fail = 0
    write_lock = Lock()

    def process(row):
        return process_one(llm, row)

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process, row): row for row in rows}
        for i, future in enumerate(as_completed(futures), 1):
            row = futures[future]
            try:
                result = future.result()
                if result:
                    with write_lock:
                        sid = result["store_id"]
                        conn.execute(
                            "UPDATE store SET name_en=COALESCE(?, name_en) WHERE id=?",
                            (result["name_en"], sid),
                        )
                        conn.execute(
                            "UPDATE store_info SET summary_zh=COALESCE(?, summary_zh), "
                            "summary_en=COALESCE(?, summary_en), "
                            "address_en=COALESCE(?, address_en), "
                            "visit_notice=COALESCE(?, visit_notice), "
                            "signature_items=COALESCE(?, signature_items), "
                            "tags=COALESCE(?, tags), "
                            "subratings=COALESCE(?, subratings) "
                            "WHERE store_id=?",
                            (result["summary_zh"], result["summary_en"], result["address_en"],
                             result["visit_notice"], result["signature_items"], result["tags"],
                             result["subratings"], sid),
                        )
                        if result.get("facility_names"):
                            facility_list = json.loads(result["facility_names"])
                            for f in facility_list:
                                conn.execute(
                                    "INSERT OR IGNORE INTO store_facility (store_id, category, facility_name, is_bold, description) "
                                    "VALUES (?,?,?,?,?)",
                                    (sid, f.get("category"), f.get("facility_name"),
                                     1 if f.get("is_bold") else 0, f.get("description")),
                                )
                        if result.get("ranking_desc"):
                            conn.execute(
                                "UPDATE store SET ranking_desc=? WHERE id=?",
                                (result["ranking_desc"], sid),
                            )
                        if result.get("cuisine_tags"):
                            conn.execute(
                                "UPDATE store SET cuisine_tags=? WHERE id=?",
                                (result["cuisine_tags"], sid),
                            )
                        conn.commit()
                        ok += 1
                else:
                    fail += 1
                    if fail <= 5:
                        logger.warning(f"  [{row['id']}] LLM supplement failed")
            except Exception as e:
                fail += 1
                logger.error(f"  [{row['id']}] Error: {e}")

            if i % 50 == 0:
                logger.info(f"  Progress: {i}/{total} (ok={ok}, fail={fail})")

    logger.info(f"\n=== Supplemental Summary ===")
    logger.info(f"  OK: {ok}, Fail: {fail}")
    conn.close()


if __name__ == "__main__":
    main()
