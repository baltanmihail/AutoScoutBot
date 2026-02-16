"""
Обработчики для фильтров поиска
"""
from typing import Any, Dict
from aiogram import Router, F, types, Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from states import SkStates
from constants.constants import FILTER_NAMES


def register_filters_handlers(
    router: Router,
    bot: Bot,
    user_repository,
    available_filters: dict,
    start_search_func,
    parse_criteria_text_func,
    create_criteria_keyboard_func,
    get_filters_func
):
    """Регистрирует обработчики для фильтров"""
    
    @router.callback_query(F.data == "filter_analysis")
    async def process_analysis(query: types.CallbackQuery, state: FSMContext):
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Без критериев", callback_data="no_criteria")]]
        )
        await query.message.edit_text(
            "⚙️ Введите критерии оценки (если нужны) в формате:\n"
            "DeepTech=3 - только высокотехнологичные\n"
            "GenAI=есть - с использованием GenAI\n"
            "WOW=да - с WOW-эффектом\n"
            "Можно комбинировать: DeepTech=3 GenAI=есть\n\n"
            "Или нажмите кнопку 'Без критериев'",
            reply_markup=keyboard,
        )
        await state.set_state(SkStates.FILTERS_CRITERIA)

    @router.callback_query(SkStates.FILTERS_CRITERIA, F.data == "no_criteria")
    async def criteria_none(query: types.CallbackQuery, state: FSMContext):
        await query.answer()
        await show_filters_menu(query, state, available_filters=available_filters)

    @router.message(SkStates.FILTERS_CRITERIA, F.text)
    async def process_filters_criteria_text(message: types.Message, state: FSMContext):
        user_input = message.text.strip()
        criteria_parsed = parse_criteria_text_func(user_input)
        if criteria_parsed:
            user_data = await state.get_data()
            filters = user_data.get("filters", {"criteria": {}, "additional": {}})
            filters["criteria"].update(criteria_parsed)
            await state.update_data(filters=filters)
            criteria_text = ", ".join([f"{k}={v}" for k, v in criteria_parsed.items()])
            await message.answer(f"✅ Установлены критерии: {criteria_text}")
            await show_filters_menu(message, state, available_filters=available_filters)
        else:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="Без критериев", callback_data="no_criteria")]]
            )
            await message.answer(
                "⚠️ Неверный формат критериев. Используйте формат:\n"
                "DeepTech=3 GenAI=есть WOW=да\n\n"
                "Или нажмите кнопку ниже:",
                reply_markup=keyboard,
            )

    @router.callback_query(SkStates.FILTERS_MENU)
    async def main_callback_handler(query: types.CallbackQuery, state: FSMContext):
        await query.answer()
        data = query.data
        ud = await state.get_data()
        
        if data == "apply_filters":
            filters = await get_filters_func(ud)
            await start_search_func(query, state, filters)
            return
        
        if data == "reset_filters":
            await show_filters_menu(query, state, reset=True, available_filters=available_filters)
            return
        
        if data == "cancel_filters":
            await query.message.edit_text("❌ Настройка фильтров отменена")
            await state.clear()
            return

        if data.startswith("criteria_"):
            # Выбор критериев через inline-кнопки
            parts = data.split("_", 2)
            if len(parts) == 3:
                _, criteria_key, value = parts
                ud = await state.get_data()
                filters = ud.get("filters", {"criteria": {}, "additional": {}})
                filters["criteria"][criteria_key] = value
                await state.update_data(filters=filters)
                kb = create_criteria_keyboard_func(filters["criteria"])
                await query.message.edit_reply_markup(reply_markup=kb)
            elif data == "criteria_done":
                await show_filters_menu(query, state, available_filters=available_filters)
            return

        if data.startswith("filter_") and not data.startswith("filterval_"):
            filter_type = data.split("_", 1)[1]
            if filter_type in FILTER_NAMES:
                await show_filter_options_improved(query, state, filter_type, available_filters=available_filters)
            else:
                await query.answer("⚠️ Неизвестный фильтр")
                await show_filters_menu(query, state, available_filters=available_filters)
            return

        if data.startswith("filterval_") or data in ["filter_done", "filter_clear", "filter_back"]:
            ud = await state.get_data()
            current_filter = ud.get("current_filter")
            if data == "filter_back":
                await show_filters_menu(query, state, available_filters=available_filters)
                return
            if data == "filter_done":
                await show_filters_menu(query, state, available_filters=available_filters)
                return
            if data == "filter_clear":
                filters = ud.get("filters", {"criteria": {}, "additional": {}})
                if current_filter in filters["additional"]:
                    del filters["additional"][current_filter]
                await state.update_data(filters=filters)
                await show_filter_options_improved(query, state, current_filter, available_filters=available_filters)
                return
            if data.startswith("filterval_"):
                parts = data.split("_")
                filter_type = parts[1]
                ud = await state.get_data()
                filters = ud.get("filters", {"criteria": {}, "additional": {}})
                current_values = filters["additional"].get(filter_type, [])
                if not isinstance(current_values, list):
                    current_values = [current_values] if current_values else []
                if filter_type in ["trl", "irl", "mrl", "crl"]:
                    value = parts[2]
                    if value in current_values:
                        current_values.remove(value)
                    else:
                        current_values.append(value)
                else:
                    option_index = int(parts[2])
                    options = available_filters.get(filter_type, [])
                    if 0 <= option_index < len(options):
                        value = options[option_index]
                        if value in current_values:
                            current_values.remove(value)
                        else:
                            current_values.append(value)
                if current_values:
                    filters["additional"][filter_type] = current_values
                else:
                    filters["additional"].pop(filter_type, None)
                await state.update_data(filters=filters, current_filter=filter_type)
                await show_filter_options_improved(query, state, filter_type, available_filters=available_filters)
            return

        if data.startswith("format_"):
            # Обработка формата вывода (будет в другом модуле)
            return

        if data == "cancel":
            await query.message.edit_text("❌ Операция отменена")
            await state.clear()
            return

        await query.message.edit_text("❌ Неизвестная команда")


