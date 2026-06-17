import json
import logging
import os
import sqlite3

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "xootour_sanya.db")


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT store_id, signature_items FROM store_info "
        "WHERE signature_items IS NOT NULL AND signature_items != '' AND signature_items != '[]'"
    ).fetchall()
    logger.info(f"Found {len(rows)} store_info rows with signature_items")

    inserted = 0
    for row in rows:
        store_id = row["store_id"]
        try:
            items = json.loads(row["signature_items"])
        except (json.JSONDecodeError, TypeError):
            continue

        if not isinstance(items, list) or len(items) == 0:
            continue

        existing = conn.execute(
            "SELECT COUNT(*) as cnt FROM store_product WHERE store_id=?", (store_id,)
        ).fetchone()["cnt"]
        if existing > 0:
            continue

        for i, item in enumerate(items, 1):
            if not isinstance(item, dict):
                continue
            product_name = item.get("name", "")
            if not product_name:
                continue
            conn.execute(
                "INSERT INTO store_product (store_id, product_name, price, description, currency, is_signature, sort_order) "
                "VALUES (?,?,?,?,?,?,?)",
                (store_id, product_name, item.get("price"), item.get("description", ""), "RMB", 1, i)
            )
            inserted += 1

    conn.commit()
    logger.info(f"Inserted {inserted} store_product rows")

    total_products = conn.execute("SELECT COUNT(*) as cnt FROM store_product").fetchone()["cnt"]
    stores_with_products = conn.execute(
        "SELECT COUNT(DISTINCT store_id) as cnt FROM store_product"
    ).fetchone()["cnt"]
    logger.info(f"store_product now has {total_products} rows across {stores_with_products} stores")

    conn.close()


if __name__ == "__main__":
    main()
