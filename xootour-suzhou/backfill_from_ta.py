"""Backfill store fields from TripAdvisor restaurants data (if available)."""
import json, logging, os, re, sqlite3, sys

log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "_backfill_from_ta.log")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "xootour_suzhou.db")


def parse_price(price_detail):
    if not price_detail:
        return None
    level = len(str(price_detail).strip())
    mapping = {1: "平价", 2: "中等", 3: "高档", 4: "奢华"}
    return mapping.get(level)


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Check if tripadvisor_restaurants table exists
    try:
        conn.execute("SELECT 1 FROM tripadvisor_restaurants LIMIT 1")
    except sqlite3.OperationalError:
        logger.info("No tripadvisor_restaurants table found, skipping.")
        conn.close()
        return

    logger.info("Building TA lookup table (deduplicating by amap_id)...")
    ta_rows = conn.execute(
        "SELECT amap_id, MAX(rating) AS rating, MAX(reviewsCount) AS reviewsCount, "
        "MAX(rankingDesc) AS rankingDesc, MAX(coverImage) AS coverImage, "
        "MAX(priceDetail) AS priceDetail, MAX(CAST(michelinStatus AS INTEGER)) AS michelinStatus "
        "FROM tripadvisor_restaurants "
        "WHERE amap_id IS NOT NULL AND amap_id != '' "
        "GROUP BY amap_id"
    ).fetchall()

    ta_lookup = {}
    for row in ta_rows:
        amap_id, rating, rev_cnt, rank_desc, cover, price_det, michelin = row
        ta_lookup[amap_id] = {
            "rating": rating,
            "review_count": rev_cnt,
            "ranking_desc": rank_desc,
            "cover_img": cover,
            "price_detail": price_det,
            "michelin_status": michelin,
        }
    logger.info(f"TA lookup: {len(ta_lookup)} unique amap_ids")

    store_rows = conn.execute(
        "SELECT s.id, s.name_zh, si.amap_id, s.price_range, s.rating, s.review_count, "
        "s.ranking_desc, s.cover_img, s.michelin_status "
        "FROM store s "
        "INNER JOIN store_info si ON si.store_id = s.id "
        "WHERE si.amap_id IS NOT NULL AND si.amap_id != '' "
        "AND s.category_id = 1"
    ).fetchall()

    stats = {"price_range": 0, "rating": 0, "review_count": 0, "ranking_desc": 0,
             "cover_img": 0, "michelin_status": 0}

    updates = []
    for row in store_rows:
        store_id, name, amap_id, cur_price, cur_rating, cur_review, cur_rank, cur_cover, cur_michelin = row
        ta = ta_lookup.get(amap_id)
        if not ta:
            continue

        new_price = cur_price
        new_rating = cur_rating
        new_review = cur_review
        new_rank = cur_rank
        new_cover = cur_cover
        new_michelin = cur_michelin

        changed = False

        if (not cur_price or cur_price == "") and ta["price_detail"]:
            parsed = parse_price(ta["price_detail"])
            if parsed:
                new_price = parsed
                stats["price_range"] += 1
                changed = True

        if (cur_rating is None or cur_rating == 0 or cur_rating == 0.0) and ta["rating"] and ta["rating"] > 0:
            new_rating = ta["rating"]
            stats["rating"] += 1
            changed = True

        if (cur_review is None or cur_review == 0) and ta["review_count"] and ta["review_count"] > 0:
            new_review = ta["review_count"]
            stats["review_count"] += 1
            changed = True

        if (not cur_rank or cur_rank == "") and ta["ranking_desc"] and ta["ranking_desc"] != "":
            new_rank = ta["ranking_desc"]
            stats["ranking_desc"] += 1
            changed = True

        if (not cur_cover or cur_cover == "") and ta["cover_img"] and ta["cover_img"] != "":
            new_cover = ta["cover_img"]
            stats["cover_img"] += 1
            changed = True

        if (cur_michelin is None or cur_michelin == 0) and ta["michelin_status"] and ta["michelin_status"] > 0:
            new_michelin = ta["michelin_status"]
            stats["michelin_status"] += 1
            changed = True

        if changed:
            updates.append((new_price, new_rating, new_review, new_rank, new_cover, new_michelin, store_id))

    logger.info(f"Stores to update: {len(updates)}")

    if updates:
        conn.executemany(
            "UPDATE store SET price_range=?, rating=?, review_count=?, ranking_desc=?, cover_img=?, "
            "michelin_status=? WHERE id=?",
            updates
        )
        conn.commit()
        logger.info("Updates committed.")

    logger.info(f"\n=== Backfill Results ===")
    for field, count in stats.items():
        logger.info(f"  {field}: {count} updated")
    logger.info(f"  Total stores updated: {len(updates)}")

    conn.close()


if __name__ == "__main__":
    main()
