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

    def search_shop(self, keyword: str, city: str = "Xiamen") -> Optional[dict]:
        url = f"{DIANPING_BASE_URL}/search/keyword/{city}/0_{quote(keyword)}"
        self._delay()
        try:
            resp = self.session.get(url, timeout=15, allow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            first_shop = soup.select_one("div.shop-list li, div.shopall a, div.content a[href*='/shop/']")
            if not first_shop:
                items = soup.select("a[href*='/shop/']")
                if items:
                    first_shop = items[0]

            if first_shop:
                href = first_shop.get("href", "")
                shop_id_match = re.search(r"/shop/(\d+)", href)
                if shop_id_match:
                    shop_id = shop_id_match.group(1)
                    title_el = first_shop.select_one("h4, .shopname, .title, .shop-name")
                    title = title_el.get_text(strip=True) if title_el else keyword
                    return {
                        "shop_id": shop_id,
                        "shop_url": f"{DIANPING_BASE_URL}/shop/{shop_id}",
                        "title": title,
                    }

            logger.warning(f"Dianping search no result for '{keyword}'")
            return None
        except Exception as e:
            logger.error(f"Dianping search error for '{keyword}': {e}")
            return None

    def get_shop_detail(self, shop_id: str) -> Optional[dict]:
        url = f"{DIANPING_BASE_URL}/shop/{shop_id}"
        self._delay()
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            detail = {"shop_id": shop_id, "shop_url": url}

            title_el = soup.select_one("h1.shop-name, h1, .shop-name")
            if title_el:
                detail["name_zh"] = title_el.get_text(strip=True)

            rating_el = soup.select_one(".shop-rating, .score, [class*='rating'], .item-score")
            if rating_el:
                rating_match = re.search(r"[\d.]+", rating_el.get_text(strip=True))
                if rating_match:
                    detail["rating"] = float(rating_match.group())

            avg_price_el = soup.select_one(".avg-price, [class*='price'], .mean-price")
            if avg_price_el:
                price_match = re.search(r"[\d.]+", avg_price_el.get_text(strip=True))
                if price_match:
                    detail["avg_price"] = float(price_match.group())

            address_el = soup.select_one(".address, .item-address, [class*='address']")
            if address_el:
                detail["address_zh"] = address_el.get_text(strip=True)

            phone_el = soup.select_one(".phone, .item-phone, [class*='phone']")
            if phone_el:
                detail["phone"] = phone_el.get_text(strip=True)

            open_hours_el = soup.select_one(".open-hours, [class*='hours'], .item-time")
            if open_hours_el:
                detail["open_hours"] = open_hours_el.get_text(strip=True)

            for meta_item in soup.select(".meta-item, .info-item, .basic-info li, .shop-info dd"):
                text = meta_item.get_text(strip=True)
                if "营业" in text or "开放" in text:
                    detail["open_hours"] = text
                elif "电话" in text or "联系" in text:
                    detail["phone"] = text
                elif "地址" in text and not detail.get("address_zh"):
                    detail["address_zh"] = text
                elif "交通" in text:
                    detail["transportation"] = text

            tags = []
            for tag_el in soup.select(".tag, .shop-tag, .category-tag, [class*='tag'] a, .tags a"):
                tag_text = tag_el.get_text(strip=True)
                if tag_text and len(tag_text) < 20:
                    tags.append(tag_text)
            if tags:
                detail["tags"] = tags[:10]

            summary_el = soup.select_one(".shop-summary, .desc, .description, [class*='summary']")
            if summary_el:
                detail["summary"] = summary_el.get_text(strip=True)

            images = []
            for img in soup.select(".shop-banner img, .photo-grid img, .carousel img, .shop-img img, .pic img"):
                src = img.get("data-src") or img.get("src", "")
                if src:
                    if src.startswith("//"):
                        src = "https:" + src
                    if "dianping" in src or "dpfile" in src:
                        images.append(src)
            detail["images"] = images[:15]

            return detail
        except Exception as e:
            logger.error(f"Dianping shop detail error for shop_id={shop_id}: {e}")
            return None

    def get_shop_menu(self, shop_id: str) -> list:
        menu_url = f"{DIANPING_BASE_URL}/shop/{shop_id}/menu"
        self._delay()
        try:
            resp = self.session.get(menu_url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            products = []
            for item in soup.select(".menu-item, .dish-item, .recommend-item, [class*='dish'], [class*='product']"):
                product = {}
                name_el = item.select_one(".name, .dish-name, .title, h4, h5")
                if name_el:
                    product["product_name"] = name_el.get_text(strip=True)

                price_el = item.select_one(".price, [class*='price']")
                if price_el:
                    price_match = re.search(r"[\d.]+", price_el.get_text(strip=True))
                    if price_match:
                        product["price"] = float(price_match.group())

                desc_el = item.select_one(".desc, .description, .info")
                if desc_el:
                    product["description"] = desc_el.get_text(strip=True)

                img_el = item.select_one("img")
                if img_el:
                    src = img_el.get("data-src") or img_el.get("src", "")
                    if src:
                        if src.startswith("//"):
                            src = "https:" + src
                        product["image_url"] = src

                recommend_el = item.select_one(".recommend, .hot, [class*='recommend']")
                product["is_signature"] = recommend_el is not None

                if product.get("product_name"):
                    products.append(product)

            return products
        except Exception as e:
            logger.error(f"Dianping menu error for shop_id={shop_id}: {e}")
            return []

    def get_shop_reviews(self, shop_id: str, max_reviews: int = 10) -> list:
        review_url = f"{DIANPING_BASE_URL}/shop/{shop_id}/review_all"
        self._delay()
        try:
            resp = self.session.get(review_url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            reviews = []
            for review_el in soup.select(".review-item, .comment-item, [class*='review'], [class*='comment']")[:max_reviews]:
                review = {}
                rating_el = review_el.select_one(".score, .rating, [class*='score'], [class*='star']")
                if rating_el:
                    rating_match = re.search(r"[\d.]+", rating_el.get_text(strip=True) if rating_el.text else str(rating_el.get("class", "")))
                    if rating_match:
                        review["rating"] = float(rating_match.group())

                text_el = review_el.select_one(".content, .text, .review-text, [class*='content']")
                if text_el:
                    review["text"] = text_el.get_text(strip=True)

                date_el = review_el.select_one(".date, .time, [class*='date']")
                if date_el:
                    review["date"] = date_el.get_text(strip=True)

                if review.get("text"):
                    reviews.append(review)

            return reviews
        except Exception as e:
            logger.error(f"Dianping reviews error for shop_id={shop_id}: {e}")
            return []

    def scrape_shop(self, name_zh: str, category: str = "") -> dict:
        logger.info(f"[Dianping] Starting scrape for: {name_zh}")

        result = {"shop": None, "products": [], "reviews": [], "source": "dianping"}

        search = self.search_shop(name_zh)
        if not search:
            logger.warning(f"[Dianping] Could not find shop: {name_zh}")
            return result

        logger.info(f"[Dianping] Found: {search['title']} (shop_id={search['shop_id']})")

        detail = self.get_shop_detail(search["shop_id"])
        if detail:
            result["shop"] = detail

        if category in ("美食", "Food", "餐饮", "Dining") or not category:
            products = self.get_shop_menu(search["shop_id"])
            if products:
                result["products"] = products
                logger.info(f"[Dianping] Found {len(products)} menu items")

        reviews = self.get_shop_reviews(search["shop_id"], max_reviews=5)
        result["reviews"] = reviews
        logger.info(f"[Dianping] Found {len(reviews)} reviews for {name_zh}")

        return result

