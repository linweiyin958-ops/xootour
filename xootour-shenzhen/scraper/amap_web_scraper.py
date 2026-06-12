import json
import logging
import random
import re
import time
from typing import Optional, List
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from .config import (
    HEADERS, REQUEST_DELAY_MIN, REQUEST_DELAY_MAX,
    NOMINATIM_USER_AGENT,
)

logger = logging.getLogger(__name__)

AMAP_SEARCH_URL = "https://www.amap.com/search"
AMAP_DETAIL_URL = "https://www.amap.com/detail"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


class AmapWebScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.headers.update({
            "Referer": "https://www.amap.com/",
            "Host": "www.amap.com",
        })

    def _delay(self):
        time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))

    def _parse_search_json(self, html: str) -> list:
        pois = []
        json_patterns = [
            r'window\._INIT_DATA\s*=\s*({.*?});',
            r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
            r'"poiList"\s*:\s*(\[.*?\])',
            r'"pois"\s*:\s*(\[.*?\])',
        ]
        for pattern in json_patterns:
            matches = re.findall(pattern, html, re.DOTALL)
            for match in matches:
                try:
                    data = json.loads(match)
                    if isinstance(data, dict):
                        for key in ("poiList", "pois", "data", "resultList", "items"):
                            found = data.get(key)
                            if isinstance(found, list):
                                pois.extend(found)
                        if not pois and "poi" in data:
                            pois.append(data["poi"])
                    elif isinstance(data, list):
                        pois.extend(data)
                except (json.JSONDecodeError, TypeError):
                    continue

        if not pois:
            soup = BeautifulSoup(html, "lxml")
            for item in soup.select("[class*='poi-item'], [class*='search-item'], .result-item"):
                poi = {}
                name_el = item.select_one("[class*='name'], [class*='title'], h3, h4")
                if name_el:
                    poi["name"] = name_el.get_text(strip=True)
                addr_el = item.select_one("[class*='addr'], [class*='address']")
                if addr_el:
                    poi["address"] = addr_el.get_text(strip=True)
                tel_el = item.select_one("[class*='tel'], [class*='phone']")
                if tel_el:
                    poi["tel"] = tel_el.get_text(strip=True)
                if poi.get("name"):
                    pois.append(poi)

        return pois

    def _normalize_poi(self, poi: dict) -> Optional[dict]:
        name = poi.get("name", "")
        if not name:
            return None

        lat = None
        lng = None
        location = poi.get("location", "")
        if location:
            parts = str(location).split(",")
            if len(parts) == 2:
                try:
                    lng = float(parts[0])
                    lat = float(parts[1])
                except ValueError:
                    pass

        if lat is None and lng is None:
            for key in ("latitude", "lat"), ("longitude", "lng", "lon"):
                for k in key:
                    if k in poi:
                        if "lat" in k:
                            lat = float(poi[k]) if poi[k] else None
                        else:
                            lng = float(poi[k]) if poi[k] else None

        pname = poi.get("pname", "") or poi.get("province", "")
        cityname = poi.get("cityname", "") or poi.get("city", "")
        district = poi.get("adname", "") or poi.get("district", "")
        if not district and pname:
            district = pname
            if cityname:
                district = cityname
            if pname and pname != cityname:
                district = pname + cityname.replace("深圳市", "")

        return {
            "name_zh": name,
            "lat": lat,
            "lng": lng,
            "district": district,
            "address_zh": poi.get("address", "") or poi.get("addr", ""),
            "adcode": poi.get("adcode", "") or poi.get("adId", ""),
            "tel": poi.get("tel", "") or poi.get("phone", ""),
            "type": poi.get("type", "") or poi.get("category", ""),
            "rating": poi.get("rating", ""),
            "cost": poi.get("cost", "") or poi.get("price", ""),
        }

    def search_geo(self, name_zh: str, keywords: str = "") -> Optional[dict]:
        search_term = keywords or name_zh
        logger.info(f"[AmapWeb] Searching geo for: {search_term}")

        result = self._amap_search(search_term)
        if result:
            return result

        logger.info(f"[AmapWeb] Amap search no result, trying Nominatim fallback...")
        return self._nominatim_search(name_zh)

    def _amap_search(self, keyword: str, city: str = "深圳") -> Optional[dict]:
        self._delay()
        try:
            params = {
                "query": keyword,
                "city": city,
                "geo": "l",
            }
            resp = self.session.get(AMAP_SEARCH_URL, params=params, timeout=15)
            resp.raise_for_status()

            pois = self._parse_search_json(resp.text)
            if pois:
                normalized = self._normalize_poi(pois[0])
                if normalized:
                    logger.info(f"[AmapWeb] Found: {normalized['name_zh']} ({normalized.get('lat')}, {normalized.get('lng')})")
                    return normalized

            logger.warning(f"[AmapWeb] No result for '{keyword}'")
            return None
        except Exception as e:
            logger.error(f"[AmapWeb] Search error for '{keyword}': {e}")
            return None

    def _nominatim_search(self, name: str, city: str = "Shenzhen") -> Optional[dict]:
        self._delay()
        try:
            params = {
                "q": f"{name}, {city}, China",
                "format": "json",
                "limit": 1,
                "addressdetails": 1,
                "extratags": 1,
            }
            headers = {"User-Agent": NOMINATIM_USER_AGENT}
            resp = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if data:
                item = data[0]
                lat = float(item.get("lat", 0))
                lng = float(item.get("lon", 0))
                address = item.get("address", {})
                district = address.get("city_district", "") or address.get("suburb", "") or address.get("city", "")

                return {
                    "name_zh": name,
                    "lat": lat,
                    "lng": lng,
                    "district": district,
                    "address_zh": item.get("display_name", ""),
                    "adcode": "",
                    "tel": "",
                    "type": item.get("type", ""),
                    "rating": "",
                    "cost": "",
                    "source": "nominatim",
                }

            logger.warning(f"[Nominatim] No result for '{name}'")
            return None
        except Exception as e:
            logger.error(f"[Nominatim] Search error for '{name}': {e}")
            return None

    def search_pois(self, keyword: str, city: str = "深圳", max_count: int = 25) -> List[dict]:
        logger.info(f"[AmapWeb] Searching POIs: {keyword}")
        all_pois = []

        self._delay()
        try:
            params = {
                "query": keyword,
                "city": city,
                "geo": "l",
            }
            resp = self.session.get(AMAP_SEARCH_URL, params=params, timeout=15)
            resp.raise_for_status()

            raw_pois = self._parse_search_json(resp.text)
            for poi in raw_pois[:max_count]:
                normalized = self._normalize_poi(poi)
                if normalized:
                    all_pois.append(normalized)

            logger.info(f"[AmapWeb] Found {len(all_pois)} POIs for '{keyword}'")
        except Exception as e:
            logger.error(f"[AmapWeb] POI search error for '{keyword}': {e}")

        return all_pois

    def batch_search_by_category(self, category_config: dict, max_per_keyword: int = 25) -> List[dict]:
        all_pois = []
        seen_names = set()

        keywords_list = category_config.get("amap_keywords", [])
        amap_types = category_config.get("amap_types", "")

        for kw in keywords_list:
            logger.info(f"[AmapWeb] Category search: {kw}")
            pois = self.search_pois(kw, max_count=max_per_keyword)
            for poi in pois:
                if poi["name_zh"] not in seen_names:
                    seen_names.add(poi["name_zh"])
                    all_pois.append(poi)

        if not all_pois and amap_types:
            type_keywords = {
                "050000": "餐厅",
                "100000": "酒店",
                "110000": "景区",
                "140000": "博物馆",
                "060000": "购物中心",
                "080000": "娱乐",
            }
            fallback_kw = type_keywords.get(amap_types, category_config.get("category_name_zh", ""))
            logger.info(f"[AmapWeb] Fallback search by type keyword: {fallback_kw}")
            pois = self.search_pois(fallback_kw, max_count=max_per_keyword)
            for poi in pois:
                if poi["name_zh"] not in seen_names:
                    seen_names.add(poi["name_zh"])
                    all_pois.append(poi)

        logger.info(f"[AmapWeb] Total unique POIs for {category_config.get('category_name_zh')}: {len(all_pois)}")
        return all_pois
