from __future__ import annotations

import requests
import logging
from typing import Optional
from monitor.config import Config

logger = logging.getLogger(__name__)

HEADERS = {
    "Content-Type": "application/json",
    "x-rapidapi-host": Config.RAPIDAPI_HOST,
    "x-rapidapi-key": Config.RAPIDAPI_KEY,
}
BASE_URL = f"https://{Config.RAPIDAPI_HOST}"


def get_user_info(user_ids: list[str]) -> dict:
    """通过用户ID列表批量获取用户信息"""
    try:
        resp = requests.get(
            f"{BASE_URL}/get-users-v2",
            headers=HEADERS,
            params={"users": ",".join(user_ids)},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        result = {}
        users = data.get("result", {}).get("users", {})
        for uid, info in users.items():
            legacy = info.get("result", {}).get("legacy", {})
            result[uid] = {
                "user_id": uid,
                "username": legacy.get("screen_name", ""),
                "display_name": legacy.get("name", ""),
                "avatar_url": legacy.get("profile_image_url_https", ""),
                "description": legacy.get("description", ""),
            }
        return result
    except Exception as e:
        logger.error(f"获取用户信息失败: {e}")
        return {}


def search_user_by_username(username: str) -> Optional[dict]:
    """通过用户名搜索用户，返回用户信息"""
    try:
        resp = requests.get(
            f"{BASE_URL}/user",
            headers=HEADERS,
            params={"username": username},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        # API 返回结构: result.data.user.result
        user_result = (
            data.get("result", {})
            .get("data", {})
            .get("user", {})
            .get("result", {})
        )
        if not user_result:
            return None
        rest_id = user_result.get("rest_id", "")
        core = user_result.get("core", {})
        avatar = user_result.get("avatar", {})
        legacy = user_result.get("legacy", {})
        if not rest_id:
            return None
        return {
            "user_id": rest_id,
            "username": core.get("screen_name", username),
            "display_name": core.get("name", ""),
            "avatar_url": avatar.get("image_url", "").replace("_normal", "_bigger"),
            "description": legacy.get("description", ""),
        }
    except Exception as e:
        logger.error(f"搜索用户 {username} 失败: {e}")
        return None


def get_user_tweets(user_id: str, count: int = 20) -> list[dict]:
    """获取用户最新推文列表"""
    try:
        resp = requests.get(
            f"{BASE_URL}/user-tweets",
            headers=HEADERS,
            params={"user": user_id, "count": count},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        tweets = []
        timeline = data.get("result", {}).get("timeline", {})
        instructions = timeline.get("instructions", [])

        for instruction in instructions:
            entries = instruction.get("entries", [])
            for entry in entries:
                content = entry.get("content", {})
                item_content = content.get("content", content.get("itemContent", {}))
                tweet_result = item_content.get("tweetResult", item_content.get("tweet_results", {}))
                result = tweet_result.get("result", {})

                if not result:
                    continue

                legacy = result.get("legacy", {})
                tweet_id = legacy.get("id_str", result.get("rest_id", ""))
                if not tweet_id:
                    continue

                full_text = legacy.get("full_text", "")
                created_at = legacy.get("created_at", "")

                # 媒体
                media_list = []
                entities = legacy.get("entities", {})
                for media in entities.get("media", []):
                    media_list.append(media.get("media_url_https", ""))

                # 互动数据
                metrics = {
                    "likes": legacy.get("favorite_count", 0),
                    "retweets": legacy.get("retweet_count", 0),
                    "replies": legacy.get("reply_count", 0),
                    "quotes": legacy.get("quote_count", 0),
                }

                # 推文类型
                tweet_type = "tweet"
                if legacy.get("retweeted_status_result"):
                    tweet_type = "retweet"
                elif legacy.get("in_reply_to_status_id_str"):
                    tweet_type = "reply"
                elif legacy.get("is_quote_status"):
                    tweet_type = "quote"

                tweets.append({
                    "tweet_id": tweet_id,
                    "content": full_text,
                    "created_at": created_at,
                    "tweet_type": tweet_type,
                    "media_urls": media_list,
                    "metrics": metrics,
                })

        tweets.sort(key=lambda t: t["tweet_id"], reverse=True)
        return tweets

    except Exception as e:
        logger.error(f"获取用户 {user_id} 推文失败: {e}")
        return []


def poll_new_tweets(user_id: str, last_tweet_id: str = "") -> list[dict]:
    """轮询新推文，只返回 last_tweet_id 之后的推文"""
    all_tweets = get_user_tweets(user_id)
    if not last_tweet_id:
        return all_tweets[:1] if all_tweets else []
    return [t for t in all_tweets if t["tweet_id"] > last_tweet_id]