async def show_filters_menu(event: types.Message | types.CallbackQuery, state: FSMContext, reset: bool = False, available_filters: dict = None):
    """Показать меню фильтров"""
    from constants.constants import FILTER_NAMES
    
    user_data = await state.get_data()
    filters = user_data.get("filters", {"criteria": {}, "additional": {}})
    if reset:
        filters = {"criteria": {}, "additional": {}}
        await state.update_data(filters=filters)

    active_filters_text = []
    if filters["criteria"]:
        criteria_items = [f"{k}={v}" for k, v in filters["criteria"].items()]
        active_filters_text.append(f"🎯 Критерии: {', '.join(criteria_items)}")
    if filters["additional"]:
        additional_items = []
        for k, v in filters["additional"].items():
            name = FILTER_NAMES.get(k, k)
            if isinstance(v, list):
                additional_items.append(f"{name}: {len(v)} выбрано")
            else:
                additional_items.append(f"{name}: {v}")
        if additional_items:
            active_filters_text.append(f"🔧 Фильтры: {', '.join(additional_items)}")
    if not active_filters_text:
        active_filters_text.append("🔍 Фильтры не заданы")
    filter_text = "\n".join(active_filters_text)

    keyboard = [
        [
            InlineKeyboardButton(text="📂 Направление", callback_data="filter_category"),
            InlineKeyboardButton(text="📅 Год", callback_data="filter_year"),
        ],
        [
            InlineKeyboardButton(text="🚀 Стадия", callback_data="filter_stage"),
            InlineKeyboardButton(text="🌍 Регион", callback_data="filter_country"),
        ],
        [
            InlineKeyboardButton(text="🔬 TRL", callback_data="filter_trl"),
            InlineKeyboardButton(text="🏭 IRL", callback_data="filter_irl"),
        ],
        [
            InlineKeyboardButton(text="⚙️ MRL", callback_data="filter_mrl"),
            InlineKeyboardButton(text="💼 CRL", callback_data="filter_crl"),
        ],
        [
            InlineKeyboardButton(text="✅ Применить фильтры", callback_data="apply_filters"),
            InlineKeyboardButton(text="🗑 Сбросить все", callback_data="reset_filters"),
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_filters")],
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    text = f"🔧 Настройка фильтров\n\n{filter_text}\n\nВыберите фильтр для настройки:"

    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, reply_markup=reply_markup)
    else:
        await event.answer(text, reply_markup=reply_markup)
    await state.set_state(SkStates.FILTERS_MENU)


async def show_filter_options_improved(query: types.CallbackQuery, state: FSMContext, filter_type: str, available_filters: dict = None):
    """Показать опции для выбранного фильтра"""
    from constants.constants import FILTER_NAMES
    
    user_data = await state.get_data()
    filters = user_data.get("filters", {"criteria": {}, "additional": {}})
    current_values = filters["additional"].get(filter_type, [])
    if not isinstance(current_values, list):
        current_values = [current_values] if current_values else []

    filter_name = FILTER_NAMES[filter_type]

    if filter_type in ["trl", "irl", "mrl", "crl"]:
        keyboard = []
        row1 = []
        for i in range(1, 6):
            selected = "✅" if str(i) in current_values else ""
            row1.append(
                InlineKeyboardButton(text=f"{selected}{i}", callback_data=f"filterval_{filter_type}_{i}")
            )
        keyboard.append(row1)
        row2 = []
        for i in range(6, 10):
            selected = "✅" if str(i) in current_values else ""
            row2.append(
                InlineKeyboardButton(text=f"{selected}{i}", callback_data=f"filterval_{filter_type}_{i}")
            )
        keyboard.append(row2)
        keyboard.append(
            [
                InlineKeyboardButton(text="✅ Готово", callback_data="filter_done"),
                InlineKeyboardButton(text="🗑 Очистить", callback_data="filter_clear"),
            ]
        )
        keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="filter_back")])
    else:
        if available_filters is None:
            available_filters = {}
        options = available_filters.get(filter_type, [])
        keyboard = []
        for i in range(0, len(options), 2):
            row = []
            for j in range(i, min(i + 2, len(options))):
                option = options[j]
                selected = "✅ " if option in current_values else ""
                short_name = option[:15] + "..." if len(option) > 15 else option
                row.append(
                    InlineKeyboardButton(
                        text=f"{selected}{short_name}",
                        callback_data=f"filterval_{filter_type}_{j}",
                    )
                )
            keyboard.append(row)
        keyboard.append(
            [
                InlineKeyboardButton(text="✅ Готово", callback_data="filter_done"),
                InlineKeyboardButton(text="🗑 Очистить", callback_data="filter_clear"),
            ]
        )
        keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="filter_back")])

    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    current_text = f"\n\n🎯 Выбрано: {', '.join(current_values)}" if current_values else "\n\n❌ Ничего не выбрано"
    text = f"🔧 {filter_name}{current_text}\n\nВыберите значения (можно несколько):"

    await query.message.edit_text(text, reply_markup=reply_markup)
    await state.update_data(current_filter=filter_type)
    await state.set_state(SkStates.FILTERS_MENU)