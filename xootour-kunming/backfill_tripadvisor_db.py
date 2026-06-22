"""Backfill missing fields in tripadvisor-bj.db (tripadvisor_restaurants table).

Phases:
  1. Amap geocoding (address -> lat/lng)
  1b.Nominatim fallback geocoding
  2. Amap POI search (name -> amap_id, phone, etc.)
  3. Parse restaurantHours JSON -> businessHours
  4. LLM supplement (Qwen -> description, features, subratings)
  5. TripAdvisor scrape (h5Url -> lat/lng)

Usage:
  py backfill_tripadvisor_db.py --phase 1           # geocoding only
  py backfill_tripadvisor_db.py --phase all         # all phases
  py backfill_tripadvisor_db.py --dry-run           # preview only
  py backfill_tripadvisor_db.py --limit 100          # limit processing
"""

import argparse
import json
import logging
import os
import random
import re
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from threading import Lock

import requests
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scraper.config import AMAP_API_KEY
from scraper.ai_extractor import FreeLLMExtractor

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "_backfill_tripadvisor.log")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

AMAP_GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"
AMAP_TEXT_SEARCH_URL = "https://restapi.amap.com/v3/place/text"
AMAP_REGEO_URL = "https://restapi.amap.com/v3/geocode/regeo"
LOWER_CONCURRENCY_THRESHOLD = 500

# ─────────────────── helpers ───────────────────

def _delay(lo=0.3, hi=0.8):
    time.sleep(random.uniform(lo, hi))


def amap_geocode(address, city="北京"):
    if not AMAP_API_KEY:
        return None
    params = {"key": AMAP_API_KEY, "address": address, "city": city, "output": "JSON"}
    _delay(0.5, 1.2)
    try:
        resp = requests.get(AMAP_GEOCODE_URL, params=params, timeout=10)
        data = resp.json()
        if data.get("status") == "1" and data.get("geocodes"):
            geo = data["geocodes"][0]
            loc = geo.get("location", "").split(",")
            return {
                "lng": float(loc[0]) if len(loc) >= 2 else None,
                "lat": float(loc[1]) if len(loc) >= 2 else None,
                "address_zh": geo.get("formatted_address", ""),
                "district": geo.get("district", ""),
                "adcode": geo.get("adcode", ""),
            }
    except Exception as e:
        logger.warning(f"[Geocode] Error for '{address}': {e}")
    return None


def amap_text_search(name, city="北京"):
    if not AMAP_API_KEY:
        return None
    params = {"key": AMAP_API_KEY, "keywords": name, "city": city, "citylimit": "true",
              "output": "JSON", "offset": 1, "page": 1}
    _delay(0.5, 1.5)
    try:
        resp = requests.get(AMAP_TEXT_SEARCH_URL, params=params, timeout=10)
        data = resp.json()
        if data.get("status") == "1" and data.get("pois"):
            poi = data["pois"][0]
            loc = poi.get("location", "").split(",")
            return {
                "lng": float(loc[0]) if len(loc) >= 2 else None,
                "lat": float(loc[1]) if len(loc) >= 2 else None,
                "amap_id": poi.get("id", ""),
                "amap_name": poi.get("name", ""),
                "amap_address": poi.get("address", ""),
                "amap_type": poi.get("type", ""),
                "phone": "|".join(poi.get("tel", [])) if isinstance(poi.get("tel"), list) else poi.get("tel", ""),
            }
    except Exception as e:
        logger.warning(f"[POI Search] Error for '{name}': {e}")
    return None


def amap_regeocode(lng, lat):
    if not AMAP_API_KEY:
        return None
    params = {"key": AMAP_API_KEY, "location": f"{lng},{lat}", "output": "JSON", "extensions": "base"}
    _delay(0.3, 0.6)
    try:
        resp = requests.get(AMAP_REGEO_URL, params=params, timeout=8)
        data = resp.json()
        if data.get("status") == "1" and data.get("regeocode"):
            comp = data["regeocode"].get("addressComponent", {})
            return comp.get("district", "") or None
    except Exception:
        pass
    return None


