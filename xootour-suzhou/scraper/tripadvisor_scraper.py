import logging
import random
import re
import time
from typing import Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from .config import TRIPADVISOR_BASE_URL, HEADERS, REQUEST_DELAY_MIN, REQUEST_DELAY_MAX

logger = logging.getLogger(__name__)


class TripAdvisorScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.headers.update({
            "Referer": f"{TRIPADVISOR_BASE_URL}/",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def _delay(self):
        time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))

    def search_spot(self, name_en: str, city: str = "Suzhou") -> Optional[dict]:
        search_url = f"{TRIPADVISOR_BASE_URL}/Search?q={quote(name_en + ' ' + city)}"
        self._delay()
        try:
            resp = self.session.get(search_url, timeout=15, allow_redirects=True)
            resp.raise_for_status()

            current_url = resp.url
            if "/Attraction_" in current_url or "/Attractions-" in current_url:
                return {
                    "attraction_url": current_url,
                    "title": name_en,
                }

            soup = BeautifulSoup(resp.text, "lxml")

            for a in soup.select("a[href*='/Attraction_'], a[href*='/Attractions-']"):
                href = a.get("href", "")
                if href.startswith("/"):
                    href = TRIPADVISOR_BASE_URL + href
                title = a.get_text(strip=True)
                if city.lower() in title.lower() or name_en.lower() in title.lower():
                    return {
                        "attraction_url": href,
                        "title": title,
                    }

            first_link = soup.select_one("a[href*='/Attraction_']")
            if first_link:
                href = first_link.get("href", "")
                if href.startswith("/"):
                    href = TRIPADVISOR_BASE_URL + href
                return {
                    "attraction_url": href,
                    "title": first_link.get_text(strip=True),
                }

            logger.warning(f"TripAdvisor search no result for '{name_en}'")
            return None
        except Exception as e:
            logger.error(f"TripAdvisor search error for '{name_en}': {e}")
            return None

    def get_spot_detail(self, attraction_url: str) -> Optional[dict]:
        self._delay()
        try:
            resp = self.session.get(attraction_url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            detail = {"attraction_url": attraction_url}

            title_el = soup.select_one("h1, [data-automation='mainH1']")
            if title_el:
                detail["name_en"] = title_el.get_text(strip=True)

            rating_el = soup.select_one("[data-automation='tripPicsRating'] .ui_bubble_rating, .overallRating, [class*='rating']")
            if rating_el:
                rating_match = re.search(r"[\d.]+", rating_el.get_text(strip=True) if rating_el.text else str(rating_el.get("class", "")))
                if rating_match:
                    detail["rating"] = float(rating_match.group())

            about_el = soup.select_one("[data-automation='aboutText'], .attractions-about, .detail-section-description")
            if about_el:
                detail["about_en"] = about_el.get_text(strip=True)

            address_el = soup.select_one("[data-automation='address'], .address, .location-text")
            if address_el:
                detail["address_en"] = address_el.get_text(strip=True)

            open_hours_el = soup.select_one("[data-automation='hours'], .hours, .open-hours")
            if open_hours_el:
                detail["open_hours_en"] = open_hours_el.get_text(strip=True)

            images = []
            for img in soup.select(".basicImg, .sizedImg, [data-automation='tripPics'] img, .photo-grid img"):
                src = img.get("data-src") or img.get("src", "")
                if src:
                    if src.startswith("//"):
                        src = "https:" + src
                    images.append(src)
            detail["images"] = images[:10]

            return detail
        except Exception as e:
            logger.error(f"TripAdvisor spot detail error for {attraction_url}: {e}")
            return None

    def get_reviews(self, attraction_url: str, max_reviews: int = 10) -> list:
        if attraction_url.endswith(".html"):
            reviews_url = attraction_url.replace(".html", "-Reviews.html")
        else:
            reviews_url = attraction_url

        self._delay()
        try:
            resp = self.session.get(reviews_url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            reviews = []
            for review_el in soup.select("div.review-container, [data-automation='reviewCard'], .review-item")[:max_reviews]:
                review = {}

                rating_el = review_el.select_one(".ui_bubble_rating, .rating, [class*='bubble']")
                if rating_el:
                    rating_match = re.search(r"[\d.]+", str(rating_el.get("class", "")))
                    if not rating_match:
                        rating_match = re.search(r"[\d.]+", rating_el.get_text(strip=True))
                    if rating_match:
                        review["rating"] = float(rating_match.group())

                title_el = review_el.select_one(".quote, .title, [data-automation='reviewTitle']")
                if title_el:
                    review["title"] = title_el.get_text(strip=True)

                text_el = review_el.select_one(".partial_entry, .text, [data-automation='reviewBody']")
                if text_el:
                    review["text"] = text_el.get_text(strip=True)

                date_el = review_el.select_one(".ratingDate, .date, [data-automation='reviewDate']")
                if date_el:
                    review["date"] = date_el.get_text(strip=True)

                if review.get("text"):
                    reviews.append(review)

            return reviews
        except Exception as e:
            logger.error(f"TripAdvisor reviews error for {attraction_url}: {e}")
            return []

    def scrape_spot(self, name_en: str, max_reviews: int = 10) -> dict:
        logger.info(f"[TripAdvisor] Starting scrape for: {name_en}")

        result = {"spot": None, "reviews": [], "source": "tripadvisor"}

        search = self.search_spot(name_en)
        if not search:
            logger.warning(f"[TripAdvisor] Could not find spot: {name_en}")
            return result

        logger.info(f"[TripAdvisor] Found: {search.get('title', '')}")

        detail = self.get_spot_detail(search["attraction_url"])
        if detail:
            result["spot"] = detail

        reviews = self.get_reviews(search["attraction_url"], max_reviews=max_reviews)
        result["reviews"] = reviews
        logger.info(f"[TripAdvisor] Found {len(reviews)} reviews for {name_en}")

        return result
