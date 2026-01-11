from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

ISO = "%Y-%m-%dT%H:%M:%S%z"

def utcnow() -> str:
    return datetime.now(timezone.utc).strftime(ISO)

@contextmanager
def connect(db_path: str):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db(db_path: str) -> None:
    with connect(db_path) as conn:
        cur = conn.cursor()
        cur.executescript(
            '''
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                lang TEXT DEFAULT 'ru',
                created_at TEXT,
                last_seen_at TEXT,
                timezone TEXT DEFAULT 'UTC',
                is_admin INTEGER DEFAULT 0,
                sub_until TEXT DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS products_global (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name_ru TEXT,
                name_en TEXT,
                kcal REAL,
                p REAL,
                f REAL,
                c REAL,
                source TEXT,
                created_by_user_id INTEGER,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS products_user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name_ru TEXT,
                name_en TEXT,
                kcal REAL,
                p REAL,
                f REAL,
                c REAL,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS food_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                product_ref_type TEXT,  -- 'global' or 'user'
                product_ref_id INTEGER,
                grams REAL,
                meal TEXT,
                eaten_at TEXT
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                event_name TEXT,
                meta_json TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message TEXT,
                rating INTEGER,
                status TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                provider TEXT, -- 'stars' or 'yookassa'
                amount REAL,
                currency TEXT,
                status TEXT, -- pending/succeeded/failed/canceled
                provider_payment_id TEXT,
                idempotency_key TEXT,
                created_at TEXT,
                updated_at TEXT,
                meta_json TEXT
            );
            '''
        )
        conn.commit()

        # Defaults
        set_setting(conn, "subscription_enabled", "0")
        set_setting(conn, "subscription_days", "30")
        set_setting(conn, "sub_price_stars", "100")  # can be changed in admin
        set_setting(conn, "sub_price_rub", "199")    # can be changed in admin
        set_setting(conn, "free_my_products_limit", "10")
        set_setting(conn, "sub_included_text_ru", "Подписка на 30 дней открывает:\n• статистику за месяц\n• экспорт PDF\n• историю без ограничений\n• снимает лимит «Мои продукты» (10 → ∞)")
        set_setting(conn, "sub_included_text_en", "30-day subscription unlocks:\n• monthly analytics\n• PDF export\n• unlimited history\n• removes 'My products' limit (10 → ∞)")

def get_setting(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    cur = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cur.fetchone()
    if row is None:
        return default
    return row["value"]

def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )

def upsert_user(db_path: str, user_id: int, username: str | None, is_admin: bool) -> None:
    with connect(db_path) as conn:
        now = utcnow()
        conn.execute(
            '''
            INSERT INTO users(user_id, username, created_at, last_seen_at, is_admin)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                last_seen_at=excluded.last_seen_at,
                is_admin=excluded.is_admin
            ''',
            (user_id, username, now, now, 1 if is_admin else 0),
        )
        conn.commit()

def set_user_lang(db_path: str, user_id: int, lang: str) -> None:
    with connect(db_path) as conn:
        conn.execute("UPDATE users SET lang=? WHERE user_id=?", (lang, user_id))
        conn.commit()

def get_user(db_path: str, user_id: int) -> sqlite3.Row | None:
    with connect(db_path) as conn:
        cur = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        return cur.fetchone()

def log_event(db_path: str, user_id: int, event_name: str, meta: dict[str, Any] | None = None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO events(user_id, event_name, meta_json, created_at) VALUES(?, ?, ?, ?)",
            (user_id, event_name, json.dumps(meta or {}, ensure_ascii=False), utcnow()),
        )
        conn.commit()

def is_subscription_enabled(db_path: str) -> bool:
    with connect(db_path) as conn:
        val = get_setting(conn, "subscription_enabled", "0")
        return val == "1"

def get_free_my_products_limit(db_path: str) -> int:
    with connect(db_path) as conn:
        val = get_setting(conn, "free_my_products_limit", "10") or "10"
        return int(val)

