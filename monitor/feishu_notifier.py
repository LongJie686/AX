from __future__ import annotations

import json
import time
import logging
import threading
import requests
from monitor.config import Config

logger = logging.getLogger(__name__)

# 缓存 tenant_access_token
_token_cache = {"token": "", "expires_at": 0}


def _get_tenant_token() -> str:
    """获取飞书 tenant_access_token，带缓存"""
    now = time.time()
    if _token_cache["token"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["token"]

    if not Config.FEISHU_APP_ID or not Config.FEISHU_APP_SECRET:
        logger.warning("飞书 App ID/Secret 未配置，无法获取 token")
        return ""

    try:
        resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": Config.FEISHU_APP_ID, "app_secret": Config.FEISHU_APP_SECRET},
            timeout=10,
        )
        data = resp.json()
        if data.get("code") == 0:
            token = data["tenant_access_token"]
            expire = data.get("expire", 7200)
            _token_cache["token"] = token
            _token_cache["expires_at"] = now + expire
            logger.info("飞书 token 获取成功")
            return token
        else:
            logger.error(f"获取飞书 token 失败: {data}")
            return ""
    except Exception as e:
        logger.error(f"获取飞书 token 异常: {e}")
        return ""


def send_webhook(tweet_data: dict, monitor_info: dict):
    """通过飞书 Webhook 发送推文通知（卡片消息）"""
    webhook_url = Config.FEISHU_WEBHOOK_URL
    if not webhook_url:
        logger.warning("飞书 Webhook URL 未配置")
        return False

    username = monitor_info.get("twitter_username", "未知")
    display_name = monitor_info.get("display_name", username)
    original = tweet_data.get("content", "")
    translated = tweet_data.get("translated", "")
    tweet_type = tweet_data.get("tweet_type", "tweet")
    metrics = tweet_data.get("metrics", {})
    created_at = tweet_data.get("created_at", "")

    type_label = {"tweet": "推文", "retweet": "转推", "reply": "回复", "quote": "引用"}.get(tweet_type, "推文")
    metrics_text = f"点赞 {metrics.get('likes', 0)} | 转推 {metrics.get('retweets', 0)} | 回复 {metrics.get('replies', 0)}"

    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"content": f"[{type_label}] @{username} ({display_name})", "tag": "plain_text"},
                "template": "blue",
            },
            "elements": [
                {"tag": "markdown", "content": f"**原文:**\n{original}"},
                {"tag": "markdown", "content": f"**翻译:**\n{translated}" if translated else ""},
                {"tag": "markdown", "content": f"---\n{metrics_text} | {created_at}"},
            ],
        },
    }
    # 移除空元素
    card["card"]["elements"] = [e for e in card["card"]["elements"] if e.get("content")]

    try:
        resp = requests.post(webhook_url, json=card, timeout=10)
        data = resp.json()
        if data.get("code") == 0 or data.get("StatusCode") == 0:
            logger.info(f"Webhook 通知发送成功: @{username}")
            return True
        else:
            logger.error(f"Webhook 通知失败: {data}")
            return False
    except Exception as e:
        logger.error(f"Webhook 发送异常: {e}")
        return False


def _send_message_to_user(token: str, user_id: str, text: str) -> str:
    """通过飞书 API 发送消息给用户，返回 message_id"""
    try:
        resp = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/messages",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            params={"receive_id_type": "open_id"},
            json={
                "receive_id": user_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}),
            },
            timeout=10,
        )
        data = resp.json()
        if data.get("code") == 0:
            message_id = data["data"]["message_id"]
            logger.info(f"飞书消息发送成功, message_id={message_id}")
            return message_id
        else:
            logger.error(f"飞书消息发送失败: {data}")
            return ""
    except Exception as e:
        logger.error(f"飞书消息发送异常: {e}")
        return ""


def _send_urgent_phone(token: str, message_id: str, user_ids: list[str]) -> bool:
    """触发飞书电话加急"""
    try:
        resp = requests.patch(
            f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/urgent_phone",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"user_id_list": user_ids},
            params={"user_id_type": "open_id"},
            timeout=10,
        )
        data = resp.json()
        if data.get("code") == 0:
            logger.info(f"电话加急触发成功: {user_ids}")
            return True
        else:
            logger.error(f"电话加急失败: {data}")
            return False
    except Exception as e:
        logger.error(f"电话加急异常: {e}")
        return False


def _check_message_read(token: str, message_id: str, target_user_id: str) -> bool:
    """检查消息是否已被目标用户阅读"""
    try:
        resp = requests.get(
            f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/read_users",
            headers={"Authorization": f"Bearer {token}"},
            params={"user_id_type": "open_id", "page_size": 100},
            timeout=10,
        )
        data = resp.json()
        if data.get("code") == 0:
            items = data.get("data", {}).get("items", [])
            for item in items:
                if item.get("user_id") == target_user_id:
                    return True
        return False
    except Exception as e:
        logger.error(f"查询消息已读状态异常: {e}")
        return False


def phone_call_with_retry(tweet_data: dict, monitor_info: dict):
    """电话加急 + 智能重试（独立线程中运行）"""
    token = _get_tenant_token()
    if not token:
        logger.error("无法获取飞书 token，跳过电话提醒")
        return

    user_id = Config.FEISHU_USER_ID
    if not user_id:
        logger.warning("FEISHU_USER_ID 未配置，跳过电话提醒")
        return

    username = monitor_info.get("twitter_username", "")
    original = tweet_data.get("content", "")[:100]
    translated = tweet_data.get("translated", "")[:100]
    text = f"[Web3 Monitor] @{username} 发布了新推文!\n原文: {original}\n翻译: {translated}"

    message_id = _send_message_to_user(token, user_id, text)
    if not message_id:
        return

    _send_urgent_phone(token, message_id, [user_id])

    max_retries = Config.PHONE_RETRY_MAX
    retry_interval = Config.PHONE_RETRY_INTERVAL

    for i in range(max_retries):
        time.sleep(retry_interval)

        # 刷新 token（可能已过期）
        token = _get_tenant_token()
        if not token:
            break

        if _check_message_read(token, message_id, user_id):
            logger.info(f"用户已阅读消息，停止电话重试 (第{i+1}轮)")
            return

        logger.info(f"用户未阅读，第{i+2}次电话加急...")
        _send_urgent_phone(token, message_id, [user_id])

    logger.warning(f"已达最大重试次数({max_retries})，停止电话提醒")


def trigger_phone_async(tweet_data: dict, monitor_info: dict):
    """异步触发电话加急（在新线程中执行）"""
    t = threading.Thread(
        target=phone_call_with_retry,
        args=(tweet_data, monitor_info),
        daemon=True,
    )
    t.start()
