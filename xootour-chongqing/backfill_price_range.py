"""Backfill price_range for non-dining stores via LLM (FreeLLMExtractor)."""
import json, logging, os, sqlite3, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "_backfill_price_range.log")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "xootour_chongqing.db")

PRICE_PROMPT = """你是一名重庆旅游消费价格评估专家。根据门店的名称、品类和地址，推断其价格档次。

价格档次定义：
- "平价"：人均50元以下，大众消费（经济型酒店/便利店/快餐/普通药房/公交地铁）
- "中等"：人均50-200元，中档消费（三星酒店/百货商场/普通餐厅/连锁药妆）
- "高档"：人均200-800元，高端消费（四星酒店/精品店/高端餐厅/私立医院）
- "奢华"：人均800元以上，奢华消费（五星酒店/奢侈品店/米其林/国际医院）

请返回JSON格式，不要输出其他内容：
{
  "price_range": "平价/中等/高档/奢华",
  "reason": "判断依据(一句话)"
}"""


def process_one(llm_client, row):
    store_id, name_zh, cat_name, district, address_zh = row
    user = f"门店名称：{name_zh}\n品类：{cat_name}\n行政区：{district or '未知'}\n地址：{address_zh or '未知'}"

    try:
        response = llm_client.chat.completions.create(
            model=llm_client.model if hasattr(llm_client, 'model') else "qwen-plus",
            messages=[
                {"role": "system", "content": PRICE_PROMPT},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            max_tokens=256,
        )
        content = response.choices[0].message.content.strip()

        json_str = content
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0].strip()

        result = json.loads(json_str)
        price_range = result.get("price_range", "")
        if price_range in ("平价", "中等", "高档", "奢华"):
            return store_id, price_range
        return store_id, None
    except Exception as e:
        return store_id, None


def main():
    from openai import OpenAI
    from scraper.config import FREE_LLM_PROVIDER, QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL

    if not QWEN_API_KEY:
        logger.error("QWEN_API_KEY not configured.")
        return

    provider = FREE_LLM_PROVIDER
    if provider == "qwen":
        client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)
        model = QWEN_MODEL
    else:
        logger.error(f"Unsupported provider: {provider}")
        return

    client.model = model

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")

    rows = conn.execute("""
        SELECT s.id, s.name_zh, sc.name_zh, si.district, si.address_zh
        FROM store s
        JOIN store_category sc ON sc.id = s.category_id
        LEFT JOIN store_info si ON si.store_id = s.id
        WHERE s.category_id != 1
        AND (s.price_range IS NULL OR s.price_range = '')
        ORDER BY s.category_id, s.id
    """).fetchall()

    total = len(rows)
    logger.info(f"Non-dining stores missing price_range: {total}")

    if total == 0:
        logger.info("All stores have price_range.")
        conn.close()
        return

    updated = 0
    skipped = 0
    write_lock = Lock()

    def process(row):
        store_id, name_zh, cat_name, district, address = row
        return process_one(client, row)

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(process, row): row for row in rows}

        for i, future in enumerate(as_completed(futures), 1):
            row = futures[future]
            store_id, name_zh = row[0], row[1]
            try:
                result = future.result()
                if result and result[1]:
                    sid, price_range = result
                    with write_lock:
                        conn.execute("UPDATE store SET price_range=? WHERE id=?", (price_range, sid))
                        conn.commit()
                    updated += 1
                else:
                    skipped += 1
                    if skipped <= 5:
                        logger.warning(f"  [{store_id}] Failed: {name_zh}")
            except Exception as e:
                skipped += 1
                logger.error(f"  [{store_id}] Error: {name_zh} - {e}")

            if i % 100 == 0:
                with write_lock:
                    conn.commit()
                logger.info(f"  Progress: {i}/{total} (updated={updated}, skipped={skipped})")

    conn.commit()

    logger.info(f"\n=== Price Range Backfill Results ===")
    for cat_id in range(2, 6):
        cnt = conn.execute(
            "SELECT COUNT(*) FROM store WHERE category_id=? AND price_range IS NOT NULL AND price_range != ''",
            (cat_id,)
        ).fetchone()[0]
        total_cat = conn.execute("SELECT COUNT(*) FROM store WHERE category_id=?", (cat_id,)).fetchone()[0]
        logger.info(f"  Category {cat_id}: {cnt}/{total_cat} filled")

    logger.info(f"\n  Total updated: {updated}, skipped: {skipped}")

    conn.close()


if __name__ == "__main__":
    main()
