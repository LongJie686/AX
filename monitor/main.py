from __future__ import annotations

import time
import logging
import threading
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Optional

import bcrypt
import jwt
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from monitor.config import Config
from monitor import db
from monitor.twitter_poller import poll_new_tweets, search_user_by_username
from monitor.translator import translate_text
from monitor.feishu_notifier import send_webhook, trigger_phone_async

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ============================
# 后台轮询线程
# ============================

def monitor_loop():
    """后台轮询：定时检查所有活跃监控账号的新推文"""
    logger.info(f"监控线程启动，轮询间隔 {Config.POLL_INTERVAL}s")
    while True:
        try:
            monitors = db.get_monitors(active_only=True)
            for mon in monitors:
                if not mon["twitter_user_id"]:
                    continue

                logger.info(f"轮询 @{mon['twitter_username']} (ID:{mon['twitter_user_id']})")
                new_tweets = poll_new_tweets(mon["twitter_user_id"], mon["last_tweet_id"])

                if not new_tweets:
                    continue

                logger.info(f"@{mon['twitter_username']} 发现 {len(new_tweets)} 条新推文")

                for tweet in new_tweets:
                    translated = translate_text(tweet["content"])
                    tweet["translated"] = translated

                    db.save_tweet(
                        tweet_id=tweet["tweet_id"],
                        monitor_id=mon["id"],
                        content_original=tweet["content"],
                        content_translated=translated,
                        tweet_type=tweet["tweet_type"],
                        media_urls=tweet["media_urls"],
                        metrics=tweet["metrics"],
                        created_at=tweet["created_at"],
                    )

                    monitor_info = {
                        "twitter_username": mon["twitter_username"],
                        "display_name": mon["display_name"],
                    }

                    # 飞书 Webhook 通知
                    send_webhook(tweet, monitor_info)

                    # 电话加急（仅 urgent 优先级）
                    if mon["priority"] == "urgent":
                        trigger_phone_async(tweet, monitor_info)

                # 更新 last_tweet_id
                newest_id = new_tweets[0]["tweet_id"]
                db.update_monitor(mon["id"], last_tweet_id=newest_id)

        except Exception as e:
            logger.error(f"轮询循环异常: {e}", exc_info=True)

        time.sleep(Config.POLL_INTERVAL)


# ============================
# FastAPI 应用
# ============================

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    Config.validate()
    t = threading.Thread(target=monitor_loop, daemon=True)
    t.start()
    logger.info(f"API 服务启动于 {Config.API_HOST}:{Config.API_PORT}")
    yield