def parse_business_hours(restaurant_hours_json):
    if not restaurant_hours_json:
        return None
    try:
        hours_list = json.loads(restaurant_hours_json)
        if not isinstance(hours_list, list) or not hours_list:
            return None
        day_groups = {}
        for item in hours_list:
            wd = item.get("weekDay", "")
            tr = item.get("openTimeRange", "").strip()
            if not wd or not tr:
                continue
            key = tr
            if key not in day_groups:
                day_groups[key] = []
            day_groups[key].append(wd)

        if not day_groups:
            return None

        parts = []
        day_order = ["星期一", "星期�?, "星期�?, "星期�?, "星期�?, "星期�?, "星期�?]
        for time_range, days in sorted(day_groups.items(), key=lambda x: len(x[1]), reverse=True):
            ordered = [d for d in day_order if d in days]
            if len(ordered) == 7:
                parts.append(f"每日 {time_range}")
            elif len(ordered) >= 2:
                parts.append(f"{ordered[0][-2:] if len(ordered[0]) >= 3 else ordered[0]}至{ordered[-1][-2:] if len(ordered[-1]) >= 3 else ordered[-1]} {time_range}")
            else:
                for d in ordered:
                    parts.append(f"{d[-2:] if len(d) >= 3 else d} {time_range}")

        return "; ".join(parts)
    except (json.JSONDecodeError, TypeError):
        pass
    return None


# ─────────────────── phase implementations ───────────────────

def _open_db(db_path, dry_run=False):
    """Open DB connection, read-only if dry-run."""
    if dry_run:
        uri = db_path.replace("\\", "/")
        conn = sqlite3.connect(f"file:{uri}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=OFF")
    conn.row_factory = sqlite3.Row
    return conn


def phase1_geocode(db_path, limit=0, dry_run=False):
    """Geocode addresses via Amap API to get lat/lng."""
    conn = _open_db(db_path, dry_run)

    query = (
        "SELECT locationId, name, address FROM tripadvisor_restaurants "
        "WHERE address IS NOT NULL AND address != '' "
        "AND (latitude IS NULL OR latitude = '' OR latitude = 0.0 OR latitude = '0')"
    )
    if limit > 0:
        query += f" LIMIT {limit}"
    rows = conn.execute(query).fetchall()
    total = len(rows)
    logger.info(f"[Phase 1] Geocoding: {total} records")

    if total == 0:
        logger.info("[Phase 1] All records already have coordinates.")
        conn.close()
        return 0

    if dry_run:
        logger.info("[Phase 1] DRY RUN - showing first 10")
        for r in rows[:10]:
            logger.info(f"  {r['locationId']} | {r['name'][:30]} | {r['address'][:40]}")
        conn.close()
        return 0

    updated = 0
    failed = 0
    write_lock = Lock()
    updates = []

    def process(row):
        loc_id = row["locationId"]
        name = row["name"]
        address = row["address"]
        # Clean address - remove English parts after Chinese
        clean_addr = address
        for sep in [" Chaoyang", " Dongcheng", " Xicheng", " Haidian", " Fengtai",
                      " Shijingshan", " Tongzhou", " Daxing", " Shunyi", " Changping",
                      " Fangshan", " Mentougou", " Pinggu", " Huairou", " Miyun", " Yanqing"]:
            idx = clean_addr.find(sep)
            if idx > 0:
                clean_addr = clean_addr[:idx]
                break
        clean_addr = clean_addr.replace("中国 北京�?", "").replace("100020 ", "").strip()
        result = amap_geocode(clean_addr)
        return loc_id, name, result

    workers = min(10, total)
    if total < LOWER_CONCURRENCY_THRESHOLD:
        workers = min(5, total)
    logger.info(f"[Phase 1] Using {workers} workers")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process, row): row for row in rows}
        for i, future in enumerate(as_completed(futures), 1):
            loc_id, name, result = future.result()
            if result and result.get("lat") and result.get("lng"):
                with write_lock:
                    updates.append((result["lng"], result["lat"], loc_id))
                    updated += 1
            else:
                failed += 1
                if failed <= 5:
                    logger.warning(f"  [FAIL] {loc_id} | {name[:30]}")
            if i % 200 == 0:
                with write_lock:
                    conn.executemany(
                        "UPDATE tripadvisor_restaurants SET longitude=?, latitude=? WHERE locationId=?",
                        updates,
                    )
                    conn.commit()
                    updates.clear()
                logger.info(f"  [Phase 1] Progress: {i}/{total} (ok={updated}, fail={failed})")

    if updates:
        conn.executemany(
            "UPDATE tripadvisor_restaurants SET longitude=?, latitude=? WHERE locationId=?",
            updates,
        )
        conn.commit()

    logger.info(f"[Phase 1] Complete: {updated} updated, {failed} failed")
    conn.close()
    return updated


