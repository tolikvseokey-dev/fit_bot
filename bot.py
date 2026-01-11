from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import requests
import telebot
from telebot import types
from dotenv import load_dotenv
from flask import Flask, request, jsonify

from config import load_config
from texts import t
import database as db
from pdf_export import export_day_pdf
from payments_yookassa import YooKassaConfig, create_sbp_payment, fetch_payment_status

load_dotenv()
cfg = load_config()

# Init DB
db.init_db(cfg.db_path)

bot = telebot.TeleBot(cfg.bot_token, parse_mode="HTML")

# --- Simple in-memory state (MVP). Restart-safe steps stored here.
# For production, you can persist states in DB. For now: stable enough.
STATE: Dict[int, Dict[str, Any]] = {}

# Flask app for YooKassa webhooks
app = Flask(__name__)

# ------------------ Helpers ------------------

ISO = "%Y-%m-%dT%H:%M:%S%z"

def now_utc():
    return datetime.now(timezone.utc)

def is_admin_user(message_or_user) -> bool:
    username = None
    if hasattr(message_or_user, "from_user") and message_or_user.from_user:
        username = message_or_user.from_user.username
    elif hasattr(message_or_user, "username"):
        username = message_or_user.username
    return (username or "") == cfg.admin_username

def user_lang(user_id: int) -> str:
    row = db.get_user(cfg.db_path, user_id)
    return (row["lang"] if row and row["lang"] else "ru")

def main_menu_kb(lang: str):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(t("btn_add_food", lang), t("btn_diary", lang))
    kb.row(t("btn_summary", lang), t("btn_more", lang))
    return kb

def more_menu_kb(lang: str, show_sub: bool, show_admin: bool):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(t("btn_my_products", lang), t("btn_search", lang))
    kb.row(t("btn_goals", lang), t("btn_settings", lang))
    kb.row(t("btn_feedback", lang))
    if show_sub:
        kb.row(t("btn_sub", lang))
    if show_admin:
        kb.row(t("btn_admin", lang))
    kb.row(t("btn_back", lang))
    return kb

def back_kb(lang: str):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(t("btn_back", lang))
    return kb

def inline_back(lang: str, data: str = "back"):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(t("btn_back", lang), callback_data=data))
    return kb

def log(user_id: int, event: str, meta: dict | None = None):
    db.log_event(cfg.db_path, user_id, event, meta or {})

def ensure_user(message):
    user_id = message.from_user.id
    username = message.from_user.username
    is_admin = is_admin_user(message)
    db.upsert_user(cfg.db_path, user_id, username, is_admin)

def clear_state(user_id: int):
    STATE.pop(user_id, None)

def set_state(user_id: int, **kwargs):
    STATE[user_id] = {**STATE.get(user_id, {}), **kwargs}

def get_state(user_id: int) -> dict:
    return STATE.get(user_id, {})

# ------------------ Language Onboarding ------------------

@bot.message_handler(commands=["start"])
def start(message):
    ensure_user(message)
    user_id = message.from_user.id
    lang = user_lang(user_id)
    # If lang not set yet (default ru), still offer picker only first time
    row = db.get_user(cfg.db_path, user_id)
    if row and row["created_at"] and row["created_at"] == row["last_seen_at"]:
        # first touch
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(t("lang_ru", "ru"), callback_data="setlang:ru"))
        kb.add(types.InlineKeyboardButton(t("lang_en", "ru"), callback_data="setlang:en"))
        bot.send_message(user_id, t("choose_lang", "ru"), reply_markup=kb)
        log(user_id, "start_first")
        return
    bot.send_message(user_id, t("main_title", lang), reply_markup=main_menu_kb(lang))
    log(user_id, "start")

@bot.callback_query_handler(func=lambda c: c.data.startswith("setlang:"))
def cb_setlang(call):
    user_id = call.from_user.id
    lang = call.data.split(":", 1)[1]
    db.set_user_lang(cfg.db_path, user_id, lang)
    bot.answer_callback_query(call.id, "OK")
    bot.send_message(user_id, t("main_title", lang), reply_markup=main_menu_kb(lang))
    log(user_id, "set_lang", {"lang": lang})

# ------------------ Main navigation ------------------

