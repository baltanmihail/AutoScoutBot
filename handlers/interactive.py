"""
Обработчики для интерактивных действий после вывода результатов
"""
from aiogram import Router, F, types, Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext

from states import SkStates
from utils.excel_generator import generate_csv, generate_excel
from logger import logger


def register_interactive_handlers(
    router: Router,
    bot: Bot,
    user_repository,
    gigachat_client,
    start_search_func
):
    """Регистрирует обработчики для интерактивных действий"""
    
    @router.callback_query(F.data.in_(["format_excel", "format_csv"]))
    async def process_output_format_callback(query: types.CallbackQuery, state: FSMContext):
        """Обработчик экспорта - работает независимо от состояния"""
        data = await state.get_data()
        processed_startups = data.get("processed_startups", [])
        
        if not processed_startups:
            await query.answer("❌ Нет данных для экспорта. Выполните поиск сначала.", show_alert=True)
            return
        
        actual_count = len(processed_startups)

        if query.data == "format_excel":
            excel_file = generate_excel(processed_startups)
            await query.message.answer_document(
                document=BufferedInputFile(excel_file.read(), filename="startups_report.xlsx"),
                caption=f"📊 Отчет по {actual_count} стартапам из базы Сколково",
            )
        elif query.data == "format_csv":
            filename, _ = generate_csv(processed_startups)
            with open(filename, "rb") as f:
                await query.message.answer_document(
                    document=BufferedInputFile(f.read(), filename=filename),
                    caption=f"📊 Отчет по {actual_count} стартапам из базы Сколково",
                )
        
        await query.answer("✅ Файл отправлен!")
        
        # НЕ очищаем состояние, чтобы данные оставались доступны для других действий

    @router.callback_query(F.data.startswith("action_rerun_"))
    async def action_rerun_callback(query: types.CallbackQuery, state: FSMContext):
        """Обработчик: Повторный поиск по тому же запросу"""
        await query.answer()
        
        user_id = query.from_user.id
        data = await state.get_data()
        user_request = data.get("user_request", "")
        filters = data.get("filters", {})
        
        if not user_request:
            await query.message.edit_text("❌ Не удалось найти исходный запрос. Начните новый поиск.")
            await state.clear()
            return
        
        # Показываем выбор модели
        from services.interactive_actions import create_model_selection_keyboard
        
        keyboard = await create_model_selection_keyboard(
            user_id=user_id,
            user_repository=user_repository,
            action_type="rerun",
            action_data="none"
        )
        
        if not keyboard:
            await query.message.edit_text(
                "❌ У вас нет доступных запросов. Приобретите их для продолжения.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Приобрести запросы", callback_data="pay")]
                ])
            )
            return
        
        await query.message.edit_text(
            "🔄 <b>Повторный поиск</b>\n\n"
            f"Запрос: <i>{user_request}</i>\n\n"
            "Списывается 1 запрос выбранной модели.\n\n"
            "Выберите модель для поиска:",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        await state.set_state(SkStates.ACTION_RERUN)

    @router.callback_query(F.data.startswith("action_refine_"))
    async def action_refine_callback(query: types.CallbackQuery, state: FSMContext):
        """Обработчик: Уточнение запроса"""
        await query.answer()
        
        data = await state.get_data()
        user_request = data.get("user_request", "")
        
        await query.message.edit_text(
            "✏️ <b>Уточнение запроса</b>\n\n"
            f"Текущий запрос: <i>{user_request}</i>\n\n"
            "Введите уточненный запрос:",
            parse_mode='HTML'
        )
        await state.set_state(SkStates.ACTION_REFINE)

    @router.message(SkStates.ACTION_REFINE, F.text)
    async def process_refined_query(message: types.Message, state: FSMContext):
        """Обработка уточненного запроса"""
        user_id = message.from_user.id
        refined_query = message.text.strip()
        
        # Показываем выбор модели
        from services.interactive_actions import create_model_selection_keyboard
        
        keyboard = await create_model_selection_keyboard(
            user_id=user_id,
            user_repository=user_repository,
            action_type="refine",
            action_data="none"
        )
        
        if not keyboard:
            await message.answer(
                "❌ У вас нет доступных запросов. Приобретите их для продолжения.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Приобрести запросы", callback_data="pay")]
                ])
            )
            await state.clear()
            return
        
        # Сохраняем уточненный запрос
        await state.update_data(user_request=refined_query)
        
        await message.answer(
            f"✏️ <b>Уточненный запрос:</b> <i>{refined_query}</i>\n\n"
            "Списывается 1 запрос выбранной модели.\n\n"
            "Выберите модель для поиска:",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        await state.set_state(SkStates.ACTION_REFINE)

    @router.callback_query(F.data == "action_deep_analysis_menu")
    async def action_deep_analysis_menu_callback(query: types.CallbackQuery, state: FSMContext):
        """Обработчик: Меню выбора стартапа для глубокого анализа"""
        await query.answer()
        
        data = await state.get_data()
        processed_startups = data.get("processed_startups", [])
        
        if not processed_startups:
            await query.message.edit_text("❌ Не найдено стартапов для анализа.")
            return
        
        from services.interactive_actions import create_deep_analysis_keyboard
        
        startup_ids = [s.get("id", "") for s in processed_startups]
        startup_names = [s.get("name", f"Стартап {i}") for i, s in enumerate(processed_startups, 1)]
        
        keyboard = create_deep_analysis_keyboard(startup_ids, startup_names)
        
        await query.message.edit_text(
            "🔬 <b>Глубокий анализ стартапа</b>\n\n"
            "Выберите стартап для детального анализа:",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        await state.set_state(SkStates.DEEP_ANALYSIS_SELECTION)

    @router.callback_query(F.data.startswith("deep_analysis_"))
    async def deep_analysis_startup_callback(query: types.CallbackQuery, state: FSMContext):
        """Обработчик: Выбор стартапа для глубокого анализа"""
        await query.answer()
        
        startup_id = query.data.replace("deep_analysis_", "")
        
        data = await state.get_data()
        processed_startups = data.get("processed_startups", [])
        
        # Находим выбранный стартап
        selected_startup = None
        for s in processed_startups:
            if s.get("id", "") == startup_id:
                selected_startup = s
                break
        
        if not selected_startup:
            await query.message.edit_text("❌ Стартап не найден.")
            return
        
        user_id = query.from_user.id
        
        # Показываем выбор модели
        from services.interactive_actions import create_model_selection_keyboard
        
        keyboard = await create_model_selection_keyboard(
            user_id=user_id,
            user_repository=user_repository,
            action_type="deep_analysis",
            action_data=startup_id
        )
        
        if not keyboard:
            await query.message.edit_text(
                "❌ У вас нет доступных запросов. Приобретите их для продолжения.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Приобрести запросы", callback_data="pay")]
                ])
            )
            return
        
        startup_name = selected_startup.get("name", "н/д")
        
        await query.message.edit_text(
            f"🔬 <b>Глубокий анализ</b>\n\n"
            f"Стартап: <b>{startup_name}</b>\n\n"
            "Списывается <b>1 запрос</b> выбранной модели (как один обычный анализ).\n"
            "Тарифы и пакеты: /help\n\n"
            "Выберите модель для анализа:",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        
        await state.update_data(selected_startup_id=startup_id, selected_startup=selected_startup)
        await state.set_state(SkStates.DEEP_ANALYSIS_MODEL)

    @router.callback_query(F.data.startswith("model_"))
    async def model_selected_for_action(query: types.CallbackQuery, state: FSMContext):
        """Обработчик: Выбор модели для интерактивного действия"""
        await query.answer()
        
        from services.interactive_actions import parse_action_callback
        
        parsed = parse_action_callback(query.data)
        
        # Проверяем, что это callback для интерактивного действия (не простой выбор модели для оплаты)
        if parsed.get("type") != "model_selected":
            # Это не наш callback, пропускаем (это простой выбор модели для оплаты)
            return
        
        action_type = parsed.get("action_type")
        model_type = parsed.get("model")
        action_data = parsed.get("action_data", "none")
        
        logger.info(f"Обработка выбора модели для интерактивного действия: {action_type}, модель: {model_type}, данные: {action_data}")
        
        user_id = query.from_user.id
        
        # Проверяем наличие запросов
        balance = await user_repository.get_user_balance(user_id)
        logger.info(f"Баланс пользователя {user_id}: {balance}")
        
        if not balance or balance.get(model_type, 0) <= 0:
            await query.message.edit_text(
                f"❌ У вас нет доступных запросов для модели {model_type}.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Приобрести запросы", callback_data="pay")]
                ])
            )
            return
        
        # Устанавливаем модель
        gigachat_client.set_model(model_type)
        
        data = await state.get_data()
        
        if action_type == "rerun" or action_type == "refine":
            # Повторный поиск или уточненный поиск
            user_request = data.get("user_request", "")
            if not user_request:
                await query.message.edit_text("❌ Не найден запрос для поиска.")
                return
            
            # Получаем фильтры
            filters = gigachat_client.get_startup_filters(user_request, user_repository, user_id)
            
            await state.update_data(model_type=model_type, user_request=user_request)
            await start_search_func(query, state, filters)
        
        elif action_type == "deep_analysis":
            # Глубокий анализ
            selected_startup = data.get("selected_startup")
            if not selected_startup:
                await query.message.edit_text("❌ Стартап не найден.")
                return
            
            # Списание запроса
            await user_repository.use_request(user_id, model_type)
            balance = await user_repository.get_user_balance(user_id)
            logger.info(f"Пользователь {user_id} использовал запрос для глубокого анализа ({model_type}). Баланс: {balance}")
            
            await query.message.edit_text("🔬 Провожу глубокий анализ...")
            
            try:
                from services.deep_analysis import DeepAnalysisService
                
                deep_analysis_service = DeepAnalysisService()
                user_request = data.get("user_request", "")
                
                # Use async deep analysis with external sources
                analysis = await deep_analysis_service.analyze_startup_deep_async(
                    selected_startup,
                    user_request=user_request,
                    include_external=True,
                )
                
                # Форматируем отчет
                report = deep_analysis_service.format_deep_analysis_report(analysis)
                
                # Send report (may exceed 4096 char Telegram limit)
                if len(report) > 4000:
                    await query.message.edit_text("🔬 Анализ завершён. Отчёт отправлен ниже.")
                    parts = [report[i:i + 4000] for i in range(0, len(report), 4000)]
                    for part in parts:
                        await bot.send_message(chat_id=query.message.chat.id, text=part, parse_mode="HTML")
                else:
                    await query.message.edit_text(report, parse_mode='HTML')
                
                # Предлагаем экспорт
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="📤 Экспорт в Excel", callback_data="deep_export_excel")],
                        [InlineKeyboardButton(text="◀️ Назад к результатам", callback_data="action_back_to_results")],
                    ]
                )
                await query.message.answer(
                    "📤 Хотите экспортировать полный отчет?",
                    reply_markup=keyboard
                )
                
                await state.update_data(deep_analysis=analysis)
                
            except Exception as e:
                logger.exception("Ошибка глубокого анализа")
                await query.message.edit_text(f"❌ Ошибка при проведении анализа: {str(e)}")

    @router.callback_query(F.data == "action_back_to_results")
    async def action_back_to_results(query: types.CallbackQuery, state: FSMContext):
        """Возврат к результатам поиска"""
        await query.answer()
        
        data = await state.get_data()
        processed_startups = data.get("processed_startups", [])
        user_request = data.get("user_request", "")
        startup_ids = data.get("startup_ids", [])
        query_id = data.get("query_id")
        
        from services.interactive_actions import create_results_actions_keyboard
        
        keyboard = create_results_actions_keyboard(
            user_request=user_request,
            startup_ids=startup_ids,
            query_id=query_id
        )
        
        await query.message.edit_text(
            "🔍 <b>Результаты поиска</b>\n\n"
            "Выберите действие:",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        await state.set_state(SkStates.OUTPUT_FORMAT)

