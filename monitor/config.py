import os
from pathlib import Path
from dotenv import load_dotenv

# 加载项目根目录的 .env
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class Config:
    # RapidAPI
    RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
    RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "twitter241.p.rapidapi.com")

    # 飞书
    FEISHU_WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL", "")
    FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
    FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
    FEISHU_USER_ID = os.getenv("FEISHU_USER_ID", "")

    # 监控
    POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "300"))
    PHONE_RETRY_MAX = int(os.getenv("PHONE_RETRY_MAX", "3"))
    PHONE_RETRY_INTERVAL = int(os.getenv("PHONE_RETRY_INTERVAL", "120"))

    # 服务
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", "8080"))
    JWT_SECRET = os.getenv("JWT_SECRET", "web3monitor_default_secret")

    # 数据库
    DB_PATH = str(PROJECT_ROOT / os.getenv("DB_PATH", "data/web3monitor.db"))

    @classmethod
    def validate(cls):
        errors = []
        if not cls.RAPIDAPI_KEY:
            errors.append("RAPIDAPI_KEY 未配置")
        if not cls.FEISHU_WEBHOOK_URL:
            errors.append("FEISHU_WEBHOOK_URL 未配置")
        if errors:
            raise ValueError("配置错误:\n" + "\n".join(f"  - {e}" for e in errors))
