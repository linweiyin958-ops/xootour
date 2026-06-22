import json
import logging
import os
import sqlite3

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "xootour_nanjing.db")


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    stores = conn.execute(
        "SELECT s.id, s.name_zh, sc.name_zh FROM store s "
        "JOIN store_category sc ON sc.id = s.category_id "
        "WHERE NOT EXISTS (SELECT 1 FROM store_product WHERE store_id = s.id)"
    ).fetchall()

    total = len(stores)
    logger.info(f"Stores without products: {total}")

    if total == 0:
        logger.info("All stores have products.")
        conn.close()
        return

    count = 0
    for sid, name_zh, cat_name in stores:
        products = []

        if cat_name == "美食":
            products.append({"product_name": f"{name_zh}招牌套餐", "price": 0.00, "description": "", "is_signature": True})
            products.append({"product_name": f"{name_zh}精选套餐", "price": 0.00, "description": "", "is_signature": False})
        elif cat_name == "酒店":
            products.append({"product_name": "标准间", "price": 0.00, "description": "", "is_signature": False})
            products.append({"product_name": "豪华大床房", "price": 0.00, "description": "", "is_signature": True})
        elif cat_name == "景点":
            products.append({"product_name": "成人票", "price": 0.00, "description": "", "is_signature": True})
            products.append({"product_name": "优待票", "price": 0.00, "description": "", "is_signature": False})
        elif cat_name == "购物":
            products.append({"product_name": "热门商品", "price": 0.00, "description": "", "is_signature": True})
        elif cat_name == "娱乐":
            products.append({"product_name": "单人体验", "price": 0.00, "description": "", "is_signature": True})
            products.append({"product_name": "双人套餐", "price": 0.00, "description": "", "is_signature": False})

        for p in products:
            p["currency"] = "RMB"
            p["sort_order"] = 0
            conn.execute(
                "INSERT INTO store_product (store_id, product_name, price, description, currency, is_signature, sort_order) "
                "VALUES (?,?,?,?,?,?,?)",
                (sid, p["product_name"], p["price"], p.get("description", ""), p["currency"],
                 1 if p["is_signature"] else 0, p["sort_order"]),
            )
        count += 1

    conn.commit()
    logger.info(f"Populated {count} stores with {total * 2} products (approx).")
    conn.close()


if __name__ == "__main__":
    main()
