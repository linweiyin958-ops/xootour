import json
import logging
import random
import re
import time
from typing import Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from .config import MAFENGWO_BASE_URL, HEADERS, REQUEST_DELAY_MIN, REQUEST_DELAY_MAX

logger = logging.getLogger(__name__)


class MafengwoScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.headers.update({
            "Referer": f"{MAFENGWO_BASE_URL}/",
            "Host": "www.mafengwo.cn",
        })

    def _delay(self):
        time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))

    def search_spot(self, keyword: str) -> Optional[dict]:
        self._delay()
        try:
            search_url = f"{MAFENGWO_BASE_URL}/search/s.php"
            params = {"q": keyword, "t": "poi"}
            resp = self.session.get(search_url, params=params, timeout=15)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")
            first_result = soup.select_one("a[href*='/poi/']")

            if first_result:
                href = first_result.get("href", "")
                poi_match = re.search(r"/poi/(\d+)", href)
                if poi_match:
                    poi_id = poi_match.group(1)
                    title_el = first_result.select_one(".title, h3, h4, .poi-name")
                    title = title_el.get_text(strip=True) if title_el else keyword
                    return {
                        "poi_id": poi_id,
                        "poi_url": f"{MAFENGWO_BASE_URL}/poi/{poi_id}.html",
                        "title": title,
                    }

            logger.warning(f"MaFengWo search no result for '{keyword}'")
            return None
        except Exception as e:
            logger.error(f"MaFengWo search error for '{keyword}': {e}")
            return None

    def get_spot_detail(self, poi_id: str) -> Optional[dict]:
        detail_url = f"{MAFENGWO_BASE_URL}/poi/{poi_id}.html"
        self._delay()
        try:
            resp = self.session.get(detail_url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            detail = {"poi_id": poi_id, "poi_url": detail_url}

            title_el = soup.select_one("h1.title, h1, .poi-name, .title")
            if title_el:
                detail["name_zh"] = title_el.get_text(strip=True)

            rating_el = soup.select_one(".grade, .rating, .score, [class*='grade']")
            if rating_el:
                rating_match = re.search(r"[\d.]+", rating_el.get_text(strip=True))
                if rating_match:
                    detail["rating"] = float(rating_match.group())

            address_el = soup.select_one(".address, .poi-address, [class*='address']")
            if address_el:
                detail["address"] = address_el.get_text(strip=True)

            open_hours_el = soup.select_one(".open-time, .time, [class*='open'], [class*='time']")
            if open_hours_el:
                detail["open_hours"] = open_hours_el.get_text(strip=True)

            transport_el = soup.select_one(".transport, .traffic, [class*='transport'], [class*='traffic']")
            if transport_el:
                detail["transportation"] = transport_el.get_text(strip=True)

            price_el = soup.select_one(".price, .ticket, [class*='price'], [class*='ticket']")
            if price_el:
                detail["price_info"] = price_el.get_text(strip=True)

            summary_el = soup.select_one(".summary, .desc, .poi-summary, [class*='summary'], [class*='desc']")
            if summary_el:
                detail["summary"] = summary_el.get_text(strip=True)

            images = []
            for img in soup.select(".pic img, .photo img, .banner img, .slides img, img[src*='mafengwo']"):
                src = img.get("data-src") or img.get("src", "")
                if src and src.startswith("http"):
                    images.append(src)
            detail["images"] = images[:20]

            return detail
        except Exception as e:
            logger.error(f"MaFengWo detail error for poi_id={poi_id}: {e}")
            return None

    def get_notes(self, poi_id: str, max_notes: int = 5) -> list:
        notes_url = f"{MAFENGWO_BASE_URL}/poi/{poi_id}/notes.html"
        self._delay()
        try:
            resp = self.session.get(notes_url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            notes = []
            for article in soup.select(".note-item, .article-item, .feed-item, ._j_async_post, .note-card, .post-item, article")[:max_notes]:
                note = {}

                title_el = article.select_one(".title, h2, h3, h4, .note-title, a[href*='/note/']")
                if title_el:
                    note["title"] = title_el.get_text(strip=True)
                    note["url"] = title_el.get("href", "")
                    if note["url"] and not note["url"].startswith("http"):
                        note["url"] = MAFENGWO_BASE_URL + note["url"]

                content_el = article.select_one(".content, .summary, .desc, .note-summary, .text, ._j_content")
                if content_el:
                    note["content"] = content_el.get_text(strip=True)[:2000]

                images = []
                for img in article.select("img[src*='mafengwo'], img[data-src*='mafengwo']"):
                    src = img.get("data-src") or img.get("src", "")
                    if src:
                        if src.startswith("//"):
                            src = "https:" + src
                        images.append(src)
                if images:
                    note["images"] = images[:10]

                meta = {}
                author_el = article.select_one(".author, .user, .name, [class*='author'], [class*='user']")
                if author_el:
                    meta["author"] = author_el.get_text(strip=True)
                date_el = article.select_one(".date, .time, [class*='date']")
                if date_el:
                    meta["date"] = date_el.get_text(strip=True)
                if meta:
                    note["meta"] = meta

                if note.get("title") or note.get("content"):
                    notes.append(note)

            return notes
        except Exception as e:
            logger.error(f"MaFengWo notes error for poi_id={poi_id}: {e}")
            return []

    def scrape_spot(self, keyword: str, max_notes: int = 5) -> dict:
        logger.info(f"[MaFengWo] Starting scrape for: {keyword}")

        result = {"spot": None, "notes": [], "source": "mafengwo"}

        search = self.search_spot(keyword)
        if not search:
            logger.warning(f"[MaFengWo] Could not find spot: {keyword}")
            return result

        logger.info(f"[MaFengWo] Found: {search['title']} (poi_id={search['poi_id']})")

        detail = self.get_spot_detail(search["poi_id"])
        if detail:
            result["spot"] = detail

        notes = self.get_notes(search["poi_id"], max_notes=max_notes)
        if notes:
            result["notes"] = notes
            logger.info(f"[MaFengWo] Found {len(notes)} notes")

        return result