@bot.message_handler(func=lambda m: True, content_types=["text"])
def router(message):
    ensure_user(message)
    user_id = message.from_user.id
    lang = user_lang(user_id)
    text = (message.text or "").strip()

    # Global back
    if text == t("btn_back", lang):
        clear_state(user_id)
        bot.send_message(user_id, t("main_title", lang), reply_markup=main_menu_kb(lang))
        log(user_id, "back_to_main")
        return

    # State-driven steps
    st = get_state(user_id)
    if st.get("step") == "add_product_kbju":
        handle_add_product_kbju(message, lang)
        return
    if st.get("step") == "add_product_names":
        handle_add_product_names(message, lang)
        return
    if st.get("step") == "search_query":
        handle_search_query(message, lang)
        return
    if st.get("step") == "enter_grams":
        handle_enter_grams(message, lang)
        return
    if st.get("step") == "feedback_text":
        handle_feedback(message, lang)
        return
    if st.get("step") == "barcode":
        handle_barcode(message, lang)
        return
    if st.get("step") == "admin_set_price_stars":
        handle_admin_set_price(message, lang, which="stars")
        return
    if st.get("step") == "admin_set_price_rub":
        handle_admin_set_price(message, lang, which="rub")
        return
    if st.get("step") == "admin_edit_sub_text":
        handle_admin_edit_sub_text(message, lang)
        return

    # Menu clicks
    if text == t("btn_add_food", lang):
        show_add_food_menu(user_id, lang)
        return

    if text == t("btn_more", lang):
        show_more(user_id, lang)
        return

    if text == t("btn_diary", lang):
        show_diary(user_id, lang)
        return

    if text == t("btn_summary", lang):
        show_summary(user_id, lang)
        return

    # More section
    if text == t("btn_my_products", lang):
        show_my_products(user_id, lang)
        return

    if text == t("btn_search", lang):
        start_search(user_id, lang)
        return

    if text == t("btn_goals", lang):
        show_goals(user_id, lang)
        return

    if text == t("btn_settings", lang):
        show_settings(user_id, lang)
        return

    if text == t("btn_feedback", lang):
        start_feedback(user_id, lang)
        return

    if text == t("btn_sub", lang):
        if not db.is_subscription_enabled(cfg.db_path):
            # should not appear, but just in case:
            show_more(user_id, lang)
        else:
            show_subscription(user_id, lang)
        return

    if text == t("btn_admin", lang):
        if is_admin_user(message):
            show_admin(user_id, lang)
        else:
            bot.send_message(user_id, "⛔", reply_markup=main_menu_kb(lang))
        return

    # Add food submenu (reply keyboard)
    if text == t("btn_find_product", lang):
        start_search(user_id, lang, for_add=True)
        return
    if text == t("btn_recent", lang):
        show_recent(user_id, lang)
        return
    if text == t("btn_add_new_product", lang):
        start_add_new_product(user_id, lang)
        return

    # Diary actions
    if text == t("export_pdf", lang):
        export_today_pdf(user_id, lang)
        return

    # Default
    bot.send_message(user_id, t("main_title", lang), reply_markup=main_menu_kb(lang))

# ------------------ Menus ------------------

def show_more(user_id: int, lang: str):
    show_sub = db.is_subscription_enabled(cfg.db_path)
    show_admin = (cfg.admin_username != "" and (db.get_user(cfg.db_path, user_id) or {}).get("is_admin", 0) == 1)
    bot.send_message(user_id, t("more_title", lang), reply_markup=more_menu_kb(lang, show_sub, show_admin))
    log(user_id, "open_more")

def show_add_food_menu(user_id: int, lang: str):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(t("btn_find_product", lang), t("btn_recent", lang))
    kb.row(t("btn_my_products", lang), t("btn_add_new_product", lang))
    kb.row(t("btn_back", lang))
    bot.send_message(user_id, t("add_food_title", lang), reply_markup=kb)
    log(user_id, "open_add_food")

def show_diary(user_id: int, lang: str):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(t("today", lang), t("export_pdf", lang))
    kb.row(t("list_view", lang))
    kb.row(t("btn_back", lang))
    bot.send_message(user_id, t("diary_title", lang), reply_markup=kb)
    log(user_id, "open_diary")

def show_summary(user_id: int, lang: str):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(t("sum_today", lang), t("sum_week", lang))
    kb.row(t("sum_month", lang), t("remaining", lang))
    kb.row(t("btn_back", lang))
    bot.send_message(user_id, t("summary_title", lang), reply_markup=kb)
    log(user_id, "open_summary")

def show_my_products(user_id: int, lang: str):
    # quick list (first 10)
    with db.connect(cfg.db_path) as conn:
        rows = conn.execute(
            "SELECT id, name_ru, name_en FROM products_user WHERE user_id=? ORDER BY created_at DESC LIMIT 10",
            (user_id,),
        ).fetchall()
    lines = [t("my_products_title", lang)]
    if not rows:
        lines.append("—")
    else:
        for r in rows:
            lines.append(f"• {r['name_ru']} / {r['name_en']}")
    lines.append("")
    lines.append(t("btn_add_new_product", lang) + " — чтобы добавить")
    bot.send_message(user_id, "\n".join(lines), reply_markup=back_kb(lang))
    log(user_id, "open_my_products")

