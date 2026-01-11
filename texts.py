from __future__ import annotations

TEXTS = {
    "ru": {
        "choose_lang": "Выбери язык / Choose language:",
        "lang_ru": "🇷🇺 Русский",
        "lang_en": "🇬🇧 English",

        "main_title": "Главное меню",
        "btn_add_food": "➕ Добавить еду",
        "btn_diary": "📒 Дневник",
        "btn_summary": "📊 Сводка",
        "btn_more": "☰ Ещё",
        "btn_back": "⬅️ Назад",

        "more_title": "Ещё",
        "btn_my_products": "⭐ Мои продукты",
        "btn_search": "🔎 Поиск",
        "btn_goals": "🎯 Цели и нормы",
        "btn_settings": "⚙️ Настройки",
        "btn_feedback": "💬 Обратная связь",
        "btn_sub": "💎 Подписка",
        "btn_admin": "👑 Админ-панель",

        "add_food_title": "Добавить еду",
        "btn_find_product": "🔎 Найти продукт",
        "btn_recent": "🕘 Недавние",
        "btn_add_new_product": "➕ Добавить новый продукт",

        "pick_meal": "Выбери приём пищи:",
        "meal_breakfast": "🍳 Завтрак",
        "meal_lunch": "🍲 Обед",
        "meal_dinner": "🍽 Ужин",
        "meal_snack": "🍏 Перекус",

        "enter_query": "Напиши название продукта (RU/EN).",
        "no_results": "Ничего не нашла 😕 Попробуй другое название или добавь новый продукт.",
        "choose_product": "Выбери продукт:",
        "enter_grams": "Сколько грамм? (числом, например 150)",
        "grams_hint": "Можно кнопками: +50, +100, +200, или ввести вручную 👇",
        "added_ok": "✅ Добавила! Запись внесена в дневник.",

        "my_products_title": "Мои продукты",
        "limit_reached": "Упс 😅 В бесплатной версии можно хранить только {n} продуктов в «Мои продукты». Подписка снимает лимит 💎",
        "send_kbju_per100": "Введи КБЖУ на 100 г в формате:\n\n"
                     "Ккал Б Ж У\n\n"
                     "Пример: 165 31 3.6 0",

        "send_names": "Теперь названия продукта.

Напиши так:
RU: <название>
EN: <name>

Пример:
RU: Куриная грудка
EN: Chicken breast",
        "bad_format": "Не поняла формат 😕 Попробуй ещё раз.",

        "diary_title": "Дневник",
        "today": "Сегодня",
        "pick_date": "📅 Выбрать дату",
        "list_view": "🧾 Показать списком",
        "edit_entry": "✏️ Редактировать запись",
        "delete_entry": "🗑 Удалить запись",

        "summary_title": "Сводка",
        "sum_today": "Сегодня",
        "sum_week": "Неделя",
        "sum_month": "Месяц",
        "remaining": "🎯 До цели осталось",

        "settings_title": "Настройки",
        "set_lang": "🌐 Язык",
        "set_tz": "🕒 Часовой пояс",
        "set_quick_grams": "⚡ Быстрые граммы",

        "goals_title": "Цели и нормы",
        "goal_pick": "Выбери цель:",
        "goal_cut": "Похудение",
        "goal_maint": "Поддержание",
        "goal_bulk": "Набор",
        "profile": "👤 Профиль",
        "activity": "🏃 Активность",
        "cal_norm": "🧮 Норма",
        "macros": "🥩 Макросы",

        "activity_pick": "Выбери активность (по движению):",
        "act_min": "Минимальная · мало движения",
        "act_light": "Лёгкая · много ходьбы",
        "act_med": "Средняя · активный день",
        "act_high": "Высокая · постоянно в движении",
        "act_ext": "Экстремальная · спорт/тяжёлая работа",

        "act_desc_min": "🪑 Минимальная (1.2)
Сидячая работа, мало ходьбы.
Шаги ~2–4 тыс/день.",
        "act_desc_light": "🚶 Лёгкая (1.375)
Много ходьбы и активный быт.
Шаги ~5–7 тыс/день.",
        "act_desc_med": "🚶‍♂️ Средняя (1.55)
Активный день, часто в движении.
Шаги ~8–10 тыс/день.",
        "act_desc_high": "🏃 Высокая (1.725)
Физическая работа или почти весь день на ногах.
Шаги ~11–14 тыс/день.",
        "act_desc_ext": "🔥 Экстремальная (1.9)
Спорт/очень тяжёлая работа.
Шаги 15+ тыс/день.",

        "macros_auto": "Авто",
        "macros_manual": "Ручной",

        "feedback_title": "Обратная связь",
        "feedback_prompt": "Напиши сообщение — я передам админу 💬",
        "thanks": "Спасибо! 🫶",

        "sub_title": "Подписка",
        "sub_inactive": "Подписка не активна.",
        "sub_active_until": "Подписка активна до: {date}",
        "pay_stars": "⭐️ Оплатить Stars",
        "pay_sbp": "🏦 Оплатить СБП (ЮKassa)",
        "sub_what": "📜 Что входит",
        "sub_check": "🔄 Проверить оплату",

        "admin_title": "Админ-панель",
        "admin_analytics": "📈 Аналитика",
        "admin_sub_mgmt": "💎 Управление подпиской",
        "admin_subscribers": "🧾 Подписчики",
        "admin_fb_in": "💬 Обратная связь (входящие)",

        "sub_toggle": "✅ Подписка: ВКЛ / ❌ ВЫКЛ",
        "sub_price_stars": "💰 Цена Stars",
        "sub_price_rub": "💰 Цена ЮKassa (руб)",
        "sub_text_edit": "📜 Текст “что входит”",
        "sub_keys": "🔑 Настройки ЮKassa",

        "pdf_ready": "📄 Готово! Отправляю PDF 👇",
        "export_pdf": "📄 Экспорт в PDF",
    },
    "en": {
        "choose_lang": "Choose language / Выбери язык:",
        "lang_ru": "🇷🇺 Русский",
        "lang_en": "🇬🇧 English",

        "main_title": "Main menu",
        "btn_add_food": "➕ Add food",
        "btn_diary": "📒 Diary",
        "btn_summary": "📊 Summary",
        "btn_more": "☰ More",
        "btn_back": "⬅️ Back",

        "more_title": "More",
        "btn_my_products": "⭐ My products",
        "btn_search": "🔎 Search",
        "btn_goals": "🎯 Goals & norms",
        "btn_settings": "⚙️ Settings",
        "btn_feedback": "💬 Feedback",
        "btn_sub": "💎 Subscription",
        "btn_admin": "👑 Admin",

        "add_food_title": "Add food",
        "btn_find_product": "🔎 Find product",
        "btn_recent": "🕘 Recent",
        "btn_add_new_product": "➕ Add new product",

        "pick_meal": "Pick meal:",
        "meal_breakfast": "🍳 Breakfast",
        "meal_lunch": "🍲 Lunch",
        "meal_dinner": "🍽 Dinner",
        "meal_snack": "🍏 Snack",

        "enter_query": "Type a product name (RU/EN).",
        "no_results": "No results 😕 Try another name or add a new product.",
        "choose_product": "Choose a product:",
        "enter_grams": "How many grams? (number, e.g. 150)",
        "grams_hint": "Use buttons: +50, +100, +200 or type manually 👇",
        "added_ok": "✅ Added! Logged into your diary.",

        "my_products_title": "My products",
        "limit_reached": "Oops 😅 Free plan allows only {n} items in “My products”. Subscription removes the limit 💎",
        "send_kbju_per100": "Enter nutrition per 100 g as:

Kcal P F C

Example: 165 31 3.6 0",
        "send_names": "Now product names.

Send:
RU: <name>
EN: <name>

Example:
RU: Куриная грудка
EN: Chicken breast",
        "bad_format": "Wrong format 😕 Please try again.",

        "diary_title": "Diary",
        "today": "Today",
        "pick_date": "📅 Pick date",
        "list_view": "🧾 List view",
        "edit_entry": "✏️ Edit entry",
        "delete_entry": "🗑 Delete entry",

        "summary_title": "Summary",
        "sum_today": "Today",
        "sum_week": "Week",
        "sum_month": "Month",
        "remaining": "🎯 Remaining",

        "settings_title": "Settings",
        "set_lang": "🌐 Language",
        "set_tz": "🕒 Timezone",
        "set_quick_grams": "⚡ Quick grams",

        "goals_title": "Goals & norms",
        "goal_pick": "Pick goal:",
        "goal_cut": "Cut",
        "goal_maint": "Maintain",
        "goal_bulk": "Bulk",
        "profile": "👤 Profile",
        "activity": "🏃 Activity",
        "cal_norm": "🧮 Calories",
        "macros": "🥩 Macros",

        "activity_pick": "Choose activity (movement-based):",
        "act_min": "Minimal · low movement",
        "act_light": "Light · lots of walking",
        "act_med": "Moderate · active day",
        "act_high": "High · always moving",
        "act_ext": "Extreme · sport/hard work",

        "act_desc_min": "🪑 Minimal (1.2)
Mostly sitting, little walking.
Steps ~2–4k/day.",
        "act_desc_light": "🚶 Light (1.375)
Lots of walking and active routine.
Steps ~5–7k/day.",
        "act_desc_med": "🚶‍♂️ Moderate (1.55)
Active day, often moving.
Steps ~8–10k/day.",
        "act_desc_high": "🏃 High (1.725)
Physical work or on feet most of the day.
Steps ~11–14k/day.",
        "act_desc_ext": "🔥 Extreme (1.9)
Sport/very hard work.
Steps 15k+/day.",

        "macros_auto": "Auto",
        "macros_manual": "Manual",

        "feedback_title": "Feedback",
        "feedback_prompt": "Write your message — I'll send it to admin 💬",
        "thanks": "Thanks! 🫶",

        "sub_title": "Subscription",
        "sub_inactive": "Subscription is not active.",
        "sub_active_until": "Active until: {date}",
        "pay_stars": "⭐️ Pay with Stars",
        "pay_sbp": "🏦 Pay via SBP (YooKassa)",
        "sub_what": "📜 What's included",
        "sub_check": "🔄 Check payment",

        "admin_title": "Admin",
        "admin_analytics": "📈 Analytics",
        "admin_sub_mgmt": "💎 Subscription management",
        "admin_subscribers": "🧾 Subscribers",
        "admin_fb_in": "💬 Feedback inbox",

        "sub_toggle": "✅ Subscription: ON / ❌ OFF",
        "sub_price_stars": "💰 Stars price",
        "sub_price_rub": "💰 YooKassa price (RUB)",
        "sub_text_edit": "📜 Edit 'included' text",
        "sub_keys": "🔑 YooKassa settings",

        "pdf_ready": "📄 Done! Sending PDF 👇",
        "export_pdf": "📄 Export PDF",
    },
}

def t(key: str, lang: str) -> str:
    lang = lang if lang in TEXTS else "ru"
    return TEXTS[lang].get(key, f"[{key}]")
