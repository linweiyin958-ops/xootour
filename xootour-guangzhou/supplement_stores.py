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
        l2 = supplement["L2_operations"]
        visit_notice = l2.get("visit_notice", "")
        tags = json.dumps(l2.get("tags", []), ensure_ascii=False) if l2.get("tags") else None
        sig_list = l2.get("signature_items", [])
        if sig_list:
            sig = json.dumps(sig_list, ensure_ascii=False)
        ranking_desc = l2.get("ranking_desc", "")
        ct = l2.get("cuisine_tags", [])
        if ct:
            cuisine_tags = json.dumps(ct, ensure_ascii=False)
        sr = l2.get("subratings", [])
        if sr:
            subratings = json.dumps(sr, ensure_ascii=False)

    if "sub_tables" in supplement and supplement["sub_tables"].get("store_facility"):
        facility_names = supplement["sub_tables"]["store_facility"]

    products = []
    if "sub_tables" in supplement and supplement["sub_tables"].get("store_product"):
        products = supplement["sub_tables"]["store_product"]

    return {
        "store_id": store_id,
        "name": name,
        "summary_zh": summary_zh,
        "summary_en": summary_en,
        "name_en": name_en,
        "address_en": address_en,
        "visit_notice": visit_notice,
        "tags": tags,
        "signature_items": sig,
        "facility_names": facility_names,
        "products": products,
        "ranking_desc": ranking_desc,
        "cuisine_tags": cuisine_tags,
        "subratings": subratings,
    }


def main():
    parser = argparse.ArgumentParser(description="Batch LLM supplement for Guangzhou stores")
    parser.add_argument("--limit", type=int, default=0, help="Max stores to process (0=all)")
    parser.add_argument("--category", type=int, default=0, help="Category ID filter (0=all)")
    parser.add_argument("--workers", type=int, default=3, help="Parallel LLM workers")
    parser.add_argument("--chunk-size", type=int, default=50, help="Progress log interval")
    args = parser.parse_args()

    DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "xootour_guangzhou.db")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    query = """
        SELECT s.id, s.name_zh, sc.name_zh, si.district, si.address_zh,
               si.open_hours, si.phone, s.price_range, s.rating
        FROM store s
        JOIN store_category sc ON sc.id = s.category_id
        LEFT JOIN store_info si ON si.store_id = s.id
        WHERE (si.summary_zh IS NULL OR si.summary_zh = '')
    """
    params = []
    if args.category:
        query += " AND s.category_id = ?"
        params.append(args.category)
    query += " ORDER BY s.category_id, s.id"
    if args.limit:
        query += f" LIMIT {args.limit}"

    missing = conn.execute(query, params).fetchall()
    total = len(missing)
    logger.info(f"Stores missing AI supplement: {total}")

    if total == 0:
        logger.info("All stores have AI supplement data.")
        conn.close()
        return

    llm = FreeLLMExtractor()
    updated = 0
    errors = 0
    write_lock = Lock()
    chunk_size = args.chunk_size

    def write_result(result):
        nonlocal updated
        try:
            conn.execute(
                "UPDATE store SET name_en=?, ranking_desc=?, cuisine_tags=? WHERE id=?",
                (result["name_en"] or None, result["ranking_desc"] or None,
                 result["cuisine_tags"] or None, result["store_id"])
            )
            conn.execute(
                "UPDATE store_info SET summary_zh=?, summary_en=?, address_en=?, "
                "visit_notice=?, tags=?, signature_items=?, subratings=? WHERE store_id=?",
                (result["summary_zh"] or None, result["summary_en"] or None,
                 result["address_en"] or None, result["visit_notice"] or None,
                 result["tags"] or None, result["signature_items"] or None,
                 result["subratings"] or None, result["store_id"])
            )

            if result["facility_names"]:
                conn.execute("DELETE FROM store_facility WHERE store_id=?", (result["store_id"],))
                for f in result["facility_names"]:
                    if isinstance(f, dict):
                        conn.execute(
                            "INSERT INTO store_facility (store_id, category, facility_name, is_bold, description) "
                            "VALUES (?,?,?,?,?)",
                            (result["store_id"], f.get("category", ""),
                             f.get("facility_name", ""), 1 if f.get("is_bold") else 0,
                             f.get("description", ""))
                        )

            if result["products"]:
                existing = conn.execute(
                    "SELECT COUNT(*) FROM store_product WHERE store_id=?", (result["store_id"],)
                ).fetchone()[0]
                if existing == 0:
                    for i, p in enumerate(result["products"], 1):
                        if isinstance(p, dict) and p.get("product_name"):
                            conn.execute(
                                "INSERT INTO store_product (store_id, product_name, price, description, currency, is_signature, sort_order) "
                                "VALUES (?,?,?,?,?,?,?)",
                                (result["store_id"], p["product_name"], p.get("price"),
                                 p.get("description", ""), p.get("currency", "RMB"),
                                 1 if p.get("is_signature") else 0, p.get("sort_order", i))
                            )

            conn.commit()
            updated += 1
        except Exception as e:
            conn.rollback()
            logger.error(f"  [DB] Write error for store {result['store_id']}: {e}")

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_one, llm, row): row for row in missing}

        for i, future in enumerate(as_completed(futures), 1):
            row = futures[future]
            store_id = row[0]
            name = row[1]
            try:
                result = future.result()
                if result:
                    with write_lock:
                        write_result(result)
                    logger.info(f"  [{store_id}] Updated: {name[:30]}")
                else:
                    errors += 1
                    logger.warning(f"  [{store_id}] LLM failed: {name[:30]}")
            except Exception as e:
                errors += 1
                logger.error(f"  [{store_id}] Error: {name[:30]} - {e}")

            if updated > 0 and updated % chunk_size == 0:
                logger.info(f"  --- Progress: {updated}/{total} (errors: {errors}) ---")

    logger.info(f"\nDone! Updated {updated}/{total} stores (errors: {errors})")
    conn.close()


if __name__ == "__main__":
    main()
