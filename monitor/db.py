import sqlite3
import json
from datetime import datetime
from pathlib import Path
from monitor.config import Config


def get_connection():
    Path(Config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(Config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            plan TEXT DEFAULT 'free',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS monitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            twitter_username TEXT NOT NULL,
            twitter_user_id TEXT DEFAULT '',
            display_name TEXT DEFAULT '',
            avatar_url TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            priority TEXT DEFAULT 'normal',
            last_tweet_id TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS tweets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tweet_id TEXT UNIQUE NOT NULL,
            monitor_id INTEGER NOT NULL,
            content_original TEXT DEFAULT '',
            content_translated TEXT DEFAULT '',
            tweet_type TEXT DEFAULT 'tweet',
            media_urls TEXT DEFAULT '[]',
            metrics TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT '',
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (monitor_id) REFERENCES monitors(id)
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tweet_id INTEGER,
            channel TEXT NOT NULL,
            status TEXT DEFAULT 'sent',
            message_id TEXT DEFAULT '',
            retry_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tweet_id) REFERENCES tweets(id)
        );

        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            feishu_webhook_url TEXT DEFAULT '',
            feishu_app_id TEXT DEFAULT '',
            feishu_app_secret TEXT DEFAULT '',
            feishu_user_id TEXT DEFAULT '',
            phone_enabled INTEGER DEFAULT 0,
            email_enabled INTEGER DEFAULT 0,
            email_address TEXT DEFAULT '',
            phone_retry_max INTEGER DEFAULT 3,
            phone_retry_interval INTEGER DEFAULT 120,
            poll_interval INTEGER DEFAULT 300,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE INDEX IF NOT EXISTS idx_monitors_user ON monitors(user_id);
        CREATE INDEX IF NOT EXISTS idx_tweets_monitor ON tweets(monitor_id);
        CREATE INDEX IF NOT EXISTS idx_tweets_fetched ON tweets(fetched_at);
    """)
    conn.commit()
    conn.close()


# ===== Users =====

def create_user(username, email, password_hash):
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
            (username, email, password_hash),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_user_by_email(email):
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id):
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ===== Monitors =====

def get_monitors(user_id=None, active_only=False):
    conn = get_connection()
    try:
        sql = "SELECT * FROM monitors WHERE 1=1"
        params = []
        if user_id is not None:
            sql += " AND user_id = ?"
            params.append(user_id)
        if active_only:
            sql += " AND is_active = 1"
        sql += " ORDER BY created_at DESC"
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_monitor(user_id, twitter_username, twitter_user_id="", display_name="", avatar_url="", priority="normal"):
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO monitors (user_id, twitter_username, twitter_user_id, display_name, avatar_url, priority)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, twitter_username, twitter_user_id, display_name, avatar_url, priority),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_monitor(monitor_id, **kwargs):
    conn = get_connection()
    try:
        allowed = {"is_active", "priority", "last_tweet_id", "twitter_user_id", "display_name", "avatar_url"}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [monitor_id]
        conn.execute(f"UPDATE monitors SET {set_clause} WHERE id = ?", values)
        conn.commit()
    finally:
        conn.close()


def delete_monitor(monitor_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM monitors WHERE id = ?", (monitor_id,))
        conn.commit()
    finally:
        conn.close()


# ===== Tweets =====

def save_tweet(tweet_id, monitor_id, content_original, content_translated="",
               tweet_type="tweet", media_urls=None, metrics=None, created_at=""):
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO tweets
               (tweet_id, monitor_id, content_original, content_translated, tweet_type, media_urls, metrics, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tweet_id, monitor_id, content_original, content_translated,
                tweet_type, json.dumps(media_urls or []), json.dumps(metrics or {}), created_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_tweets(monitor_id=None, page=1, limit=20):
    conn = get_connection()
    try:
        sql = "SELECT t.*, m.twitter_username, m.display_name, m.avatar_url FROM tweets t JOIN monitors m ON t.monitor_id = m.id WHERE 1=1"
        params = []
        if monitor_id is not None:
            sql += " AND t.monitor_id = ?"
            params.append(monitor_id)
        sql += " ORDER BY t.fetched_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, (page - 1) * limit])
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_tweet_count(monitor_id=None):
    conn = get_connection()
    try:
        sql = "SELECT COUNT(*) as cnt FROM tweets WHERE 1=1"
        params = []
        if monitor_id is not None:
            sql += " AND monitor_id = ?"
            params.append(monitor_id)
        row = conn.execute(sql, params).fetchone()
        return row["cnt"]
    finally:
        conn.close()


def get_today_tweet_count():
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM tweets WHERE date(fetched_at) = date('now')"
        ).fetchone()
        return row["cnt"]
    finally:
        conn.close()


# ===== Notifications =====

def save_notification(tweet_id, channel, status="sent", message_id=""):
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO notifications (tweet_id, channel, status, message_id) VALUES (?, ?, ?, ?)",
            (tweet_id, channel, status, message_id),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_notification(notif_id, **kwargs):
    conn = get_connection()
    try:
        allowed = {"status", "retry_count", "message_id"}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [notif_id]
        conn.execute(f"UPDATE notifications SET {set_clause} WHERE id = ?", values)
        conn.commit()
    finally:
        conn.close()


# ===== Settings =====

def get_settings(user_id):
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM settings WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def upsert_settings(user_id, **kwargs):
    conn = get_connection()
    try:
        existing = conn.execute("SELECT id FROM settings WHERE user_id = ?", (user_id,)).fetchone()
        allowed = {
            "feishu_webhook_url", "feishu_app_id", "feishu_app_secret", "feishu_user_id",
            "phone_enabled", "email_enabled", "email_address",
            "phone_retry_max", "phone_retry_interval", "poll_interval",
        }
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if existing:
            if fields:
                set_clause = ", ".join(f"{k} = ?" for k in fields)
                values = list(fields.values()) + [user_id]
                conn.execute(f"UPDATE settings SET {set_clause} WHERE user_id = ?", values)
        else:
            fields["user_id"] = user_id
            cols = ", ".join(fields.keys())
            placeholders = ", ".join("?" for _ in fields)
            conn.execute(f"INSERT INTO settings ({cols}) VALUES ({placeholders})", list(fields.values()))
        conn.commit()
    finally:
        conn.close()
