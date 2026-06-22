import os
from dotenv import load_dotenv

load_dotenv()

AMAP_API_KEY = os.getenv("AMAP_API_KEY", "")
AMAP_BASE_URL = "https://restapi.amap.com/v3"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

FREE_LLM_PROVIDER = os.getenv("FREE_LLM_PROVIDER", "qwen")

QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-plus")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

NOMINATIM_USER_AGENT = os.getenv("NOMINATIM_USER_AGENT", "xootour-scraper/1.0")

NANJING_CITY_ID = 2

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "xootour_nanjing")
DB_CHARSET = os.getenv("DB_CHARSET", "utf8mb4")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

MAFENGWO_BASE_URL = "https://www.mafengwo.cn"
CTRIP_BASE_URL = "https://you.ctrip.com"
TRIPADVISOR_BASE_URL = "https://www.tripadvisor.com"
DIANPING_BASE_URL = "https://www.dianping.com"

REQUEST_DELAY_MIN = 2
REQUEST_DELAY_MAX = 5

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

NANJING_DISTRICTS = [
    "玄武区", "秦淮区", "建邺区", "鼓楼区", "浦口区",
    "栖霞区", "雨花台区", "江宁区", "六合区", "溧水区", "高淳区"
]
