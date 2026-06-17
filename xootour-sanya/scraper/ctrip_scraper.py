import json
import logging
import random
import re
import time
from typing import Optional
from urllib.parse import quote

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
            "Host": "you.ctrip.com",
        })

    def _delay(self):
        time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))

    def search_spot(self, keyword: str) -> Optional[dict]:
        self._delay()
        try:
            search_url = f"{CTRIP_BASE_URL}/search"
            params = {"query": keyword, "type": "sight"}
            resp = self.session.get(search_url, params=params, timeout=15)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")
            first_result = soup.select_one("a[href*='/sight/']")

            if first_result:
                href = first_result.get("href", "")
                sight_match = re.search(r"/sight/(\w+)/", href)
                if sight_match:
                    sight_id = sight_match.group(1)
                    title_el = first_result.select_one(".title, h3, h4, .sight-name")
                    title = title_el.get_text(strip=True) if title_el else keyword
                    return {
                        "sight_id": sight_id,
                        "sight_url": f"https://you.ctrip.com/sight/{sight_id}/",
                        "title": title,
                    }

            logger.warning(f"Ctrip search no result for '{keyword}'")
            return None
        except Exception as e:
            logger.error(f"Ctrip search error for '{keyword}': {e}")
            return None

    def get_spot_detail(self, sight_id: str) -> Optional[dict]:
        detail_url = f"https://you.ctrip.com/sight/{sight_id}/"
        self._delay()
        try:
            resp = self.session.get(detail_url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            detail = {"sight_id": sight_id, "sight_url": detail_url}

            title_el = soup.select_one("h1.title, h1, .sight-title, .title")
            if title_el:
                detail["name_zh"] = title_el.get_text(strip=True)

            rating_el = soup.select_one(".grade, .rating, .score, [class*='grade'], [class*='rating']")
            if rating_el:
                rating_match = re.search(r"[\d.]+", rating_el.get_text(strip=True))
                if rating_match:
                    detail["rating"] = float(rating_match.group())

            address_el = soup.select_one(".address, .sight-address, [class*='address']")
            if address_el:
                detail["address"] = address_el.get_text(strip=True)

            open_hours_el = soup.select_one(".open-time, .time, [class*='open'], [class*='time']")
            if open_hours_el:
                detail["open_hours"] = open_hours_el.get_text(strip=True)

            transport_el = soup.select_one(".transport, .traffic, [class*='transport'], [class*='traffic']")
            if transport_el:
                detail["transportation"] = transport_el.get_text(strip=True)

            notice_el = soup.select_one(".notice, .tip, [class*='notice'], [class*='tip']")
            if notice_el:
                detail["visit_notice"] = notice_el.get_text(strip=True)

            summary_el = soup.select_one(".summary, .desc, [class*='summary'], [class*='desc'], .sight-summary")
            if summary_el:
                detail["summary"] = summary_el.get_text(strip=True)

            images = []
            for img in soup.select(".pic img, .photo img, .banner img, .slides img, img[src*='ctrip']"):
                src = img.get("data-src") or img.get("src", "")
                if src:
                    if src.startswith("//"):
                        src = "https:" + src
                    images.append(src)
            detail["images"] = images[:15]

            return detail
        except Exception as e:
            logger.error(f"Ctrip detail error for sight_id={sight_id}: {e}")
            return None

    def get_packages(self, sight_id: str) -> list:
        api_url = f"https://you.ctrip.com/sight/{sight_id}/tickets.html"
        self._delay()
        try:
            resp = self.session.get(api_url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            packages = []
            for item in soup.select(".ticket-item, .package-item, [class*='ticket'], [class*='package']"):
                pkg = {}
                name_el = item.select_one(".name, .title, .package-name, h4, h5")
                if name_el:
                    pkg["package_name"] = name_el.get_text(strip=True)

                price_el = item.select_one(".price, [class*='price']")
                if price_el:
                    price_match = re.search(r"[\d.]+", price_el.get_text(strip=True))
                    if price_match:
                        pkg["price"] = float(price_match.group())

                desc_el = item.select_one(".desc, .description, .info, .package-desc")
                if desc_el:
                    pkg["description"] = desc_el.get_text(strip=True)

                if pkg.get("package_name"):
                    packages.append(pkg)

            return packages
        except Exception as e:
            logger.error(f"Ctrip packages error for sight_id={sight_id}: {e}")
            return []

    def scrape_spot(self, keyword: str) -> dict:
        logger.info(f"[Ctrip] Starting scrape for: {keyword}")

        result = {"spot": None, "packages": [], "source": "ctrip"}

        search = self.search_spot(keyword)
        if not search:
            logger.warning(f"[Ctrip] Could not find spot: {keyword}")
            return result

        logger.info(f"[Ctrip] Found: {search['title']} (sight_id={search['sight_id']})")

        detail = self.get_spot_detail(search["sight_id"])
        if detail:
            result["spot"] = detail

        packages = self.get_packages(search["sight_id"])
        if packages:
            result["packages"] = packages
            logger.info(f"[Ctrip] Found {len(packages)} packages")

        return result
