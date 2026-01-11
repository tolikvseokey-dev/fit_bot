from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any, Dict

import requests
import telebot
from telebot import types
from dotenv import load_dotenv

from config import load_config
from texts import t
import database as db

load_dotenv()
cfg = load_config()

db.init_db(cfg.db_path)

bot = telebot.TeleBot(cfg.bot_token, parse_mode="HTML")

STATE: Dict[int, Dict[str, Any]] = {}


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


def more_menu_kb(lang: str, show_admin: bool):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(t("btn_my_products", lang), t("btn_search", lang))
    kb.row(t("btn_goals", lang), t("btn_settings", lang))
    kb.row(t("btn_feedback", lang))
    if show_admin:
        kb.row(t("btn_admin", lang))
    kb.row(t("btn_back", lang))
    return kb


def back_kb(lang: str):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(t("btn_back", lang))
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


@bot.message_handler(commands=["start"])
def start(message):
    ensure_user(message)
    user_id = message.from_user.id

    row = db.get_user(cfg.db_path, user_id)
    if row and row["created_at"] and row["created_at"] == row["last_seen_at"]:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(t("lang_ru", "ru"), callback_data="setlang:ru"))
        kb.add(types.InlineKeyboardButton(t("lang_en", "ru"), callback_data="setlang:en"))
        bot.send_message(user_id, t("choose_lang", "ru"), reply_markup=kb)
        log(user_id, "start_first")
        return

    lang = user_lang(user_id)
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


@bot.message_handler(func=lambda m: True, content_types=["text"])
def router(message):
    ensure_user(message)
    user_id = message.from_user.id
    lang = user_lang(user_id)
    text = (message.text or "").strip()

    if text == t("btn_back", lang):
        clear_state(user_id)
        bot.send_message(user_id, t("main_title", lang), reply_markup=main_menu_kb(lang))
        log(user_id, "back_to_main")
        return

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

    if text == t("btn_my_products", lang):
        show_my_products(user_id, lang)
        return
    if text == t("btn_search", lang):
        start_search(user_id, lang, for_add=False)
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
    if text == t("btn_admin", lang):
        if is_admin_user(message):
            show_admin(user_id, lang)
        else:
            bot.send_message(user_id, "⛔", reply_markup=main_menu_kb(lang))
        return

    if text == t("btn_find_product", lang):
        start_search(user_id, lang, for_add=True)
        return
    if text == t("btn_recent", lang):
        show_recent(user_id, lang)
        return
    if text == t("btn_add_new_product", lang):
        start_add_new_product(user_id, lang)
        return

    bot.send_message(user_id, t("main_title", lang), reply_markup=main_menu_kb(lang))


def show_more(user_id: int, lang: str):
    row = db.get_user(cfg.db_path, user_id)
    show_admin = bool(row and row.get("is_admin", 0) == 1)
    bot.send_message(user_id, t("more_title", lang), reply_markup=more_menu_kb(lang, show_admin))
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
    kb.row(t("today", lang), t("list_view", lang))
    kb.row(t("btn_back", lang))
    bot.send_message(
        user_id,
        t("diary_title", lang) + "\n\n📄 PDF пока временно отключен (вернём позже).",
        reply_markup=kb
    )
    log(user_id, "open_diary")


def show_summary(user_id: int, lang: str):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(t("sum_today", lang), t("sum_week", lang))
    kb.row(t("sum_month", lang), t("remaining", lang))
    kb.row(t("btn_back", lang))
    bot.send_message(user_id, t("summary_title", lang), reply_markup=kb)
    log(user_id, "open_summary")


def show_my_products(user_id: int, lang: str):
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


def start_add_new_product(user_id: int, lang: str):
    limit = db.get_free_my_products_limit(cfg.db_path)
    has_sub = False  # подписки сейчас отключены
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

    user_pid = db.add_user_product(cfg.db_path, user_id, name_ru, name_en, kcal, p, f, c_)
    existing = db.find_global_product_by_names(cfg.db_path, name_ru, name_en)
    if existing is None:
        db.add_global_product(cfg.db_path, user_id, name_ru, name_en, kcal, p, f, c_, source="manual")

    clear_state(user_id)
    bot.send_message(user_id, f"✅ {name_ru} / {name_en}", reply_markup=main_menu_kb(lang))
    log(user_id, "add_product_done", {"user_product_id": user_pid})


def start_search(user_id: int, lang: str, for_add: bool):
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


@bot.message_handler(func=lambda m: True, content_types=["text"])
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

    try:
        grams = float(text.replace(",", "."))
    except Exception:
        bot.send_message(user_id, t("bad_format", lang))
        return

    set_state(user_id, grams=grams)
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

    name_ru = name
    name_en = name
    user_pid = db.add_user_product(cfg.db_path, user_id, name_ru, name_en, float(kcal), float(p), float(f), float(c_))
    existing = db.find_global_product_by_names(cfg.db_path, name_ru, name_en)
    if existing is None:
        db.add_global_product(cfg.db_path, user_id, name_ru, name_en, float(kcal), float(p), float(f), float(c_), source="off")

    clear_state(user_id)
    bot.send_message(
        user_id,
        f"✅ {name_ru}\n100g: {float(kcal):.0f} kcal | P {float(p):.1f} F {float(f):.1f} C {float(c_):.1f}",
        reply_markup=main_menu_kb(lang)
    )
    log(user_id, "barcode_added", {"barcode": barcode, "user_product_id": user_pid})


def show_admin(user_id: int, lang: str):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📈 Аналитика")
    kb.row("⬅️ Назад")
    bot.send_message(user_id, t("admin_title", lang), reply_markup=kb)
    log(user_id, "open_admin")


@bot.message_handler(func=lambda m: m.text == "📈 Аналитика")
def admin_analytics(message):
    ensure_user(message)
    if not is_admin_user(message):
        return
    user_id = message.from_user.id
    lang = user_lang(user_id)
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


if __name__ == "__main__":
    bot.infinity_polling(skip_pending=True)