def show_goals(user_id: int, lang: str):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(t("goal_cut", lang), t("goal_maint", lang), t("goal_bulk", lang))
    kb.row(t("profile", lang), t("activity", lang))
    kb.row(t("cal_norm", lang), t("macros", lang))
    kb.row(t("btn_back", lang))
    bot.send_message(user_id, t("goals_title", lang), reply_markup=kb)
    log(user_id, "open_goals")

def show_settings(user_id: int, lang: str):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(t("set_lang", lang), t("set_tz", lang))
    kb.row(t("set_quick_grams", lang))
    kb.row(t("btn_back", lang))
    bot.send_message(user_id, t("settings_title", lang), reply_markup=kb)
    log(user_id, "open_settings")

def start_feedback(user_id: int, lang: str):
    set_state(user_id, step="feedback_text")
    bot.send_message(user_id, t("feedback_prompt", lang), reply_markup=back_kb(lang))
    log(user_id, "feedback_start")

def handle_feedback(message, lang: str):
    user_id = message.from_user.id
    text = (message.text or "").strip()
    if not text:
        bot.send_message(user_id, t("bad_format", lang))
        return
    db.add_feedback(cfg.db_path, user_id, text, None)
    clear_state(user_id)
    bot.send_message(user_id, t("thanks", lang), reply_markup=main_menu_kb(lang))
    log(user_id, "feedback_sent")

# ------------------ Product adding ------------------

def start_add_new_product(user_id: int, lang: str):
    # subscription gating for 'my products' size
    limit = db.get_free_my_products_limit(cfg.db_path)
    has_sub = db.user_has_active_sub(cfg.db_path, user_id)
    if not has_sub and db.count_user_products(cfg.db_path, user_id) >= limit:
        bot.send_message(user_id, t("limit_reached", lang).format(n=limit), reply_markup=main_menu_kb(lang))
        log(user_id, "my_products_limit_hit", {"limit": limit})
        return

    set_state(user_id, step="add_product_kbju")
    bot.send_message(user_id, t("send_kbju_per100", lang), reply_markup=back_kb(lang))
    log(user_id, "add_product_start")

def handle_add_product_kbju(message, lang: str):
    user_id = message.from_user.id
    raw = (message.text or "").strip().replace(",", ".")
    # expect: kcal p f c
    parts = re.split(r"\s+", raw)
    if len(parts) != 4:
        bot.send_message(user_id, t("bad_format", lang))
        return
    try:
        kcal, p, f, c_ = map(float, parts)
    except Exception:
        bot.send_message(user_id, t("bad_format", lang))
        return
    set_state(user_id, step="add_product_names", kbju=(kcal, p, f, c_))
    bot.send_message(user_id, t("send_names", lang), reply_markup=back_kb(lang))