def phase1b_nominatim(db_path, limit=0, dry_run=False):
    """Geocode remaining records via Nominatim (OpenStreetMap). Slow but free."""
    conn = _open_db(db_path, dry_run)
    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

    query = (
        "SELECT locationId, name, address FROM tripadvisor_restaurants "
        "WHERE (latitude IS NULL OR latitude = '' OR latitude = '0' OR latitude = 0.0) "
        "AND address IS NOT NULL AND address != ''"
    )
    if limit > 0:
        query += f" LIMIT {limit}"
    rows = conn.execute(query).fetchall()
    total = len(rows)
    logger.info(f"[Phase 1b] Nominatim: {total} records")

    if total == 0:
        logger.info("[Phase 1b] All records already have coordinates.")
        conn.close()
        return 0

    if dry_run:
        logger.info("[Phase 1b] DRY RUN - showing first 10")
        for r in rows[:10]:
            logger.info(f"  {r['locationId']} | {r['name'][:30]}")
        conn.close()
        return 0

    updated = 0
    failed = 0

    def nominatim_geocode(name, address):
        time.sleep(random.uniform(1.0, 1.5))
        clean_addr = address
        for sep in [" Chaoyang", " Dongcheng", " Xicheng", " Haidian", " Fengtai",
                      " Shijingshan", " Tongzhou", " Daxing", " Shunyi", " Changping",
                      " Fangshan", " Mentougou", " Pinggu", " Huairou", " Miyun", " Yanqing"]:
            idx = clean_addr.find(sep)
            if idx > 0:
                clean_addr = clean_addr[:idx]
                break
        clean_addr = clean_addr.replace("中国 北京�?", "").replace("100020 ", "").replace("100600 ", "").strip()
        q = f"{name}, {clean_addr}, Kunming, China"
        try:
            resp = requests.get(NOMINATIM_URL, params={"q": q, "format": "json", "limit": 1},
                              headers={"User-Agent": "xootour-scraper/1.0"}, timeout=15)
            data = resp.json()
            if data:
                return {
                    "lat": float(data[0].get("lat", 0)),
                    "lng": float(data[0].get("lon", 0)),
                }
        except Exception:
            pass
        return None

    for i, row in enumerate(rows, 1):
        result = nominatim_geocode(row["name"], row["address"] or "")
        if result and result.get("lat") and result.get("lng"):
            conn.execute(
                "UPDATE tripadvisor_restaurants SET latitude=?, longitude=? WHERE locationId=?",
                (result["lat"], result["lng"], row["locationId"]),
            )
            conn.commit()
            updated += 1
        else:
            failed += 1
            if failed <= 5:
                logger.warning(f"  [FAIL] {row['locationId']} | {row['name'][:30]}")
        if i % 100 == 0:
            logger.info(f"  [Phase 1b] Progress: {i}/{total} (ok={updated}, fail={failed})")

    logger.info(f"[Phase 1b] Complete: {updated} updated, {failed} failed")
    conn.close()
    return updated


