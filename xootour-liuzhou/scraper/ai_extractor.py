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

SYSTEM_PROMPT = """你是一名专业的柳州旅游景点数据结构化提取专家。你的任务是从多源原始数据（马蜂窝游记、携程景点信息、TripAdvisor英文点评、高德地图坐标）中，按照 XOOTOUR 系统的 L1~L5 分层结构，提取并结构化景点数据。

你必须严格按照以下JSON Schema输出，不要输出任何其他内容：

{
  "L1_base_and_info": {
    "name_zh": "中文全名",
    "name_en": "英文全名",
    "city_id": 10,
    "district": "柳州行政区（如：城中区）",
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

SPOT_SUPPLEMENT_PROMPT = """你是一名专业的柳州旅游景点数据补充专家。已有部分字段通过规则提取完成，现在需要你补充AI生成的字段。

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

STORE_SUPPLEMENT_PROMPT = """你是一名专业的柳州旅游服务门店数据补充专家。已有部分字段通过规则提取完成，现在需要你补充AI生成的字段。

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
      {"product_name": "菜品/产品名称", "price": 0.00, "description": "产品描述", "currency": "RMB", "is_signature": true, "sort_order": 1}
    ]
  }
}

关键要求：
1. summary_zh 必须是AI原创转写
2. summary_en 面向外宾，语言自然专业
3. tags 重点关注：外宾友好、有英文菜单/服务、可刷外卡、无障碍、有WiFi
4. signature_items 提炼3-5个最被推荐的特色项目
5. store_facility 外宾重点关注：英文菜单、外卡支付、无障碍、WiFi、行李寄存
6. subratings 可从名称/品类推断：餐饮有食物/服务/性价比，住宿有房间/服务/位置
7. cuisine_tags 仅餐饮类需要，其他品类留空数组
8. ranking_desc 若有排名信息则填写，否则留空
9. store_product 从 signature_items 中提炼核心产品：餐饮为菜品，住宿为房型，购物为热门商品，其他为核心服务"""


