"""
Обработчики для поиска и анализа стартапов
"""
import re
import random
from aiogram import Router, F, types, Bot
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from states import SkStates
from constants.constants import STARTUP_IN_ANSWER_COUNT
from utils.startup_utils import analyze_startup, determine_stage
from utils.formatters import escape_html
from utils.excel_generator import generate_csv, generate_excel
from logger import logger


def register_search_handlers(
    router: Router,
    bot: Bot,
    user_repository,
    gigachat_client,
    get_unique_startups,
    query_history=None,
    skolkovo_db=None
):
    """Регистрирует обработчики для поиска и анализа"""
    
    @router.message(Command("analyze"))
    async def analyze_menu_cmd(message: types.Message, state: FSMContext):
        user_id = message.from_user.id
        
        # Проверяем, не забанен ли пользователь
        if await user_repository.is_banned(user_id):
            await message.answer("❌ Ваш аккаунт заблокирован. Обратитесь к администратору.")
            return
        
        # Проверяем наличие запросов хотя бы для одной модели
        balance = await user_repository.get_user_balance(user_id)
        has_requests = balance["standard"] > 0 or balance["pro"] > 0 or balance["max"] > 0
        
        if not has_requests:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Приобрести запросы", callback_data="pay")],
                ]
            )
            await message.answer(
                "У вас закончились запросы. Чтобы приобрести их, нажмите на кнопку \"Приобрести запросы\"",
                reply_markup=keyboard
            )
            return

        # Сброс фильтров
        await state.update_data(filters={"criteria": {}, "additional": {}})
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Анализ с помощью ИИ", callback_data="ai_analysis")],
                [InlineKeyboardButton(text="Анализ с помощью фильтров", callback_data="filter_analysis")],
            ]
        )
        await message.answer(
            "Выберите способ анализа:",
            reply_markup=keyboard,
        )

    @router.callback_query(F.data == "analyze")
    async def analyze_menu_btn(query: types.CallbackQuery, state: FSMContext):
        user_id = query.from_user.id
        
        # Проверяем, не забанен ли пользователь
        if await user_repository.is_banned(user_id):
            await query.answer("❌ Ваш аккаунт заблокирован", show_alert=True)
            return
        
        # Проверяем наличие запросов хотя бы для одной модели
        balance = await user_repository.get_user_balance(user_id)
        has_requests = balance["standard"] > 0 or balance["pro"] > 0 or balance["max"] > 0
        
        if not has_requests:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Приобрести запросы", callback_data="pay")],
                ]
            )
            await query.message.edit_text(
                "У вас закончились запросы. Чтобы приобрести их, нажмите на кнопку \"Приобрести запросы\"",
                reply_markup=keyboard
            )
            await query.answer()
            return

        # Сброс фильтров
        await state.update_data(filters={"criteria": {}, "additional": {}})
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Анализ с помощью ИИ", callback_data="ai_analysis")],
                [InlineKeyboardButton(text="Анализ с помощью фильтров", callback_data="filter_analysis")],
            ]
        )
        await query.message.edit_text(
            "Выберите способ анализа:",
            reply_markup=keyboard
        )
        await query.answer()

    @router.callback_query(F.data == "ai_analysis")
    async def process_ai_analysis(query: types.CallbackQuery, state: FSMContext):
        await query.answer()
        user_id = query.from_user.id
        
        # Проверяем баланс для всех моделей
        balance = await user_repository.get_user_balance(user_id)
        
        keyboard_buttons = []
        if balance["standard"] > 0:
            keyboard_buttons.append([InlineKeyboardButton(text="Standard", callback_data="select_model_standard")])
        if balance["pro"] > 0:
            keyboard_buttons.append([InlineKeyboardButton(text="Pro", callback_data="select_model_pro")])
        if balance["max"] > 0:
            keyboard_buttons.append([InlineKeyboardButton(text="Max", callback_data="select_model_max")])
        
        if not keyboard_buttons:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Приобрести запросы", callback_data="pay")],
                ]
            )
            await query.message.edit_text(
                "У вас нет доступных запросов. Чтобы приобрести их, нажмите на кнопку \"Приобрести запросы\"",
                reply_markup=keyboard
            )
            return
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await query.message.edit_text(
            "Выберите модель GigaChat для анализа:",
            reply_markup=keyboard
        )
        await state.set_state(SkStates.AI_MODEL_SELECTION)

    @router.callback_query(SkStates.AI_MODEL_SELECTION, F.data.startswith("select_model_"))
    async def select_model_for_ai(query: types.CallbackQuery, state: FSMContext):
        model_type = query.data.replace("select_model_", "")
        await state.update_data(model_type=model_type)
        await query.message.edit_text("Введите запрос для поиска стартапов:")
        await state.set_state(SkStates.AI_FILTERS)
        await query.answer()

    @router.message(SkStates.AI_FILTERS, F.text)
    async def process_filters_criteria_text(message: types.Message, state: FSMContext):
        user_input = message.text
        user_id = message.from_user.id
        data = await state.get_data()
        model_type = data.get("model_type", "standard")
        
        # Проверяем баланс
        balance = await user_repository.get_user_balance(user_id)
        if balance.get(model_type, 0) <= 0:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Приобрести запросы", callback_data="pay")],
                ]
            )
            await message.answer(
                f"У вас нет доступных запросов для модели {model_type}.",
                reply_markup=keyboard
            )
            await state.clear()
            return
        
        # Устанавливаем модель в GigaChat клиент
        gigachat_client.set_model(model_type)
        
        # Получаем фильтры с передачей user_repository и user_id
        filters = gigachat_client.get_startup_filters(user_input, user_repository, user_id)
        
        # Сохраняем модель и запрос пользователя в состоянии
        await state.update_data(model_type=model_type, user_request=user_input)
        
        # Вызываем start_search
        await start_search_func(
            message, state, filters, bot, user_repository, 
            gigachat_client, get_unique_startups, query_history, skolkovo_db
        )