def user_has_active_sub(db_path: str, user_id: int) -> bool:
    row = get_user(db_path, user_id)
    if not row:
        return False
    sub_until = row["sub_until"]
    if not sub_until:
        return False
    try:
        dt = datetime.strptime(sub_until, ISO)
    except Exception:
        return False
    return dt > datetime.now(timezone.utc)

def activate_subscription(db_path: str, user_id: int, days: int = 30) -> None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT sub_until FROM users WHERE user_id=?", (user_id,)).fetchone()
        now = datetime.now(timezone.utc)
        base = now
        if row and row["sub_until"]:
            try:
                prev = datetime.strptime(row["sub_until"], ISO)
                if prev > now:
                    base = prev
            except Exception:
                pass
        new_until = (base + __import__("datetime").timedelta(days=days)).strftime(ISO)
        conn.execute("UPDATE users SET sub_until=? WHERE user_id=?", (new_until, user_id))
        conn.commit()

def count_user_products(db_path: str, user_id: int) -> int:
    with connect(db_path) as conn:
        cur = conn.execute("SELECT COUNT(*) AS n FROM products_user WHERE user_id=?", (user_id,))
        return int(cur.fetchone()["n"])

def add_user_product(db_path: str, user_id: int, name_ru: str, name_en: str, kcal: float, p: float, f: float, c: float) -> int:
    with connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO products_user(user_id, name_ru, name_en, kcal, p, f, c, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, name_ru, name_en, kcal, p, f, c, utcnow()),
        )
        conn.commit()
        return int(cur.lastrowid)

def find_global_product_by_names(db_path: str, name_ru: str, name_en: str) -> int | None:
    with connect(db_path) as conn:
        cur = conn.execute(
            "SELECT id FROM products_global WHERE lower(name_ru)=lower(?) OR lower(name_en)=lower(?) LIMIT 1",
            (name_ru.strip(), name_en.strip()),
        )
        row = cur.fetchone()
        return int(row["id"]) if row else None

def add_global_product(db_path: str, created_by_user_id: int, name_ru: str, name_en: str, kcal: float, p: float, f: float, c: float, source: str = "manual") -> int:
    with connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO products_global(name_ru, name_en, kcal, p, f, c, source, created_by_user_id, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name_ru, name_en, kcal, p, f, c, source, created_by_user_id, utcnow()),
        )
        conn.commit()
        return int(cur.lastrowid)

def search_products(db_path: str, user_id: int, query: str, limit: int = 10) -> list[dict[str, Any]]:
    q = f"%{query.strip().lower()}%"
    with connect(db_path) as conn:
        rows_u = conn.execute(
            "SELECT id, name_ru, name_en, kcal, p, f, c, 'user' AS ref_type FROM products_user WHERE user_id=? AND (lower(name_ru) LIKE ? OR lower(name_en) LIKE ?) LIMIT ?",
            (user_id, q, q, limit),
        ).fetchall()
        rows_g = conn.execute(
            "SELECT id, name_ru, name_en, kcal, p, f, c, 'global' AS ref_type FROM products_global WHERE (lower(name_ru) LIKE ? OR lower(name_en) LIKE ?) LIMIT ?",
            (q, q, limit),
        ).fetchall()
    # merge: user first
    out = []
    for r in list(rows_u) + list(rows_g):
        out.append(dict(r))
    return out[:limit]

def get_product(db_path: str, ref_type: str, ref_id: int, user_id: int) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        if ref_type == "user":
            row = conn.execute(
                "SELECT id, name_ru, name_en, kcal, p, f, c FROM products_user WHERE id=? AND user_id=?",
                (ref_id, user_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id, name_ru, name_en, kcal, p, f, c FROM products_global WHERE id=?",
                (ref_id,),
            ).fetchone()
    return dict(row) if row else None

def add_food_log(db_path: str, user_id: int, ref_type: str, ref_id: int, grams: float, meal: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO food_log(user_id, product_ref_type, product_ref_id, grams, meal, eaten_at) VALUES(?, ?, ?, ?, ?, ?)",
            (user_id, ref_type, ref_id, grams, meal, utcnow()),
        )
        conn.commit()

def get_recent_products(db_path: str, user_id: int, limit: int = 10) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            '''
            SELECT product_ref_type AS ref_type, product_ref_id AS ref_id, MAX(eaten_at) AS last_time
            FROM food_log
            WHERE user_id=?
            GROUP BY product_ref_type, product_ref_id
            ORDER BY last_time DESC
            LIMIT ?
            ''',
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]