def phase2_poi_search(db_path, limit=0, dry_run=False):
    """Search Amap POI by restaurant name to get amap_id, phone, etc."""
    conn = _open_db(db_path, dry_run)

    query = (
        "SELECT locationId, name, latitude, longitude FROM tripadvisor_restaurants "
        "WHERE (amap_id IS NULL OR amap_id = '') "
        "AND name IS NOT NULL AND name != '' "
        "ORDER BY locationId"
    )
    if limit > 0:
        query += f" LIMIT {limit}"
    rows = conn.execute(query).fetchall()
    total = len(rows)
    logger.info(f"[Phase 2] POI Search: {total} records")

    if total == 0:
        logger.info("[Phase 2] All records already have amap data.")
        conn.close()
        return 0

    if dry_run:
        logger.info("[Phase 2] DRY RUN - showing first 10")
        for r in rows[:10]:
            logger.info(f"  {r['locationId']} | {r['name'][:30]}")
        conn.close()
        return 0

    updated = 0
    failed = 0
    write_lock = Lock()
    updates = []

    def process(row):
        loc_id = row["locationId"]
        name = row["name"]
        # Clean name for POI search - remove branch info in parens for better match
        search_name = name
        result = amap_text_search(search_name)
        if not result:
            # Try without parenthetical
            if "(" in name:
                search_name = name.split("(")[0].strip()
                result = amap_text_search(search_name)
        return loc_id, name, result

    workers = min(8, total)
    if total < LOWER_CONCURRENCY_THRESHOLD:
        workers = min(4, total)
    logger.info(f"[Phase 2] Using {workers} workers")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process, row): row for row in rows}
        for i, future in enumerate(as_completed(futures), 1):
            loc_id, name, result = future.result()
            if result and result.get("amap_id"):
                with write_lock:
                    updates.append((
                        result.get("amap_id", ""),
                        result.get("amap_name", ""),
                        result.get("amap_address", ""),
                        result.get("amap_type", ""),
                        result.get("phone", ""),
                        # Also fill lat/lng if not already set from phase 1
                        result.get("lng"),
                        result.get("lat"),
                        loc_id,
                    ))
                    updated += 1
            else:
                failed += 1
                if failed <= 5:
                    logger.warning(f"  [FAIL] {loc_id} | {name[:30]}")
            if i % 200 == 0:
                with write_lock:
                    conn.executemany(
                        "UPDATE tripadvisor_restaurants SET amap_id=?, amap_name=?, amap_address=?, "
                        "amap_type=?, phone=?, longitude=?, latitude=? WHERE locationId=?",
                        [(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]) for r in updates],
                    )
                    conn.commit()
                    updates.clear()
                logger.info(f"  [Phase 2] Progress: {i}/{total} (ok={updated}, fail={failed})")

    if updates:
        conn.executemany(
            "UPDATE tripadvisor_restaurants SET amap_id=?, amap_name=?, amap_address=?, "
            "amap_type=?, phone=?, longitude=?, latitude=? WHERE locationId=?",
            [(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]) for r in updates],
        )
        conn.commit()

    logger.info(f"[Phase 2] Complete: {updated} updated, {failed} failed")
    conn.close()
    return updated


def phase3_business_hours(db_path, limit=0, dry_run=False):
    """Parse restaurantHours JSON into businessHours."""
    conn = _open_db(db_path, dry_run)

    query = (
        "SELECT locationId, name, restaurantHours FROM tripadvisor_restaurants "
        "WHERE restaurantHours IS NOT NULL AND restaurantHours != '' "
        "AND (businessHours IS NULL OR businessHours = '')"
    )
    if limit > 0:
        query += f" LIMIT {limit}"
    rows = conn.execute(query).fetchall()
    total = len(rows)
    logger.info(f"[Phase 3] Business Hours: {total} records")

    if total == 0:
        logger.info("[Phase 3] All records already have business hours.")
        conn.close()
        return 0

    if dry_run:
        logger.info("[Phase 3] DRY RUN - showing first 10")
        for r in rows[:10]:
            parsed = parse_business_hours(r["restaurantHours"])
            logger.info(f"  {r['locationId']} | {r['name'][:30]} | {r['restaurantHours'][:60]}... �?{parsed}")
        conn.close()
        return 0

    updated = 0
    updates = []
    for row in rows:
        parsed = parse_business_hours(row["restaurantHours"])
        if parsed:
            updates.append((parsed, row["locationId"]))
            updated += 1

    if updates:
        conn.executemany(
            "UPDATE tripadvisor_restaurants SET businessHours=? WHERE locationId=?",
            updates,
        )
        conn.commit()

    logger.info(f"[Phase 3] Complete: {updated} updated")
    conn.close()
    return updated


