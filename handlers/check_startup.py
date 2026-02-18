"""
Handler for "Проверить стартап" -- check any startup by INN using external sources.

Flow:
1. User enters /check or presses "Проверить стартап" button
2. User provides INN or company name
3. Bot searches Skolkovo DB first (ground truth)
4. Concurrently fetches data from external parsers (BFO, EGRUL, MOEX, news, Checko)
5. Extracts features, runs XGBoost model
6. Shows card with ML score and source reliability markers
7. Saves to external_startups DB
"""
from __future__ import annotations

import json
import logging
import re

from aiogram import Router, F, types, Bot
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from states import SkStates
from utils.formatters import escape_html

logger = logging.getLogger(__name__)


def register_check_startup_handlers(
    router: Router,
    bot: Bot,
    user_repository,
    skolkovo_db=None,
):
    """Register handlers for the /check (Проверить стартап) command."""

    @router.message(Command("check"))
    async def check_startup_cmd(message: types.Message, state: FSMContext):
        user_id = message.from_user.id
        if await user_repository.is_banned(user_id):
            await message.answer("❌ Ваш аккаунт заблокирован.")
            return

        await message.answer(
            "🔍 <b>Проверить стартап</b>\n\n"
            "Введите <b>ИНН</b> компании (10 или 12 цифр) или <b>название</b>:",
            parse_mode="HTML",
        )
        await state.set_state(SkStates.CHECK_STARTUP_INPUT)

    @router.callback_query(F.data == "check_startup")
    async def check_startup_btn(query: types.CallbackQuery, state: FSMContext):
        user_id = query.from_user.id
        if await user_repository.is_banned(user_id):
            await query.answer("❌ Ваш аккаунт заблокирован", show_alert=True)
            return

        await query.message.edit_text(
            "🔍 <b>Проверить стартап</b>\n\n"
            "Введите <b>ИНН</b> компании (10 или 12 цифр) или <b>название</b>:",
            parse_mode="HTML",
        )
        await state.set_state(SkStates.CHECK_STARTUP_INPUT)
        await query.answer()

    @router.message(SkStates.CHECK_STARTUP_INPUT, F.text)
    async def process_check_input(message: types.Message, state: FSMContext):
        user_input = message.text.strip()
        user_id = message.from_user.id

        # Determine if input is INN or name
        is_inn = bool(re.match(r"^\d{10}(\d{2})?$", user_input))
        inn = user_input if is_inn else ""
        company_name = "" if is_inn else user_input

        wait_msg = await message.answer("⏳ Собираю данные из внешних источников...")

        # 1. Check Skolkovo ground truth first
        skolkovo_match = None
        if skolkovo_db:
            for startup in skolkovo_db:
                if is_inn and str(startup.get("inn", "")).strip() == inn:
                    skolkovo_match = startup
                    break
                if not is_inn and company_name.lower() in str(startup.get("name", "")).lower():
                    skolkovo_match = startup
                    inn = str(startup.get("inn", ""))
                    break

        # 2. Fetch external data
        external_data = {}
        try:
            from parsers.manager import ParserManager
            mgr = ParserManager()
            if not inn and skolkovo_match:
                inn = str(skolkovo_match.get("inn", ""))
            if inn:
                external_data = await mgr.fetch_all(
                    inn=inn,
                    company_name=company_name or (skolkovo_match or {}).get("name", ""),
                )
            await mgr.close()
        except Exception as e:
            logger.error(f"Ошибка при получении внешних данных: {e}")

        # 3. Build response
        response_parts = []

        response_parts.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        response_parts.append(f"🔍 <b>Проверка: {escape_html(company_name or inn)}</b>")
        response_parts.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

        if skolkovo_match:
            response_parts.append("✅ <b>Найден в базе Сколково (Ground Truth)</b>")
            name = skolkovo_match.get("name", "н/д")
            response_parts.append(f"  • Название: {escape_html(name)}")
            response_parts.append(f"  • Кластер: {escape_html(skolkovo_match.get('cluster', 'н/д'))}")
            response_parts.append(f"  • Статус: {escape_html(skolkovo_match.get('status', 'н/д'))}")
            response_parts.append(f"  • ИНН: {skolkovo_match.get('inn', 'н/д')}")

            # Show ML score if available
            try:
                from scoring.ml_scoring import ml_analyze_startup
                analysis = ml_analyze_startup(skolkovo_match)
                if analysis:
                    overall = analysis.get("ml_overall", 0)
                    tl_map = {1: "🔴", 2: "🟡", 3: "🟢"}
                    tl = tl_map.get(analysis.get("TrafficLight", 1), "🔴")
                    response_parts.append(f"\n  {tl} ML-оценка: <b>{overall:.1f}/10</b>")
            except Exception:
                pass

            response_parts.append("")

        # 4. External data sections
        egrul = external_data.get("egrul", {})
        if egrul:
            response_parts.append("<b>📋 ЕГРЮЛ:</b>")
            response_parts.append(f"  • Название: {escape_html(egrul.get('name', 'н/д'))}")
            response_parts.append(f"  • ОГРН: {egrul.get('ogrn', 'н/д')}")
            response_parts.append(f"  • Статус: {escape_html(egrul.get('status', 'н/д'))}")
            if egrul.get("registration_date"):
                response_parts.append(f"  • Дата рег.: {egrul.get('registration_date')}")
            response_parts.append("")

        bfo = external_data.get("bfo", {})
        if bfo:
            response_parts.append("<b>💰 Финансы (БФО ФНС):</b>")
            financials = bfo.get("financials", {})
            if financials:
                for year in sorted(financials.keys(), reverse=True)[:3]:
                    yd = financials[year]
                    rev = yd.get("revenue", 0)
                    profit = yd.get("net_profit", 0)
                    rev_str = f"{rev / 1_000_000:.1f} млн" if rev else "н/д"
                    profit_str = f"{profit / 1_000_000:.1f} млн" if profit else "н/д"
                    response_parts.append(f"  • {year}: выручка {rev_str}, прибыль {profit_str}")
            else:
                response_parts.append("  • Отчёты не найдены")
            response_parts.append("")

        checko = external_data.get("checko", {})
        if checko:
            response_parts.append("<b>📊 Checko.ru:</b>")
            if checko.get("revenue"):
                response_parts.append(f"  • Выручка: {checko['revenue'] / 1_000_000:.1f} млн")
            if checko.get("net_profit"):
                response_parts.append(f"  • Чистая прибыль: {checko['net_profit'] / 1_000_000:.1f} млн")
            if checko.get("employees"):
                response_parts.append(f"  • Сотрудники: {checko['employees']}")
            if checko.get("status"):
                response_parts.append(f"  • Статус: {escape_html(checko['status'])}")
            response_parts.append("")

        moex = external_data.get("moex", {})
        if moex and moex.get("has_quotes"):
            response_parts.append("<b>📈 MOEX:</b>")
            response_parts.append(f"  • Тикер: {moex.get('ticker', 'н/д')}")
            if moex.get("last"):
                response_parts.append(f"  • Цена: {moex['last']}")
            if moex.get("marketcap"):
                cap = moex["marketcap"]
                response_parts.append(f"  • Капитализация: {cap / 1_000_000_000:.2f} млрд")
            response_parts.append("")

        news = external_data.get("news", {})
        if news and news.get("total_count", 0) > 0:
            response_parts.append(f"<b>📰 Упоминания в СМИ ({news['total_count']}):</b>")
            for mention in news.get("mentions", [])[:3]:
                src = mention.get("source", "").upper()
                title = escape_html(mention.get("title", "")[:100])
                response_parts.append(f"  • [{src}] {title}")
            response_parts.append("")

        # 5. ML scoring for external startup (if not in Skolkovo)
        if not skolkovo_match and (bfo or egrul):
            try:
                features = _extract_features_from_external(external_data)
                if features:
                    from scoring.ml_scoring import ml_analyze_startup
                    analysis = ml_analyze_startup(features)
                    if analysis:
                        overall = analysis.get("ml_overall", 0)
                        tl_map = {1: "🔴", 2: "🟡", 3: "🟢"}
                        tl = tl_map.get(analysis.get("TrafficLight", 1), "🔴")
                        response_parts.append(f"{tl} <b>ML-оценка (на основе внешних данных): {overall:.1f}/10</b>")
                        response_parts.append(f"  • Заполнено признаков: {features.get('_filled', 0)}/39")
                        response_parts.append(
                            "<i>Точность зависит от полноты данных. "
                            "Чем больше признаков заполнено, тем надёжнее оценка.</i>"
                        )
                        response_parts.append("")
            except Exception as e:
                logger.warning(f"ML scoring для внешнего стартапа: {e}")

        if not skolkovo_match and not external_data:
            response_parts.append("❌ Данные не найдены. Проверьте правильность ИНН.")

        # Send response
        text = "\n".join(response_parts)
        if len(text) > 4000:
            parts = [text[i:i + 4000] for i in range(0, len(text), 4000)]
            for part in parts:
                await bot.send_message(chat_id=message.chat.id, text=part, parse_mode="HTML")
        else:
            await wait_msg.edit_text(text, parse_mode="HTML")

        # 6. Save external startup to DB for future retraining
        if inn and external_data and not skolkovo_match:
            try:
                _save_external_startup(inn, external_data)
            except Exception as e:
                logger.warning("Не удалось сохранить внешний стартап в БД: %s", e)

        # Navigation keyboard
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔍 Проверить ещё", callback_data="check_startup")],
                [InlineKeyboardButton(text="📊 Анализ по базе", callback_data="analyze")],
            ]
        )
        await bot.send_message(chat_id=message.chat.id, text="Что дальше?", reply_markup=keyboard)

        await state.clear()


