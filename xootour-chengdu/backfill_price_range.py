"""Backfill price_range for non-dining stores via LLM (FreeLLMExtractor)."""
import json, logging, os, sqlite3, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "_backfill_price_range.log")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "xootour_chengdu.db")

PRICE_PROMPT = """你是一名成都旅游消费价格评估专家。根据门店的名称、品类和地址，推断其价格档次。

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
        return store_id, name_zh, result.get("price_range", ""), result.get("reason", "")
    except Exception as e:
        logger.error(f"  [LLM] Error for {name_zh}: {e}")
        return None


def main():
    # Lazy import to avoid loading llm client until needed
    from openai import OpenAI
    from scraper.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL

    if not QWEN_API_KEY:
        logger.error("QWEN_API_KEY not set. Skipping.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")

    rows = conn.execute(
        "SELECT s.id, s.name_zh, sc.name_zh, si.district, si.address_zh "
        "FROM store s "
        "LEFT JOIN store_info si ON si.store_id = s.id "
        "LEFT JOIN store_category sc ON sc.id = s.category_id "
        "WHERE (s.price_range IS NULL OR s.price_range = '')"
    ).fetchall()

    if not rows:
        logger.info("No stores missing price_range.")
        conn.close()
        return

    logger.info(f"Stores missing price_range: {len(rows)}")

    llm = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)
    llm.model = QWEN_MODEL

    updated = 0
    lock = Lock()

    def write_result(store_id, price_range):
        conn.execute("UPDATE store SET price_range=? WHERE id=?", (price_range, store_id))
        conn.commit()

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(process_one, llm, row): row for row in rows}
        for future in as_completed(futures):
            result = future.result()
            if result:
                store_id, name, price_range, reason = result
                with lock:
                    write_result(store_id, price_range)
                    updated += 1
                logger.info(f"  [{store_id}] {name} -> {price_range} ({reason})")

    logger.info(f"\nDone. Updated {updated}/{len(rows)} stores with price_range.")
    conn.close()


if __name__ == "__main__":
    main()