def phase4_llm_supplement(db_path, limit=0, dry_run=False, workers=3):
    """Use LLM to supplement missing description, features, subratings."""
    conn = _open_db(db_path, dry_run)

    query = (
        "SELECT locationId, name, ename, cuisine, cuisineTags, priceDetail, rating, "
        "description, features, subratings, address "
        "FROM tripadvisor_restaurants "
        "WHERE (description IS NULL OR description = '') "
        "   OR (features IS NULL OR features = '') "
        "   OR (subratings IS NULL OR subratings = '') "
        "ORDER BY locationId"
    )
    if limit > 0:
        query += f" LIMIT {limit}"
    rows = conn.execute(query).fetchall()
    total = len(rows)
    logger.info(f"[Phase 4] LLM Supplement: {total} records")

    if total == 0:
        logger.info("[Phase 4] All records already have full data.")
        conn.close()
        return 0

    if dry_run:
        logger.info("[Phase 4] DRY RUN - showing first 5")
        for r in rows[:5]:
            missing = []
            if not r["description"]:
                missing.append("description")
            if not r["features"]:
                missing.append("features")
            if not r["subratings"]:
                missing.append("subratings")
            logger.info(f"  {r['locationId']} | {r['name'][:30]} | need: {missing}")
        conn.close()
        return 0

    # Build prompt template - target only missing fields
    llm = FreeLLMExtractor()
    if not llm.client:
        logger.error("[Phase 4] LLM client not initialized. Check QWEN_API_KEY in .env")
        conn.close()
        return 0

    llm_ok = 0
    llm_fail = 0
    write_lock = Lock()

    def build_prompt(row):
        row = dict(row)
        parts = []
        parts.append("请为以下北京餐厅补充信息�?)
        parts.append(f"餐厅名称：{row['name']}")
        if row.get("ename"):
            parts.append(f"英文名：{row['ename']}")
        if row.get("cuisine"):
            parts.append(f"菜系：{row['cuisine']}")
        if row.get("priceDetail"):
            parts.append(f"价格等级：{row['priceDetail']}")
        if row.get("rating"):
            parts.append(f"评分：{row['rating']}/5.0")
        if row.get("address"):
            addr = row["address"] or ""
            if len(addr) > 200:
                addr = addr[:200]
            parts.append(f"地址：{addr}")

        needs = []
        if not row.get("description"):
            needs.append("description (简�?特色介绍, 80-150字中�?")
        if not row.get("features"):
            needs.append("features (设施特点, 逗号分隔的中文列�? 如：免费WiFi,可预�?有包间等)")
        if not row.get("subratings"):
            needs.append("subratings (细项评分, JSON数组中文, 如：[{\"category\":\"食物\",\"rating\":4.5},{\"category\":\"服务\",\"rating\":4.0}])")

        parts.append(f"\n请补充以下缺失字段：{'�?.join(needs)}")
        parts.append("\n请严格按以下JSON格式输出，只输出需要补充的字段：{")
        if not row.get("description"):
            parts.append('  "description": "简介内�?,')
        if not row.get("features"):
            parts.append('  "features": "设施1,设施2,设施3",')
        if not row.get("subratings"):
            parts.append('  "subratings": [{"category": "分类", "rating": 评分}],')
        parts.append("}")
        return "\n".join(parts)

    system_prompt = "你是一位专业的北京餐厅数据补充专家。只输出JSON，不要其他内容�?

    def process(row):
        try:
            prompt = build_prompt(row)
            response = llm._call_llm(system_prompt, prompt)
            return dict(row), response
        except Exception as e:
            logger.error(f"  [LLM] Error for {row['locationId']}: {e}")
            return dict(row), None

    def write_to_db(row, result):
        desc = result.get("description", "") if result else ""
        features = result.get("features", "") if result else ""
        subratings = result.get("subratings", "") if result else ""

        if isinstance(subratings, (list, dict)):
            subratings = json.dumps(subratings, ensure_ascii=False)
        if isinstance(features, (list, dict)):
            features = json.dumps(features, ensure_ascii=False)

        loc_id = row["locationId"]
        local_conn = sqlite3.connect(db_path)
        try:
            current = local_conn.execute(
                "SELECT description, features, subratings FROM tripadvisor_restaurants WHERE locationId=?",
                (loc_id,)
            ).fetchone()
            if not current:
                return False

            fields = []
            params = []
            if desc and (not current[0]):
                fields.append("description=?")
                params.append(desc)
            if features and (not current[1]):
                fields.append("features=?")
                params.append(features)
            cur_sub = current[2]
            if subratings and (not cur_sub or str(cur_sub).strip() in ("", "[]", "{}", "None")):
                fields.append("subratings=?")
                params.append(subratings)

            if fields:
                params.append(loc_id)
                local_conn.execute(
                    f"UPDATE tripadvisor_restaurants SET {', '.join(fields)} WHERE locationId=?",
                    tuple(params),
                )
                local_conn.commit()
                return True
            return False
        finally:
            local_conn.close()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process, row): row for row in rows}
        for i, future in enumerate(as_completed(futures), 1):
            row_dict, result = future.result()
            loc_id = row_dict["locationId"]
            name = row_dict["name"]

            if result:
                try:
                    written = write_to_db(row_dict, result)
                    if written:
                        with write_lock:
                            llm_ok += 1
                        logger.info(f"  [LLM] {loc_id} | {name[:30]} [OK]")
                    else:
                        logger.info(f"  [LLM] {loc_id} | {name[:30]} (already filled)")
                except Exception as e:
                    with write_lock:
                        llm_fail += 1
                    if llm_fail <= 5:
                        logger.warning(f"  [LLM] Write error for {loc_id}: {e}")
            else:
                with write_lock:
                    llm_fail += 1
                if llm_fail <= 5:
                    logger.warning(f"  [LLM] No result for {loc_id} | {name[:30]}")

            if i % 10 == 0:
                logger.info(f"  [Phase 4] Progress: {i}/{total} (ok={llm_ok}, fail={llm_fail})")

    logger.info(f"[Phase 4] Complete: {llm_ok} updated, {llm_fail} LLM failures")
    conn.close()
    return llm_ok


