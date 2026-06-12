import json, logging, os, re, sqlite3, sys
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TA_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "xootour_shenzhen.db")
XO_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "xootour.db")
SCHEMA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "schema_sqlite.sql")
SHENZHEN_CITY_ID = 2
DINING_ID = 1


def _to_scalar(val, default=None):
    if val is None:
        return default
    if isinstance(val, (str, int, float, bool)):
        return val
    if isinstance(val, (list, dict)):
        return json.dumps(val, ensure_ascii=False)
    return str(val)


def parse_location(loc):
    if not loc:
        return None, None
    parts = str(loc).split(",")
    if len(parts) >= 2:
        try:
            return float(parts[1]), float(parts[0])
        except ValueError:
            pass
    return None, None


def parse_price(price_detail):
    if not price_detail:
        return ""
    level = len(str(price_detail).strip())
    return {1: "平价", 2: "中等", 3: "高档", 4: "奢华"}.get(level, str(price_detail))


def parse_photos(photos_str):
    if not photos_str:
        return []
    try:
        data = json.loads(photos_str)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("data", data.get("photos", []))
    except (json.JSONDecodeError, TypeError):
        pass
    urls = re.findall(r'https?://[^\s,"\'()]+\.(?:jpg|jpeg|png|webp)', str(photos_str))
    return [{"image_url": u} for u in urls[:20]]


def parse_features(features_str):
    if not features_str:
        return []
    try:
        data = json.loads(features_str)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [{"facility_name": k, "description": str(v)} for k, v in data.items()]
    except (json.JSONDecodeError, TypeError):
        pass
    return [{"facility_name": f.strip()} for f in str(features_str).split(",") if f.strip()]


def build_tags(cuisine, cuisine_tags, michelin_status, features_list, description):
    tags = []
    if cuisine:
        for c in cuisine.split(","):
            c = c.strip()
            if c:
                tags.append(c)
    if cuisine_tags:
        try:
            ct = json.loads(cuisine_tags) if isinstance(cuisine_tags, str) else cuisine_tags
            if isinstance(ct, list):
                for t in ct:
                    t = t.strip() if isinstance(t, str) else str(t)
                    if t and t not in tags:
                        tags.append(t)
        except (json.JSONDecodeError, TypeError):
            pass
    if michelin_status == 1:
        tags.append("米其林餐厅")
    if features_list:
        text = json.dumps(features_list, ensure_ascii=False).lower()
        if "english" in text or "english menu" in text:
            tags.append("有英文菜单")
        if "credit card" in text or "visa" in text or "mastercard" in text:
            tags.append("可刷外卡")
        if "wheelchair" in text or "accessible" in text:
            tags.append("无障碍设施")
        if "wifi" in text or "free wifi" in text:
            tags.append("有WiFi")
    tags = list(set(tags))
    return tags[:10]


def init_db():
    logger.info("[Step 1] Initializing Shenzhen database schema...")
    conn = sqlite3.connect(TA_DB)
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    conn.executescript(schema_sql)
    conn.commit()
    conn.close()
    logger.info("  Schema initialized.")


def step2_migrate_tripadvisor():
    conn = sqlite3.connect(XO_DB)
    has_tripadvisor = False
    try:
        conn.execute("SELECT 1 FROM tripadvisor_restaurants LIMIT 1")
        has_tripadvisor = True
    except sqlite3.OperationalError:
        pass

    if not has_tripadvisor:
        conn.close()
        return 0

    logger.info("[Step 2] Migrating TripAdvisor restaurants...")

    try:
        ta_rows = conn.execute(
            "SELECT locationId, name, rating, reviewsCount, rankingDesc, "
            "priceDetail, cuisineDesc, photosData, featuresData, "
            "michelinStatus, location "
            "FROM tripadvisor_restaurants"
        ).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return 0

    out = sqlite3.connect(TA_DB)
    out.execute("PRAGMA journal_mode=WAL")
    out.execute("PRAGMA foreign_keys=ON")

    seq_sql = "SELECT COALESCE(MAX(id), 0) + 1 FROM store"
    store_id = out.execute(seq_sql).fetchone()[0]
    count = 0

    for row in ta_rows:
        loc_id, name, rating, rev_cnt, rank_desc, price_d, cuisine, photos_d, features_d, michelin, loc = row

        if not name:
            continue

        lat, lng = parse_location(loc)
        price_range = parse_price(price_d)
        photos = parse_photos(photos_d)
        features = parse_features(features_d)
        tags = build_tags(cuisine, "", michelin, features, "")

        try:
            out.execute(
                "INSERT OR IGNORE INTO store (id, name_zh, name_en, category_id, city_id, cover_img, seo_desc, "
                "price_range, rating, review_count, ranking_desc, cuisine_tags, "
                "michelin_status, source_platform, data_quality_score, is_ai_generated) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (store_id, name, name, DINING_ID, SHENZHEN_CITY_ID,
                 photos[0].get("image_url") if photos else "",
                 f"{name} Shenzhen dining guide",
                 price_range, rating or 0.0, rev_cnt or 0, rank_desc or "",
                 cuisine or "", michelin or 0, "TripAdvisor", 0.67, 0)
            )
        except sqlite3.IntegrityError:
            continue

        out.execute(
            "INSERT OR REPLACE INTO store_info (store_id, category_id, amap_id, district, lat, lng, "
            "summary_zh, summary_en, visit_notice, signature_items, tags, "
            "subratings, features, photos_count, source_platform, source_urls, "
            "data_collected_at, data_quality_score, is_ai_generated) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (store_id, DINING_ID, loc_id, "", lat, lng,
             "", "", "", "[]",
             _to_scalar(tags),
             "[]", _to_scalar(features), len(photos),
             "TripAdvisor", "[]",
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 0.67, 0)
        )

        for i, photo in enumerate(photos[:20], 1):
            out.execute(
                "INSERT INTO store_banner (store_id, image_url, sort_order, caption, photo_credit) VALUES (?,?,?,?,?)",
                (store_id, photo.get("image_url", ""), i, photo.get("caption", ""), "TripAdvisor")
            )

        for fac in features:
            out.execute(
                "INSERT INTO store_facility (store_id, category, facility_name, is_bold, description) VALUES (?,?,?,?,?)",
                (store_id, "", fac.get("facility_name", ""),
                 1 if fac.get("is_bold") else 0, fac.get("description", ""))
            )

        store_id += 1
        count += 1

    out.commit()
    out.close()
    conn.close()
    logger.info(f"  Migrated {count} TripAdvisor restaurants")
    return count


def main():
    logger.info("=" * 60)
    logger.info("Shenzhen TripAdvisor / XOOTOUR Database Merge")
    logger.info("=" * 60)

    init_db()

    migrated = step2_migrate_tripadvisor()

    if migrated == 0:
        logger.info("No TripAdvisor data found. Run scraper pipeline to collect data:")
        logger.info("  python -m scraper              # Tourist spots")
        logger.info("  python -m scraper.store_main   # Store data (5 categories)")
    else:
        logger.info(f"Merge complete. {migrated} records imported.")

    conn = sqlite3.connect(TA_DB)
    total = conn.execute("SELECT COUNT(*) FROM store").fetchone()[0]
    logger.info(f"Total stores: {total}")
    for cat_id, cat_name in [(1, "美食"), (2, "酒店"), (3, "景点"), (4, "购物"), (5, "娱乐")]:
        cnt = conn.execute("SELECT COUNT(*) FROM store WHERE category_id=?", (cat_id,)).fetchone()[0]
        logger.info(f"  {cat_name}: {cnt}")
    conn.close()


if __name__ == "__main__":
    main()
