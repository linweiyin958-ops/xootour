import asyncio
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
        url = f"{MAFENGWO_BASE_URL}/search/q.php"
        params = {"q": keyword, "t": "poi"}
        self._delay()
        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            first_result = soup.select_one("a._j_search_item")
            if not first_result:
                items = soup.select("div.search-result a[href*='/poi/']")
                if items:
                    first_result = items[0]

            if first_result:
                href = first_result.get("href", "")
                poi_id_match = re.search(r"/poi/(\d+)\.html", href)
                if poi_id_match:
                    poi_id = poi_id_match.group(1)
                    title_el = first_result.select_one("h3, .title, .name")
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
        url = f"{MAFENGWO_BASE_URL}/poi/{poi_id}.html"
        self._delay()
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            detail = {"poi_id": poi_id, "poi_url": url}

            title_el = soup.select_one("h1, .title")
            if title_el:
                detail["title"] = title_el.get_text(strip=True)

            rating_el = soup.select_one(".score, .rating, [class*='score']")
            if rating_el:
                rating_text = rating_el.get_text(strip=True)
                rating_match = re.search(r"[\d.]+", rating_text)
                if rating_match:
                    detail["rating"] = float(rating_match.group())

            info_section = soup.select("div.mod-detail dd, div.mod-info dd, .detail-info li")
            for item in info_section:
                text = item.get_text(strip=True)
                if "开放" in text:
                    detail["open_hours"] = text
                elif "交通" in text or "地铁" in text:
                    detail["transportation"] = text
                elif "电话" in text or "tel" in text.lower():
                    detail["tel"] = text
                elif "门票" in text or "价格" in text:
                    detail["price_info"] = text
                elif "地址" in text:
                    detail["address"] = text

            summary_el = soup.select_one(".summary, .mod-summary, .desc")
            if summary_el:
                detail["summary"] = summary_el.get_text(strip=True)

            images = []
            for img in soup.select("div._j_cover_box img, .photo-grid img, .carousel img, .big-photo img"):
                src = img.get("data-src") or img.get("src", "")
                if src and ("mafengwo" in src or "bdimg" in src):
                    if src.startswith("//"):
                        src = "https:" + src
                    images.append(src)
            detail["images"] = images[:10]

            return detail
        except Exception as e:
            logger.error(f"MaFengWo spot detail error for poi_id={poi_id}: {e}")
            return None

    def get_spot_travel_notes(self, poi_id: str, max_notes: int = 10) -> list:
        url = f"{MAFENGWO_BASE_URL}/poi/{poi_id}/notes.html"
        self._delay()
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            notes = []
            note_items = soup.select("div._j_note_item, div.note-item, .travel-notes li, article.note")

            for item in note_items[:max_notes]:
                note = {}
                link_el = item.select_one("a[href*='/note/'], a[href*='/gonglve/']")
                if link_el:
                    note["url"] = link_el.get("href", "")
                    if note["url"] and not note["url"].startswith("http"):
                        note["url"] = MAFENGWO_BASE_URL + note["url"]
                    title_el = link_el.select_one("h3, .title")
                    note["title"] = title_el.get_text(strip=True) if title_el else link_el.get_text(strip=True)

                author_el = item.select_one(".author, .user-name, .name")
                if author_el:
                    note["author"] = author_el.get_text(strip=True)

                stats_el = item.select_one(".stats, .view-count, [class*='read']")
                if stats_el:
                    note["stats"] = stats_el.get_text(strip=True)

                if note.get("url"):
                    notes.append(note)

            return notes
        except Exception as e:
            logger.error(f"MaFengWo travel notes error for poi_id={poi_id}: {e}")
            return []

    def get_note_detail(self, note_url: str) -> Optional[dict]:
        self._delay()
        try:
            resp = self.session.get(note_url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            note = {"url": note_url}

            title_el = soup.select_one("h1, .title")
            if title_el:
                note["title"] = title_el.get_text(strip=True)

            content_el = soup.select_one("div._j_content_box, div.note-content, article.content, .va_con")
            if content_el:
                paragraphs = content_el.select("p")
                note["content"] = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

            images = []
            for img in content_el.select("img") if content_el else []:
                src = img.get("data-src") or img.get("src", "")
                if src:
                    if src.startswith("//"):
                        src = "https:" + src
                    images.append(src)
            note["images"] = images[:15]

            return note
        except Exception as e:
            logger.error(f"MaFengWo note detail error for {note_url}: {e}")
            return None

    def scrape_spot(self, name_zh: str, max_notes: int = 5) -> dict:
        logger.info(f"[MaFengWo] Starting scrape for: {name_zh}")

        result = {"spot": None, "notes": [], "source": "mafengwo"}

        search = self.search_spot(name_zh)
        if not search:
            logger.warning(f"[MaFengWo] Could not find spot: {name_zh}")
            return result

        logger.info(f"[MaFengWo] Found: {search['title']} (poi_id={search['poi_id']})")

        detail = self.get_spot_detail(search["poi_id"])
        if detail:
            result["spot"] = detail

        note_list = self.get_spot_travel_notes(search["poi_id"], max_notes=max_notes)
        logger.info(f"[MaFengWo] Found {len(note_list)} travel notes")

        for note_meta in note_list[:max_notes]:
            note_detail = self.get_note_detail(note_meta["url"])
            if note_detail:
                note_detail["meta"] = note_meta
                result["notes"].append(note_detail)

        logger.info(f"[MaFengWo] Scraped {len(result['notes'])} detailed notes for {name_zh}")
        return result

