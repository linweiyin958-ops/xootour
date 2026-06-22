import requests
import time
import random
import logging
from typing import Optional

from .config import AMAP_API_KEY, AMAP_BASE_URL, REQUEST_DELAY_MIN, REQUEST_DELAY_MAX

logger = logging.getLogger(__name__)


class AmapClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or AMAP_API_KEY
        if not self.api_key:
            logger.warning("AMAP_API_KEY not set. AmapClient will not work.")

    def _delay(self):
        time.sleep(random.uniform(0.5, 1.5))

    def geocode(self, address: str, city: str = "厦门") -> Optional[dict]:
        url = f"{AMAP_BASE_URL}/geocode/geo"
        params = {
            "key": self.api_key,
            "address": address,
            "city": city,
            "output": "JSON",
        }
        self._delay()
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "1" and data.get("geocodes"):
                geo = data["geocodes"][0]
                location = geo.get("location", "").split(",")
                lng = float(location[0]) if len(location) == 2 else None
                lat = float(location[1]) if len(location) == 2 else None
                district = geo.get("district", "")
                formatted_address = geo.get("formatted_address", "")
                adcode = geo.get("adcode", "")
                return {
                    "lat": lat,
                    "lng": lng,
                    "district": district,
                    "address_zh": formatted_address,
                    "adcode": adcode,
                }
            else:
                logger.warning(f"Geocode failed for '{address}': {data.get('info')}")
                return None
        except Exception as e:
            logger.error(f"Geocode request error for '{address}': {e}")
            return None

    def search_poi(self, keywords: str, city: str = "厦门", citylimit: bool = True) -> Optional[dict]:
        url = f"{AMAP_BASE_URL}/place/text"
        params = {
            "key": self.api_key,
            "keywords": keywords,
            "city": city,
            "citylimit": str(citylimit).lower(),
            "output": "JSON",
            "offset": 5,
            "page": 1,
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
                    "district": poi.get("pname", "") + poi.get("cityname", "").replace("厦门市", ""),
                    "address_zh": poi.get("address", ""),
                    "adcode": poi.get("adcode", ""),
                    "tel": poi.get("tel", ""),
                }
            else:
                logger.warning(f"POI search failed for '{keywords}': {data.get('info')}")
                return None
        except Exception as e:
            logger.error(f"POI search request error for '{keywords}': {e}")
            return None

    def get_spot_geo(self, name_zh: str, address_hint: str = "") -> Optional[dict]:
        if not self.api_key:
            logger.error("AMAP_API_KEY not configured, skipping geocode")
            return None

        search_term = f"{name_zh}"
        if address_hint:
            search_term = f"{name_zh} {address_hint}"

        poi_result = self.search_poi(search_term)
        if poi_result and poi_result.get("lat") and poi_result.get("lng"):
            return poi_result

        geo_result = self.geocode(name_zh)
        if geo_result and geo_result.get("lat") and geo_result.get("lng"):
            return geo_result

        logger.error(f"Could not find geo data for '{name_zh}'")
        return None

