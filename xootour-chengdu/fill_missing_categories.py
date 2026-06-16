import json
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

from scraper.config import OUTPUT_DIR, CHENGDU_CITY_ID
from scraper.store_scraper import StoreScraper
from scraper.rule_extractor import RuleExtractor
from scraper.ai_extractor import FreeLLMExtractor
from scraper.sqlite_writer import SQLiteWriter


def main():
    store_api = StoreScraper()
    rule_ext = RuleExtractor()
    llm = FreeLLMExtractor()

    sdb = SQLiteWriter()
    if not sdb.connect():
        logger.error("SQLite connection failed")
        return

    store_id_counter = sdb.conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM store").fetchone()[0]
    logger.info(f"Starting store_id_counter from: {store_id_counter}")

    # Check which categories might need more data
    for cat_id in range(1, 6):
        count = sdb.conn.execute(
            "SELECT COUNT(*) FROM store WHERE category_id=?", (cat_id,)
        ).fetchone()[0]
        logger.info(f"  Category {cat_id}: {count} stores")

    sdb.close()
    logger.info("fill_missing_categories: Use store_main.py pipeline instead for comprehensive collection.")


if __name__ == "__main__":
    main()
