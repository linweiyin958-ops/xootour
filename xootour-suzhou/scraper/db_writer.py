import json
import logging
import os
from typing import Optional, List, Any

import pymysql
from pymysql.cursors import DictCursor

from .config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, DB_CHARSET, SUZHOU_CITY_ID

logger = logging.getLogger(__name__)


class DBWriter:
    def __init__(
        self,
        host: str = None,
        port: int = None,
        user: str = None,
        password: str = None,
        database: str = None,
        charset: str = None,
    ):
        self.host = host or DB_HOST
        self.port = port or DB_PORT
        self.user = user or DB_USER
        self.password = password or DB_PASSWORD
        self.database = database or DB_NAME
        self.charset = charset or DB_CHARSET
        self.connection = None

    def connect(self):
        try:
            self.connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                charset=self.charset,
                cursorclass=DictCursor,
                autocommit=False,
            )
            logger.info(f"[DB] Connected to {self.host}:{self.port}/{self.database}")
            return True
        except Exception as e:
            logger.error(f"[DB] Connection failed: {e}")
            return False

    def close(self):
        if self.connection:
            self.connection.close()
            self.connection = None
            logger.info("[DB] Connection closed")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _ensure_connection(self):
        if not self.connection:
            if not self.connect():
                raise RuntimeError("Database connection not available")
        try:
            self.connection.ping(reconnect=True)
        except Exception:
            self.connect()

    def execute(self, sql: str, params: tuple = None) -> int:
        self._ensure_connection()
        try:
            with self.connection.cursor() as cursor:
                affected = cursor.execute(sql, params)
                self.connection.commit()
                return affected
        except Exception as e:
            self.connection.rollback()
            logger.error(f"[DB] Execute error: {e}\n  SQL: {sql[:200]}")
            raise

    def execute_many(self, sql: str, params_list: List[tuple]) -> int:
        self._ensure_connection()
        try:
            with self.connection.cursor() as cursor:
                affected = cursor.executemany(sql, params_list)
                self.connection.commit()
                return affected
        except Exception as e:
            self.connection.rollback()
            logger.error(f"[DB] ExecuteMany error: {e}\n  SQL: {sql[:200]}")
            raise

    def query_one(self, sql: str, params: tuple = None) -> Optional[dict]:
        self._ensure_connection()
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"[DB] Query error: {e}")
            return None

    def query_all(self, sql: str, params: tuple = None) -> List[dict]:
        self._ensure_connection()
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"[DB] Query error: {e}")
            return []

    def insert_and_get_id(self, sql: str, params: tuple = None) -> Optional[int]:
        self._ensure_connection()
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql, params)
                self.connection.commit()
                return cursor.lastrowid
        except Exception as e:
            self.connection.rollback()
            logger.error(f"[DB] Insert error: {e}\n  SQL: {sql[:200]}")
            return None

    def upsert(self, table: str, data: dict, unique_keys: List[str]) -> Optional[int]:
        columns = list(data.keys())
        placeholders = ["%s"] * len(columns)
        values = [data[c] for c in columns]

        insert_sql = f"INSERT INTO `{table}` (`{'`, `'.join(columns)}`) VALUES ({', '.join(placeholders)})"

        update_parts = []
        for c in columns:
            if c not in unique_keys:
                update_parts.append(f"`{c}` = VALUES(`{c}`)")
        if update_parts:
            insert_sql += f" ON DUPLICATE KEY UPDATE {', '.join(update_parts)}"

        return self.insert_and_get_id(insert_sql, tuple(values))

    def insert_tour_spot(self, data: dict) -> Optional[int]:
        sql = (
            "INSERT INTO `tour_spot` (`id`, `name`, `subtitle`, `city_id`, `cover_img`, `seo_desc`, `base_price`, `rating`) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
        )
        params = (
            data.get("id"),
            data.get("name"),
            data.get("subtitle"),
            data.get("city_id", SUZHOU_CITY_ID),
            data.get("cover_img"),
            data.get("seo_desc"),
            data.get("base_price", 0.00),
            data.get("rating", 0.0),
        )
        return self.insert_and_get_id(sql, params)

    def insert_tour_spot_info(self, data: dict) -> Optional[int]:
        sql = (
            "INSERT INTO `tour_spot_info` (`spot_id`, `district`, `address_zh`, `address_en`, `lat`, `lng`, "
            "`summary_zh`, `summary_en`, `open_hours`, `transportation`, `visit_notice`, "
            "`best_visit_season`, `photo_spots`, `crowd_tags`, "
            "`source_platform`, `source_note_ids`, `data_collected_at`, `data_quality_score`, `is_ai_generated`) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        )
        params = (
            data.get("spot_id"),
            data.get("district"),
            data.get("address_zh"),
            data.get("address_en"),
            data.get("lat"),
            data.get("lng"),
            data.get("summary_zh"),
            data.get("summary_en"),
            data.get("open_hours"),
            data.get("transportation"),
            data.get("visit_notice"),
            data.get("best_visit_season"),
            json.dumps(data.get("photo_spots"), ensure_ascii=False) if isinstance(data.get("photo_spots"), (list, dict)) else data.get("photo_spots"),
            json.dumps(data.get("crowd_tags"), ensure_ascii=False) if isinstance(data.get("crowd_tags"), (list, dict)) else data.get("crowd_tags"),
            data.get("source_platform"),
            json.dumps(data.get("source_note_ids"), ensure_ascii=False) if isinstance(data.get("source_note_ids"), (list, dict)) else data.get("source_note_ids"),
            data.get("data_collected_at"),
            data.get("data_quality_score"),
            data.get("is_ai_generated", True),
        )
        return self.insert_and_get_id(sql, params)

    def insert_tour_spot_banners(self, spot_id: int, banners: list):
        if not banners:
            return
        sql = "INSERT INTO `tour_spot_banner` (`spot_id`, `image_url`, `sort_order`, `photo_credit`) VALUES (%s, %s, %s, %s)"
        params_list = [
            (spot_id, b.get("image_url"), b.get("sort_order", i), b.get("photo_credit"))
            for i, b in enumerate(banners, 1)
        ]
        self.execute_many(sql, params_list)

    def insert_tour_spot_features(self, spot_id: int, features: list):
        if not features:
            return
        sql = "INSERT INTO `tour_spot_feature` (`spot_id`, `title`, `description`) VALUES (%s, %s, %s)"
        params_list = [(spot_id, f.get("title"), f.get("description")) for f in features]
        self.execute_many(sql, params_list)

    def insert_tour_spot_routes(self, spot_id: int, routes: list):
        if not routes:
            return
        sql = "INSERT INTO `tour_spot_route` (`spot_id`, `route_name`, `duration_hours`, `route_nodes`, `description`) VALUES (%s, %s, %s, %s, %s)"
        params_list = [
            (spot_id, r.get("route_name"), r.get("duration_hours"),
             json.dumps(r.get("route_nodes"), ensure_ascii=False) if isinstance(r.get("route_nodes"), (list, dict)) else r.get("route_nodes"),
             r.get("description"))
            for r in routes
        ]
        self.execute_many(sql, params_list)

    def insert_tour_spot_facilities(self, spot_id: int, facilities: list):
        if not facilities:
            return
        sql = "INSERT INTO `tour_spot_facility` (`spot_id`, `facility_name`, `is_bold`, `description`) VALUES (%s, %s, %s, %s)"
        params_list = [(spot_id, f.get("facility_name"), f.get("is_bold", False), f.get("description")) for f in facilities]
        self.execute_many(sql, params_list)

    def insert_tour_spot_packages(self, spot_id: int, packages: list):
        if not packages:
            return
        sql = "INSERT INTO `tour_spot_package` (`spot_id`, `package_name`, `price`, `description`, `currency`) VALUES (%s, %s, %s, %s, %s)"
        params_list = [(spot_id, p.get("package_name"), p.get("price"), p.get("description"), p.get("currency", "RMB")) for p in packages]
        self.execute_many(sql, params_list)

    def write_spot_data(self, spot_id: int, structured_data: dict):
        l1 = structured_data.get("L1_base_and_info", {})
        l2 = structured_data.get("L2_operations", {})
        l3 = structured_data.get("L3_ugc_trends", {})
        l5 = structured_data.get("L5_quality_control", {})
        sub = structured_data.get("sub_tables", {})

        self.insert_tour_spot({
            "id": spot_id,
            "name": l1.get("name_zh"),
            "subtitle": l1.get("name_en"),
            "city_id": l1.get("city_id", 1),
            "cover_img": l1.get("cover_img"),
            "seo_desc": l1.get("seo_desc"),
            "base_price": l2.get("base_price", 0.00),
            "rating": l2.get("rating", 0.0),
        })

        self.insert_tour_spot_info({
            "spot_id": spot_id,
            "district": l1.get("district"),
            "address_zh": l1.get("address_zh"),
            "address_en": l1.get("address_en"),
            "lat": l1.get("lat"),
            "lng": l1.get("lng"),
            "summary_zh": l1.get("summary_zh"),
            "summary_en": l1.get("summary_en"),
            "open_hours": l2.get("open_hours"),
            "transportation": l2.get("transportation"),
            "visit_notice": l2.get("visit_notice"),
            "best_visit_season": l3.get("best_visit_season"),
            "photo_spots": l3.get("photo_spots"),
            "crowd_tags": l3.get("crowd_tags"),
            "source_platform": l5.get("source_platform"),
            "source_note_ids": l5.get("source_note_ids"),
            "data_collected_at": l5.get("data_collected_at"),
            "data_quality_score": l5.get("data_quality_score"),
            "is_ai_generated": l5.get("is_ai_generated", True),
        })

        self.insert_tour_spot_banners(spot_id, sub.get("tour_spot_banner", []))
        self.insert_tour_spot_features(spot_id, sub.get("tour_spot_feature", []))
        self.insert_tour_spot_routes(spot_id, sub.get("tour_spot_route", []))
        self.insert_tour_spot_facilities(spot_id, sub.get("tour_spot_facility", []))
        self.insert_tour_spot_packages(spot_id, sub.get("tour_spot_package", []))

        logger.info(f"[DB] Wrote spot_id={spot_id} with all sub-tables")

    def insert_store(self, data: dict) -> Optional[int]:
        sql = (
            "INSERT INTO `store` (`id`, `name_zh`, `name_en`, `category_id`, `city_id`, `cover_img`, `seo_desc`, "
            "`price_range`, `rating`, `review_count`, `ranking_desc`, `cuisine_tags`, "
            "`michelin_status`, `source_platform`, `data_quality_score`, `is_ai_generated`) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        )
        params = (
            data.get("id"),
            data.get("name_zh"),
            data.get("name_en"),
            data.get("category_id"),
            data.get("city_id", SUZHOU_CITY_ID),
            data.get("cover_img"),
            data.get("seo_desc"),
            data.get("price_range"),
            data.get("rating", 0.0),
            data.get("review_count", 0),
            data.get("ranking_desc"),
            data.get("cuisine_tags"),
            data.get("michelin_status", 0),
            data.get("source_platform"),
            data.get("data_quality_score", 0.0),
            1 if data.get("is_ai_generated", True) else 0,
        )
        return self.insert_and_get_id(sql, params)

    def insert_store_info(self, data: dict) -> Optional[int]:
        sql = (
            "INSERT INTO `store_info` (`store_id`, `category_id`, `amap_id`, `district`, `address_zh`, `address_en`, "
            "`lat`, `lng`, `phone`, `website`, `open_hours`, `summary_zh`, `summary_en`, "
            "`visit_notice`, `signature_items`, `tags`, `category_specific_fields`, "
            "`subratings`, `features`, `photos_count`, "
            "`source_platform`, `source_urls`, "
            "`data_collected_at`, `data_quality_score`, `is_ai_generated`) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        )
        params = (
            data.get("store_id"),
            data.get("category_id"),
            data.get("amap_id"),
            data.get("district"),
            data.get("address_zh"),
            data.get("address_en"),
            data.get("lat"),
            data.get("lng"),
            data.get("phone"),
            data.get("website"),
            data.get("open_hours"),
            data.get("summary_zh"),
            data.get("summary_en"),
            data.get("visit_notice"),
            json.dumps(data.get("signature_items"), ensure_ascii=False) if isinstance(data.get("signature_items"), (list, dict)) else data.get("signature_items"),
            json.dumps(data.get("tags"), ensure_ascii=False) if isinstance(data.get("tags"), (list, dict)) else data.get("tags"),
            json.dumps(data.get("category_specific_fields"), ensure_ascii=False) if isinstance(data.get("category_specific_fields"), (list, dict)) else data.get("category_specific_fields"),
            json.dumps(data.get("subratings"), ensure_ascii=False) if isinstance(data.get("subratings"), (list, dict)) else data.get("subratings"),
            json.dumps(data.get("features"), ensure_ascii=False) if isinstance(data.get("features"), (list, dict)) else data.get("features"),
            data.get("photos_count", 0),
            data.get("source_platform"),
            json.dumps(data.get("source_urls"), ensure_ascii=False) if isinstance(data.get("source_urls"), (list, dict)) else data.get("source_urls"),
            data.get("data_collected_at"),
            data.get("data_quality_score"),
            data.get("is_ai_generated", True),
        )
        return self.insert_and_get_id(sql, params)

    def insert_store_banners(self, store_id: int, banners: list):
        if not banners:
            return
        sql = "INSERT INTO `store_banner` (`store_id`, `image_url`, `sort_order`, `caption`, `photo_credit`) VALUES (%s, %s, %s, %s, %s)"
        params_list = [
            (store_id, b.get("image_url"), b.get("sort_order", i), b.get("caption"), b.get("photo_credit"))
            for i, b in enumerate(banners, 1)
        ]
        self.execute_many(sql, params_list)

    def insert_store_products(self, store_id: int, products: list):
        if not products:
            return
        product_ids = []
        for p in products:
            sql = (
                "INSERT INTO `store_product` (`store_id`, `product_name`, `price`, `description`, `currency`, `is_signature`, `sort_order`) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)"
            )
            params = (
                store_id, p.get("product_name"), p.get("price"), p.get("description"),
                p.get("currency", "RMB"), p.get("is_signature", False), p.get("sort_order", 0),
            )
            pid = self.insert_and_get_id(sql, params)
            if pid:
                product_ids.append((pid, p))
        return product_ids

    def insert_store_product_images(self, product_id: int, images: list):
        if not images:
            return
        sql = "INSERT INTO `store_product_image` (`product_id`, `image_url`, `sort_order`) VALUES (%s, %s, %s)"
        params_list = [(product_id, img.get("image_url", img) if isinstance(img, dict) else img, i) for i, img in enumerate(images, 1)]
        self.execute_many(sql, params_list)

    def insert_store_facilities(self, store_id: int, facilities: list):
        if not facilities:
            return
        sql = "INSERT INTO `store_facility` (`store_id`, `category`, `facility_name`, `is_bold`, `description`) VALUES (%s, %s, %s, %s, %s)"
        params_list = [(store_id, f.get("category"), f.get("facility_name"), f.get("is_bold", False), f.get("description")) for f in facilities]
        self.execute_many(sql, params_list)

    def write_store_data(self, store_id: int, structured_data: dict):
        """Write store sub-tables (info, banners, products, facilities).
        Assumes the store row itself was already inserted via insert_store()."""
        l1 = structured_data.get("L1_base_and_info", {})
        l2 = structured_data.get("L2_operations", {})
        l5 = structured_data.get("L5_quality_control", {})
        sub = structured_data.get("sub_tables", {})

        self.insert_store_info({
            "store_id": store_id,
            "category_id": l1.get("category_id"),
            "amap_id": l2.get("amap_id"),
            "district": l1.get("district"),
            "address_zh": l1.get("address_zh"),
            "address_en": l1.get("address_en"),
            "lat": l1.get("lat"),
            "lng": l1.get("lng"),
            "phone": l2.get("phone"),
            "website": l2.get("website"),
            "open_hours": l2.get("open_hours"),
            "summary_zh": l1.get("summary_zh"),
            "summary_en": l1.get("summary_en"),
            "visit_notice": l2.get("visit_notice"),
            "signature_items": l2.get("signature_items"),
            "tags": l2.get("tags"),
            "category_specific_fields": l2.get("category_specific_fields"),
            "subratings": l2.get("subratings"),
            "features": l2.get("features"),
            "photos_count": l2.get("photos_count", 0),
            "source_platform": l5.get("source_platform"),
            "source_urls": l5.get("source_urls"),
            "data_collected_at": l5.get("data_collected_at"),
            "data_quality_score": l5.get("data_quality_score"),
            "is_ai_generated": l5.get("is_ai_generated", True),
        })

        self.insert_store_banners(store_id, sub.get("store_banner", []))

        product_ids = self.insert_store_products(store_id, sub.get("store_product", []))
        if product_ids:
            for pid, p in product_ids:
                if p.get("images"):
                    self.insert_store_product_images(pid, p["images"])

        self.insert_store_facilities(store_id, sub.get("store_facility", []))

        logger.info(f"[DB] Wrote store_id={store_id} with all sub-tables")

    def init_schema(self, schema_file: str = None):
        if not schema_file:
            schema_file = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data", "schema.sql"
            )
        with open(schema_file, "r", encoding="utf-8") as f:
            schema_sql = f.read()

        self._ensure_connection()
        try:
            with self.connection.cursor() as cursor:
                for statement in schema_sql.split(";"):
                    stmt = statement.strip()
                    if stmt and not stmt.startswith("--") and not stmt.startswith("CREATE DATABASE"):
                        cursor.execute(stmt)
                self.connection.commit()
            logger.info("[DB] Schema initialized successfully")
        except Exception as e:
            self.connection.rollback()
            logger.error(f"[DB] Schema init error: {e}")
            raise