def _extract_features_from_external(external_data: dict) -> dict:
    """Build a startup-like dict from external data for ML scoring.

    Returns a dict that mimics the Skolkovo CSV fields as closely as possible,
    filled with whatever data the parsers provided.
    """
    features: dict = {}
    filled = 0

    bfo = external_data.get("bfo", {})
    egrul = external_data.get("egrul", {})
    checko = external_data.get("checko", {})

    # Name
    features["name"] = (
        egrul.get("name")
        or bfo.get("name")
        or checko.get("name", "Неизвестная компания")
    )

    # INN / OGRN
    features["inn"] = egrul.get("inn", bfo.get("inn", ""))
    features["ogrn"] = egrul.get("ogrn", "")

    # Status
    if egrul.get("is_active") is not None:
        features["status"] = "active" if egrul["is_active"] else "inactive"
        filled += 1

    # Year founded
    reg_date = egrul.get("registration_date", checko.get("registration_date", ""))
    if reg_date:
        import re
        year_match = re.search(r"(\d{4})", str(reg_date))
        if year_match:
            features["year"] = int(year_match.group(1))
            filled += 1

    # Financials from BFO
    financials = bfo.get("financials", {})
    for year in range(2020, 2026):
        year_data = financials.get(year, financials.get(str(year), {}))
        if year_data:
            rev = year_data.get("revenue", 0)
            profit = year_data.get("net_profit", 0)
            if rev:
                features[f"revenue_{year}"] = rev
                filled += 1
            if profit:
                features[f"profit_{year}"] = profit
                filled += 1

    # TRL/IRL/MRL/CRL -- unknown for external, leave at 0
    features["trl"] = 0
    features["mrl"] = 0
    features["irl"] = 0
    features["crl"] = 0

    # Patent count -- unknown
    features["patent_count"] = 0

    # Description
    features["company_description"] = ""
    features["product_description"] = ""
    features["technologies"] = ""

    features["_filled"] = filled
    return features if filled >= 2 else {}


