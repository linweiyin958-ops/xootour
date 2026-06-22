import logging
import re
from typing import Optional

from .config import HARBIN_CITY_ID, HARBIN_DISTRICTS

logger = logging.getLogger(__name__)


class RuleExtractor:
    def extract_spot(
        self,
        spot_info: dict,
        geo_data: Optional[dict],
        mafengwo_data: dict,
        ctrip_data: dict,
        tripadvisor_data: dict,
    ) -> dict:
        l1 = {
            "name_zh": spot_info.get("name_zh", ""),
            "name_en": spot_info.get("name_en", ""),
            "city_id": HARBIN_CITY_ID,
            "district": "",
            "address_zh": "",
            "address_en": "",
            "lat": None,
            "lng": None,
            "cover_img": "",
            "seo_desc": "",
            "summary_zh": "",
            "summary_en": "",
        }
        l2 = {
            "open_hours": "",
            "transportation": "",
            "visit_notice": "",
            "base_price": 0.00,
            "rating": 0.0,
        }
        l3 = {
            "best_visit_season": "",
            "photo_spots": [],
            "crowd_tags": [],
        }
        sub = {
            "tour_spot_banner": [],
            "tour_spot_feature": [],
            "tour_spot_route": [],
            "tour_spot_facility": [],
            "tour_spot_package": [],
        }

        if geo_data:
            l1["lat"] = geo_data.get("lat")
            l1["lng"] = geo_data.get("lng")
            l1["district"] = geo_data.get("district", "")
            l1["address_zh"] = geo_data.get("address_zh", "")

        self._merge_mafengwo(l1, l2, l3, sub, mafengwo_data)
        self._merge_ctrip(l1, l2, sub, ctrip_data)
        self._merge_tripadvisor(l1, l2, sub, tripadvisor_data)

        if l1["name_zh"] and l1["name_en"]:
            l1["seo_desc"] = f"{l1['name_zh']}({l1['name_en']})哈尔滨旅游指南 - 游玩攻略、开放时间、交通路线"
        elif l1["name_zh"]:
            l1["seo_desc"] = f"{l1['name_zh']}哈尔滨旅游指南 - 游玩攻略、开放时间、交通路线"

        if not l1["cover_img"] and sub["tour_spot_banner"]:
            l1["cover_img"] = sub["tour_spot_banner"][0].get("image_url", "")

        return {
            "L1_base_and_info": l1,
            "L2_operations": l2,
            "L3_ugc_trends": l3,
            "sub_tables": sub,
        }

    def _merge_mafengwo(self, l1, l2, l3, sub, mafengwo_data: dict):
        spot = mafengwo_data.get("spot", {})
        if not spot:
            return

        if not l1.get("district") and spot.get("address"):
            addr = spot["address"]
            for d in HARBIN_DISTRICTS:
                if d in addr:
                    l1["district"] = d
                    break

        if not l1.get("address_zh") and spot.get("address"):
            l1["address_zh"] = spot["address"]

        if spot.get("rating"):
            l2["rating"] = max(l2["rating"], float(spot["rating"]))

        if spot.get("open_hours") and not l2["open_hours"]:
            l2["open_hours"] = spot["open_hours"]

        if spot.get("transportation") and not l2["transportation"]:
            l2["transportation"] = spot["transportation"]

        if spot.get("price_info"):
            price_match = re.search(r"[\d.]+", spot["price_info"])
            if price_match and l2["base_price"] == 0.00:
                l2["base_price"] = float(price_match.group())

        if spot.get("summary") and not l1["summary_zh"]:
            l1["summary_zh"] = spot["summary"]

        if spot.get("images"):
            for i, img_url in enumerate(spot["images"][:10], 1):
                sub["tour_spot_banner"].append({
                    "image_url": img_url,
                    "sort_order": i,
                    "photo_credit": "Mafengwo",
                })

        for note in mafengwo_data.get("notes", []):
            if note.get("images"):
                for img_url in note["images"][:3]:
                    if not any(b["image_url"] == img_url for b in sub["tour_spot_banner"]):
                        sub["tour_spot_banner"].append({
                            "image_url": img_url,
                            "sort_order": len(sub["tour_spot_banner"]) + 1,
                            "photo_credit": f"Mafengwo@{note.get('meta', {}).get('author', '')}",
                        })

    def _merge_ctrip(self, l1, l2, sub, ctrip_data: dict):
        spot = ctrip_data.get("spot", {})
        if not spot:
            return

        if not l1.get("address_zh") and spot.get("address"):
            l1["address_zh"] = spot["address"]

        if spot.get("rating"):
            l2["rating"] = max(l2["rating"], float(spot["rating"]))

        if spot.get("open_hours") and not l2["open_hours"]:
            l2["open_hours"] = spot["open_hours"]

        if spot.get("transportation") and not l2["transportation"]:
            l2["transportation"] = spot["transportation"]

        if spot.get("visit_notice") and not l2["visit_notice"]:
            l2["visit_notice"] = spot["visit_notice"]

        if spot.get("summary") and not l1["summary_zh"]:
            l1["summary_zh"] = spot["summary"]

        if spot.get("images"):
            for img_url in spot["images"][:5]:
                if not any(b["image_url"] == img_url for b in sub["tour_spot_banner"]):
                    sub["tour_spot_banner"].append({
                        "image_url": img_url,
                        "sort_order": len(sub["tour_spot_banner"]) + 1,
                        "photo_credit": "Ctrip",
                    })

        for pkg in ctrip_data.get("packages", []):
            sub["tour_spot_package"].append({
                "package_name": pkg.get("package_name", ""),
                "price": pkg.get("price", 0.00),
                "description": pkg.get("description", ""),
                "currency": "RMB",
            })
            if pkg.get("price") and l2["base_price"] == 0.00:
                l2["base_price"] = float(pkg["price"])

    def _merge_tripadvisor(self, l1, l2, sub, ta_data: dict):
        spot = ta_data.get("spot", {})
        if not spot:
            return

        if spot.get("address_en") and not l1["address_en"]:
            l1["address_en"] = spot["address_en"]

        if spot.get("about_en") and not l1["summary_en"]:
            l1["summary_en"] = spot["about_en"]

        if spot.get("open_hours_en") and not l2["open_hours"]:
            l2["open_hours"] = spot["open_hours_en"]

        if spot.get("images"):
            for img_url in spot["images"][:5]:
                if not any(b["image_url"] == img_url for b in sub["tour_spot_banner"]):
                    sub["tour_spot_banner"].append({
                        "image_url": img_url,
                        "sort_order": len(sub["tour_spot_banner"]) + 1,
                        "photo_credit": "TripAdvisor",
                    })

    def extract_store(
        self,
        poi_data: dict,
        dianping_data: dict,
        category_config: dict,
    ) -> dict:
        cat_name = category_config.get("category_name_zh", "")
        cat_id = category_config.get("category_id", 0)

        l1 = {
            "name_zh": poi_data.get("name_zh", ""),
            "name_en": "",
            "category_id": cat_id,
            "city_id": HARBIN_CITY_ID,
            "district": poi_data.get("district", ""),
            "address_zh": poi_data.get("address_zh", ""),
            "address_en": "",
            "lat": poi_data.get("lat"),
            "lng": poi_data.get("lng"),
            "cover_img": "",
            "seo_desc": "",
            "summary_zh": "",
            "summary_en": "",
        }
        l2 = {
            "open_hours": "",
            "phone": poi_data.get("tel", ""),
            "website": "",
            "price_range": "",
            "rating": 0.0,
            "review_count": 0,
            "ranking_desc": "",
            "cuisine_tags": "[]",
            "michelin_status": 0,
            "visit_notice": "",
            "signature_items": [],
            "tags": [],
        }
        sub = {
            "store_banner": [],
            "store_product": [],
            "store_facility": [],
        }

        self._merge_dianping_store(l1, l2, sub, dianping_data)

        if l1["name_zh"] and l1["name_en"]:
            l1["seo_desc"] = f"{l1['name_zh']}({l1['name_en']})-{cat_name}哈尔滨旅游服务指南"
        elif l1["name_zh"]:
            l1["seo_desc"] = f"{l1['name_zh']}-{cat_name}哈尔滨旅游服务指南"

        if not l1["cover_img"] and sub["store_banner"]:
            l1["cover_img"] = sub["store_banner"][0].get("image_url", "")

        if cat_config := category_config:
            l2["category_specific_fields"] = self._build_category_specific_fields(cat_config, poi_data, dianping_data)

        return {
            "L1_base_and_info": l1,
            "L2_operations": l2,
            "sub_tables": sub,
        }

    def _build_category_specific_fields(self, category_config: dict, poi_data: dict, dianping_data: dict) -> dict:
        cat_name = category_config.get("category_name_zh", "")
        cat_id = category_config.get("category_id", 0)
        fields = {}

        if cat_id == 1:  # 美食
            fields["cuisine_type"] = ""
            fields["meal_type"] = []
            fields["seating_capacity"] = None
            fields["private_rooms"] = None
            fields["parking"] = False
            fields["delivery"] = False
            fields["reservation"] = False
            fields["signature_dishes"] = []
            fields["michelin_star"] = None
        elif cat_id == 2:  # 酒店
            fields["hotel_level"] = ""
            fields["star_rating"] = ""
            fields["room_count"] = None
            fields["room_types"] = []
            fields["check_in_time"] = ""
            fields["check_out_time"] = ""
            fields["facilities"] = []
            fields["nearby_attractions"] = []
            fields["cancellation_policy"] = ""
        elif cat_id == 3:  # 景点
            fields["attraction_type"] = ""
            fields["ticket_price"] = ""
            fields["ticket_policy"] = ""
            fields["open_time"] = ""
            fields["suggested_duration"] = ""
            fields["best_season"] = ""
            fields["must_see_spots"] = []
            fields["official_website"] = ""
            fields["accessibility"] = ""
        elif cat_id == 4:  # 购物
            fields["mall_type"] = ""
            fields["total_area"] = ""
            fields["anchor_stores"] = []
            fields["brand_count"] = None
            fields["parking_spaces"] = None
            fields["metro_access"] = ""
            fields["tax_free"] = False
            fields["highlights"] = []
        elif cat_id == 5:  # 娱乐
            fields["entertainment_type"] = ""
            fields["price_range"] = ""
            fields["group_size"] = ""
            fields["duration"] = ""
            fields["age_limit"] = ""
            fields["booking_required"] = False
            fields["vr_ar_support"] = False
            fields["online_rating"] = None
            fields["popular_activities"] = []

        return fields

    def _merge_dianping_store(self, l1, l2, sub, dianping_data: dict):
        shop = dianping_data.get("shop", {})
        if not shop:
            return

        if shop.get("rating"):
            l2["rating"] = float(shop["rating"])

        if shop.get("avg_price"):
            l2["price_range"] = f"人均¥{int(shop['avg_price'])}"

        if shop.get("open_hours") and not l2["open_hours"]:
            l2["open_hours"] = shop["open_hours"]

        if shop.get("phone") and not l2["phone"]:
            l2["phone"] = shop["phone"]

        if shop.get("address_zh") and not l1["address_zh"]:
            l1["address_zh"] = shop["address_zh"]

        if shop.get("summary") and not l1["summary_zh"]:
            l1["summary_zh"] = shop["summary"]

        if shop.get("tags"):
            l2["tags"] = shop["tags"][:10]

        if shop.get("images"):
            for i, img_url in enumerate(shop["images"][:10], 1):
                sub["store_banner"].append({
                    "image_url": img_url,
                    "sort_order": i,
                    "photo_credit": "Dianping",
                })

        for p in dianping_data.get("products", []):
            product = {
                "product_name": p.get("product_name", ""),
                "price": p.get("price"),
                "description": p.get("description", ""),
                "currency": "RMB",
                "is_signature": p.get("is_signature", False),
                "sort_order": 0,
                "images": [],
            }
            if p.get("image_url"):
                product["images"].append({"image_url": p["image_url"]})
            sub["store_product"].append(product)

        for review in dianping_data.get("reviews", []):
            text = review.get("text", "")
            if "外卡" in text or "visa" in text.lower():
                l2["tags"].append("可刷外卡")
            if "英文" in text or "english" in text.lower():
                l2["tags"].append("有英文服务")
            if "无障碍" in text or "wheelchair" in text.lower():
                l2["tags"].append("无障碍")
            if "WiFi" in text or "wifi" in text.lower() or "无线" in text:
                l2["tags"].append("有WiFi")

        l2["tags"] = list(set(l2["tags"]))[:10]
