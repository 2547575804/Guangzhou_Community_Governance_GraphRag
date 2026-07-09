import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# Neo4j 配置
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# DeepSeek API 配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# 数据路径
PROCESS_DATA_DIR = BASE_DIR / "process_data"
NEO4J_DATA_DIR = BASE_DIR / "neo4j_data"

WORKORDER_CSV = PROCESS_DATA_DIR / "12345热线案例_en.csv"
COURTCASE_CSV = PROCESS_DATA_DIR / "法律文书_en.csv"
NEWS_CSV = PROCESS_DATA_DIR / "新闻报道_en.csv"

# 知识库检索
KB_TOP_K = int(os.getenv("KB_TOP_K", "5"))

# Flask
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "true").lower() == "true"