def phase5_ta_scrape(db_path, limit=0, dry_run=False, workers=2):
    """Scrape TripAdvisor pages to extract coordinates and phone."""
    conn = _open_db(db_path, dry_run)

    query = (
        "SELECT locationId, name, h5Url FROM tripadvisor_restaurants "
        "WHERE (latitude IS NULL OR latitude = '' OR latitude = '0' OR latitude = 0.0) "
        "AND h5Url IS NOT NULL AND h5Url != '' "
        "ORDER BY locationId"
    )
    if limit > 0:
        query += f" LIMIT {limit}"
    rows = conn.execute(query).fetchall()
    total = len(rows)
    logger.info(f"[Phase 5] TripAdvisor scrape: {total} records")

    if total == 0:
        logger.info("[Phase 5] All records already have coordinates.")
        conn.close()
        return 0

    if dry_run:
        logger.info("[Phase 5] DRY RUN - showing first 10")
        for r in rows[:10]:
            logger.info(f"  {r['locationId']} | {r['name'][:30]}")
        conn.close()
        return 0

    updated = 0
    failed = 0
    write_lock = Lock()

    TA_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.tripadvisor.cn/",
    }

    def scrape_ta(row):
        time.sleep(random.uniform(2.0, 4.0))
        url = row["h5Url"]
        if not url:
            return row["locationId"], row["name"], None
        try:
            resp = requests.get(url, headers=TA_HEADERS, timeout=20)
            if resp.status_code != 200:
                return row["locationId"], row["name"], None
            html = resp.text
            # Extract coordinates - Kunming is around 25.0 N, 102.7 E
            lat_match = re.search(r'(39\.\d{4,})', html)
            lng_match = re.search(r'(116\.\d{4,})', html)
            if lat_match and lng_match:
                return row["locationId"], row["name"], {
                    "lat": float(lat_match.group(1)),
                    "lng": float(lng_match.group(1)),
                }
            # Fallback: try generic lat/lng patterns
            lat_m2 = re.search(r'"latitude"\s*:\s*([\d.]+)', html)
            lng_m2 = re.search(r'"longitude"\s*:\s*([\d.]+)', html)
            if lat_m2 and lng_m2:
                return row["locationId"], row["name"], {
                    "lat": float(lat_m2.group(1)),
                    "lng": float(lng_m2.group(1)),
                }
        except Exception:
            pass
        return row["locationId"], row["name"], None

    updates = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(scrape_ta, row): row for row in rows}
        for i, future in enumerate(as_completed(futures), 1):
            loc_id, name, result = future.result()
            if result and result.get("lat") and result.get("lng"):
                with write_lock:
                    updates.append((result["lat"], result["lng"], loc_id))
                    updated += 1
            else:
                failed += 1
                if failed <= 5:
                    logger.warning(f"  [FAIL] {loc_id} | {name[:30]}")
            if i % 50 == 0:
                with write_lock:
                    conn.executemany(
                        "UPDATE tripadvisor_restaurants SET latitude=?, longitude=? WHERE locationId=?",
                        updates,
                    )
                    conn.commit()
                    updates.clear()
                logger.info(f"  [Phase 5] Progress: {i}/{total} (ok={updated}, fail={failed})")

    if updates:
        conn.executemany(
            "UPDATE tripadvisor_restaurants SET latitude=?, longitude=? WHERE locationId=?",
            updates,
        )
        conn.commit()

    logger.info(f"[Phase 5] Complete: {updated} updated, {failed} failed")
    conn.close()
    return updated