class FreeLLMExtractor:
    def __init__(self, provider: str = None):
        self.provider = (provider or FREE_LLM_PROVIDER).lower()
        self.client = None
        self.model = ""
        self._init_client()

    def _init_client(self):
        if self.provider == "qwen":
            api_key = QWEN_API_KEY
            base_url = QWEN_BASE_URL
            self.model = QWEN_MODEL
            if not api_key:
                logger.warning("QWEN_API_KEY not set. FreeLLM will not work.")
                return
        elif self.provider == "openai":
            api_key = OPENAI_API_KEY
            base_url = OPENAI_BASE_URL
            self.model = OPENAI_MODEL
            if not api_key:
                logger.warning("OPENAI_API_KEY not set. FreeLLM will not work.")
                return
        elif self.provider == "ollama":
            api_key = "ollama"
            base_url = OLLAMA_BASE_URL + "/v1"
            self.model = OLLAMA_MODEL
        elif self.provider == "gemini":
            api_key = GEMINI_API_KEY
            base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
            self.model = "gemini-2.0-flash"
            if not api_key:
                logger.warning("GEMINI_API_KEY not set. FreeLLM will not work.")
                return
        else:
            logger.error(f"Unknown LLM provider: {self.provider}")
            return

        try:
            self.client = OpenAI(api_key=api_key, base_url=base_url)
            logger.info(f"[FreeLLM] Initialized: provider={self.provider}, model={self.model}")
        except Exception as e:
            logger.error(f"[FreeLLM] Init error: {e}")

    def _call_llm(self, system_prompt: str, user_prompt: str) -> Optional[dict]:
        if not self.client:
            logger.error("[FreeLLM] Client not initialized, skipping")
            return None

        logger.info(f"[FreeLLM] Calling {self.provider}/{self.model}...")

        content = None
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=4096,
                stream=False,
            )
            if hasattr(response, 'choices') and response.choices:
                content = response.choices[0].message.content.strip()
                logger.info(f"[FreeLLM] OpenAI client success, got {len(content)} chars")
        except Exception as e:
            logger.info(f"[FreeLLM] OpenAI client failed ({e}), trying raw HTTP...")

        if not content:
            content = self._call_llm_raw(system_prompt, user_prompt)

        if not content:
            logger.error("[FreeLLM] No content from any method")
            return None

        return self._parse_llm_response(content)

    def _call_llm_raw(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        import requests as req
        base = str(self.client.base_url).rstrip("/")
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 4096,
        }
        try:
            resp = req.post(
                base + "/chat/completions",
                headers={"Authorization": f"Bearer {self.client.api_key}", "Content-Type": "application/json"},
                json=body,
                timeout=(30, 120),
                stream=True,
            )
        except Exception as e:
            logger.error(f"[FreeLLM] HTTP request failed: {e}")
            return None

        if resp.status_code != 200:
            logger.error(f"[FreeLLM] HTTP {resp.status_code}: {resp.text[:200]}")
            return None

        ct = resp.headers.get("content-type", "")
        if "event-stream" in ct or "text/event-stream" in ct:
            content = ""
            try:
                for chunk in resp.iter_content(chunk_size=None, decode_unicode=True):
                    if not chunk:
                        continue
                    for line in chunk.split("\n"):
                        line = line.strip()
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk_data = json.loads(data_str)
                                if "choices" in chunk_data and chunk_data["choices"]:
                                    delta = chunk_data["choices"][0].get("delta", {})
                                    content += delta.get("content", "")
                            except json.JSONDecodeError:
                                pass
            except Exception as e:
                logger.error(f"[FreeLLM] SSE read error: {e}")
        else:
            try:
                data = resp.json()
                if "choices" in data:
                    content = data["choices"][0]["message"]["content"]
                else:
                    content = ""
            except Exception:
                content = ""

        if content:
            logger.info(f"[FreeLLM] Raw HTTP success, got {len(content)} chars")
            return content
        return None

    def _parse_llm_response(self, content: str) -> Optional[dict]:
        if not content:
            return None
        try:
            json_match = content
            if "```json" in content:
                json_match = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_match = content.split("```")[1].split("```")[0].strip()
            result = json.loads(json_match)
            logger.info(f"[FreeLLM] Successfully extracted data via {self.provider}")
            return result
        except json.JSONDecodeError as e:
            logger.error(f"[FreeLLM] JSON parse error: {e}")
            logger.error(f"[FreeLLM] Raw response: {content[:500]}")
            return None

    def supplement_spot(self, rule_data: dict, raw_data: dict) -> Optional[dict]:
        prompt = self._build_spot_supplement_prompt(rule_data, raw_data)
        return self._call_llm(SPOT_SUPPLEMENT_PROMPT, prompt)

    def supplement_store(self, rule_data: dict, raw_data: dict) -> Optional[dict]:
        prompt = self._build_store_supplement_prompt(rule_data, raw_data)
        return self._call_llm(STORE_SUPPLEMENT_PROMPT, prompt)

    def extract_full_spot(self, spot_info: dict, mafengwo_data: dict, ctrip_data: dict, tripadvisor_data: dict) -> Optional[dict]:
        prompt = self._build_full_spot_prompt(spot_info, mafengwo_data, ctrip_data, tripadvisor_data)
        return self._call_llm(SYSTEM_PROMPT, prompt)

    def _build_spot_supplement_prompt(self, rule_data: dict, raw_data: dict) -> str:
        parts = []
        l1 = rule_data.get("L1_base_and_info", {})
        parts.append(f"## 景点基本信息(规则已提取)\n名称：{l1.get('name_zh', '')} / {l1.get('name_en', '')}\n")
        parts.append(f"行政区：{l1.get('district', '')}\n地址：{l1.get('address_zh', '')}\n")

        l2 = rule_data.get("L2_operations", {})
        if l2.get("open_hours"):
            parts.append(f"开放时间：{l2['open_hours']}\n")
        if l2.get("transportation"):
            parts.append(f"交通方式：{l2['transportation']}\n")

        if raw_data.get("mafengwo", {}).get("notes"):
            parts.append("\n### 马蜂窝游记摘要\n")
            for i, note in enumerate(raw_data["mafengwo"]["notes"][:3], 1):
                parts.append(f"游记{i}: {note.get('title', '')}\n")
                if note.get("content"):
                    parts.append(note["content"][:800] + "\n")

        if raw_data.get("tripadvisor", {}).get("reviews"):
            parts.append("\n### TripAdvisor外宾点评\n")
            for i, review in enumerate(raw_data["tripadvisor"]["reviews"][:5], 1):
                parts.append(f"Review{i}: {review.get('text', '')[:400]}\n")

        return "\n".join(parts)

    def _build_store_supplement_prompt(self, rule_data: dict, raw_data: dict) -> str:
        parts = []
        l1 = rule_data.get("L1_base_and_info", {})
        l2 = rule_data.get("L2_operations", {})
        parts.append(f"## 门店基本信息(规则已提取)\n名称：{l1.get('name_zh', '')}\n")
        parts.append(f"品类ID：{l1.get('category_id', '')}\n")
        parts.append(f"行政区：{l1.get('district', '')}\n地址：{l1.get('address_zh', '')}\n")
        if l2.get("open_hours"):
            parts.append(f"营业时间：{l2['open_hours']}\n")
        if l2.get("price_range"):
            parts.append(f"价格区间：{l2['price_range']}\n")

        dianping = raw_data.get("dianping", {})
        if dianping.get("reviews"):
            parts.append("\n### 大众点评用户评价\n")
            for i, review in enumerate(dianping["reviews"][:5], 1):
                parts.append(f"评价{i}: {review.get('text', '')[:400]}\n")

        return "\n".join(parts)

    def _build_full_spot_prompt(self, spot_info, mafengwo_data, ctrip_data, tripadvisor_data):
        parts = []
        parts.append(f"## 目标景点信息\n名称：{spot_info.get('name_zh', '')} / {spot_info.get('name_en', '')}\n")

        if mafengwo_data.get("spot"):
            parts.append("## 马蜂窝景点数据\n")
            parts.append(json.dumps(mafengwo_data["spot"], ensure_ascii=False, indent=2))
            if mafengwo_data.get("notes"):
                parts.append("\n### 马蜂窝热门游记\n")
                for i, note in enumerate(mafengwo_data["notes"][:5], 1):
                    parts.append(f"\n--- 游记{i}: {note.get('title', '')} ---")
                    if note.get("content"):
                        parts.append(note["content"][:1500])
                    if note.get("images"):
                        parts.append(f"\n图片链接: {json.dumps(note['images'][:5], ensure_ascii=False)}")

        if ctrip_data.get("spot"):
            parts.append("\n## 携程景点数据\n")
            parts.append(json.dumps(ctrip_data["spot"], ensure_ascii=False, indent=2))
            if ctrip_data.get("packages"):
                parts.append("\n### 携程门票套餐\n")
                parts.append(json.dumps(ctrip_data["packages"], ensure_ascii=False, indent=2))

        if tripadvisor_data.get("spot"):
            parts.append("\n## TripAdvisor景点数据\n")
            parts.append(json.dumps(tripadvisor_data["spot"], ensure_ascii=False, indent=2))
            if tripadvisor_data.get("reviews"):
                parts.append("\n### TripAdvisor外宾点评\n")
                for i, review in enumerate(tripadvisor_data["reviews"][:10], 1):
                    parts.append(f"\n--- Review {i} (Rating: {review.get('rating', 'N/A')}) ---")
                    if review.get("title"):
                        parts.append(f"Title: {review['title']}")
                    if review.get("text"):
                        parts.append(review["text"][:800])

        return "\n".join(parts)


