import logging
import random
import re
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

from .config import CTRIP_BASE_URL, HEADERS, REQUEST_DELAY_MIN, REQUEST_DELAY_MAX

logger = logging.getLogger(__name__)


class CtripScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.headers.update({
            "Referer": f"{CTRIP_BASE_URL}/",
        })

    def _delay(self):
        time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))

    def search_spot(self, keyword: str) -> Optional[dict]:
        url = f"{CTRIP_BASE_URL}/sight/{keyword}"
        search_url = f"{CTRIP_BASE_URL}/searchsite/?query={keyword}&type=sight"
        self._delay()
        try:
            resp = self.session.get(search_url, timeout=15, allow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            first_link = None
            for a in soup.select("a[href*='/sight/']"):
                href = a.get("href", "")
                if re.search(r"/sight/\d+/\d+\.html", href):
                    first_link = href
                    title_el = a.select_one("h3, .title, .name")
                    title = title_el.get_text(strip=True) if title_el else a.get_text(strip=True)[:50]
                    break

            if first_link:
                if first_link.startswith("/"):
                    first_link = CTRIP_BASE_URL + first_link
                sight_id_match = re.search(r"/sight/\d+/(\d+)\.html", first_link)
                sight_id = sight_id_match.group(1) if sight_id_match else ""
                return {
                    "sight_id": sight_id,
                    "sight_url": first_link,
                    "title": title,
                }

            logger.warning(f"Ctrip search no result for '{keyword}'")
            return None
        except Exception as e:
            logger.error(f"Ctrip search error for '{keyword}': {e}")
            return None

    def get_spot_detail(self, sight_url: str) -> Optional[dict]:
        self._delay()
        try:
            resp = self.session.get(sight_url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            detail = {"sight_url": sight_url}

            title_el = soup.select_one("h1, .sight_title, .title")
            if title_el:
                detail["title"] = title_el.get_text(strip=True)

            rating_el = soup.select_one(".score, .rating, [class*='score']")
            if rating_el:
                rating_match = re.search(r"[\d.]+", rating_el.get_text(strip=True))
                if rating_match:
                    detail["rating"] = float(rating_match.group())

            open_el = soup.select_one("[class*='open-time'], [class*='opentime']")
            if open_el:
                detail["open_hours"] = open_el.get_text(strip=True)

            for section in soup.select("div.detail模块, div.module, .sight-detail"):
                text = section.get_text(strip=True)
                if "开放" in text:
                    detail["open_hours"] = text[:200]
                elif "交通" in text:
                    detail["transportation"] = text[:200]
                elif "须知" in text or "提示" in text:
                    detail["visit_notice"] = text[:500]

            info_items = soup.select("div.sight-detail dd, div.detail-info li, .sight-info-item")
            for item in info_items:
                text = item.get_text(strip=True)
                if "开放" in text and not detail.get("open_hours"):
                    detail["open_hours"] = text
                elif "交通" in text and not detail.get("transportation"):
                    detail["transportation"] = text
                elif "地址" in text:
                    detail["address"] = text
                elif "电话" in text:
                    detail["tel"] = text

            summary_el = soup.select_one(".sight-summary, .desc, .detail-descri")
            if summary_el:
                detail["summary"] = summary_el.get_text(strip=True)

            images = []
            for img in soup.select(".sight-img img, .photo-grid img, .banner img, .big-photo img"):
                src = img.get("data-src") or img.get("src", "")
                if src:
                    if src.startswith("//"):
                        src = "https:" + src
                    images.append(src)
            detail["images"] = images[:10]

            return detail
        except Exception as e:
            logger.error(f"Ctrip spot detail error for {sight_url}: {e}")
            return None

    def get_ticket_info(self, sight_url: str) -> list:
        ticket_url = sight_url.replace(".html", "/ticket.html")
        self._delay()
        try:
            resp = self.session.get(ticket_url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            packages = []
            for item in soup.select(".ticket-item, .product-item, [class*='ticket']"):
                pkg = {}
                name_el = item.select_one(".name, .title, h4")
                if name_el:
                    pkg["package_name"] = name_el.get_text(strip=True)

                price_el = item.select_one(".price, [class*='price']")
                if price_el:
                    price_match = re.search(r"[\d.]+", price_el.get_text(strip=True))
                    if price_match:
                        pkg["price"] = float(price_match.group())

                desc_el = item.select_one(".desc, .description")
                if desc_el:
                    pkg["description"] = desc_el.get_text(strip=True)

                if pkg.get("package_name"):
                    packages.append(pkg)

            return packages
        except Exception as e:
            logger.error(f"Ctrip ticket info error for {ticket_url}: {e}")
            return []

    def scrape_spot(self, name_zh: str) -> dict:
        logger.info(f"[Ctrip] Starting scrape for: {name_zh}")

        result = {"spot": None, "packages": [], "source": "ctrip"}

        search = self.search_spot(name_zh)
        if not search:
            logger.warning(f"[Ctrip] Could not find spot: {name_zh}")
            return result

        logger.info(f"[Ctrip] Found: {search.get('title', '')} (url={search['sight_url']})")

        detail = self.get_spot_detail(search["sight_url"])
        if detail:
            result["spot"] = detail

        packages = self.get_ticket_info(search["sight_url"])
        if packages:
            result["packages"] = packages
            logger.info(f"[Ctrip] Found {len(packages)} ticket packages")

        return result