def sum_day(db_path: str, user_id: int, date_yyyy_mm_dd: str) -> dict[str, float]:
    # Sum for a UTC day; for simplicity in MVP (timezone can adjust later)
    start = f"{date_yyyy_mm_dd}T00:00:00+0000"
    end = f"{date_yyyy_mm_dd}T23:59:59+0000"
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT product_ref_type, product_ref_id, grams FROM food_log WHERE user_id=? AND eaten_at BETWEEN ? AND ?",
            (user_id, start, end),
        ).fetchall()
    total = {"kcal": 0.0, "p": 0.0, "f": 0.0, "c": 0.0}
    for r in rows:
        prod = get_product(db_path, r["product_ref_type"], int(r["product_ref_id"]), user_id)
        if not prod:
            continue
        grams = float(r["grams"])
        factor = grams / 100.0
        total["kcal"] += float(prod["kcal"]) * factor
        total["p"] += float(prod["p"]) * factor
        total["f"] += float(prod["f"]) * factor
        total["c"] += float(prod["c"]) * factor
    return total

def create_payment(db_path: str, user_id: int, provider: str, amount: float, currency: str, provider_payment_id: str, idempotency_key: str, status: str = "pending", meta: dict[str, Any] | None = None) -> int:
    with connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO payments(user_id, provider, amount, currency, status, provider_payment_id, idempotency_key, created_at, updated_at, meta_json) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, provider, amount, currency, status, provider_payment_id, idempotency_key, utcnow(), utcnow(), json.dumps(meta or {}, ensure_ascii=False)),
        )
        conn.commit()
        return int(cur.lastrowid)

def update_payment_status(db_path: str, provider_payment_id: str, status: str, meta: dict[str, Any] | None = None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE payments SET status=?, updated_at=?, meta_json=? WHERE provider_payment_id=?",
            (status, utcnow(), json.dumps(meta or {}, ensure_ascii=False), provider_payment_id),
        )
        conn.commit()

def get_payment_by_provider_id(db_path: str, provider_payment_id: str) -> sqlite3.Row | None:
    with connect(db_path) as conn:
        return conn.execute("SELECT * FROM payments WHERE provider_payment_id=?", (provider_payment_id,)).fetchone()

def list_feedback(db_path: str, status: str = "new", limit: int = 20) -> list[sqlite3.Row]:
    with connect(db_path) as conn:
        return conn.execute(
            "SELECT * FROM feedback WHERE status=? ORDER BY created_at DESC LIMIT ?",
            (status, limit),
        ).fetchall()

def add_feedback(db_path: str, user_id: int, message: str, rating: int | None = None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO feedback(user_id, message, rating, status, created_at) VALUES(?, ?, ?, 'new', ?)",
            (user_id, message, rating, utcnow()),
        )
        conn.commit()

def analytics_snapshot(db_path: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        total_users = int(conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"])
        # last 7 days activity
        now = datetime.now(timezone.utc)
        d7 = (now - __import__("datetime").timedelta(days=7)).strftime(ISO)
        active_7d = int(conn.execute("SELECT COUNT(DISTINCT user_id) AS n FROM events WHERE created_at >= ?", (d7,)).fetchone()["n"])
        top_events = conn.execute(
            "SELECT event_name, COUNT(*) AS n FROM events GROUP BY event_name ORDER BY n DESC LIMIT 10"
        ).fetchall()
    return {
        "total_users": total_users,
        "active_7d": active_7d,
        "top_events": [(r["event_name"], int(r["n"])) for r in top_events],
    }