def handle_add_product_names(message, lang: str):
    user_id = message.from_user.id
    text = (message.text or "").strip()
    mru = re.search(r"^RU:\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
    men = re.search(r"^EN:\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
    if not mru or not men:
        bot.send_message(user_id, t("bad_format", lang))
        return
    name_ru = mru.group(1).strip()
    name_en = men.group(1).strip()

    st = get_state(user_id)
    kcal, p, f, c_ = st.get("kbju", (0, 0, 0, 0))

    # Add to user products
    user_pid = db.add_user_product(cfg.db_path, user_id, name_ru, name_en, kcal, p, f, c_)
    # Add to global if not exists
    existing = db.find_global_product_by_names(cfg.db_path, name_ru, name_en)
    if existing is None:
        db.add_global_product(cfg.db_path, user_id, name_ru, name_en, kcal, p, f, c_, source="manual")

    clear_state(user_id)
    bot.send_message(user_id, f"✅ {name_ru} / {name_en}", reply_markup=main_menu_kb(lang))
    log(user_id, "add_product_done", {"user_product_id": user_pid})

# ------------------ Search / select product ------------------

def start_search(user_id: int, lang: str, for_add: bool = False):
    set_state(user_id, step="search_query", for_add=for_add)
    bot.send_message(user_id, t("enter_query", lang), reply_markup=back_kb(lang))
    log(user_id, "search_start", {"for_add": for_add})

def handle_search_query(message, lang: str):
    user_id = message.from_user.id
    query = (message.text or "").strip()
    if not query:
        bot.send_message(user_id, t("bad_format", lang))
        return

    st = get_state(user_id)
    results = db.search_products(cfg.db_path, user_id, query, limit=10)

    if not results and cfg.off_enabled and query.isdigit():
        # treat as barcode
        set_state(user_id, step="barcode", barcode=query, for_add=st.get("for_add", False))
        handle_barcode(message, lang)
        return

    if not results:
        bot.send_message(user_id, t("no_results", lang), reply_markup=back_kb(lang))
        return

    kb = types.InlineKeyboardMarkup()
    for r in results:
        title = (r["name_ru"] or r["name_en"] or "—")[:48]
        kb.add(types.InlineKeyboardButton(
            f"{title} ({r['ref_type']})",
            callback_data=f"pick:{r['ref_type']}:{r['id']}:{'1' if st.get('for_add') else '0'}"
        ))
    bot.send_message(user_id, t("choose_product", lang), reply_markup=kb)
    log(user_id, "search_results", {"n": len(results)})

@bot.callback_query_handler(func=lambda c: c.data.startswith("pick:"))
def cb_pick_product(call):
    user_id = call.from_user.id
    lang = user_lang(user_id)
    _, ref_type, ref_id, for_add = call.data.split(":")
    for_add = (for_add == "1")

    prod = db.get_product(cfg.db_path, ref_type, int(ref_id), user_id)
    if not prod:
        bot.answer_callback_query(call.id, "Not found")
        return

    # If not for add, just show product
    if not for_add:
        bot.answer_callback_query(call.id, "OK")
        bot.send_message(
            user_id,
            f"{prod['name_ru']} / {prod['name_en']}\n"
            f"100g: {prod['kcal']:.0f} kcal | P {prod['p']:.1f} F {prod['f']:.1f} C {prod['c']:.1f}",
            reply_markup=main_menu_kb(lang),
        )
        log(user_id, "product_view", {"ref_type": ref_type, "ref_id": ref_id})
        return

    # For add flow:
    set_state(user_id, step="pick_meal", ref_type=ref_type, ref_id=int(ref_id))
    bot.answer_callback_query(call.id, "OK")
    show_meal_picker(user_id, lang)

def show_meal_picker(user_id: int, lang: str):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(t("meal_breakfast", lang), t("meal_lunch", lang))
    kb.row(t("meal_dinner", lang), t("meal_snack", lang))
    kb.row(t("btn_back", lang))
    bot.send_message(user_id, t("pick_meal", lang), reply_markup=kb)
    log(user_id, "pick_meal")

@bot.message_handler(func=lambda m: m.text in [t("meal_breakfast", "ru"), t("meal_lunch", "ru"), t("meal_dinner", "ru"), t("meal_snack", "ru"),
                                             t("meal_breakfast", "en"), t("meal_lunch", "en"), t("meal_dinner", "en"), t("meal_snack", "en")])
def handle_meal_choice(message):
    ensure_user(message)
    user_id = message.from_user.id
    lang = user_lang(user_id)
    st = get_state(user_id)
    if st.get("step") != "pick_meal":
        return
    meal_map = {
        t("meal_breakfast", lang): "breakfast",
        t("meal_lunch", lang): "lunch",
        t("meal_dinner", lang): "dinner",
        t("meal_snack", lang): "snack",
    }
    meal = meal_map.get(message.text)
    if not meal:
        return
    set_state(user_id, step="enter_grams", remind_meal=meal)
    bot.send_message(user_id, t("grams_hint", lang) + "\n\n" + t("enter_grams", lang), reply_markup=quick_grams_kb(lang))
    log(user_id, "meal_chosen", {"meal": meal})

def quick_grams_kb(lang: str):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("➕ +50 г", "➕ +100 г", "➕ +200 г")
    kb.row(t("btn_back", lang))
    return kb

def handle_enter_grams(message, lang: str):
    user_id = message.from_user.id
    st = get_state(user_id)
    text = (message.text or "").strip()

    # quick buttons
    add = None
    if "+50" in text:
        add = 50
    elif "+100" in text:
        add = 100
    elif "+200" in text:
        add = 200

    if add is not None:
        current = float(st.get("grams", 0))
        new = current + add
        set_state(user_id, grams=new)
        bot.send_message(user_id, f"{t('enter_grams', lang)}\n✅ {new:.0f} g", reply_markup=quick_grams_kb(lang))
        return

    # manual
    try:
        grams = float(text.replace(",", "."))
    except Exception:
        bot.send_message(user_id, t("bad_format", lang))
        return

    set_state(user_id, grams=grams)
    # commit
    grams_val = float(get_state(user_id).get("grams", grams))
    ref_type = st.get("ref_type")
    ref_id = st.get("ref_id")
    meal = st.get("remind_meal")

    if not ref_type or not ref_id or not meal:
        clear_state(user_id)
        bot.send_message(user_id, t("main_title", lang), reply_markup=main_menu_kb(lang))
        return

    db.add_food_log(cfg.db_path, user_id, ref_type, int(ref_id), grams_val, meal)
    clear_state(user_id)
    bot.send_message(user_id, t("added_ok", lang), reply_markup=main_menu_kb(lang))
    log(user_id, "add_food_done", {"ref_type": ref_type, "ref_id": ref_id, "grams": grams_val, "meal": meal})

def show_recent(user_id: int, lang: str):
    rec = db.get_recent_products(cfg.db_path, user_id, limit=10)
    if not rec:
        bot.send_message(user_id, "—", reply_markup=main_menu_kb(lang))
        return

    kb = types.InlineKeyboardMarkup()
    for r in rec:
        prod = db.get_product(cfg.db_path, r["ref_type"], int(r["ref_id"]), user_id)
        if not prod:
            continue
        title = (prod["name_ru"] or prod["name_en"] or "—")[:48]
        kb.add(types.InlineKeyboardButton(
            f"{title} ({r['ref_type']})",
            callback_data=f"pick:{r['ref_type']}:{r['ref_id']}:1"
        ))
    bot.send_message(user_id, t("choose_product", lang), reply_markup=kb)
    log(user_id, "open_recent")

# ------------------ Barcode (Open Food Facts) ------------------

def handle_barcode(message, lang: str):
    user_id = message.from_user.id
    st = get_state(user_id)
    barcode = st.get("barcode") or (message.text or "").strip()
    if not (barcode and barcode.isdigit()):
        bot.send_message(user_id, t("bad_format", lang))
        return

    if not cfg.off_enabled:
        bot.send_message(user_id, t("no_results", lang))
        return

    try:
        url = f"https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
        resp = requests.get(url, timeout=cfg.off_timeout)
        data = resp.json()
    except Exception:
        bot.send_message(user_id, t("no_results", lang))
        return

    if data.get("status") != 1:
        bot.send_message(user_id, t("no_results", lang))
        return

    prod = data.get("product", {})
    name = prod.get("product_name") or prod.get("product_name_en") or "—"
    nutr = (prod.get("nutriments") or {})
    kcal = nutr.get("energy-kcal_100g") or nutr.get("energy-kcal_value")
    p = nutr.get("proteins_100g")
    f = nutr.get("fat_100g")
    c_ = nutr.get("carbohydrates_100g")
    if any(v is None for v in [kcal, p, f, c_]):
        bot.send_message(user_id, t("no_results", lang))
        return

    # add to user and global (source=off)
    name_ru = name
    name_en = name
    user_pid = db.add_user_product(cfg.db_path, user_id, name_ru, name_en, float(kcal), float(p), float(f), float(c_))
    existing = db.find_global_product_by_names(cfg.db_path, name_ru, name_en)
    if existing is None:
        db.add_global_product(cfg.db_path, user_id, name_ru, name_en, float(kcal), float(p), float(f), float(c_), source="off")
    clear_state(user_id)
    bot.send_message(user_id, f"✅ {name_ru}\n100g: {float(kcal):.0f} kcal | P {float(p):.1f} F {float(f):.1f} C {float(c_):.1f}", reply_markup=main_menu_kb(lang))
    log(user_id, "barcode_added", {"barcode": barcode, "user_product_id": user_pid})

# ------------------ PDF Export ------------------

def export_today_pdf(user_id: int, lang: str):
    today = now_utc().strftime("%Y-%m-%d")
    totals = db.sum_day(cfg.db_path, user_id, today)
    pdf_dir = os.path.join(os.path.dirname(__file__), cfg.pdf_dir)
    path = export_day_pdf(pdf_dir, user_id, today, totals, lang=lang)
    bot.send_message(user_id, t("pdf_ready", lang))
    with open(path, "rb") as f:
        bot.send_document(user_id, f)
    log(user_id, "export_pdf", {"date": today})

# ------------------ Subscription ------------------

def show_subscription(user_id: int, lang: str):
    row = db.get_user(cfg.db_path, user_id)
    active = db.user_has_active_sub(cfg.db_path, user_id)
    text = t("sub_title", lang) + "\n\n"
    if active and row and row["sub_until"]:
        text += t("sub_active_until", lang).format(date=row["sub_until"])
    else:
        text += t("sub_inactive", lang)

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(t("pay_stars", lang), callback_data="pay:stars"))
    kb.add(types.InlineKeyboardButton(t("pay_sbp", lang), callback_data="pay:sbp"))
    kb.add(types.InlineKeyboardButton(t("sub_what", lang), callback_data="sub:what"))
    kb.add(types.InlineKeyboardButton(t("sub_check", lang), callback_data="pay:check"))
    bot.send_message(user_id, text, reply_markup=kb)
    log(user_id, "open_subscription")

@bot.callback_query_handler(func=lambda c: c.data in ("sub:what", "pay:check", "pay:stars", "pay:sbp"))
def cb_sub(call):
    user_id = call.from_user.id
    lang = user_lang(user_id)
    bot.answer_callback_query(call.id, "OK")

    if call.data == "sub:what":
        with db.connect(cfg.db_path) as conn:
            txt = db.get_setting(conn, "sub_included_text_ru" if lang=="ru" else "sub_included_text_en", "")
        bot.send_message(user_id, txt or "—", reply_markup=inline_back(lang))
        return

    if call.data == "pay:check":
        # find latest pending yookassa payment, fetch status
        with db.connect(cfg.db_path) as conn:
            row = conn.execute(
                "SELECT provider_payment_id FROM payments WHERE user_id=? AND provider='yookassa' ORDER BY created_at DESC LIMIT 1",
                (user_id,),
            ).fetchone()
        if not row:
            bot.send_message(user_id, "—", reply_markup=inline_back(lang))
            return
        pid = row["provider_payment_id"]
        ycfg = YooKassaConfig(cfg.yookassa_shop_id, cfg.yookassa_secret_key, cfg.yookassa_return_url)
        try:
            status = fetch_payment_status(ycfg, pid)
        except Exception:
            bot.send_message(user_id, "😕 Не получилось проверить. Попробуй позже.", reply_markup=inline_back(lang))
            return
        if status.get("status") == "succeeded":
            db.update_payment_status(cfg.db_path, pid, "succeeded", status)
            db.activate_subscription(cfg.db_path, user_id, days=30)
            bot.send_message(user_id, "✅ Оплата подтверждена. Подписка активирована 🎉", reply_markup=main_menu_kb(lang))
        else:
            bot.send_message(user_id, f"Статус: {status.get('status')}", reply_markup=inline_back(lang))
        return

    if call.data == "pay:sbp":
        # create yookassa payment link
        with db.connect(cfg.db_path) as conn:
            price_rub = int(db.get_setting(conn, "sub_price_rub", "199") or "199")
        if not cfg.yookassa_shop_id or not cfg.yookassa_secret_key:
            bot.send_message(user_id, "⚠️ ЮKassa не настроена у админа.", reply_markup=inline_back(lang))
            return
        ycfg = YooKassaConfig(cfg.yookassa_shop_id, cfg.yookassa_secret_key, cfg.yookassa_return_url)
        idem = str(uuid.uuid4())
        res = create_sbp_payment(
            cfg=ycfg,
            amount_rub=price_rub,
            description=f"Subscription 30 days (telegram_user_id={user_id})",
            user_id=user_id,
            idempotency_key=idem,
        )
        pid = res["id"]
        db.create_payment(cfg.db_path, user_id, "yookassa", price_rub, "RUB", pid, idem, status="pending", meta=res)
        url = res.get("confirmation_url")
        if not url:
            bot.send_message(user_id, "😕 Не удалось создать ссылку оплаты.", reply_markup=inline_back(lang))
            return
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🏦 Перейти к оплате", url=url))
        bot.send_message(user_id, "Оплати по ссылке, после оплаты доступ откроется автоматически ✅", reply_markup=kb)
        log(user_id, "pay_sbp_created", {"payment_id": pid, "amount": price_rub})
        return

    if call.data == "pay:stars":
        # Telegram Stars invoice: currency XTR
        with db.connect(cfg.db_path) as conn:
            price_stars = int(db.get_setting(conn, "sub_price_stars", "100") or "100")
        prices = [types.LabeledPrice(label="Subscription 30 days", amount=price_stars)]
        # provider_token is empty for Stars. Telegram docs describe using Stars for digital services with currency="XTR". citeturn0search1turn0search9
        bot.send_invoice(
            user_id,
            title="Subscription",
            description="30 days access",
            invoice_payload=f"sub30:{user_id}:{int(time.time())}",
            provider_token="",
            currency="XTR",
            prices=prices,
        )
        log(user_id, "pay_stars_invoice", {"amount": price_stars})

@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(pre_checkout_query):
    # Must answer within 10 sec. citeturn0search3
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def got_payment(message):
    ensure_user(message)
    user_id = message.from_user.id
    lang = user_lang(user_id)
    sp = message.successful_payment
    # Stars payment successful
    # We treat any successful_payment with currency XTR as subscription.
    try:
        currency = getattr(sp, "currency", "")
    except Exception:
        currency = ""
    if currency == "XTR":
        # mark payment
        pid = getattr(sp, "telegram_payment_charge_id", str(uuid.uuid4()))
        db.create_payment(cfg.db_path, user_id, "stars", getattr(sp, "total_amount", 0), "XTR", pid, str(uuid.uuid4()), status="succeeded", meta={"payload": getattr(sp, "invoice_payload", "")})
        db.activate_subscription(cfg.db_path, user_id, days=30)
        bot.send_message(user_id, "✅ Подписка активирована на 30 дней 🎉", reply_markup=main_menu_kb(lang))
        log(user_id, "pay_stars_success")
    else:
        bot.send_message(user_id, "✅ Оплата получена", reply_markup=main_menu_kb(lang))

# ------------------ Admin ------------------

def show_admin(user_id: int, lang: str):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(t("admin_analytics", lang), t("admin_sub_mgmt", lang))
    kb.row(t("admin_subscribers", lang), t("admin_fb_in", lang))
    kb.row(t("btn_back", lang))
    bot.send_message(user_id, t("admin_title", lang), reply_markup=kb)
    log(user_id, "open_admin")

@bot.message_handler(func=lambda m: m.text in [t("admin_analytics","ru"), t("admin_analytics","en"),
                                             t("admin_sub_mgmt","ru"), t("admin_sub_mgmt","en"),
                                             t("admin_subscribers","ru"), t("admin_subscribers","en"),
                                             t("admin_fb_in","ru"), t("admin_fb_in","en")])
def admin_router(message):
    ensure_user(message)
    user_id = message.from_user.id
    if not is_admin_user(message):
        return
    lang = user_lang(user_id)
    text = message.text

    if text == t("admin_analytics", lang):
        snap = db.analytics_snapshot(cfg.db_path)
        lines = [
            "📈 Аналитика",
            f"👥 Пользователей всего: {snap['total_users']}",
            f"⚡ Активных за 7 дней: {snap['active_7d']}",
            "",
            "🔥 ТОП событий:",
        ]
        for name, n in snap["top_events"]:
            lines.append(f"• {name}: {n}")
        bot.send_message(user_id, "\n".join(lines), reply_markup=back_kb(lang))
        return

    if text == t("admin_sub_mgmt", lang):
        show_admin_sub_mgmt(user_id, lang)
        return

    if text == t("admin_subscribers", lang):
        with db.connect(cfg.db_path) as conn:
            rows = conn.execute("SELECT user_id, username, sub_until FROM users WHERE sub_until IS NOT NULL ORDER BY sub_until DESC LIMIT 30").fetchall()
        out = ["🧾 Подписчики:"]
        for r in rows:
            out.append(f"• {r['user_id']} @{r['username'] or '-'} до {r['sub_until']}")
        bot.send_message(user_id, "\n".join(out), reply_markup=back_kb(lang))
        return

    if text == t("admin_fb_in", lang):
        rows = db.list_feedback(cfg.db_path, status="new", limit=20)
        if not rows:
            bot.send_message(user_id, "—", reply_markup=back_kb(lang))
            return
        out = ["💬 Новая обратная связь:"]
        for r in rows:
            out.append(f"• {r['created_at']} | {r['user_id']}: {r['message']}")
        bot.send_message(user_id, "\n".join(out), reply_markup=back_kb(lang))
        return

def show_admin_sub_mgmt(user_id: int, lang: str):
    with db.connect(cfg.db_path) as conn:
        enabled = (db.get_setting(conn, "subscription_enabled", "0") == "1")
        ps = db.get_setting(conn, "sub_price_stars", "100")
        pr = db.get_setting(conn, "sub_price_rub", "199")
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(t("sub_toggle", lang))
    kb.row(t("sub_price_stars", lang), t("sub_price_rub", lang))
    kb.row(t("sub_text_edit", lang), t("sub_keys", lang))
    kb.row(t("btn_back", lang))
    bot.send_message(user_id, f"💎 Управление подпиской\n\nСтатус: {'ON' if enabled else 'OFF'}\nStars: {ps}\nRUB: {pr}", reply_markup=kb)

@bot.message_handler(func=lambda m: is_admin_user(m) and m.text in [t("sub_toggle","ru"), t("sub_toggle","en"),
                                                                  t("sub_price_stars","ru"), t("sub_price_stars","en"),
                                                                  t("sub_price_rub","ru"), t("sub_price_rub","en"),
                                                                  t("sub_text_edit","ru"), t("sub_text_edit","en"),
                                                                  t("sub_keys","ru"), t("sub_keys","en")])
def admin_sub_actions(message):
    user_id = message.from_user.id
    lang = user_lang(user_id)
    text = message.text

    if text == t("sub_toggle", lang):
        with db.connect(cfg.db_path) as conn:
            cur = db.get_setting(conn, "subscription_enabled", "0")
            new = "0" if cur == "1" else "1"
            db.set_setting(conn, "subscription_enabled", new)
            conn.commit()
        show_admin_sub_mgmt(user_id, lang)
        log(user_id, "sub_toggle", {"value": new})
        return

    if text == t("sub_price_stars", lang):
        set_state(user_id, step="admin_set_price_stars")
        bot.send_message(user_id, "Введи цену в Stars (целое число).", reply_markup=back_kb(lang))
        return

    if text == t("sub_price_rub", lang):
        set_state(user_id, step="admin_set_price_rub")
        bot.send_message(user_id, "Введи цену в рублях (целое число).", reply_markup=back_kb(lang))
        return

    if text == t("sub_text_edit", lang):
        set_state(user_id, step="admin_edit_sub_text")
        bot.send_message(user_id, "Пришли новый текст (для текущего языка).", reply_markup=back_kb(lang))
        return

    if text == t("sub_keys", lang):
        bot.send_message(
            user_id,
            "🔑 ЮKassa берёт ключи из .env\n"
            "YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, YOOKASSA_RETURN_URL\n\n"
            "Webhook URL: " + cfg.webhook_path,
            reply_markup=back_kb(lang),
        )
        return

def handle_admin_set_price(message, lang: str, which: str):
    user_id = message.from_user.id
    raw = (message.text or "").strip()
    try:
        val = int(raw)
        if val <= 0:
            raise ValueError
    except Exception:
        bot.send_message(user_id, "Нужно положительное целое число.")
        return
    with db.connect(cfg.db_path) as conn:
        if which == "stars":
            db.set_setting(conn, "sub_price_stars", str(val))
        else:
            db.set_setting(conn, "sub_price_rub", str(val))
        conn.commit()
    clear_state(user_id)
    show_admin_sub_mgmt(user_id, lang)
    log(user_id, "sub_price_set", {"which": which, "value": val})

def handle_admin_edit_sub_text(message, lang: str):
    user_id = message.from_user.id
    txt = (message.text or "").strip()
    with db.connect(cfg.db_path) as conn:
        db.set_setting(conn, "sub_included_text_ru" if lang=="ru" else "sub_included_text_en", txt)
        conn.commit()
    clear_state(user_id)
    show_admin_sub_mgmt(user_id, lang)
    log(user_id, "sub_text_set")

# ------------------ YooKassa Webhook ------------------

@app.route(cfg.webhook_path, methods=["POST"])
def yookassa_webhook():
    # Optional shared secret check
    if cfg.webhook_secret:
        auth = request.headers.get("Authorization", "")
        if auth != cfg.webhook_secret:
            return jsonify({"ok": False}), 401

    payload = request.get_json(silent=True) or {}
    event = payload.get("event")
    obj = payload.get("object") or {}
    payment_id = obj.get("id")

    if not payment_id:
        return jsonify({"ok": True})

    # Verify status by asking YooKassa API (protects from spoofed webhooks)
    if not cfg.yookassa_shop_id or not cfg.yookassa_secret_key:
        return jsonify({"ok": True})

    ycfg = YooKassaConfig(cfg.yookassa_shop_id, cfg.yookassa_secret_key, cfg.yookassa_return_url)
    try:
        status = fetch_payment_status(ycfg, payment_id)
    except Exception:
        return jsonify({"ok": True})

    row = db.get_payment_by_provider_id(cfg.db_path, payment_id)
    # if payment wasn't created by us, ignore
    if not row:
        return jsonify({"ok": True})

    if status.get("status") == "succeeded":
        db.update_payment_status(cfg.db_path, payment_id, "succeeded", status)
        db.activate_subscription(cfg.db_path, int(row["user_id"]), days=30)
        try:
            bot.send_message(int(row["user_id"]), "✅ Оплата СБП подтверждена. Подписка активирована 🎉")
        except Exception:
            pass
    elif status.get("status") in ("canceled", "failed"):
        db.update_payment_status(cfg.db_path, payment_id, status.get("status"), status)

    return jsonify({"ok": True})

def run_webhook_server():
    app.run(host=cfg.webhook_host, port=cfg.webhook_port)

# ------------------ Run ------------------

if __name__ == "__main__":
    # Run webhook server in background thread
    th = threading.Thread(target=run_webhook_server, daemon=True)
    th.start()
    bot.infinity_polling(skip_pending=True)