def _save_external_startup(inn: str, external_data: dict) -> None:
    """
    Сохранение данных внешнего стартапа в SQLite для последующего дообучения ML.

    Каждый `/check` пополняет таблицу external_startups, которая потом
    используется в scoring/retrain.py для Semi-Supervised дообучения.
    """
    import sqlite3
    import os

    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "users.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS external_startups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inn TEXT UNIQUE NOT NULL,
            ogrn TEXT DEFAULT '',
            name TEXT NOT NULL DEFAULT '',
            full_legal_name TEXT DEFAULT '',
            region TEXT DEFAULT '',
            status_egrul TEXT DEFAULT '',
            registration_date TEXT,
            features_json TEXT DEFAULT '{}',
            features_filled_count INTEGER DEFAULT 0,
            ml_overall REAL,
            raw_data_json TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    egrul = external_data.get("egrul", {})
    bfo = external_data.get("bfo", {})
    checko = external_data.get("checko", {})

    name = egrul.get("name") or bfo.get("name") or checko.get("name", "")
    ogrn = egrul.get("ogrn", "")
    status = egrul.get("status", "")
    reg_date = egrul.get("registration_date", "")

    features = _extract_features_from_external(external_data)
    filled = features.pop("_filled", 0) if features else 0

    ml_overall = None
    if features:
        try:
            from scoring.ml_scoring import ml_analyze_startup
            analysis = ml_analyze_startup(features)
            if analysis:
                ml_overall = analysis.get("ml_overall")
        except Exception:
            pass

    cursor.execute("""
        INSERT INTO external_startups
            (inn, ogrn, name, status_egrul, registration_date,
             features_json, features_filled_count, ml_overall, raw_data_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(inn) DO UPDATE SET
            name = excluded.name,
            ogrn = excluded.ogrn,
            status_egrul = excluded.status_egrul,
            registration_date = excluded.registration_date,
            features_json = excluded.features_json,
            features_filled_count = excluded.features_filled_count,
            ml_overall = excluded.ml_overall,
            raw_data_json = excluded.raw_data_json,
            updated_at = CURRENT_TIMESTAMP
    """, (
        inn,
        ogrn,
        name,
        status,
        reg_date,
        json.dumps(features, ensure_ascii=False),
        filled,
        ml_overall,
        json.dumps(external_data, ensure_ascii=False, default=str),
    ))

    conn.commit()
    conn.close()
    logger.info("Внешний стартап сохранён: INN=%s, name=%s, filled=%d", inn, name, filled)
