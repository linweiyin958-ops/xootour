import json, logging, os, re, sqlite3, sys
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TA_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "xootour_changsha.db")
SCHEMA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "schema_sqlite.sql")
CHANGSHA_CITY_ID = 2
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
    logger.info("[Step 1] Initializing Changsha database schema...")
    conn = sqlite3.connect(TA_DB)
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    conn.executescript(schema_sql)
    conn.commit()
    conn.close()
    logger.info("  Schema initialized.")


def main():
    logger.info("=" * 60)
    logger.info("Changsha xootour Database Setup")
    logger.info("=" * 60)

    init_db()

    conn = sqlite3.connect(TA_DB)
    total = conn.execute("SELECT COUNT(*) FROM store").fetchone()[0]
    logger.info(f"Total stores: {total}")
    for cat_id, cat_name in [(1, "美食"), (2, "酒店"), (3, "景点"), (4, "购物"), (5, "娱乐")]:
        cnt = conn.execute("SELECT COUNT(*) FROM store WHERE category_id=?", (cat_id,)).fetchone()[0]
        logger.info(f"  {cat_name}: {cnt}")
    conn.close()

    logger.info("\nRun the store scraper pipeline to collect data:")
    logger.info("  python -m scraper.store_main   # Store data (5 categories)")


if __name__ == "__main__":
    main()
