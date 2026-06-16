import json
import logging
import os
import sqlite3

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "xootour_chongqing.db")


def merge_info(conn, keep_id, dup_id):
    keep = dict(conn.execute(
        "SELECT * FROM store_info WHERE store_id=?", (keep_id,)
    ).fetchone())
    dup = dict(conn.execute(
        "SELECT * FROM store_info WHERE store_id=?", (dup_id,)
    ).fetchone())

    if not keep or not dup:
        return

    updates = {}
    for col in ["district", "address_zh", "address_en", "lat", "lng", "phone", "website",
                 "open_hours", "summary_zh", "summary_en", "visit_notice",
                 "signature_items", "tags", "category_specific_fields", "source_urls"]:
        if (not keep.get(col) or keep.get(col) in ("", "[]", "null", "{}")) and dup.get(col) and dup.get(col) not in ("", "[]", "null", "{}"):
            updates[col] = dup[col]

    if updates:
        set_clause = ", ".join(f"{k}=?" for k in updates)
        conn.execute(
            f"UPDATE store_info SET {set_clause} WHERE store_id=?",
            tuple(updates.values()) + (keep_id,)
        )

    logger.info(f"  Merged store_info from store_id={dup_id} into {keep_id}: {list(updates.keys())}")


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row

    dups = conn.execute(
        "SELECT amap_id, COUNT(*) as cnt, GROUP_CONCAT(store_id) as ids "
        "FROM store_info WHERE amap_id IS NOT NULL AND amap_id != '' "
        "GROUP BY amap_id HAVING cnt > 1 ORDER BY cnt DESC"
    ).fetchall()
    logger.info(f"Found {len(dups)} groups of duplicate amap_id")

    total_removed = 0
    for group in dups:
        amap_id = group["amap_id"]
        ids = [int(x) for x in group["ids"].split(",")]

        rows = conn.execute(
            "SELECT s.id, s.data_quality_score, COALESCE(LENGTH(s.name_en), 0) as en_len "
            "FROM store s WHERE s.id IN ({}) ORDER BY s.data_quality_score DESC, en_len DESC, s.id ASC".format(
                ",".join("?" * len(ids))
            ), ids
        ).fetchall()

        keep_id = rows[0]["id"]
        dupe_ids = [r["id"] for r in rows[1:]]

        logger.info(f"amap_id={amap_id}: keep={keep_id}, remove={dupe_ids}")

        for dup_id in dupe_ids:
            merge_info(conn, keep_id, dup_id)

            conn.execute(
                "UPDATE store_banner SET store_id=? WHERE store_id=?",
                (keep_id, dup_id)
            )
            conn.execute(
                "UPDATE store_facility SET store_id=? WHERE store_id=?",
                (keep_id, dup_id)
            )
            conn.execute(
                "UPDATE store_product SET store_id=? WHERE store_id=?",
                (keep_id, dup_id)
            )

            conn.execute("DELETE FROM store_info WHERE store_id=?", (dup_id,))
            conn.execute("DELETE FROM store WHERE id=?", (dup_id,))
            total_removed += 1

        conn.commit()

    logger.info(f"Removed {total_removed} duplicate stores by amap_id")

    total = conn.execute("SELECT COUNT(*) FROM store").fetchone()[0]
    logger.info(f"store now has {total} rows")
    conn.close()


if __name__ == "__main__":
    main()