class AIExtractor:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or OPENAI_API_KEY
        self.base_url = base_url or OPENAI_BASE_URL
        self.model = model or OPENAI_MODEL

        if not self.api_key:
            logger.warning("OPENAI_API_KEY not set. AIExtractor will not work.")
            self.client = None
        else:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )

    def extract(self, spot_info: dict, mafengwo_data: dict, ctrip_data: dict, tripadvisor_data: dict) -> Optional[dict]:
        if not self.client:
            logger.error("OPENAI_API_KEY not configured, skipping AI extraction")
            return None

        prompt = self._build_prompt(spot_info, mafengwo_data, ctrip_data, tripadvisor_data)

        logger.info(f"[AI] Calling {self.model} for structured extraction...")

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=4096,
            )

            content = response.choices[0].message.content.strip()

            json_match = content
            if "```json" in content:
                json_match = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_match = content.split("```")[1].split("```")[0].strip()

            result = json.loads(json_match)
            logger.info("[AI] Successfully extracted structured data")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"[AI] JSON parse error: {e}")
            logger.error(f"[AI] Raw response: {content[:500]}")
            return None
        except Exception as e:
            logger.error(f"[AI] Extraction error: {e}")
            return None

    def _build_prompt(self, spot_info: dict, mafengwo_data: dict, ctrip_data: dict, tripadvisor_data: dict) -> str:
        parts = []

        parts.append(f"## 目标景点信息\n名称：{spot_info.get('name_zh', '')} / {spot_info.get('name_en', '')}\n")

        if mafengwo_data.get("spot"):
            parts.append("## 马蜂窝景点数据\n")
            parts.append(json.dumps(mafengwo_data["spot"], ensure_ascii=False, indent=2))
            if mafengwo_data.get("notes"):
                parts.append("\n### 马蜂窝热门游记\n")
                for i, note in enumerate(mafengwo_data["notes"][:5], 1):
                    parts.append(f"\n--- 游记{i}: {note.get('title', '')} ---")
                    if note.get("content"):
                        parts.append(note["content"][:1500])
                    if note.get("images"):
                        parts.append(f"\n图片链接: {json.dumps(note['images'][:5], ensure_ascii=False)}")

        if ctrip_data.get("spot"):
            parts.append("\n## 携程景点数据\n")
            parts.append(json.dumps(ctrip_data["spot"], ensure_ascii=False, indent=2))
            if ctrip_data.get("packages"):
                parts.append("\n### 携程门票套餐\n")
                parts.append(json.dumps(ctrip_data["packages"], ensure_ascii=False, indent=2))

        if tripadvisor_data.get("spot"):
            parts.append("\n## TripAdvisor景点数据\n")
            parts.append(json.dumps(tripadvisor_data["spot"], ensure_ascii=False, indent=2))
            if tripadvisor_data.get("reviews"):
                parts.append("\n### TripAdvisor外宾点评\n")
                for i, review in enumerate(tripadvisor_data["reviews"][:10], 1):
                    parts.append(f"\n--- Review {i} (Rating: {review.get('rating', 'N/A')}) ---")
                    if review.get("title"):
                        parts.append(f"Title: {review['title']}")
                    if review.get("text"):
                        parts.append(review["text"][:800])

        return "\n".join(parts)
