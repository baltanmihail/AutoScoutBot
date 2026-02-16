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
            [InlineKeyboardButton(text="Анализ Сколково", callback_data="analyze")],
            [InlineKeyboardButton(text="Мой аккаунт", callback_data="user_account")],
            [InlineKeyboardButton(text="Помощь", callback_data="help")],
        ]
        
        # Добавляем кнопку админ-панели только для админов
        if is_admin:
            keyboard_buttons.insert(1, [InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_panel")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        welcome_text = (
            "🚀 Привет! Я бот для поиска перспективных стартапов из базы Сколково.\n\n"
            "📋 Доступные команды:\n"
            "/start - Начало работы с ботом\n"
            "/analyze - Анализ базы Сколково\n"
            "/help - Показать список всех команд\n"
            "/pay - Приобрести запросы\n"
            "/paysupport - Поддержка по вопросам оплаты\n\n"
        )
        
        # Добавляем информацию о бесплатных запросах для новых пользователей
        if balance["standard"] == 3 and balance["pro"] == 0 and balance["max"] == 0:
            welcome_text += "🎁 Вам предоставлено 3 бесплатных запроса по модели Standard!\n\n"
        
        welcome_text += "🔍 Выберите команду для продолжения:"
        
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
            "/start - Начало работы с ботом\n"
            "/analyze - Анализ стартапов из базы Сколково\n"
            "/help - Показать этот список команд\n"
            "/pay - Приобрести запросы\n"
            "/paysupport - Поддержка по вопросам оплаты\n\n"
            "Анализ стартапов из базы Сколково:\n"
            "- Выберите анализ с помощью ИИ или фильтров\n"
            "- Выберите модель для анализа или настройте фильтры\n"
            "- Получите детальный анализ с оценками DeepTech, GenAI, WOW и светофор\n"
            "- Результаты доступны в текстовом виде (3 стартапа) и в файлах Excel/CSV\n\n"
            "Критерии оценки стартапов:\n"
            "- DeepTech: 1-3 (уровень технологичности)\n"
            "- GenAI: есть/нет (использование генеративного ИИ)\n"
            "- WOW: да/нет (DeepTech≥2 + GenAI)\n"
            "- Светофор: 1-3 (комплексная оценка)\n\n\n"
            "Не является инвестиционным советником и не предоставляет соотвествующие рекомендации!!!\n" 
            "Пользование продуктом осуществляется на свой страх и риск.\n\n"
            "❓ По всем вопросам обращайтесь к разработчику бота\n"
            "@bfm5451",
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
            [InlineKeyboardButton(text="Анализ Сколково", callback_data="analyze")],
            [InlineKeyboardButton(text="Мой аккаунт", callback_data="user_account")],
            [InlineKeyboardButton(text="Помощь", callback_data="help")],
        ]
        
        if is_admin:
            keyboard_buttons.insert(1, [InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_panel")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        welcome_text = (
            "🚀 Привет! Я бот для поиска перспективных стартапов из базы Сколково.\n\n"
            "📋 Доступные команды:\n"
            "/start - Начало работы с ботом\n"
            "/analyze - Анализ базы Сколково\n"
            "/help - Показать список всех команд\n"
            "/pay - Приобрести запросы\n"
            "/paysupport - Поддержка по вопросам оплаты\n\n"
        )
        
        if balance["standard"] == 3 and balance["pro"] == 0 and balance["max"] == 0:
            welcome_text += "🎁 Вам предоставлено 3 бесплатных запроса по модели Standard!\n\n"
        
        welcome_text += "🔍 Выберите команду для продолжения:"
        
        await query.message.edit_text(welcome_text, reply_markup=keyboard)

    @router.callback_query(F.data == "help")
    async def help_btn(query: types.CallbackQuery):
        await query.message.edit_text(
            "📋 Список доступных команд:\n\n"
            "/start - Начало работы с ботом\n"
            "/analyze - Анализ стартапов из базы Сколково\n"
            "/help - Показать этот список команд\n"
            "/pay - Приобрести запросы\n"
            "/paysupport - Поддержка по вопросам оплаты\n\n"
            "Анализ стартапов из базы Сколково:\n"
            "- Выберите анализ с помощью ИИ или фильтров\n"
            "- Выберите модель для анализа или настройте фильтры\n"
            "- Получите детальный анализ с оценками DeepTech, GenAI, WOW и светофор\n"
            "- Результаты доступны в текстовом виде (3 стартапа) и в файлах Excel/CSV\n\n"
            "Критерии оценки стартапов:\n"
            "- DeepTech: 1-3 (уровень технологичности)\n"
            "- GenAI: есть/нет (использование генеративного ИИ)\n"
            "- WOW: да/нет (DeepTech≥2 + GenAI)\n"
            "- Светофор: 1-3 (комплексная оценка)\n\n\n"
            "Не является инвестиционным советником и не предоставляет соотвествующие рекомендации!!!\n" 
            "Пользование продуктом осуществляется на свой страх и риск.\n\n"
            "❓ По всем вопросам обращайтесь к разработчику бота\n"
            "@bfm5451",
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
        text += f"• Standard: {balance['standard']} запросов\n"
        text += f"• Pro: {balance['pro']} запросов\n"
        text += f"• Max: {balance['max']} запросов\n\n"
        
        if purchases:
            text += "📜 История покупок:\n"
            for i, purchase in enumerate(purchases[:10], 1):  # Показываем последние 10
                model_type, requests_amount, price, stars_spent, created_at = purchase
                date_str = created_at[:10] if created_at else "Неизвестно"
                text += f"{i}. {model_type}: {requests_amount} запросов за {stars_spent} ⭐ ({date_str})\n"
        else:
            text += "📜 История покупок пуста\n"
        
        # Добавляем информацию о бесплатных запросах
        if balance["standard"] == 3 and balance["pro"] == 0 and balance["max"] == 0 and not purchases:
            text += "\n🎁 Вам предоставлено 3 бесплатных запроса по модели Standard!"
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💳 Приобрести запросы", callback_data="pay")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="start_over")],
            ]
        )
        
        await query.message.edit_text(text, reply_markup=keyboard)