app = FastAPI(title="Web3 Monitor API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================
# JWT 认证
# ============================

def create_token(user_id: int) -> str:
    return jwt.encode(
        {"user_id": user_id, "exp": datetime.utcnow().timestamp() + 86400},
        Config.JWT_SECRET,
        algorithm="HS256",
    )


def get_current_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")
    token = auth[7:]
    try:
        payload = jwt.decode(token, Config.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="登录已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效 token")
    user = db.get_user_by_id(int(payload["user_id"]))
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


# ============================
# API 路由 - 认证
# ============================

class RegisterBody(BaseModel):
    username: str
    email: str
    password: str

class LoginBody(BaseModel):
    email: str
    password: str


@app.post("/api/auth/register")
def register(body: RegisterBody):
    if db.get_user_by_email(body.email):
        raise HTTPException(status_code=400, detail="邮箱已注册")
    hashed = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    user_id = db.create_user(body.username, body.email, hashed)
    db.upsert_settings(user_id)
    return {"code": 200, "data": {"token": create_token(user_id), "user_id": user_id}}


@app.post("/api/auth/login")
def login(body: LoginBody):
    user = db.get_user_by_email(body.email)
    if not user:
        raise HTTPException(status_code=400, detail="邮箱或密码错误")
    if not bcrypt.checkpw(body.password.encode(), user["password_hash"].encode()):
        raise HTTPException(status_code=400, detail="邮箱或密码错误")
    return {"code": 200, "data": {"token": create_token(user["id"]), "user_id": user["id"]}}


@app.get("/api/auth/me")
def get_me(user: dict = Depends(get_current_user)):
    return {
        "code": 200,
        "data": {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "plan": user["plan"],
        },
    }


# ============================
# API 路由 - 监控账号
# ============================

class MonitorBody(BaseModel):
    twitter_username: str
    twitter_user_id: Optional[str] = None
    priority: str = "normal"

class MonitorUpdateBody(BaseModel):
    is_active: Optional[int] = None
    priority: Optional[str] = None


@app.get("/api/monitors")
def list_monitors(user: dict = Depends(get_current_user)):
    monitors = db.get_monitors(user_id=user["id"])
    return {"code": 200, "data": monitors}


@app.post("/api/monitors")
def add_monitor(body: MonitorBody, user: dict = Depends(get_current_user)):
    # 尝试搜索 Twitter 用户，失败则使用手动提供的 ID
    info = search_user_by_username(body.twitter_username)
    if not info:
        info = {
            "user_id": body.twitter_user_id or "",
            "username": body.twitter_username,
            "display_name": body.twitter_username,
            "avatar_url": "",
        }

    monitor_id = db.create_monitor(
        user_id=user["id"],
        twitter_username=info["username"],
        twitter_user_id=info["user_id"],
        display_name=info["display_name"],
        avatar_url=info["avatar_url"],
        priority=body.priority,
    )
    return {"code": 200, "data": {"id": monitor_id, **info}}


@app.put("/api/monitors/{monitor_id}")
def update_monitor_api(monitor_id: int, body: MonitorUpdateBody, user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    db.update_monitor(monitor_id, **updates)
    return {"code": 200, "message": "更新成功"}


@app.delete("/api/monitors/{monitor_id}")
def delete_monitor_api(monitor_id: int, user: dict = Depends(get_current_user)):
    db.delete_monitor(monitor_id)
    return {"code": 200, "message": "删除成功"}


# ============================
# API 路由 - 推文
# ============================

@app.get("/api/tweets")
def list_tweets(
    monitor_id: Optional[int] = None,
    page: int = 1,
    limit: int = 20,
    user: dict = Depends(get_current_user),
):
    tweets = db.get_tweets(monitor_id=monitor_id, page=page, limit=limit)
    total = db.get_tweet_count(monitor_id=monitor_id)
    return {"code": 200, "data": {"items": tweets, "total": total, "page": page, "limit": limit}}


@app.get("/api/tweets/stats")
def tweet_stats(user: dict = Depends(get_current_user)):
    monitors = db.get_monitors(user_id=user["id"])
    active_count = sum(1 for m in monitors if m["is_active"])
    total_tweets = db.get_tweet_count()
    today_tweets = db.get_today_tweet_count()
    return {
        "code": 200,
        "data": {
            "monitor_count": len(monitors),
            "active_count": active_count,
            "total_tweets": total_tweets,
            "today_tweets": today_tweets,
        },
    }


# ============================
# API 路由 - 设置
# ============================

class SettingsBody(BaseModel):
    feishu_webhook_url: Optional[str] = None
    feishu_user_id: Optional[str] = None
    phone_enabled: Optional[int] = None
    email_enabled: Optional[int] = None
    email_address: Optional[str] = None
    phone_retry_max: Optional[int] = None
    phone_retry_interval: Optional[int] = None
    poll_interval: Optional[int] = None


@app.get("/api/settings")
def get_settings(user: dict = Depends(get_current_user)):
    settings = db.get_settings(user["id"])
    return {"code": 200, "data": settings}


@app.put("/api/settings")
def update_settings(body: SettingsBody, user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    db.upsert_settings(user["id"], **updates)
    return {"code": 200, "message": "设置已更新"}


# ============================
# 健康检查
# ============================

@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


# ============================
# 入口
# ============================

if __name__ == "__main__":
    uvicorn.run("monitor.main:app", host=Config.API_HOST, port=Config.API_PORT, reload=False)