# ─────────────────── main ───────────────────

def get_missing_stats(db_path):
    """Print summary of missing fields."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    total = conn.execute("SELECT COUNT(*) FROM tripadvisor_restaurants").fetchone()[0]
    logger.info(f"\n{'='*60}")
    logger.info(f"  Total records: {total}")
    logger.info(f"{'='*60}")

    fields = [
        ("latitude/longitude", "latitude IS NULL OR latitude = '' OR latitude = 0.0 OR latitude = '0'"),
        ("amap_id/name/type", "amap_id IS NULL OR amap_id = ''"),
        ("phone", "phone IS NULL OR phone = ''"),
        ("businessHours", "businessHours IS NULL OR businessHours = ''"),
        ("description", "description IS NULL OR description = ''"),
        ("features", "features IS NULL OR features = ''"),
        ("subratings", "subratings IS NULL OR subratings = ''"),
        ("rating", "rating IS NULL OR rating = '' OR rating = 0.0"),
    ]

    for label, condition in fields:
        missing = conn.execute(f"SELECT COUNT(*) FROM tripadvisor_restaurants WHERE {condition}").fetchone()[0]
        pct = round(missing / total * 100, 1) if total else 0
        logger.info(f"  {label}: {missing}/{total} ({pct}%) missing")

    logger.info(f"{'='*60}\n")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Backfill tripadvisor-bj.db missing fields")
    parser.add_argument("--db", default="output/tripadvisor-bj.db", help="Path to SQLite DB")
    parser.add_argument("--phase", default="all",
                        help="Phases to run: 1,2,3,4 or 'all' (e.g. '1 2' or 'all')")
    parser.add_argument("--limit", type=int, default=0, help="Limit records per phase")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no writes")
    parser.add_argument("--workers", type=int, default=3, help="LLM workers (phase 4 only)")
    args = parser.parse_args()

    db_path = args.db
    if not os.path.isabs(db_path):
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), db_path)

    if not os.path.exists(db_path):
        logger.error(f"Database not found: {db_path}")
        sys.exit(1)

    phases = args.phase.strip()
    if phases.lower() == "all":
        phase_list = [1, 2, 3, 4]
    else:
        phase_list = []
        for p in phases.split():
            try:
                phase_list.append(int(p))
            except ValueError:
                phase_list.append(p)

    logger.info("=" * 60)
    logger.info(f"Backfill tripadvisor-bj.db | DB: {db_path}")
    logger.info(f"Phases: {phase_list} | Dry-run: {args.dry_run} | Limit: {args.limit or 'unlimited'}")
    logger.info("=" * 60)

    if 1 in phase_list:
        logger.info("\n>>> Phase 1: Geocoding (address -> lat/lng)")
        phase1_geocode(db_path, limit=args.limit, dry_run=args.dry_run)

    if "1b" in phase_list:
        logger.info("\n>>> Phase 1b: Nominatim fallback geocoding")
        phase1b_nominatim(db_path, limit=args.limit, dry_run=args.dry_run)

    if 2 in phase_list:
        logger.info("\n>>> Phase 2: POI Search (name �?amap_id, phone, etc.)")
        phase2_poi_search(db_path, limit=args.limit, dry_run=args.dry_run)

    if 3 in phase_list:
        logger.info("\n>>> Phase 3: Business Hours (restaurantHours �?businessHours)")
        phase3_business_hours(db_path, limit=args.limit, dry_run=args.dry_run)

    if 4 in phase_list:
        logger.info("\n>>> Phase 4: LLM Supplement (description, features, subratings)")
        phase4_llm_supplement(db_path, limit=args.limit, dry_run=args.dry_run, workers=args.workers)

    if 5 in phase_list:
        logger.info("\n>>> Phase 5: TripAdvisor scrape (h5Url -> lat/lng)")
        phase5_ta_scrape(db_path, limit=args.limit, dry_run=args.dry_run, workers=args.workers)

    get_missing_stats(db_path)
    logger.info("All done!")


if __name__ == "__main__":
    main()

