"""
Обработчики для команд /start, /help и начального меню
"""
from aiogram import Router, F, types
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext


def register_start_handlers(router: Router, user_repository):
    """Регистрирует обработчики для /start, /help и начального меню"""
    
    @router.message(CommandStart())
    async def start(message: types.Message, state: FSMContext):
        user = message.from_user
        await user_repository.add_user(user.id)
        
        # Проверяем, не забанен ли пользователь
        if await user_repository.is_banned(user.id):
            await message.answer("❌ Ваш аккаунт заблокирован. Обратитесь к администратору.")
            return
        
        # Проверяем, является ли пользователь админом
        is_admin = await user_repository.is_admin(user.id)
        balance = await user_repository.get_user_balance(user.id)
        
        keyboard_buttons = [
            [InlineKeyboardButton(text="📊 Поиск по базе Сколково (ИИ)", callback_data="analyze")],
            [InlineKeyboardButton(text="🔍 Проверка по ИНН (внешние данные + оценка)", callback_data="check_startup")],
            [InlineKeyboardButton(text="👤 Мой аккаунт", callback_data="user_account")],
            [InlineKeyboardButton(text="❓ Помощь", callback_data="help")],
        ]
        
        if is_admin:
            keyboard_buttons.insert(2, [InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_panel")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        welcome_text = (
            "🚀 Привет! Я бот для поиска и анализа стартапов.\n\n"
            "📋 Доступные команды:\n"
            "/start — Начало работы\n"
            "/analyze — Поиск по базе Сколково (ИИ: запрос текстом)\n"
            "/check — Проверка по ИНН (внешние данные и ML-оценка)\n"
            "/pay — Приобрести запросы\n"
            "/help — Помощь\n\n"
        )
        
        # Приветственный бонус для новых пользователей
        if balance.get("standard", 0) == 3 and balance.get("premium", 0) == 0 and balance.get("ultra", 0) == 0:
            welcome_text += "🎁 Вам предоставлено 3 бесплатных запроса (Gemini 3 Pro)!\n\n"
        
        welcome_text += "🔍 Выберите действие:"
        
        await message.answer(welcome_text, reply_markup=keyboard)

    @router.message(Command("help"))
    async def help_command(message: types.Message):
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="В начало", callback_data="start_over")]
            ]
        )
        await message.answer(
            "📋 <b>Поиск по базе Сколково (ИИ)</b> — /analyze\n"
            "Произвольный запрос: название, ИНН или описание проектов. Поиск по базе, выбор модели: Gemini / Sonnet / Opus.\n\n"
            "<b>Проверка по ИНН (внешние данные + оценка)</b> — /check\n"
            "Отдельная функция: внешние источники (ЕГРЮЛ, БФО, новости), ML-оценка. Исходные данные и преддиктивная аналитика.\n\n"
            "/pay — Приобрести запросы · /help — Помощь\n\n"
            "Модели AI: ⚡ Gemini 3 Pro · 🧠 Claude Sonnet 4.5 · 💎 Claude Opus 4.6\n\n"
            "ML-оценка — преддиктивная аналитика на основе финансовых данных и кейсов из обучения. Не является инвестиционным советником.\n\n"
            "❓ Вопросы → @bfm5451",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    @router.callback_query(F.data == "start_over")
    async def start_over_callback(query: types.CallbackQuery):
        await query.answer()
        # Вызвать стартовое меню:
        user = query.from_user
        is_admin = await user_repository.is_admin(user.id)
        balance = await user_repository.get_user_balance(user.id)
        
        keyboard_buttons = [
            [InlineKeyboardButton(text="📊 Поиск по базе Сколково (ИИ)", callback_data="analyze")],
            [InlineKeyboardButton(text="🔍 Проверка по ИНН (внешние данные + оценка)", callback_data="check_startup")],
            [InlineKeyboardButton(text="👤 Мой аккаунт", callback_data="user_account")],
            [InlineKeyboardButton(text="❓ Помощь", callback_data="help")],
        ]
        
        if is_admin:
            keyboard_buttons.insert(2, [InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_panel")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        welcome_text = (
            "🚀 Привет! Я бот для поиска и анализа стартапов.\n\n"
            "📋 Доступные команды:\n"
            "/start — Начало работы\n"
            "/analyze — Поиск по базе Сколково (ИИ: запрос текстом)\n"
            "/check — Проверка по ИНН (внешние данные и ML-оценка)\n"
            "/pay — Приобрести запросы\n"
            "/help — Помощь\n\n"
        )
        
        if balance.get("standard", 0) == 3 and balance.get("premium", 0) == 0 and balance.get("ultra", 0) == 0:
            welcome_text += "🎁 Вам предоставлено 3 бесплатных запроса (Gemini 3 Pro)!\n\n"
        
        welcome_text += "🔍 Выберите действие:"
        
        await query.message.edit_text(welcome_text, reply_markup=keyboard)

    @router.callback_query(F.data == "help")
    async def help_btn(query: types.CallbackQuery):
        await query.message.edit_text(
            "📋 <b>Поиск по базе Сколково (ИИ)</b> — /analyze\n"
            "Запрос текстом: название, ИНН или описание. Модели: Gemini / Sonnet / Opus.\n\n"
            "<b>Проверка по ИНН</b> — /check: внешние данные и ML-оценка (преддиктивная аналитика).\n\n"
            "/pay — Приобрести запросы\n\n"
            "Модели: ⚡ Gemini · 🧠 Sonnet · 💎 Opus. Не является инвестиционным советником.\n\n"
            "❓ Вопросы → @bfm5451",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="В начало", callback_data="start_over")]
                ]
            ),
            parse_mode="HTML"
        )
        await query.answer()

    @router.callback_query(F.data == "user_account")
    async def user_account(query: types.CallbackQuery):
        await query.answer()
        
        user_id = query.from_user.id
        balance = await user_repository.get_user_balance(user_id)
        purchases = await user_repository.get_purchases(user_id)
        
        text = "👤 Мой аккаунт\n\n"
        text += "📊 Баланс запросов:\n"
        text += f"• Gemini 3 Pro: {balance.get('standard', 0)}\n"
        text += f"• Claude Sonnet 4.5: {balance.get('premium', 0)}\n"
        text += f"• Claude Opus 4.6: {balance.get('ultra', 0)}\n\n"
        
        if purchases:
            text += "📜 История покупок:\n"
            for i, purchase in enumerate(purchases[:10], 1):
                model_type, requests_amount, price, stars_spent, created_at = purchase
                date_str = created_at[:10] if created_at else "Неизвестно"
                text += f"{i}. {model_type}: {requests_amount} запросов за {stars_spent} ⭐ ({date_str})\n"
        else:
            text += "📜 История покупок пуста\n"
        
        if balance.get("standard", 0) == 3 and balance.get("premium", 0) == 0 and balance.get("ultra", 0) == 0 and not purchases:
            text += "\n🎁 Вам предоставлено 3 бесплатных запроса (Gemini 3 Pro)!"
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💳 Приобрести запросы", callback_data="pay")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="start_over")],
            ]
        )
        
        await query.message.edit_text(text, reply_markup=keyboard)

