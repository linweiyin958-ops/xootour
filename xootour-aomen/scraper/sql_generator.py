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


class SQLGenerator:
    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = output_dir or OUTPUT_DIR
        os.makedirs(self.output_dir, exist_ok=True)

    def generate(self, spot_id: int, data: dict) -> str:
        statements = []

        statements.append(self._generate_tour_spot(spot_id, data))
        statements.append(self._generate_tour_spot_info(spot_id, data))
        statements.append(self._generate_tour_spot_banner(spot_id, data))
        statements.append(self._generate_tour_spot_feature(spot_id, data))
        statements.append(self._generate_tour_spot_route(spot_id, data))
        statements.append(self._generate_tour_spot_facility(spot_id, data))
        statements.append(self._generate_tour_spot_package(spot_id, data))

        sql_content = "\n\n".join(s for s in statements if s)

        filename = f"spot_{spot_id}_{data.get('L1_base_and_info', {}).get('name_zh', 'unknown')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(sql_content)

        logger.info(f"[SQL] Generated: {filepath}")
        return filepath

    def _generate_tour_spot(self, spot_id: int, data: dict) -> str:
        l1 = data.get("L1_base_and_info", {})
        l2 = data.get("L2_operations", {})

        if not l1.get("name_zh"):
            return ""

        return (
            f"INSERT INTO `tour_spot` (`id`, `name`, `subtitle`, `city_id`, `cover_img`, `seo_desc`, `base_price`, `rating`) VALUES (\n"
            f"  {spot_id},\n"
            f"  {format_sql_value(l1.get('name_zh'))},\n"
            f"  {format_sql_value(l1.get('name_en'))},\n"
            f"  {MACAU_CITY_ID},\n"
            f"  {format_sql_value(l1.get('cover_img'))},\n"
            f"  {format_sql_value(l1.get('seo_desc'))},\n"
            f"  {format_sql_value(l2.get('base_price', 0.00))},\n"
            f"  {format_sql_value(l2.get('rating', 0.0))}\n"
            f");"
        )

    def _generate_tour_spot_info(self, spot_id: int, data: dict) -> str:
        l1 = data.get("L1_base_and_info", {})
        l2 = data.get("L2_operations", {})
        l3 = data.get("L3_ugc_trends", {})
        l5 = data.get("L5_quality_control", {})

        return (
            f"INSERT INTO `tour_spot_info` (`spot_id`, `district`, `address_zh`, `address_en`, `lat`, `lng`, "
            f"`summary_zh`, `summary_en`, `open_hours`, `transportation`, `visit_notice`, "
            f"`best_visit_season`, `photo_spots`, `crowd_tags`, "
            f"`source_platform`, `source_note_ids`, `data_collected_at`, `data_quality_score`, `is_ai_generated`) VALUES (\n"
            f"  {spot_id},\n"
            f"  {format_sql_value(l1.get('district'))},\n"
            f"  {format_sql_value(l1.get('address_zh'))},\n"
            f"  {format_sql_value(l1.get('address_en'))},\n"
            f"  {format_sql_value(l1.get('lat'))},\n"
            f"  {format_sql_value(l1.get('lng'))},\n"
            f"  {format_sql_value(l1.get('summary_zh'))},\n"
            f"  {format_sql_value(l1.get('summary_en'))},\n"
            f"  {format_sql_value(l2.get('open_hours'))},\n"
            f"  {format_sql_value(l2.get('transportation'))},\n"
            f"  {format_sql_value(l2.get('visit_notice'))},\n"
            f"  {format_sql_value(l3.get('best_visit_season'))},\n"
            f"  {format_sql_value(l3.get('photo_spots'))},\n"
            f"  {format_sql_value(l3.get('crowd_tags'))},\n"
            f"  {format_sql_value(l5.get('source_platform'))},\n"
            f"  {format_sql_value(l5.get('source_note_ids'))},\n"
            f"  {format_sql_value(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))},\n"
            f"  {format_sql_value(l5.get('data_quality_score'))},\n"
            f"  {format_sql_value(l5.get('is_ai_generated', True))}\n"
            f");"
        )

    def _generate_tour_spot_banner(self, spot_id: int, data: dict) -> str:
        banners = data.get("sub_tables", {}).get("tour_spot_banner", [])
        if not banners:
            return ""

        values = []
        for i, banner in enumerate(banners, 1):
            values.append(
                f"  ({spot_id}, {format_sql_value(banner.get('image_url'))}, "
                f"{format_sql_value(banner.get('sort_order', i))}, "
                f"{format_sql_value(banner.get('photo_credit'))})"
            )

        return (
            f"INSERT INTO `tour_spot_banner` (`spot_id`, `image_url`, `sort_order`, `photo_credit`) VALUES\n"
            + ",\n".join(values)
            + ";"
        )

    def _generate_tour_spot_feature(self, spot_id: int, data: dict) -> str:
        features = data.get("sub_tables", {}).get("tour_spot_feature", [])
        if not features:
            return ""

        values = []
        for feature in features:
            values.append(
                f"  ({spot_id}, {format_sql_value(feature.get('title'))}, "
                f"{format_sql_value(feature.get('description'))})"
            )

        return (
            f"INSERT INTO `tour_spot_feature` (`spot_id`, `title`, `description`) VALUES\n"
            + ",\n".join(values)
            + ";"
        )

    def _generate_tour_spot_route(self, spot_id: int, data: dict) -> str:
        routes = data.get("sub_tables", {}).get("tour_spot_route", [])
        if not routes:
            return ""

        values = []
        for route in routes:
            values.append(
                f"  ({spot_id}, {format_sql_value(route.get('route_name'))}, "
                f"{format_sql_value(route.get('duration_hours'))}, "
                f"{format_sql_value(route.get('route_nodes'))}, "
                f"{format_sql_value(route.get('description'))})"
            )

        return (
            f"INSERT INTO `tour_spot_route` (`spot_id`, `route_name`, `duration_hours`, `route_nodes`, `description`) VALUES\n"
            + ",\n".join(values)
            + ";"
        )

    def _generate_tour_spot_facility(self, spot_id: int, data: dict) -> str:
        facilities = data.get("sub_tables", {}).get("tour_spot_facility", [])
        if not facilities:
            return ""

        values = []
        for facility in facilities:
            values.append(
                f"  ({spot_id}, {format_sql_value(facility.get('facility_name'))}, "
                f"{format_sql_value(facility.get('is_bold', False))}, "
                f"{format_sql_value(facility.get('description'))})"
            )

        return (
            f"INSERT INTO `tour_spot_facility` (`spot_id`, `facility_name`, `is_bold`, `description`) VALUES\n"
            + ",\n".join(values)
            + ";"
        )

    def _generate_tour_spot_package(self, spot_id: int, data: dict) -> str:
        packages = data.get("sub_tables", {}).get("tour_spot_package", [])
        if not packages:
            return ""

        values = []
        for package in packages:
            values.append(
                f"  ({spot_id}, {format_sql_value(package.get('package_name'))}, "
                f"{format_sql_value(package.get('price'))}, "
                f"{format_sql_value(package.get('description'))}, "
                f"{format_sql_value(package.get('currency', 'MOP'))})"
            )

        return (
            f"INSERT INTO `tour_spot_package` (`spot_id`, `package_name`, `price`, `description`, `currency`) VALUES\n"
            + ",\n".join(values)
            + ";"
        )
