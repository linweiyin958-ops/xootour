import logging
import random
import re
import time
from typing import Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from .config import DIANPING_BASE_URL, HEADERS, REQUEST_DELAY_MIN, REQUEST_DELAY_MAX

logger = logging.getLogger(__name__)


class DianpingScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.headers.update({
            "Referer": f"{DIANPING_BASE_URL}/",
            "Host": "www.dianping.com",
        })

    def _delay(self):
        time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))

    def search_shop(self, keyword: str, city: str = "nanjing") -> Optional[dict]:
        url = f"{DIANPING_BASE_URL}/search/keyword/{city}/0_{quote(keyword)}"
        self._delay()
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")

            shop_card = soup.select_one(".shop-card")
            if not shop_card:
                logger.warning(f"  [Dianping] No shop found for '{keyword}'")
                return None

            shop_url_el = shop_card.select_one("a[data-href]")
            shop_url = ""
            if shop_url_el:
                shop_url = shop_url_el.get("data-href", "")
                if not shop_url.startswith("http"):
                    shop_url = DIANPING_BASE_URL + shop_url

            name_el = shop_card.select_one(".shop-name")
            name = name_el.get_text(strip=True) if name_el else ""

            rating_el = shop_card.select_one(".star-wrap")
            rating = 0.0
            if rating_el:
                star_class = rating_el.get("class", [])
                for c in star_class:
                    m = re.search(r"star-(\d+)", c)
                    if m:
                        rating = float(m.group(1)) / 10.0
                        break

            review_el = shop_card.select_one(".review-num")
            review_count = 0
            if review_el:
                m = re.search(r"[\d.]+", review_el.get_text())
                if m:
                    review_count = int(float(m.group()))

            avg_price_el = shop_card.select_one(".price")
            avg_price = 0.0
            if avg_price_el:
                m = re.search(r"[\d.]+", avg_price_el.get_text())
                if m:
                    avg_price = float(m.group())

            address_el = shop_card.select_one(".address")
            address = address_el.get_text(strip=True) if address_el else ""

            tags_el = shop_card.select_one(".tags")
            tags = []
            if tags_el:
                for t in tags_el.select("a"):
                    tags.append(t.get_text(strip=True))

            shop = {
                "name": name,
                "rating": rating,
                "review_count": review_count,
                "avg_price": avg_price,
                "address_zh": address,
                "tags": tags,
                "shop_url": shop_url,
                "source": "dianping",
            }
            logger.info(f"  [Dianping] Found shop: {name} (rating={rating}, price={avg_price})")
            return shop

        except requests.RequestException as e:
            logger.warning(f"  [Dianping] Request failed for '{keyword}': {e}")
            return None
        except Exception as e:
            logger.error(f"  [Dianping] Parse error for '{keyword}': {e}")
            return None

    def scrape_shop(self, name_zh: str, category: str = "") -> dict:
        result = {"shop": None, "products": [], "reviews": [], "source": "dianping"}

        search_keywords = [name_zh]
        if category and category not in name_zh:
            search_keywords.append(f"{name_zh} {category}")

        shop = None
        for kw in search_keywords:
            shop = self.search_shop(kw)
            if shop:
                break

        if shop:
            shop_detail = self.scrape_shop_detail(shop.get("shop_url", ""))
            if shop_detail:
                shop.update(shop_detail)
            result["shop"] = shop

        return result

    def scrape_shop_detail(self, shop_url: str) -> Optional[dict]:
        if not shop_url:
            return None

        self._delay()
        try:
            resp = self.session.get(shop_url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            detail = {}

            open_hours_el = soup.select_one(".open-hours")
            if open_hours_el:
                detail["open_hours"] = open_hours_el.get_text(strip=True)

            phone_el = soup.select_one(".phone")
            if phone_el:
                detail["phone"] = phone_el.get_text(strip=True)

            summary_el = soup.select_one(".summary")
            if summary_el:
                detail["summary"] = summary_el.get_text(strip=True)

            images = []
            img_els = soup.select(".shop-images img, .gallery img")
            for img in img_els[:20]:
                src = img.get("src") or img.get("data-src", "")
                if src and src.startswith("http"):
                    images.append(src)
            if images:
                detail["images"] = images

            return detail

        except Exception as e:
            logger.warning(f"  [Dianping] Detail scrape failed: {e}")
            return None
