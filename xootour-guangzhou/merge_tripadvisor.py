import json, logging, os, re, sqlite3, sys
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TA_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "xootour_guangzhou.db")
XO_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "xootour.db")
SCHEMA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "schema_sqlite.sql")
GUANGZHOU_CITY_ID = 3
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
                tags.extend(ct[:5])
        except (json.JSONDecodeError, TypeError):
            pass
    if michelin_status and int(michelin_status) > 0:
        tags.append("米其林")
    for f in features_list:
        name = f.get("facility_name", "") if isinstance(f, dict) else str(f)
        if name:
            tags.append(name)
    return list(set(tags))[:10]


def init_db():
    conn = sqlite3.connect(TA_DB)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        schema = f.read()
    try:
        conn.executescript(schema)
        conn.commit()
    except Exception as e:
        logger.warning(f"Schema init (may already exist): {e}")
    conn.close()
    logger.info(f"[DB] Schema ready: {TA_DB}")


def step2_migrate_tripadvisor():
    conn = sqlite3.connect(TA_DB)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row

    try:
        conn.execute("SELECT 1 FROM tripadvisor_restaurants LIMIT 1")
    except sqlite3.OperationalError:
        logger.info("No tripadvisor_restaurants table found.")
        conn.close()
        return 0

    rows = conn.execute("SELECT * FROM tripadvisor_restaurants").fetchall()
    logger.info(f"Found {len(rows)} TripAdvisor restaurant records")

    if not rows:
        conn.close()
        return 0

    out = sqlite3.connect(TA_DB)
    out.execute("PRAGMA journal_mode=WAL")
    out.execute("PRAGMA foreign_keys=ON")

    next_id = out.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM store").fetchone()[0]
    count = 0

    for row in rows:
        row = dict(row)
        name_zh = row.get("name", "") or row.get("name_zh", "")
        if not name_zh:
            continue

        name_en = row.get("name_en", "") or ""
        amap_id = row.get("amap_id", "") or ""
        rating = row.get("rating") or 0
        review_count = row.get("reviewsCount") or row.get("review_count") or 0
        ranking_desc = row.get("rankingDesc") or row.get("ranking_desc") or ""
        cover_img = row.get("coverImage") or row.get("cover_img") or ""
        price_detail = row.get("priceDetail") or row.get("price_detail") or ""
        michelin_status = row.get("michelinStatus") or row.get("michelin_status") or 0
        cuisine = row.get("cuisine") or ""
        cuisine_tags = row.get("cuisineTags") or row.get("cuisine_tags") or "[]"
        description = row.get("description") or ""
        location = row.get("location") or ""
        address = row.get("address") or ""
        phone = row.get("phone") or ""
        website = row.get("website") or ""
        open_hours = row.get("openHours") or row.get("open_hours") or ""
        photos_str = row.get("photos") or ""
        features_str = row.get("features") or ""
        district = row.get("district") or ""

        lat, lng = parse_location(location)
        price_range = parse_price(price_detail)
        photos = parse_photos(photos_str)
        features = parse_features(features_str)
        tags = build_tags(cuisine, cuisine_tags, michelin_status, features, description)

        store_id = next_id
        next_id += 1

        out.execute(
            "INSERT OR IGNORE INTO store (id, name_zh, name_en, category_id, city_id, cover_img, seo_desc, "
            "price_range, rating, review_count, ranking_desc, cuisine_tags, michelin_status, "
            "source_platform, data_quality_score, is_ai_generated) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (store_id, name_zh, name_en, DINING_ID, GUANGZHOU_CITY_ID, cover_img,
             f"{name_zh}-广州美食推荐",
             price_range, rating, review_count, ranking_desc,
             json.dumps(tags, ensure_ascii=False), michelin_status,
             "TripAdvisor", 0.6, 0)
        )

        out.execute(
            "INSERT OR IGNORE INTO store_info (store_id, category_id, amap_id, district, address_zh, "
            "lat, lng, phone, website, open_hours, summary_zh, tags, source_platform, "
            "data_quality_score, is_ai_generated) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (store_id, DINING_ID, amap_id, district, address,
             lat, lng, phone, website, open_hours, description,
             json.dumps(tags, ensure_ascii=False), "TripAdvisor", 0.6, 0)
        )

        if photos:
            for i, p in enumerate(photos[:10], 1):
                img_url = p.get("image_url", p) if isinstance(p, dict) else str(p)
                out.execute(
                    "INSERT INTO store_banner (store_id, image_url, sort_order, photo_credit) VALUES (?,?,?,?)",
                    (store_id, img_url, i, "TripAdvisor")
                )

        if features:
            for f in features[:10]:
                fname = f.get("facility_name", "") if isinstance(f, dict) else str(f)
                fdesc = f.get("description", "") if isinstance(f, dict) else ""
                if fname:
                    out.execute(
                        "INSERT INTO store_facility (store_id, category, facility_name, is_bold, description) "
                        "VALUES (?,?,?,?,?)",
                        (store_id, "服务设施", fname, 0, fdesc)
                    )

        count += 1

    out.commit()
    out.close()
    conn.close()
    logger.info(f"  Migrated {count} TripAdvisor restaurants")
    return count


def main():
    logger.info("=" * 60)
    logger.info("Guangzhou TripAdvisor / XOOTOUR Database Merge")
    logger.info("=" * 60)

    init_db()

    migrated = step2_migrate_tripadvisor()

    if migrated == 0:
        logger.info("No TripAdvisor data found. Run scraper pipeline to collect data:")
        logger.info("  python -m scraper              # Tourist spots")
        logger.info("  python -m scraper.store_main   # Store data (5 categories)")
    else:
        logger.info(f"Merge complete. {migrated} records imported.")

    # Final stats
    conn = sqlite3.connect(TA_DB)
    total = conn.execute("SELECT COUNT(*) FROM store").fetchone()[0]
    logger.info(f"Total stores: {total}")
    for cat_id, cat_name in [(1, "美食"), (2, "酒店"), (3, "景点"), (4, "购物"), (5, "娱乐")]:
        cnt = conn.execute("SELECT COUNT(*) FROM store WHERE category_id=?", (cat_id,)).fetchone()[0]
        logger.info(f"  {cat_name}: {cnt}")
    conn.close()


if __name__ == "__main__":
    main()
