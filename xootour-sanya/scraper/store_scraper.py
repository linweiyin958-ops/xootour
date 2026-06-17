import logging
import random
import time
from typing import Optional, List

import requests

from .config import AMAP_API_KEY, AMAP_BASE_URL, REQUEST_DELAY_MIN, REQUEST_DELAY_MAX

logger = logging.getLogger(__name__)


class StoreScraper:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or AMAP_API_KEY
        if not self.api_key:
            logger.warning("AMAP_API_KEY not set. StoreScraper will not work.")

    def _delay(self):
        time.sleep(random.uniform(0.3, 0.8))

    def search_pois_by_type(
        self,
        types: str,
        city: str = "三亚",
        citylimit: bool = True,
        keywords: str = "",
        max_count: int = 50,
    ) -> List[dict]:
        if not self.api_key:
            logger.error("AMAP_API_KEY not configured")
            return []

        all_pois = []
        page = 1
        offset = 25

        while len(all_pois) < max_count:
            url = f"{AMAP_BASE_URL}/place/text"
            params = {
                "key": self.api_key,
                "keywords": keywords,
                "types": types,
                "city": city,
                "citylimit": str(citylimit).lower(),
                "output": "JSON",
                "offset": offset,
                "page": page,
            }
            self._delay()
            try:
                resp = requests.get(url, params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()

                if data.get("status") != "1":
                    logger.warning(f"POI search failed: {data.get('info')}")
                    break

                pois = data.get("pois", [])
                if not pois:
                    break

                for poi in pois:
                    location = poi.get("location", "").split(",")
                    lng = float(location[0]) if len(location) == 2 else None
                    lat = float(location[1]) if len(location) == 2 else None

                    poi_data = {
                        "name_zh": poi.get("name", ""),
                        "lat": lat,
                        "lng": lng,
                        "district": poi.get("pname", "") + poi.get("cityname", "").replace("三亚市", ""),
                        "address_zh": poi.get("address", ""),
                        "adcode": poi.get("adcode", ""),
                        "tel": poi.get("tel", ""),
                        "type": poi.get("type", ""),
                        "typecode": poi.get("typecode", ""),
                    }
                    all_pois.append(poi_data)

                count = int(data.get("count", 0))
                if count < offset:
                    break

                page += 1
                if page > 50:
                    break

            except Exception as e:
                logger.error(f"POI search request error: {e}")
                break

        return all_pois[:max_count]

    def search_pois_by_keyword(
        self,
        keyword: str,
        city: str = "三亚",
        citylimit: bool = True,
        max_count: int = 25,
    ) -> List[dict]:
        if not self.api_key:
            logger.error("AMAP_API_KEY not configured")
            return []

        url = f"{AMAP_BASE_URL}/place/text"
        params = {
            "key": self.api_key,
            "keywords": keyword,
            "city": city,
            "citylimit": str(citylimit).lower(),
            "output": "JSON",
            "offset": max_count,
            "page": 1,
        }
        self._delay()
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") != "1":
                logger.warning(f"Keyword POI search failed for '{keyword}': {data.get('info')}")
                return []

            pois = []
            for poi in data.get("pois", []):
                location = poi.get("location", "").split(",")
                lng = float(location[0]) if len(location) == 2 else None
                lat = float(location[1]) if len(location) == 2 else None

                pois.append({
                    "name_zh": poi.get("name", ""),
                    "lat": lat,
                    "lng": lng,
                    "district": poi.get("pname", "") + poi.get("cityname", "").replace("三亚市", ""),
                    "address_zh": poi.get("address", ""),
                    "adcode": poi.get("adcode", ""),
                    "tel": poi.get("tel", ""),
                    "type": poi.get("type", ""),
                    "typecode": poi.get("typecode", ""),
                })

            return pois

        except Exception as e:
            logger.error(f"Keyword POI search error for '{keyword}': {e}")
            return []

    def search_pois_by_district(
        self,
        district: str,
        keywords: str = "",
        types: str = "",
        max_count: int = 25,
    ) -> List[dict]:
        if not self.api_key:
            logger.error("AMAP_API_KEY not configured")
            return []

        url = f"{AMAP_BASE_URL}/place/text"
        params = {
            "key": self.api_key,
            "keywords": keywords,
            "types": types,
            "city": "三亚",
            "citylimit": "true",
            "district": district,
            "output": "JSON",
            "offset": max_count,
            "page": 1,
        }
        self._delay()
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") != "1":
                logger.warning(f"District POI search failed: {data.get('info')}")
                return []

            pois = []
            for poi in data.get("pois", []):
                location = poi.get("location", "").split(",")
                lng = float(location[0]) if len(location) == 2 else None
                lat = float(location[1]) if len(location) == 2 else None

                pois.append({
                    "name_zh": poi.get("name", ""),
                    "lat": lat,
                    "lng": lng,
                    "district": district,
                    "address_zh": poi.get("address", ""),
                    "adcode": poi.get("adcode", ""),
                    "tel": poi.get("tel", ""),
                    "type": poi.get("type", ""),
                    "typecode": poi.get("typecode", ""),
                })

            return pois

        except Exception as e:
            logger.error(f"District POI search error: {e}")
            return []

    def get_poi_detail(self, poi_id: str) -> Optional[dict]:
        if not self.api_key:
            logger.error("AMAP_API_KEY not configured")
            return None

        url = f"{AMAP_BASE_URL}/place/detail"
        params = {
            "key": self.api_key,
            "id": poi_id,
            "output": "JSON",
        }
        self._delay()
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") == "1" and data.get("pois"):
                poi = data["pois"][0]
                location = poi.get("location", "").split(",")
                lng = float(location[0]) if len(location) == 2 else None
                lat = float(location[1]) if len(location) == 2 else None

                return {
                    "name_zh": poi.get("name", ""),
                    "lat": lat,
                    "lng": lng,
                    "district": poi.get("pname", ""),
                    "address_zh": poi.get("address", ""),
                    "tel": poi.get("tel", ""),
                    "type": poi.get("type", ""),
                    "photos": poi.get("photos", []),
                    "biz_ext": poi.get("biz_ext", {}),
                }
            return None
        except Exception as e:
            logger.error(f"POI detail error for id={poi_id}: {e}")
            return None

    def batch_search_by_category(self, category_config: dict, max_per_keyword: int = 25) -> List[dict]:
        all_pois = []
        seen_names = set()

        amap_types = category_config.get("amap_types", "")
        keywords_list = category_config.get("amap_keywords", [])

        if amap_types:
            logger.info(f"[StoreScraper] Searching by type code: {amap_types}")
            pois = self.search_pois_by_type(types=amap_types, max_count=max_per_keyword)
            for poi in pois:
                if poi["name_zh"] not in seen_names:
                    seen_names.add(poi["name_zh"])
                    all_pois.append(poi)

        for kw in keywords_list:
            logger.info(f"[StoreScraper] Searching by keyword: {kw}")
            pois = self.search_pois_by_keyword(keyword=kw, max_count=max_per_keyword)
            for poi in pois:
                if poi["name_zh"] not in seen_names:
                    seen_names.add(poi["name_zh"])
                    all_pois.append(poi)

        logger.info(f"[StoreScraper] Total unique POIs for {category_config.get('category_name_zh')}: {len(all_pois)}")
        return all_pois
