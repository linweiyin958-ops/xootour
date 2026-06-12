import json
import logging
from typing import Optional

from openai import OpenAI

from .config import (
    OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL,
    FREE_LLM_PROVIDER, QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL,
    GEMINI_API_KEY,
    OLLAMA_BASE_URL, OLLAMA_MODEL,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一名专业的深圳旅游景点数据结构化提取专家。你的任务是从多源原始数据（马蜂窝游记、携程景点信息、TripAdvisor英文点评、高德地图坐标）中，按照 XOOTOUR 系统的 L1~L5 分层结构，提取并结构化景点数据。

你必须严格按照以下JSON Schema输出，不要输出任何其他内容：

{
  "L1_base_and_info": {
    "name_zh": "中文全名",
    "name_en": "英文全名",
    "city_id": 2,
    "district": "深圳行政区（如：南山区）",
    "address_zh": "中文详细地址",
    "address_en": "英文详细地址",
    "lat": 0.0,
    "lng": 0.0,
    "seo_desc": "SEO描述，高度概括且包含关键词",
    "summary_zh": "中文详情介绍，200-400字",
    "summary_en": "英文详情介绍，面向外宾"
  },
  "L2_operations": {
    "open_hours": "开放时间",
    "transportation": "交通方式",
    "visit_notice": "参观须知",
    "base_price": 0.00,
    "rating": 0.0
  },
  "L3_ugc_trends": {
    "best_visit_season": "最佳游玩季节/时间",
    "photo_spots": [{"position": "打卡机位", "tip": "拍照提示"}],
    "crowd_tags": ["Solo", "Couple", "Family-friendly"]
  },
  "sub_tables": {
    "tour_spot_banner": [],
    "tour_spot_feature": [
      {"title": "亮点标题", "description": "亮点描述"}
    ],
    "tour_spot_route": [
      {
        "route_name": "路线名称",
        "duration_hours": 2.0,
        "route_nodes": ["节点1", "节点2"],
        "description": "路线描述与避坑指南"
      }
    ],
    "tour_spot_facility": [
      {"facility_name": "设施名称", "is_bold": false, "description": "补充说明"}
    ],
    "tour_spot_package": [
      {"package_name": "套餐名称", "price": 0.00, "description": "套餐说明", "currency": "RMB"}
    ]
  },
  "L5_quality_control": {
    "source_platform": "Mafengwo,Amap,Ctrip,TripAdvisor",
    "source_note_ids": ["来源URL1", "来源URL2"],
    "data_quality_score": 0.0,
    "is_ai_generated": true
  }
}

关键要求：
1. summary_zh 必须是AI二次转写的原创内容，不是原文复制
2. summary_en 必须面向外宾视角，语言自然专业
3. photo_spots 从游记中提炼最佳拍照机位
4. tour_spot_feature 提炼3-5个不重复亮点
5. tour_spot_route 从多篇游记整合1-2条最佳路线
6. tour_spot_facility 外宾重点关注无障碍、外卡、行李寄存
7. tour_spot_package 如无门票则为空数组
8. base_price: 0.00 代表免费开放
9. 所有图片URL保留原始链接，放入 tour_spot_banner
10. source_note_ids 填入实际采集到的数据源URL"""

SPOT_SUPPLEMENT_PROMPT = """你是一名专业的深圳旅游景点数据补充专家。已有部分字段通过规则提取完成，现在需要你补充AI生成的字段。

你必须严格按照以下JSON格式输出，只输出需要补充的字段，不要输出其他内容：

{
  "L1_base_and_info": {
    "address_en": "英文详细地址",
    "summary_zh": "中文详情介绍，200-400字，AI原创转写",
    "summary_en": "英文详情介绍，面向外宾，语言自然专业"
  },
  "L3_ugc_trends": {
    "best_visit_season": "最佳游玩季节/时间",
    "photo_spots": [{"position": "打卡机位", "tip": "拍照提示"}],
    "crowd_tags": ["Solo", "Couple", "Family-friendly"]
  },
  "sub_tables": {
    "tour_spot_feature": [
      {"title": "亮点标题", "description": "亮点描述"}
    ],
    "tour_spot_route": [
      {
        "route_name": "路线名称",
        "duration_hours": 2.0,
        "route_nodes": ["节点1", "节点2"],
        "description": "路线描述与避坑指南"
      }
    ],
    "tour_spot_facility": [
      {"facility_name": "设施名称", "is_bold": false, "description": "补充说明"}
    ]
  }
}

关键要求：
1. summary_zh 必须是AI原创转写，不是原文复制
2. summary_en 面向外宾，语言自然专业
3. photo_spots 从游记中提炼最佳拍照机位
4. tour_spot_feature 提炼3-5个不重复亮点
5. tour_spot_route 整合1-2条最佳路线
6. tour_spot_facility 外宾重点关注无障碍、外卡、行李寄存"""

STORE_SUPPLEMENT_PROMPT = """你是一名专业的深圳旅游服务门店数据补充专家。已有部分字段通过规则提取完成，现在需要你补充AI生成的字段。

你必须严格按照以下JSON格式输出，只输出需要补充的字段，不要输出其他内容：

{
  "L1_base_and_info": {
    "name_en": "英文名",
    "address_en": "英文详细地址",
    "summary_zh": "中文详情介绍，150-300字，AI原创转写",
    "summary_en": "英文详情介绍，面向外宾"
  },
  "L2_operations": {
    "visit_notice": "消费须知/注意事项",
    "signature_items": [{"name": "招牌/特色项名称", "description": "特色说明"}],
    "tags": ["外宾友好", "有英文菜单", "可刷外卡"],
    "ranking_desc": "排名描述",
    "cuisine_tags": ["菜系标签1", "菜系标签2"],
    "subratings": [{"category": "食物/服务/性价比/氛围", "rating": 4.5}]
  },
  "sub_tables": {
    "store_facility": [
      {"category": "设施分类", "facility_name": "设施名称", "is_bold": false, "description": "补充说明"}
    ],
    "store_product": [
      {"product_name": "产品/菜品/房型名称", "price": 0.00, "description": "产品描述", "is_signature": false, "sort_order": 1}
    ]
  }
}

关键要求：
1. summary_zh 必须是AI原创转写
2. summary_en 面向外宾，语言自然专业
3. signature_items 提炼3-5个招牌/特色项
4. tags 从数据中推断外宾友好特性
5. store_facility 外宾重点关注无障碍、外卡支持、WiFi等信息
6. store_product 构建2-5个代表性产品"""


class FreeLLMExtractor:
    def __init__(self):
        self.provider = FREE_LLM_PROVIDER
        if self.provider == "qwen":
            self.client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)
            self.model = QWEN_MODEL
        elif self.provider == "openai":
            self.client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
            self.model = OPENAI_MODEL
        elif self.provider == "ollama":
            self.client = OpenAI(api_key="ollama", base_url=OLLAMA_BASE_URL)
            self.model = OLLAMA_MODEL
        else:
            logger.warning(f"Unknown FREE_LLM_PROVIDER={self.provider}, defaulting to qwen")
            self.client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)
            self.model = QWEN_MODEL

    def _call_llm(self, system_prompt: str, user_prompt: str, temperature: float = 0.3, max_tokens: int = 4096) -> Optional[dict]:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content.strip()

            json_str = content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()

            return json.loads(json_str)
        except Exception as e:
            logger.error(f"[LLM] Call error: {e}")
            return None

    def supplement_spot(self, structured_data: dict, raw_data: dict) -> Optional[dict]:
        l1 = structured_data.get("L1_base_and_info", {})
        user_prompt = f"""已有景点数据：
name_zh: {l1.get('name_zh', '')}
name_en: {l1.get('name_en', '')}
district: {l1.get('district', '')}
address_zh: {l1.get('address_zh', '')}
lat: {l1.get('lat')}
lng: {l1.get('lng')}
open_hours: {l1.get('open_hours')}

原始采集数据：
马蜂窝: {json.dumps(raw_data.get('mafengwo', {}), ensure_ascii=False)[:2000]}
携程: {json.dumps(raw_data.get('ctrip', {}), ensure_ascii=False)[:2000]}
TripAdvisor: {json.dumps(raw_data.get('tripadvisor', {}), ensure_ascii=False)[:2000]}

请补充缺失的AI生成字段。"""
        return self._call_llm(SPOT_SUPPLEMENT_PROMPT, user_prompt)

    def supplement_store(self, structured_data: dict, raw_data: dict) -> Optional[dict]:
        l1 = structured_data.get("L1_base_and_info", {})
        l2 = structured_data.get("L2_operations", {})
        user_prompt = f"""已有门店数据：
name_zh: {l1.get('name_zh', '')}
district: {l1.get('district', '')}
address_zh: {l1.get('address_zh', '')}
open_hours: {l2.get('open_hours', '')}
phone: {l2.get('phone', '')}
price_range: {l2.get('price_range', '')}
rating: {l2.get('rating')}

原始采集数据：
大众点评: {json.dumps(raw_data.get('dianping', {}), ensure_ascii=False)[:2000]}

请补充缺失的AI生成字段。"""
        return self._call_llm(STORE_SUPPLEMENT_PROMPT, user_prompt)