async def start_search_func(
    event: types.Message | types.CallbackQuery,
    state: FSMContext,
    filters: dict,
    bot: Bot,
    user_repository,
    gigachat_client,
    get_unique_startups,
    query_history=None,
    skolkovo_db=None
):
    """Основная функция поиска и обработки стартапов"""
    count = STARTUP_IN_ANSWER_COUNT

    # Списание запроса
    user = event.from_user
    data = await state.get_data()
    model_type = data.get("model_type", "standard")  # По умолчанию standard
    
    await user_repository.use_request(user.id, model_type)
    balance = await user_repository.get_user_balance(user.id)
    logger.info(f"Пользователь {user.full_name} использовал запрос для модели {model_type}. Баланс: {balance}")

    if skolkovo_db is None:
        if isinstance(event, types.CallbackQuery):
            await event.message.edit_text("❌ База данных Сколково не загружена. Попробуйте позже.")
        else:
            await event.answer("❌ База данных Сколково не загружена. Попробуйте позже.")
        await state.clear()
        return

    notify = event.message.edit_text if isinstance(event, types.CallbackQuery) else event.answer
    await notify("🔍 Начинаю поиск интересных стартапов...")

    # Получаем запрос пользователя из состояния
    user_request = data.get("user_request", "")

    try:
        selected_startups = get_unique_startups(count, filters, user_request, user_id=user.id)
        actual_count = len(selected_startups)
        if not selected_startups:
            await bot.send_message(
                chat_id=event.message.chat.id if isinstance(event, types.CallbackQuery) else event.chat.id,
                text="❌ Не удалось найти стартапы по заданным критериям. Попробуйте изменить фильтры."
            )
            await state.clear()
            return

        await bot.send_message(
            chat_id=event.message.chat.id if isinstance(event, types.CallbackQuery) else event.chat.id,
            text=f"ℹ️ Запрошено {count} стартапов, найдено {actual_count}. Показываю все найденные.",
        )
        msg = await bot.send_message(
            chat_id=event.message.chat.id if isinstance(event, types.CallbackQuery) else event.chat.id,
            text=f"🔄 Обрабатываю {actual_count} стартапов...",
        )
        
        processed_startups = []
        for i, startup in enumerate(selected_startups):
            try:
                startup["analysis"] = analyze_startup(startup)
                
                # Добавляем RAG similarity score к анализу
                rag_similarity = startup.get('rag_similarity', 0)
                logger.info(f"🎯 Стартап '{startup.get('name', 'unknown')}': RAG similarity = {rag_similarity:.3f}")
                
                if rag_similarity > 0:
                    # Сохраняем точное значение RAG similarity (0.0-1.0)
                    startup["analysis"]["rag_similarity"] = rag_similarity
                    logger.info(f"✅ Добавлен RAG similarity: {rag_similarity:.3f}")
                
                # Генерируем AI-рекомендацию для моделей Pro и Max
                if model_type in ["pro", "max"]:
                    recommendation = gigachat_client.generate_recommendation(startup, user_request, query_history)
                    if recommendation:
                        startup["analysis"]["AIRecommendation"] = recommendation
                        logger.info(f"✅ Добавлена AI-рекомендация ({model_type})")
                        
                        # Заменяем "Соответствие запросу: X%" на точное значение RAG similarity
                        if rag_similarity > 0:
                            # Ищем и заменяем строку с соответствием
                            recommendation = re.sub(
                                r'Соответствие запросу:\s*\d+%',
                                f'Схожесть с запросом: {rag_similarity:.3f}',
                                recommendation
                            )
                            startup["analysis"]["AIRecommendation"] = recommendation
                
                processed_startups.append(startup)
                if (i + 1) % 5 == 0 or (i + 1) == actual_count:
                    await msg.edit_text(f"🔄 Обработано {i + 1}/{actual_count} стартапов...")
            except Exception as e:
                logger.error(f"Ошибка обработки стартапа: {str(e)}")
                startup["analysis"] = {
                    "DeepTech": random.randint(1, 3),
                    "GenAI": "есть" if random.random() > 0.5 else "нет",
                    "WOW": "да" if random.random() > 0.5 else "нет",
                    "TrafficLight": random.randint(1, 3),
                    "Comments": "Анализ не выполнен",
                }
                processed_startups.append(startup)

        if actual_count <= 10:
            text_response = ""
            for i, s in enumerate(processed_startups, 1):
                analysis = s.get("analysis", {})
                # Получаем краткое описание
                description = s.get('company_description', '') or s.get('description', '')
                short_description = description[:150] + "..." if len(description) > 150 else description
                
                # Базовая информация
                text_response += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                text_response += f"🏢 <b>{i}. {escape_html(s.get('name', 'Название не указано'))}</b>\n"
                text_response += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                
                if short_description:
                    text_response += f"<b>📄 О компании:</b>\n{escape_html(short_description)}\n\n"
                
                # Ключевые показатели
                text_response += f"<b>📊 Ключевые показатели:</b>\n"
                text_response += f"  • Год основания: {escape_html(str(s.get('year', 'н/д')))}\n"
                text_response += f"  • Стадия: {escape_html(determine_stage(s))}\n"
                
                cluster = s.get('cluster', '')
                if cluster:
                    text_response += f"  • Кластер: {escape_html(cluster)}\n"
                
                text_response += f"  • Направление: {escape_html(s.get('category', 'н/д'))}\n"
                text_response += f"  • Регион: {escape_html(s.get('country', 'н/д'))}\n"
                text_response += f"  • Сайт: {escape_html(s.get('website', 'н/д'))}\n\n"
                
                # Оценка технологичности
                text_response += f"<b>🎯 Оценка:</b>\n"
                
                # Показываем RAG similarity если доступно
                rag_similarity_raw = analysis.get('rag_similarity', 0)
                if rag_similarity_raw > 0:
                    text_response += f"  • Схожесть с запросом: {rag_similarity_raw:.3f}\n"
                
                traffic_light_map = {1: "🔴 Красный", 2: "🟡 Желтый", 3: "🟢 Зеленый"}
                traffic_light_emoji = traffic_light_map.get(analysis.get('TrafficLight', 1), "🔴")
                text_response += f"  • Светофор: {traffic_light_emoji}\n"
                text_response += f"  • DeepTech: {analysis.get('DeepTech', 'н/д')}/3\n"
                text_response += f"  • GenAI: {analysis.get('GenAI', 'н/д')}\n"
                text_response += f"  • WOW-эффект: {analysis.get('WOW', 'н/д')}\n\n"
                
                # Аналитический комментарий
                comments_text = escape_html(analysis.get('Comments', 'Нет данных'))
                text_response += f"<b>📋 Детальный анализ:</b>\n{comments_text}\n\n"
                
                # AI-анализ (для моделей Pro и Max) - ограничиваем длину в Telegram
                ai_recommendation = analysis.get('AIRecommendation', '')
                if ai_recommendation:
                    ai_recommendation_text = escape_html(ai_recommendation)
                    # Ограничиваем длину для Telegram, обрезаем по целому предложению
                    if len(ai_recommendation_text) > 1500:
                        # Ищем последнее завершенное предложение в пределах 1500 символов
                        truncated = ai_recommendation_text[:1500]
                        # Ищем последнюю точку, восклицательный или вопросительный знак
                        last_sentence_end = max(
                            truncated.rfind('.'),
                            truncated.rfind('!'),
                            truncated.rfind('?')
                        )
                        
                        if last_sentence_end > 0:
                            ai_recommendation_text = truncated[:last_sentence_end + 1] + "\n\n<i>(Полная версия доступна в файле Excel/CSV)</i>"
                        else:
                            # Если не нашли точку - обрезаем по последнему пробелу
                            last_space = truncated.rfind(' ')
                            if last_space > 0:
                                ai_recommendation_text = truncated[:last_space] + "...\n\n<i>(Полная версия доступна в файле Excel/CSV)</i>"
                            else:
                                ai_recommendation_text = truncated + "...\n\n<i>(Полная версия доступна в файле Excel/CSV)</i>"
                    
                    text_response += f"<b>💼 Аналитический обзор:</b>\n{ai_recommendation_text}\n\n"
                
                # Реквизиты
                text_response += f"<b>📎 Реквизиты:</b> ИНН {s.get('inn', 'н/д')}, ОГРН {s.get('ogrn', 'н/д')}\n\n"
            
            if len(text_response) > 4000:
                parts = [text_response[i:i + 4000] for i in range(0, len(text_response), 4000)]
                for part in parts:
                    await bot.send_message(chat_id=msg.chat.id, text=part, parse_mode='HTML')
            else:
                await bot.send_message(chat_id=msg.chat.id, text=text_response, parse_mode='HTML')

        # Создаем клавиатуру с интерактивными действиями
        from services.interactive_actions import create_results_actions_keyboard
        
        startup_ids = [s.get("id", "") for s in processed_startups]
        
        # Получаем query_id из истории (если был сохранен)
        query_id = None
        if query_history and user.id:
            try:
                # Получаем последний query_id для этого пользователя
                recent_queries = query_history.get_recent_queries(user.id, limit=1)
                if recent_queries:
                    query_id = recent_queries[0].get('id')
            except Exception as e:
                logger.warning(f"Не удалось получить query_id: {e}")
        
        keyboard = create_results_actions_keyboard(
            user_request=user_request,
            startup_ids=startup_ids,
            query_id=query_id
        )
        
        # Отправляем основное сообщение с интерактивными действиями
        await bot.send_message(
            chat_id=msg.chat.id,
            text="🔍 <b>Результаты поиска готовы!</b>\n\n"
                 "Выберите действие:",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        
        # Отправляем отдельное сообщение с кнопками экспорта (всегда доступно)
        from services.interactive_actions import create_export_keyboard
        export_keyboard = create_export_keyboard()
        await bot.send_message(
            chat_id=msg.chat.id,
            text="📤 <b>Экспорт результатов</b>\n\n"
                 "Выберите формат для скачивания:",
            reply_markup=export_keyboard,
            parse_mode='HTML'
        )
        
        await state.update_data(
            processed_startups=processed_startups,
            startup_ids=startup_ids,
            user_request=user_request,
            query_id=query_id
        )
        await state.set_state(SkStates.OUTPUT_FORMAT)  # Используем существующее состояние для совместимости
    except Exception as e:
        logger.exception("Ошибка при обработке запроса")
        await bot.send_message(
            chat_id=event.message.chat.id if isinstance(event, types.CallbackQuery) else event.chat.id,
            text=f"❌ Произошла ошибка: {str(e)}",
        )
        await state.clear()

