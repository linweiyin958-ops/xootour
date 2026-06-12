import json
import logging
import os
from datetime import datetime
from typing import Optional

from .config import OUTPUT_DIR, MACAU_CITY_ID

logger = logging.getLogger(__name__)


def escape_sql(value: str) -> str:
    if value is None:
        return "NULL"
    return value.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')


def format_sql_value(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, dict)):
        return f"'{escape_sql(json.dumps(value, ensure_ascii=False))}'"
    return f"'{escape_sql(str(value))}'"


class StoreSQLGenerator:
    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = output_dir or OUTPUT_DIR
        os.makedirs(self.output_dir, exist_ok=True)

    def generate(self, store_id: int, data: dict) -> str:
        statements = []

        statements.append(self._generate_store(store_id, data))
        statements.append(self._generate_store_info(store_id, data))
        statements.append(self._generate_store_banner(store_id, data))
        statements.append(self._generate_store_product(store_id, data))
        statements.append(self._generate_store_facility(store_id, data))

        sql_content = "\n\n".join(s for s in statements if s)

        name = data.get("L1_base_and_info", {}).get("name_zh", "unknown")
        filename = f"store_{store_id}_{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(sql_content)

        logger.info(f"[StoreSQL] Generated: {filepath}")
        return filepath

    def _generate_store(self, store_id: int, data: dict) -> str:
        l1 = data.get("L1_base_and_info", {})
        l2 = data.get("L2_operations", {})
        l5 = data.get("L5_quality_control", {})

        if not l1.get("name_zh"):
            return ""

        return (
            f"INSERT INTO `store` (`id`, `name_zh`, `name_en`, `category_id`, `city_id`, `cover_img`, `seo_desc`, "
            f"`price_range`, `rating`, `review_count`, `ranking_desc`, `cuisine_tags`, "
            f"`michelin_status`, `source_platform`, `data_quality_score`, `is_ai_generated`) VALUES (\n"
            f"  {store_id},\n"
            f"  {format_sql_value(l1.get('name_zh'))},\n"
            f"  {format_sql_value(l1.get('name_en'))},\n"
            f"  {format_sql_value(l1.get('category_id'))},\n"
            f"  {MACAU_CITY_ID},\n"
            f"  {format_sql_value(l1.get('cover_img'))},\n"
            f"  {format_sql_value(l1.get('seo_desc'))},\n"
            f"  {format_sql_value(l2.get('price_range'))},\n"
            f"  {format_sql_value(l2.get('rating', 0.0))},\n"
            f"  {format_sql_value(l2.get('review_count', 0))},\n"
            f"  {format_sql_value(l2.get('ranking_desc'))},\n"
            f"  {format_sql_value(l2.get('cuisine_tags'))},\n"
            f"  {format_sql_value(l2.get('michelin_status', 0))},\n"
            f"  {format_sql_value(l5.get('source_platform'))},\n"
            f"  {format_sql_value(l5.get('data_quality_score', 0.0))},\n"
            f"  {format_sql_value(l5.get('is_ai_generated', True))}\n"
            f");"
        )

    def _generate_store_info(self, store_id: int, data: dict) -> str:
        l1 = data.get("L1_base_and_info", {})
        l2 = data.get("L2_operations", {})
        l5 = data.get("L5_quality_control", {})

        return (
            f"INSERT INTO `store_info` (`store_id`, `category_id`, `district`, `address_zh`, `address_en`, "
            f"`lat`, `lng`, `phone`, `open_hours`, `summary_zh`, `summary_en`, "
            f"`visit_notice`, `signature_items`, `tags`, `category_specific_fields`, "
            f"`subratings`, `features`, `photos_count`, "
            f"`source_platform`, `source_urls`, "
            f"`data_collected_at`, `data_quality_score`, `is_ai_generated`) VALUES (\n"
            f"  {store_id},\n"
            f"  {format_sql_value(l1.get('category_id'))},\n"
            f"  {format_sql_value(l1.get('district'))},\n"
            f"  {format_sql_value(l1.get('address_zh'))},\n"
            f"  {format_sql_value(l1.get('address_en'))},\n"
            f"  {format_sql_value(l1.get('lat'))},\n"
            f"  {format_sql_value(l1.get('lng'))},\n"
            f"  {format_sql_value(l2.get('phone'))},\n"
            f"  {format_sql_value(l2.get('open_hours'))},\n"
            f"  {format_sql_value(l1.get('summary_zh'))},\n"
            f"  {format_sql_value(l1.get('summary_en'))},\n"
            f"  {format_sql_value(l2.get('visit_notice'))},\n"
            f"  {format_sql_value(l2.get('signature_items'))},\n"
            f"  {format_sql_value(l2.get('tags'))},\n"
            f"  {format_sql_value(l2.get('category_specific_fields'))},\n"
            f"  {format_sql_value(l2.get('subratings'))},\n"
            f"  {format_sql_value(l2.get('features'))},\n"
            f"  {format_sql_value(l2.get('photos_count', 0))},\n"
            f"  {format_sql_value(l5.get('source_platform'))},\n"
            f"  {format_sql_value(l5.get('source_urls'))},\n"
            f"  {format_sql_value(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))},\n"
            f"  {format_sql_value(l5.get('data_quality_score'))},\n"
            f"  {format_sql_value(l5.get('is_ai_generated', True))}\n"
            f");"
        )

    def _generate_store_banner(self, store_id: int, data: dict) -> str:
        banners = data.get("sub_tables", {}).get("store_banner", [])
        if not banners:
            return ""

        values = []
        for i, banner in enumerate(banners, 1):
            values.append(
                f"  ({store_id}, {format_sql_value(banner.get('image_url'))}, "
                f"{format_sql_value(banner.get('sort_order', i))}, "
                f"{format_sql_value(banner.get('photo_credit'))})"
            )

        return (
            f"INSERT INTO `store_banner` (`store_id`, `image_url`, `sort_order`, `photo_credit`) VALUES\n"
            + ",\n".join(values)
            + ";"
        )

    def _generate_store_product(self, store_id: int, data: dict) -> str:
        products = data.get("sub_tables", {}).get("store_product", [])
        if not products:
            return ""

        values = []
        for i, product in enumerate(products, 1):
            images = json.dumps(product.get("images", []), ensure_ascii=False) if product.get("images") else None
            values.append(
                f"  ({store_id}, {format_sql_value(product.get('product_name'))}, "
                f"{format_sql_value(product.get('price'))}, "
                f"{format_sql_value(product.get('description'))}, "
                f"{format_sql_value(product.get('currency', 'MOP'))}, "
                f"{format_sql_value(product.get('is_signature', False))}, "
                f"{format_sql_value(product.get('sort_order', i))}, "
                f"{format_sql_value(images)})"
            )

        return (
            f"INSERT INTO `store_product` (`store_id`, `product_name`, `price`, `description`, `currency`, `is_signature`, `sort_order`, `images`) VALUES\n"
            + ",\n".join(values)
            + ";"
        )

    def _generate_store_facility(self, store_id: int, data: dict) -> str:
        facilities = data.get("sub_tables", {}).get("store_facility", [])
        if not facilities:
            return ""

        values = []
        for facility in facilities:
            values.append(
                f"  ({store_id}, {format_sql_value(facility.get('category'))}, "
                f"{format_sql_value(facility.get('facility_name'))}, "
                f"{format_sql_value(facility.get('is_bold', False))}, "
                f"{format_sql_value(facility.get('description'))})"
            )

        return (
            f"INSERT INTO `store_facility` (`store_id`, `category`, `facility_name`, `is_bold`, `description`) VALUES\n"
            + ",\n".join(values)
            + ";"
        )
