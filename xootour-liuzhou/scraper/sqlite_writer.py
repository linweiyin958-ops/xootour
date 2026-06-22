import json
import logging
import os
import sqlite3
from typing import Optional, List

from .config import OUTPUT_DIR, LIUZHOU_CITY_ID

logger = logging.getLogger(__name__)


class SQLiteWriter:
    def __init__(self, db_path: str = None):
        if not db_path:
            db_path = os.path.join(OUTPUT_DIR, "xootour_liuzhou.db")
        self.db_path = db_path
        self.conn = None

    def connect(self) -> bool:
        try:
            os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
            self.conn = sqlite3.connect(self.db_path)
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.row_factory = sqlite3.Row
            logger.info(f"[SQLite] Connected: {self.db_path}")
            return True
        except Exception as e:
            logger.error(f"[SQLite] Connection failed: {e}")
            return False

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
            logger.info("[SQLite] Connection closed")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def init_schema(self):
        schema_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "schema_sqlite.sql"
        )
        with open(schema_file, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        try:
            self.conn.executescript(schema_sql)
            self.conn.commit()
            logger.info("[SQLite] Schema initialized")
        except Exception as e:
            logger.error(f"[SQLite] Schema init error: {e}")
            raise

    def _exec(self, sql: str, params: tuple = None) -> int:
        try:
            cur = self.conn.execute(sql, params or ())
            self.conn.commit()
            return cur.rowcount
        except Exception as e:
            self.conn.rollback()
            logger.error(f"[SQLite] Exec error: {e}")
            raise

    def _exec_many(self, sql: str, params_list: List[tuple]) -> int:
        try:
            cur = self.conn.executemany(sql, params_list)
            self.conn.commit()
            return cur.rowcount
        except Exception as e:
            self.conn.rollback()
            logger.error(f"[SQLite] ExecMany error: {e}")
            raise

    def _insert_and_get_id(self, sql: str, params: tuple = None) -> Optional[int]:
        try:
            cur = self.conn.execute(sql, params or ())
            self.conn.commit()
            return cur.lastrowid
        except Exception as e:
            self.conn.rollback()
            logger.error(f"[SQLite] Insert error: {e}")
            return None

    def write_spot_data(self, spot_id: int, data: dict):
        l1 = data.get("L1_base_and_info", {})
        l2 = data.get("L2_operations", {})
        l3 = data.get("L3_ugc_trends", {})
        l5 = data.get("L5_quality_control", {})
        sub = data.get("sub_tables", {})

        self._exec(
            "INSERT OR REPLACE INTO tour_spot (id, name, subtitle, city_id, cover_img, seo_desc, base_price, rating) VALUES (?,?,?,?,?,?,?,?)",
            (spot_id, l1.get("name_zh"), l1.get("name_en"), l1.get("city_id", LIUZHOU_CITY_ID),
             l1.get("cover_img"), l1.get("seo_desc"), l2.get("base_price", 0.00), l2.get("rating", 0.0))
        )

        self._exec(
            "INSERT OR REPLACE INTO tour_spot_info (spot_id, district, address_zh, address_en, lat, lng, "
            "summary_zh, summary_en, open_hours, transportation, visit_notice, "
            "best_visit_season, photo_spots, crowd_tags, "
            "source_platform, source_note_ids, data_collected_at, data_quality_score, is_ai_generated) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (spot_id, l1.get("district"), l1.get("address_zh"), l1.get("address_en"),
             l1.get("lat"), l1.get("lng"), l1.get("summary_zh"), l1.get("summary_en"),
             l2.get("open_hours"), l2.get("transportation"), l2.get("visit_notice"),
             l3.get("best_visit_season"),
             json.dumps(l3.get("photo_spots"), ensure_ascii=False) if l3.get("photo_spots") else None,
             json.dumps(l3.get("crowd_tags"), ensure_ascii=False) if l3.get("crowd_tags") else None,
             l5.get("source_platform"),
             json.dumps(l5.get("source_note_ids"), ensure_ascii=False) if l5.get("source_note_ids") else None,
             l5.get("data_collected_at"), l5.get("data_quality_score"),
             1 if l5.get("is_ai_generated", True) else 0)
        )

        banners = sub.get("tour_spot_banner", [])
        if banners:
            self._exec("DELETE FROM tour_spot_banner WHERE spot_id=?", (spot_id,))
            self._exec_many(
                "INSERT INTO tour_spot_banner (spot_id, image_url, sort_order, photo_credit) VALUES (?,?,?,?)",
                [(spot_id, b.get("image_url"), b.get("sort_order", i), b.get("photo_credit")) for i, b in enumerate(banners, 1)]
            )

        features = sub.get("tour_spot_feature", [])
        if features:
            self._exec("DELETE FROM tour_spot_feature WHERE spot_id=?", (spot_id,))
            self._exec_many(
                "INSERT INTO tour_spot_feature (spot_id, title, description) VALUES (?,?,?)",
                [(spot_id, f.get("title"), f.get("description")) for f in features]
            )

        routes = sub.get("tour_spot_route", [])
        if routes:
            self._exec("DELETE FROM tour_spot_route WHERE spot_id=?", (spot_id,))
            self._exec_many(
                "INSERT INTO tour_spot_route (spot_id, route_name, duration_hours, route_nodes, description) VALUES (?,?,?,?,?)",
                [(spot_id, r.get("route_name"), r.get("duration_hours"),
                  json.dumps(r.get("route_nodes"), ensure_ascii=False) if r.get("route_nodes") else None,
                  r.get("description")) for r in routes]
            )

        facilities = sub.get("tour_spot_facility", [])
        if facilities:
            self._exec("DELETE FROM tour_spot_facility WHERE spot_id=?", (spot_id,))
            self._exec_many(
                "INSERT INTO tour_spot_facility (spot_id, facility_name, is_bold, description) VALUES (?,?,?,?)",
                [(spot_id, f.get("facility_name"), 1 if f.get("is_bold") else 0, f.get("description")) for f in facilities]
            )

        packages = sub.get("tour_spot_package", [])
        if packages:
            self._exec("DELETE FROM tour_spot_package WHERE spot_id=?", (spot_id,))
            self._exec_many(
                "INSERT INTO tour_spot_package (spot_id, package_name, price, description, currency) VALUES (?,?,?,?,?)",
                [(spot_id, p.get("package_name"), p.get("price"), p.get("description"), p.get("currency", "RMB")) for p in packages]
            )

        logger.info(f"[SQLite] Wrote spot_id={spot_id} with all sub-tables")

    @staticmethod
    def _to_scalar(val, default=None):
        if val is None:
            return default
        if isinstance(val, (str, int, float, bool)):
            return val
        if isinstance(val, (list, dict)):
            return json.dumps(val, ensure_ascii=False)
        return str(val)

    def write_store_data(self, store_id: int, data: dict):
        l1 = data.get("L1_base_and_info", {})
        l2 = data.get("L2_operations", {})
        l5 = data.get("L5_quality_control", {})
        sub = data.get("sub_tables", {})

        self._exec(
            "INSERT OR REPLACE INTO store (id, name_zh, name_en, category_id, city_id, cover_img, seo_desc, "
            "price_range, rating) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (store_id,
             self._to_scalar(l1.get("name_zh")),
             self._to_scalar(l1.get("name_en")),
             self._to_scalar(l1.get("category_id")),
             self._to_scalar(l1.get("city_id", LIUZHOU_CITY_ID)),
             self._to_scalar(l1.get("cover_img")),
             self._to_scalar(l1.get("seo_desc")),
             self._to_scalar(l2.get("price_range")),
             self._to_scalar(l2.get("rating", 0.0)))
        )

        self._exec(
            "INSERT OR REPLACE INTO store_info (store_id, category_id, amap_id, district, address_zh, address_en, "
            "lat, lng, phone, website, open_hours, summary_zh, summary_en, "
            "visit_notice, signature_items, tags, category_specific_fields, "
            "subratings, features, photos_count, "
            "source_platform, source_urls, data_collected_at, data_quality_score, is_ai_generated) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (store_id,
             self._to_scalar(l1.get("category_id")),
             self._to_scalar(l2.get("amap_id")),
             self._to_scalar(l1.get("district")),
             self._to_scalar(l1.get("address_zh")),
             self._to_scalar(l1.get("address_en")),
             self._to_scalar(l1.get("lat")),
             self._to_scalar(l1.get("lng")),
             self._to_scalar(l2.get("phone")),
             self._to_scalar(l2.get("website")),
             self._to_scalar(l2.get("open_hours")),
             self._to_scalar(l1.get("summary_zh")),
             self._to_scalar(l1.get("summary_en")),
             self._to_scalar(l2.get("visit_notice")),
             self._to_scalar(l2.get("signature_items")),
             self._to_scalar(l2.get("tags")),
             self._to_scalar(l2.get("category_specific_fields")),
             self._to_scalar(l2.get("subratings")),
             self._to_scalar(l2.get("features")),
             self._to_scalar(l2.get("photos_count", 0)),
             self._to_scalar(l5.get("source_platform")),
             self._to_scalar(l5.get("source_urls")),
             self._to_scalar(l5.get("data_collected_at")),
             self._to_scalar(l5.get("data_quality_score", 0.0)),
             1 if l5.get("is_ai_generated", True) else 0)
        )

        banners = sub.get("store_banner", [])
        if banners:
            self._exec("DELETE FROM store_banner WHERE store_id=?", (store_id,))
            self._exec_many(
                "INSERT INTO store_banner (store_id, image_url, sort_order, caption, photo_credit) VALUES (?,?,?,?,?)",
                [(store_id, self._to_scalar(b.get("image_url")), self._to_scalar(b.get("sort_order", i)),
                  self._to_scalar(b.get("caption")), self._to_scalar(b.get("photo_credit"))) for i, b in enumerate(banners, 1)]
            )

        products = sub.get("store_product", [])
        if products:
            self._exec("DELETE FROM store_product WHERE store_id=?", (store_id,))
            for p in products:
                self._insert_and_get_id(
                    "INSERT INTO store_product (store_id, product_name, price, description, currency, is_signature, sort_order) VALUES (?,?,?,?,?,?,?)",
                    (store_id, self._to_scalar(p.get("product_name")), self._to_scalar(p.get("price")),
                     self._to_scalar(p.get("description")), self._to_scalar(p.get("currency", "RMB")),
                     1 if p.get("is_signature") else 0, self._to_scalar(p.get("sort_order", 0)))
                )

        facilities = sub.get("store_facility", [])
        if facilities:
            self._exec("DELETE FROM store_facility WHERE store_id=?", (store_id,))
            self._exec_many(
                "INSERT INTO store_facility (store_id, category, facility_name, is_bold, description) VALUES (?,?,?,?,?)",
                [(store_id, self._to_scalar(f.get("category")), self._to_scalar(f.get("facility_name")),
                  1 if f.get("is_bold") else 0, self._to_scalar(f.get("description"))) for f in facilities]
            )

        logger.info(f"[SQLite] Wrote store_id={store_id} with all sub-tables")
