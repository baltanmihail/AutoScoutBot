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
            [InlineKeyboardButton(text="📊 Анализ Сколково", callback_data="analyze")],
            [InlineKeyboardButton(text="🔍 Проверить стартап (по ИНН)", callback_data="check_startup")],
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
            "/analyze — Анализ базы Сколково\n"
            "/check — Проверить стартап по ИНН\n"
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
            "📋 Список доступных команд:\n\n"
            "/start — Начало работы с ботом\n"
            "/analyze — Анализ стартапов из базы Сколково\n"
            "/check — Проверить стартап по ИНН (внешние источники)\n"
            "/pay — Приобрести запросы\n"
            "/help — Показать этот список команд\n"
            "/paysupport — Поддержка по вопросам оплаты\n\n"
            "Модели AI:\n"
            "• ⚡ Gemini 3 Pro — быстрый анализ + рекомендация\n"
            "• 🧠 Claude Sonnet 4.5 — глубокий анализ\n"
            "• 💎 Claude Opus 4.6 — максимально детальный анализ\n\n"
            "ML-оценка (XGBoost, 6 измерений 0-10):\n"
            "• Общий балл, технологии, инновации\n"
            "• Рыночный потенциал, команда, финансы\n\n"
            "Не является инвестиционным советником!\n\n"
            "❓ Вопросы → @bfm5451",
            reply_markup=keyboard
        )

    @router.callback_query(F.data == "start_over")
    async def start_over_callback(query: types.CallbackQuery):
        await query.answer()
        # Вызвать стартовое меню:
        user = query.from_user
        is_admin = await user_repository.is_admin(user.id)
        balance = await user_repository.get_user_balance(user.id)
        
        keyboard_buttons = [
            [InlineKeyboardButton(text="📊 Анализ Сколково", callback_data="analyze")],
            [InlineKeyboardButton(text="🔍 Проверить стартап (по ИНН)", callback_data="check_startup")],
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
            "/analyze — Анализ базы Сколково\n"
            "/check — Проверить стартап по ИНН\n"
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
            "📋 Список доступных команд:\n\n"
            "/start — Начало работы с ботом\n"
            "/analyze — Анализ стартапов из базы Сколково\n"
            "/check — Проверить стартап по ИНН (внешние источники)\n"
            "/pay — Приобрести запросы\n"
            "/help — Показать этот список команд\n"
            "/paysupport — Поддержка по вопросам оплаты\n\n"
            "Модели AI:\n"
            "• ⚡ Gemini 3 Pro — анализ + рекомендация\n"
            "• 🧠 Claude Sonnet 4.5 — глубокий анализ\n"
            "• 💎 Claude Opus 4.6 — максимальная детализация\n\n"
            "Не является инвестиционным советником!\n\n"
            "❓ Вопросы → @bfm5451",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="В начало", callback_data="start_over")]
                ]
            )
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

