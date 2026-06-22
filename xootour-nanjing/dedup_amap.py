import json
import logging
import os
import sqlite3

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "xootour_nanjing.db")


def merge_info(conn, keep_id, dup_id):
    keep = dict(conn.execute(
        "SELECT * FROM store_info WHERE store_id=?", (keep_id,)
    ).fetchone())
    dup = dict(conn.execute(
        "SELECT * FROM store_info WHERE store_id=?", (dup_id,)
    ).fetchone())

    merged = {}
    for k in keep:
        merged[k] = keep[k] or dup[k]

    conn.execute("DELETE FROM store_info WHERE store_id=?", (dup_id,))
    conn.execute(
        "INSERT OR REPLACE INTO store_info "
        "(store_id, category_id, amap_id, district, address_zh, address_en, "
        "lat, lng, phone, website, open_hours, summary_zh, summary_en, "
        "visit_notice, signature_items, tags, category_specific_fields, "
        "subratings, features, photos_count, "
        "source_platform, source_urls, data_collected_at, data_quality_score, is_ai_generated) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (keep_id, merged.get("category_id"), merged.get("amap_id"),
         merged.get("district"), merged.get("address_zh"), merged.get("address_en"),
         merged.get("lat"), merged.get("lng"), merged.get("phone"),
         merged.get("website"), merged.get("open_hours"),
         merged.get("summary_zh"), merged.get("summary_en"),
         merged.get("visit_notice"), merged.get("signature_items"),
         merged.get("tags"), merged.get("category_specific_fields"),
         merged.get("subratings"), merged.get("features"),
         merged.get("photos_count"), merged.get("source_platform"),
         merged.get("source_urls"), merged.get("data_collected_at"),
         merged.get("data_quality_score"), merged.get("is_ai_generated")),
    )


def main():
    if not os.path.exists(DB_PATH):
        logger.error(f"Database not found: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row

    stores = conn.execute(
        "SELECT s.id, s.name_zh, s.category_id, s.city_id, si.address_zh, si.lat, si.lng "
        "FROM store s LEFT JOIN store_info si ON si.store_id = s.id "
        "ORDER BY s.category_id, s.name_zh"
    ).fetchall()

    groups = {}
    for s in stores:
        key = (s["name_zh"].strip(), s["category_id"])
        if key not in groups:
            groups[key] = []
        groups[key].append(s)

    dup_count = 0
    for key, items in groups.items():
        if len(items) <= 1:
            continue
        items.sort(key=lambda x: x["id"])
        keep = items[0]
        for dup in items[1:]:
            logger.info(f"Merging: {dup['name_zh'][:30]} (id={dup['id']}) -> keep={keep['id']}")
            merge_info(conn, keep["id"], dup["id"])
            conn.execute("DELETE FROM store_banner WHERE store_id=?", (dup["id"],))
            conn.execute("DELETE FROM store_product WHERE store_id=?", (dup["id"],))
            conn.execute("DELETE FROM store_facility WHERE store_id=?", (dup["id"],))
            conn.execute("DELETE FROM store_info WHERE store_id=?", (dup["id"],))
            conn.execute("DELETE FROM store WHERE id=?", (dup["id"],))
            dup_count += 1

    conn.commit()
    logger.info(f"\n=== Dedup complete: {dup_count} duplicates merged ===")
    remaining = conn.execute("SELECT COUNT(*) FROM store").fetchone()[0]
    logger.info(f"Total stores: {remaining}")
    conn.close()


if __name__ == "__main__":
    main()
