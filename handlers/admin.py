"""
Обработчики для админ-панели
"""
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from datetime import datetime
from logger import logger
from states import SkStates


async def _show_admin_panel(
    user_id: int,
    user_repository,
    rag_service,
    continuous_learner,
    RAG_ENABLED,
    RAG_INDEX_FILE,
    SKOLKOVO_DB,
    answer_func,
    edit_func=None
):
    """Внутренняя функция для отображения админ-панели"""
    if not await user_repository.is_admin(user_id):
        if edit_func:
            await edit_func("❌ У вас нет доступа к админ-панели")
        else:
            await answer_func("❌ У вас нет доступа к админ-панели")
        return
    
    from config import GIGACHAT_TOKEN_PRICES
    
    # Получаем статистику
    all_users = await user_repository.get_all_users()
    total_users = len(all_users)
    banned_count = sum(1 for u in all_users if u[4] == 1)
    
    token_stats = await user_repository.get_token_statistics()
    total_tokens = 0
    tokens_by_model = {}
    total_cost = 0
    
    if isinstance(token_stats, list):
        for model_type, tokens in token_stats:
            tokens_by_model[model_type] = tokens or 0
            total_tokens += tokens or 0
            
            # Рассчитываем стоимость
            prices = GIGACHAT_TOKEN_PRICES.get(model_type, {"input": 0, "output": 0})
            input_tokens = int(tokens * 0.3)
            output_tokens = int(tokens * 0.7)
            input_cost = (input_tokens / 1_000_000) * prices["input"]
            output_cost = (output_tokens / 1_000_000) * prices["output"]
            total_cost += input_cost + output_cost
    
    admin_text = (
        "👑 Админ-панель\n\n"
        f"📊 Статистика:\n"
        f"• Всего пользователей: {total_users}\n"
        f"• Заблокированных: {banned_count}\n"
        f"• Всего использовано токенов: {total_tokens:,}\n"
    )
    
    if total_cost > 0:
        admin_text += f"• Стоимость токенов: {total_cost:.2f} ₽\n\n"
    else:
        admin_text += f"• Стоимость токенов: Бесплатно\n\n"
    
    if tokens_by_model:
        admin_text += "💰 Токены по моделям:\n"
        for model_type, tokens in tokens_by_model.items():
            model_name = {
                "standard": "Standard",
                "pro": "Pro",
                "max": "Max"
            }.get(model_type, model_type)
            admin_text += f"• {model_name}: {tokens:,}\n"
    
    # ============================================================================
    # РАСШИРЕННАЯ СТАТИСТИКА: RAG, Re-ranking, Few-shot, Самообучение
    # ============================================================================
    
    # RAG статистика
    if RAG_ENABLED and rag_service:
        admin_text += f"\n🔍 RAG-система:\n"
        admin_text += f"• Проиндексировано: {len(rag_service.startup_vectors)} стартапов\n"
        admin_text += f"• Метод: GigaChat Embeddings\n"
    
    # Query History статистика
    try:
        import sqlite3
        import os
        if os.path.exists("query_history.db"):
            conn = sqlite3.connect("query_history.db")
            cursor = conn.cursor()
            
            # Общая статистика
            cursor.execute("SELECT COUNT(*) FROM queries")
            total_queries = cursor.fetchone()[0]
            
            cursor.execute("SELECT AVG(ai_relevance) FROM query_results WHERE ai_relevance > 0")
            avg_relevance = cursor.fetchone()[0] or 0
            
            cursor.execute("SELECT COUNT(*) FROM query_results WHERE ai_relevance >= 80")
            good_results = cursor.fetchone()[0]
            
            # Паттерны самообучения
            cursor.execute("SELECT COUNT(*) FROM query_patterns")
            patterns_count = cursor.fetchone()[0]
            
            conn.close()
            
            admin_text += f"\n📊 Система поиска:\n"
            admin_text += f"• Всего запросов: {total_queries}\n"
            admin_text += f"• Средняя AI relevance: {avg_relevance:.1f}/100\n"
            admin_text += f"• Хороших результатов (≥80): {good_results}\n"
            
            # Оценка качества
            if avg_relevance >= 80:
                quality_emoji = "🟢"
                quality_text = "Отлично"
            elif avg_relevance >= 60:
                quality_emoji = "🟡"
                quality_text = "Хорошо"
            else:
                quality_emoji = "🔴"
                quality_text = "Требует улучшения"
            
            admin_text += f"• Качество: {quality_emoji} {quality_text}\n"
            
            # Самообучение
            if patterns_count > 0:
                admin_text += f"\n🧠 Самообучение:\n"
                admin_text += f"• Выявлено паттернов: {patterns_count}\n"
                
                # Проверяем файл с выученными примерами
                if os.path.exists("ai_learning/learned_examples.py"):
                    admin_text += f"• Few-shot примеры: ✅ Созданы\n"
                else:
                    admin_text += f"• Few-shot примеры: ⏳ Ожидание данных\n"
                
                # Статус continuous learning
                if continuous_learner and continuous_learner.is_running:
                    admin_text += f"• Авто-обучение: ✅ Активно\n"
                    admin_text += f"• Запросов до обучения: {continuous_learner.queries_since_training}/{continuous_learner.queries_threshold}\n"
                else:
                    admin_text += f"• Авто-обучение: ❌ Неактивно\n"
            else:
                admin_text += f"\n🧠 Самообучение:\n"
                admin_text += f"• Статус: ⏳ Накопление данных\n"
                admin_text += f"• Нужно минимум: 20 запросов\n"
            
            # Fine-tuning статус
            cursor = sqlite3.connect("query_history.db").cursor()
            cursor.execute("SELECT COUNT(*) FROM query_results WHERE ai_relevance >= 70")
            finetuning_ready = cursor.fetchone()[0]
            
            from config import FINE_TUNING
            min_for_finetuning = FINE_TUNING.get('min_examples', 100)
            
            if finetuning_ready >= min_for_finetuning:
                admin_text += f"\n🚀 Fine-tuning:\n"
                admin_text += f"• Доступен! ({finetuning_ready} примеров)\n"
                admin_text += f"• Запустите: python ai_learning/train_model.py\n"
            else:
                admin_text += f"\n🚀 Fine-tuning:\n"
                admin_text += f"• Прогресс: {finetuning_ready}/{min_for_finetuning} примеров\n"
                
    except Exception as e:
        logger.error(f"Ошибка загрузки статистики: {e}")
        admin_text += f"\n⚠️ Статистика недоступна\n"
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Просмотр пользователей", callback_data="admin_users")],
            [InlineKeyboardButton(text="📊 Детальная статистика токенов", callback_data="admin_tokens")],
        ]
    )
    
    # Кнопки для RAG
    if RAG_ENABLED and rag_service:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text="🔄 Переиндексировать RAG", callback_data="admin_reindex_rag")
        ])
    
    # Кнопки для самообучения
    try:
        import os
        if os.path.exists("query_history.db"):
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="🧠 Статистика самообучения", callback_data="admin_ai_learning")
            ])
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="🎓 Запустить обучение", callback_data="admin_train_now")
            ])
    except:
        pass
    
    # Кнопка дообучения ML на внешних стартапах
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="🔬 ML: дообучить на внешних", callback_data="admin_ml_retrain")
    ])
    
    # Кнопка "Назад"
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data="start_over")
    ])
    
    if edit_func:
        await edit_func(admin_text, reply_markup=keyboard)
    else:
        await answer_func(admin_text, reply_markup=keyboard)


def register_admin_handlers(
    router: Router,
    user_repository,
    rag_service,
    continuous_learner,
    RAG_ENABLED,
    RAG_INDEX_FILE,
    SKOLKOVO_DB
):
    """Регистрирует обработчики для админ-панели"""
    
    @router.message(Command("admin"))
    async def admin_command(message: types.Message):
        """Обработчик команды /admin"""
        user_id = message.from_user.id
        if not await user_repository.is_admin(user_id):
            await message.answer("❌ У вас нет доступа к админ-панели")
            return
        
        # Используем ту же логику, что и в admin_panel
        await _show_admin_panel(
            user_id=user_id,
            user_repository=user_repository,
            rag_service=rag_service,
            continuous_learner=continuous_learner,
            RAG_ENABLED=RAG_ENABLED,
            RAG_INDEX_FILE=RAG_INDEX_FILE,
            SKOLKOVO_DB=SKOLKOVO_DB,
            answer_func=lambda text, reply_markup=None: message.answer(text, reply_markup=reply_markup),
            edit_func=None
        )
    
    @router.callback_query(F.data == "admin_panel")
    async def admin_panel(query: types.CallbackQuery):
        user_id = query.from_user.id
        if not await user_repository.is_admin(user_id):
            await query.answer("❌ У вас нет доступа к админ-панели", show_alert=True)
            return
        
        await query.answer()
        
        # Используем общую функцию
        await _show_admin_panel(
            user_id=user_id,
            user_repository=user_repository,
            rag_service=rag_service,
            continuous_learner=continuous_learner,
            RAG_ENABLED=RAG_ENABLED,
            RAG_INDEX_FILE=RAG_INDEX_FILE,
            SKOLKOVO_DB=SKOLKOVO_DB,
            answer_func=None,
            edit_func=lambda text, reply_markup=None: query.message.edit_text(text, reply_markup=reply_markup)
        )
        return
        
        # Старый код ниже (больше не используется, но оставлен для справки)
        
        from config import GIGACHAT_TOKEN_PRICES
        
        # Получаем статистику
        all_users = await user_repository.get_all_users()
        total_users = len(all_users)
        banned_count = sum(1 for u in all_users if u[4] == 1)
        
        token_stats = await user_repository.get_token_statistics()
        total_tokens = 0
        tokens_by_model = {}
        total_cost = 0
        
        if isinstance(token_stats, list):
            for model_type, tokens in token_stats:
                tokens_by_model[model_type] = tokens or 0
                total_tokens += tokens or 0
                
                # Рассчитываем стоимость
                prices = GIGACHAT_TOKEN_PRICES.get(model_type, {"input": 0, "output": 0})
                input_tokens = int(tokens * 0.3)
                output_tokens = int(tokens * 0.7)
                input_cost = (input_tokens / 1_000_000) * prices["input"]
                output_cost = (output_tokens / 1_000_000) * prices["output"]
                total_cost += input_cost + output_cost
        
        admin_text = (
            "👑 Админ-панель\n\n"
            f"📊 Статистика:\n"
            f"• Всего пользователей: {total_users}\n"
            f"• Заблокированных: {banned_count}\n"
            f"• Всего использовано токенов: {total_tokens:,}\n"
        )
        
        if total_cost > 0:
            admin_text += f"• Стоимость токенов: {total_cost:.2f} ₽\n\n"
        else:
            admin_text += f"• Стоимость токенов: Бесплатно\n\n"
        
        if tokens_by_model:
            admin_text += "💰 Токены по моделям:\n"
            for model_type, tokens in tokens_by_model.items():
                model_name = {
                    "standard": "Standard",
                    "pro": "Pro",
                    "max": "Max"
                }.get(model_type, model_type)
                admin_text += f"• {model_name}: {tokens:,}\n"
        
        # ============================================================================
        # РАСШИРЕННАЯ СТАТИСТИКА: RAG, Re-ranking, Few-shot, Самообучение
        # ============================================================================
        
        # RAG статистика
        if RAG_ENABLED and rag_service:
            admin_text += f"\n🔍 RAG-система:\n"
            admin_text += f"• Проиндексировано: {len(rag_service.startup_vectors)} стартапов\n"
            admin_text += f"• Метод: GigaChat Embeddings\n"
        
        # Query History статистика
        try:
            import sqlite3
            import os
            if os.path.exists("query_history.db"):
                conn = sqlite3.connect("query_history.db")
                cursor = conn.cursor()
                
                # Общая статистика
                cursor.execute("SELECT COUNT(*) FROM queries")
                total_queries = cursor.fetchone()[0]
                
                cursor.execute("SELECT AVG(ai_relevance) FROM query_results WHERE ai_relevance > 0")
                avg_relevance = cursor.fetchone()[0] or 0
                
                cursor.execute("SELECT COUNT(*) FROM query_results WHERE ai_relevance >= 80")
                good_results = cursor.fetchone()[0]
                
                # Паттерны самообучения
                cursor.execute("SELECT COUNT(*) FROM query_patterns")
                patterns_count = cursor.fetchone()[0]
                
                conn.close()
                
                admin_text += f"\n📊 Система поиска:\n"
                admin_text += f"• Всего запросов: {total_queries}\n"
                admin_text += f"• Средняя AI relevance: {avg_relevance:.1f}/100\n"
                admin_text += f"• Хороших результатов (≥80): {good_results}\n"
                
                # Оценка качества
                if avg_relevance >= 80:
                    quality_emoji = "🟢"
                    quality_text = "Отлично"
                elif avg_relevance >= 60:
                    quality_emoji = "🟡"
                    quality_text = "Хорошо"
                else:
                    quality_emoji = "🔴"
                    quality_text = "Требует улучшения"
                
                admin_text += f"• Качество: {quality_emoji} {quality_text}\n"
                
                # Самообучение
                if patterns_count > 0:
                    admin_text += f"\n🧠 Самообучение:\n"
                    admin_text += f"• Выявлено паттернов: {patterns_count}\n"
                    
                    # Проверяем файл с выученными примерами
                    if os.path.exists("ai_learning/learned_examples.py"):
                        admin_text += f"• Few-shot примеры: ✅ Созданы\n"
                    else:
                        admin_text += f"• Few-shot примеры: ⏳ Ожидание данных\n"
                    
                    # Статус continuous learning
                    if continuous_learner and continuous_learner.is_running:
                        admin_text += f"• Авто-обучение: ✅ Активно\n"
                        admin_text += f"• Запросов до обучения: {continuous_learner.queries_since_training}/{continuous_learner.queries_threshold}\n"
                    else:
                        admin_text += f"• Авто-обучение: ❌ Неактивно\n"
                else:
                    admin_text += f"\n🧠 Самообучение:\n"
                    admin_text += f"• Статус: ⏳ Накопление данных\n"
                    admin_text += f"• Нужно минимум: 20 запросов\n"
                
                # Fine-tuning статус
                cursor = sqlite3.connect("query_history.db").cursor()
                cursor.execute("SELECT COUNT(*) FROM query_results WHERE ai_relevance >= 70")
                finetuning_ready = cursor.fetchone()[0]
                
                from config import FINE_TUNING
                min_for_finetuning = FINE_TUNING.get('min_examples', 100)
                
                if finetuning_ready >= min_for_finetuning:
                    admin_text += f"\n🚀 Fine-tuning:\n"
                    admin_text += f"• Доступен! ({finetuning_ready} примеров)\n"
                    admin_text += f"• Запустите: python ai_learning/train_model.py\n"
                else:
                    admin_text += f"\n🚀 Fine-tuning:\n"
                    admin_text += f"• Прогресс: {finetuning_ready}/{min_for_finetuning} примеров\n"
                    
        except Exception as e:
            logger.error(f"Ошибка загрузки статистики: {e}")
            admin_text += f"\n⚠️ Статистика недоступна\n"
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="👥 Просмотр пользователей", callback_data="admin_users")],
                [InlineKeyboardButton(text="📊 Детальная статистика токенов", callback_data="admin_tokens")],
            ]
        )
        
        # Кнопки для RAG
        if RAG_ENABLED and rag_service:
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="🔄 Переиндексировать RAG", callback_data="admin_reindex_rag")
            ])
        
        # Кнопки для самообучения
        try:
            import os
            if os.path.exists("query_history.db"):
                keyboard.inline_keyboard.append([
                    InlineKeyboardButton(text="🧠 Статистика самообучения", callback_data="admin_ai_learning")
                ])
                keyboard.inline_keyboard.append([
                    InlineKeyboardButton(text="🎓 Запустить обучение", callback_data="admin_train_now")
                ])
        except:
            pass
        
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text="◀️ Назад", callback_data="start_over")
        ])
        
        await query.message.edit_text(admin_text, reply_markup=keyboard)

    @router.callback_query(F.data == "admin_reindex_rag")
    async def admin_reindex_rag(query: types.CallbackQuery):
        user_id = query.from_user.id
        if not await user_repository.is_admin(user_id):
            await query.answer("❌ У вас нет доступа", show_alert=True)
            return
        
        await query.answer()
        
        if not RAG_ENABLED or not rag_service or not SKOLKOVO_DB:
            await query.message.edit_text("❌ RAG-система недоступна")
            return
        
        await query.message.edit_text("🔄 Начинаю переиндексацию... Это займет 5-10 минут.")
        
        try:
            indexed_count = rag_service.index_startups(SKOLKOVO_DB)
            rag_service.save_index(RAG_INDEX_FILE)
            
            await query.message.edit_text(
                f"✅ Переиндексация завершена!\n\n"
                f"Проиндексировано: {indexed_count} стартапов\n"
                f"Индекс сохранен в {RAG_INDEX_FILE}"
            )
        except Exception as e:
            logger.error(f"Ошибка переиндексации: {e}")
            await query.message.edit_text(f"❌ Ошибка переиндексации: {str(e)}")

    @router.callback_query(F.data == "admin_ai_learning")
    async def admin_ai_learning(query: types.CallbackQuery):
        """Детальная статистика самообучения"""
        user_id = query.from_user.id
        if not await user_repository.is_admin(user_id):
            await query.answer("❌ У вас нет доступа", show_alert=True)
            return
        
        await query.answer()
        
        try:
            import sqlite3
            import os
            
            if not os.path.exists("query_history.db"):
                await query.message.edit_text("❌ База данных не найдена")
                return
            
            conn = sqlite3.connect("query_history.db")
            cursor = conn.cursor()
            
            text = "🧠 СТАТИСТИКА САМООБУЧЕНИЯ\n\n"
            
            # Паттерны
            cursor.execute("SELECT COUNT(*) FROM query_patterns")
            patterns_count = cursor.fetchone()[0]
            
            text += f"📊 Паттерны:\n"
            text += f"• Всего выявлено: {patterns_count}\n\n"
            
            if patterns_count > 0:
                # Топ-5 паттернов
                cursor.execute("""
                    SELECT query_type, keywords, relevant_clusters, success_rate, usage_count
                    FROM query_patterns
                    ORDER BY usage_count DESC, success_rate DESC
                    LIMIT 5
                """)
                
                text += "🔥 Топ-5 паттернов:\n"
                for i, (qtype, keywords, clusters, success, usage) in enumerate(cursor.fetchall(), 1):
                    text += f"{i}. {qtype}\n"
                    text += f"   Слова: {keywords[:50]}...\n"
                    text += f"   Кластер: {clusters}\n"
                    text += f"   Успех: {success*100:.0f}% ({usage} использований)\n\n"
            
            # Статистика запросов
            cursor.execute("SELECT COUNT(*) FROM queries")
            total_queries = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT AVG(ai_relevance), MIN(ai_relevance), MAX(ai_relevance)
                FROM query_results WHERE ai_relevance > 0
            """)
            avg, min_rel, max_rel = cursor.fetchone()
            
            text += f"📈 Качество поиска:\n"
            text += f"• Всего запросов: {total_queries}\n"
            text += f"• Средняя AI relevance: {avg:.1f}/100\n"
            text += f"• Диапазон: {min_rel:.0f} - {max_rel:.0f}\n\n"
            
            # Топ кластеры
            cursor.execute("""
                SELECT cluster, COUNT(*) as cnt, AVG(ai_relevance) as avg_rel
                FROM query_results
                WHERE cluster != '' AND ai_relevance > 0
                GROUP BY cluster
                ORDER BY cnt DESC
                LIMIT 5
            """)
            
            text += "🎯 Топ-5 кластеров:\n"
            for i, (cluster, cnt, avg_rel) in enumerate(cursor.fetchall(), 1):
                text += f"{i}. {cluster}: {cnt} результатов (AI={avg_rel:.0f})\n"
            
            text += "\n"
            
            # Статус continuous learning
            if continuous_learner:
                text += "⚙️ Авто-обучение:\n"
                text += f"• Статус: {'✅ Активно' if continuous_learner.is_running else '❌ Неактивно'}\n"
                text += f"• Запросов до обучения: {continuous_learner.queries_since_training}/{continuous_learner.queries_threshold}\n"
                text += f"• Последнее обучение: {continuous_learner.last_training_time.strftime('%d.%m.%Y %H:%M')}\n"
            
            conn.close()
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎓 Запустить обучение", callback_data="admin_train_now")],
                [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin_panel")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Ошибка статистики самообучения: {e}")
            await query.message.edit_text(f"❌ Ошибка: {str(e)}")

    @router.callback_query(F.data == "admin_train_now")
    async def admin_train_now(query: types.CallbackQuery):
        """Запуск обучения вручную"""
        user_id = query.from_user.id
        if not await user_repository.is_admin(user_id):
            await query.answer("❌ У вас нет доступа", show_alert=True)
            return
        
        await query.answer()
        
        try:
            import os
            if not os.path.exists("query_history.db"):
                await query.message.edit_text("❌ База данных не найдена")
                return
            
            await query.message.edit_text("🧠 Запускаю самообучение...\n\nЭто может занять 10-30 секунд.")
            
            # Запускаем обучение
            from ai_learning import SelfLearningEngine
            engine = SelfLearningEngine()
            report = engine.analyze_and_learn()
            
            # Формируем отчет
            text = "✅ ОБУЧЕНИЕ ЗАВЕРШЕНО\n\n"
            text += f"📊 Результаты:\n"
            text += f"• Выявлено паттернов: {report['patterns_discovered']}\n"
            text += f"• Обновлено паттернов: {report['patterns_updated']}\n"
            text += f"• Сгенерировано синонимов: {report['synonyms_generated']}\n"
            text += f"• Создано few-shot примеров: {report['few_shot_created']}\n\n"
            
            if report.get("recommendations"):
                text += "💡 Рекомендации:\n"
                for rec in report["recommendations"][:3]:
                    text += f"• {rec[:80]}...\n"
            
            # Экспорт для fine-tuning
            exported = engine.export_for_finetuning()
            if exported > 0:
                text += f"\n🚀 Fine-tuning:\n"
                text += f"✅ Экспортировано {exported} примеров\n"
                text += f"Файл: finetuning_dataset.jsonl\n"
            
            # Сбрасываем счетчик continuous learner
            if continuous_learner:
                continuous_learner.queries_since_training = 0
                continuous_learner.last_training_time = datetime.now()
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🧠 Статистика", callback_data="admin_ai_learning")],
                [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin_panel")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Ошибка обучения: {e}")
            await query.message.edit_text(f"❌ Ошибка: {str(e)}\n\nПопробуйте позже или проверьте логи.")

    @router.callback_query(F.data == "admin_users")
    async def admin_users(query: types.CallbackQuery):
        user_id = query.from_user.id
        if not await user_repository.is_admin(user_id):
            await query.answer("❌ У вас нет доступа", show_alert=True)
            return
        
        await query.answer()
        
        all_users = await user_repository.get_all_users()
        
        if not all_users:
            await query.message.edit_text("❌ Пользователи не найдены")
            return
        
        text = "👥 Список пользователей:\n\n"
        keyboard_buttons = []
        
        # Показываем первые 10 пользователей
        for i, user_data in enumerate(all_users[:10], 1):
            tg_user_id, req_std, req_pro, req_max, is_banned, is_admin, created_at = user_data
            status = "🔴 Забанен" if is_banned else "✅ Активен"
            admin_badge = " 👑" if is_admin else ""
            text += f"{i}. ID: {tg_user_id}{admin_badge} - {status}\n"
            text += f"   Запросы: Standard={req_std or 0}, Pro={req_pro or 0}, Max={req_max or 0}\n\n"
            
            keyboard_buttons.append([InlineKeyboardButton(
                text=f"👤 Пользователь {tg_user_id}",
                callback_data=f"admin_user_{tg_user_id}"
            )])
        
        keyboard_buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await query.message.edit_text(text, reply_markup=keyboard)

    @router.callback_query(F.data.startswith("admin_user_"))
    async def admin_user_detail(query: types.CallbackQuery):
        user_id = query.from_user.id
        if not await user_repository.is_admin(user_id):
            await query.answer("❌ У вас нет доступа", show_alert=True)
            return
        
        await query.answer()
        
        target_user_id = int(query.data.split("_")[2])
        user_info = await user_repository.get_user_info(target_user_id)
        
        if not user_info:
            await query.message.edit_text("❌ Пользователь не найден")
            return
        
        tg_user_id, req_std, req_pro, req_max, is_banned, is_admin, created_at = user_info
        
        # Получаем статистику токенов пользователя
        from config import GIGACHAT_TOKEN_PRICES
        user_token_stats = await user_repository.get_user_token_statistics(target_user_id)
        
        # Подсчитываем токены и стоимость
        tokens_by_model = {}
        total_tokens = 0
        total_cost = 0
        
        for model_type, tokens in user_token_stats:
            tokens_by_model[model_type] = tokens or 0
            total_tokens += tokens or 0
            
            # Рассчитываем стоимость
            prices = GIGACHAT_TOKEN_PRICES.get(model_type, {"input": 0, "output": 0})
            # Примерное соотношение input/output токенов 30%/70%
            input_tokens = int(tokens * 0.3)
            output_tokens = int(tokens * 0.7)
            cost = (input_tokens * prices["input"] + output_tokens * prices["output"]) / 1_000_000
            total_cost += cost
        
        text = (
            f"👤 Информация о пользователе\n\n"
            f"ID: {tg_user_id}\n"
            f"Статус: {'🔴 Забанен' if is_banned else '✅ Активен'}\n"
            f"Админ: {'Да' if is_admin else 'Нет'}\n"
            f"Дата регистрации: {created_at or 'Неизвестно'}\n\n"
            f"📊 Баланс запросов:\n"
            f"• Standard: {req_std or 0}\n"
            f"• Pro: {req_pro or 0}\n"
            f"• Max: {req_max or 0}\n\n"
        )
        
        # Добавляем статистику токенов
        if tokens_by_model:
            text += f"💰 Использование токенов:\n"
            text += f"━━━━━━━━━━━━━━━━━━━━\n"
            text += f"Всего: {total_tokens:,} токенов\n"
            text += f"Общая стоимость: ~{total_cost:.2f} ₽\n\n"
            
            for model_type in ["standard", "pro", "max"]:
                if model_type in tokens_by_model:
                    tokens = tokens_by_model[model_type]
                    prices = GIGACHAT_TOKEN_PRICES.get(model_type, {"input": 0, "output": 0})
                    input_tokens = int(tokens * 0.3)
                    output_tokens = int(tokens * 0.7)
                    cost = (input_tokens * prices["input"] + output_tokens * prices["output"]) / 1_000_000
                    
                    model_name = {"standard": "Standard", "pro": "Pro", "max": "Max"}.get(model_type, model_type)
                    text += f"• {model_name}: {tokens:,} токенов (~{cost:.2f} ₽)\n"
        else:
            text += f"💰 Токены не использовались\n"
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="➕ Дать запросы", callback_data=f"admin_give_{target_user_id}")],
                [
                    InlineKeyboardButton(
                        text="🔴 Забанить" if not is_banned else "✅ Разбанить",
                        callback_data=f"admin_ban_{target_user_id}" if not is_banned else f"admin_unban_{target_user_id}"
                    )
                ],
                [InlineKeyboardButton(text="◀️ Назад к списку", callback_data="admin_users")],
            ]
        )
        
        await query.message.edit_text(text, reply_markup=keyboard)

    @router.callback_query(F.data.startswith("admin_give_"))
    async def admin_give_requests(query: types.CallbackQuery, state: FSMContext):
        user_id = query.from_user.id
        if not await user_repository.is_admin(user_id):
            await query.answer("❌ У вас нет доступа", show_alert=True)
            return
        
        await query.answer()
        target_user_id = int(query.data.split("_")[2])
        
        await state.update_data(admin_target_user=target_user_id)
        await state.set_state(SkStates.ADMIN_GIVE_REQUESTS)
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Standard", callback_data="admin_model_standard")],
                [InlineKeyboardButton(text="Pro", callback_data="admin_model_pro")],
                [InlineKeyboardButton(text="Max", callback_data="admin_model_max")],
                [InlineKeyboardButton(text="◀️ Отмена", callback_data=f"admin_user_{target_user_id}")],
            ]
        )
        
        await query.message.edit_text(
            "Выберите модель для выдачи запросов:",
            reply_markup=keyboard
        )

    @router.callback_query(F.data.startswith("admin_model_"))
    async def admin_select_model_for_give(query: types.CallbackQuery, state: FSMContext):
        user_id = query.from_user.id
        if not await user_repository.is_admin(user_id):
            await query.answer("❌ У вас нет доступа", show_alert=True)
            return
        
        await query.answer()
        model_type = query.data.split("_")[2]
        
        await state.update_data(admin_model_type=model_type)
        await state.set_state(SkStates.ADMIN_GIVE_AMOUNT)
        
        await query.message.edit_text(
            f"Введите количество запросов для модели {model_type}:\n"
            "(Отправьте число)"
        )

    @router.message(SkStates.ADMIN_GIVE_AMOUNT)
    async def admin_give_amount(message: types.Message, state: FSMContext):
        user_id = message.from_user.id
        if not await user_repository.is_admin(user_id):
            await message.answer("❌ У вас нет доступа")
            await state.clear()
            return
        
        try:
            amount = int(message.text.strip())
            if amount <= 0:
                await message.answer("❌ Количество должно быть положительным числом")
                return
            
            data = await state.get_data()
            target_user_id = data.get("admin_target_user")
            model_type = data.get("admin_model_type")
            
            await user_repository.give_requests(target_user_id, model_type, amount)
            
            await message.answer(
                f"✅ Пользователю {target_user_id} выдано {amount} запросов для модели {model_type}"
            )
            
            await state.clear()
            
            # Возвращаемся к информации о пользователе
            user_info = await user_repository.get_user_info(target_user_id)
            if user_info:
                tg_user_id, req_std, req_pro, req_max, is_banned, is_admin, created_at = user_info
                
                text = (
                    f"👤 Информация о пользователе\n\n"
                    f"ID: {tg_user_id}\n"
                    f"Статус: {'🔴 Забанен' if is_banned else '✅ Активен'}\n"
                    f"Админ: {'Да' if is_admin else 'Нет'}\n"
                    f"Дата регистрации: {created_at or 'Неизвестно'}\n\n"
                    f"📊 Баланс запросов:\n"
                    f"• Standard: {req_std or 0}\n"
                    f"• Pro: {req_pro or 0}\n"
                    f"• Max: {req_max or 0}\n"
                )
                
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="➕ Дать запросы", callback_data=f"admin_give_{target_user_id}")],
                        [
                            InlineKeyboardButton(
                                text="🔴 Забанить" if not is_banned else "✅ Разбанить",
                                callback_data=f"admin_ban_{target_user_id}" if not is_banned else f"admin_unban_{target_user_id}"
                            )
                        ],
                        [InlineKeyboardButton(text="◀️ Назад к списку", callback_data="admin_users")],
                    ]
                )
                
                await message.answer(text, reply_markup=keyboard)
        except ValueError:
            await message.answer("❌ Введите корректное число")

    @router.callback_query(F.data.startswith("admin_ban_"))
    async def admin_ban_user(query: types.CallbackQuery):
        user_id = query.from_user.id
        if not await user_repository.is_admin(user_id):
            await query.answer("❌ У вас нет доступа", show_alert=True)
            return
        
        target_user_id = int(query.data.split("_")[2])
        
        await user_repository.ban_user(target_user_id)
        await query.answer("✅ Пользователь забанен", show_alert=True)
        
        # Обновляем информацию о пользователе
        user_info = await user_repository.get_user_info(target_user_id)
        
        if not user_info:
            await query.message.edit_text("❌ Пользователь не найден")
            return
        
        tg_user_id, req_std, req_pro, req_max, is_banned, is_admin, created_at = user_info
        
        text = (
            f"👤 Информация о пользователе\n\n"
            f"ID: {tg_user_id}\n"
            f"Статус: {'🔴 Забанен' if is_banned else '✅ Активен'}\n"
            f"Админ: {'Да' if is_admin else 'Нет'}\n"
            f"Дата регистрации: {created_at or 'Неизвестно'}\n\n"
            f"📊 Баланс запросов:\n"
            f"• Standard: {req_std or 0}\n"
            f"• Pro: {req_pro or 0}\n"
            f"• Max: {req_max or 0}\n"
        )
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="➕ Дать запросы", callback_data=f"admin_give_{target_user_id}")],
                [
                    InlineKeyboardButton(
                        text="🔴 Забанить" if not is_banned else "✅ Разбанить",
                        callback_data=f"admin_ban_{target_user_id}" if not is_banned else f"admin_unban_{target_user_id}"
                    )
                ],
                [InlineKeyboardButton(text="◀️ Назад к списку", callback_data="admin_users")],
            ]
        )
        
        await query.message.edit_text(text, reply_markup=keyboard)

    @router.callback_query(F.data.startswith("admin_unban_"))
    async def admin_unban_user(query: types.CallbackQuery):
        user_id = query.from_user.id
        if not await user_repository.is_admin(user_id):
            await query.answer("❌ У вас нет доступа", show_alert=True)
            return
        
        target_user_id = int(query.data.split("_")[2])
        
        await user_repository.unban_user(target_user_id)
        await query.answer("✅ Пользователь разбанен", show_alert=True)
        
        # Обновляем информацию о пользователе
        user_info = await user_repository.get_user_info(target_user_id)
        
        if not user_info:
            await query.message.edit_text("❌ Пользователь не найден")
            return
        
        tg_user_id, req_std, req_pro, req_max, is_banned, is_admin, created_at = user_info
        
        text = (
            f"👤 Информация о пользователе\n\n"
            f"ID: {tg_user_id}\n"
            f"Статус: {'🔴 Забанен' if is_banned else '✅ Активен'}\n"
            f"Админ: {'Да' if is_admin else 'Нет'}\n"
            f"Дата регистрации: {created_at or 'Неизвестно'}\n\n"
            f"📊 Баланс запросов:\n"
            f"• Standard: {req_std or 0}\n"
            f"• Pro: {req_pro or 0}\n"
            f"• Max: {req_max or 0}\n"
        )
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="➕ Дать запросы", callback_data=f"admin_give_{target_user_id}")],
                [
                    InlineKeyboardButton(
                        text="🔴 Забанить" if not is_banned else "✅ Разбанить",
                        callback_data=f"admin_ban_{target_user_id}" if not is_banned else f"admin_unban_{target_user_id}"
                    )
                ],
                [InlineKeyboardButton(text="◀️ Назад к списку", callback_data="admin_users")],
            ]
        )
        
        await query.message.edit_text(text, reply_markup=keyboard)

    @router.callback_query(F.data == "admin_tokens")
    async def admin_tokens(query: types.CallbackQuery):
        user_id = query.from_user.id
        if not await user_repository.is_admin(user_id):
            await query.answer("❌ У вас нет доступа", show_alert=True)
            return
        
        await query.answer()
        
        from config import GIGACHAT_TOKEN_PRICES
        
        # Общая статистика
        token_stats = await user_repository.get_token_statistics()
        total_tokens = 0
        tokens_by_model = {}
        
        if isinstance(token_stats, list):
            for model_type, tokens in token_stats:
                tokens_by_model[model_type] = tokens or 0
                total_tokens += tokens or 0
        
        text = "📊 Общая статистика использования токенов\n\n"
        text += f"Всего использовано: {total_tokens:,} токенов\n\n"
        
        if tokens_by_model:
            text += "💰 Статистика по моделям:\n\n"
            
            total_cost = 0
            for model_type, tokens in tokens_by_model.items():
                # Получаем стоимость для модели
                prices = GIGACHAT_TOKEN_PRICES.get(model_type, {"input": 0, "output": 0})
                
                # Предполагаем, что 30% токенов - входные, 70% - выходные (типичное соотношение)
                input_tokens = int(tokens * 0.3)
                output_tokens = int(tokens * 0.7)
                
                # Рассчитываем стоимость (цена за 1М токенов)
                input_cost = (input_tokens / 1_000_000) * prices["input"]
                output_cost = (output_tokens / 1_000_000) * prices["output"]
                model_cost = input_cost + output_cost
                total_cost += model_cost
                
                model_name = {
                    "standard": "Standard (GigaChat)",
                    "pro": "Pro (GigaChat-Pro)",
                    "max": "Max (GigaChat-Max)"
                }.get(model_type, model_type)
                
                text += f"🔹 {model_name}\n"
                text += f"   Токенов: {tokens:,}\n"
                
                if prices["input"] > 0 or prices["output"] > 0:
                    text += f"   • Входных (~30%): {input_tokens:,} токенов\n"
                    text += f"   • Выходных (~70%): {output_tokens:,} токенов\n"
                    text += f"   💵 Стоимость: {model_cost:.2f} ₽\n"
                    text += f"   📋 Тариф: {prices['input']}₽/1М вход, {prices['output']}₽/1М выход\n"
                else:
                    text += f"   💵 Стоимость: Бесплатно\n"
                text += "\n"
            
            text += f"━━━━━━━━━━━━━━━━━━━━\n"
            text += f"💰 Общая стоимость: {total_cost:.2f} ₽\n"
            
            if total_cost == 0:
                text += "\n✨ Все запросы выполнены бесплатно!"
        else:
            text += "Данные отсутствуют"
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="👥 Статистика по пользователям", callback_data="admin_tokens_users")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel")],
            ]
        )
        
        await query.message.edit_text(text, reply_markup=keyboard)

    @router.callback_query(F.data == "admin_ml_retrain")
    async def admin_ml_retrain(query: types.CallbackQuery):
        """Дообучение ML моделей на внешних стартапах (Semi-Supervised)."""
        user_id = query.from_user.id
        if not await user_repository.is_admin(user_id):
            await query.answer("У вас нет доступа", show_alert=True)
            return

        await query.answer()
        await query.message.edit_text(
            "🔬 Запускаю дообучение ML...\n\n"
            "Шаги:\n"
            "1. Загрузка Сколково (ground truth)\n"
            "2. Загрузка внешних стартапов из БД\n"
            "3. Генерация псевдо-меток (bootstrap)\n"
            "4. Фильтрация по confidence\n"
            "5. Дообучение XGBoost\n"
            "6. Валидация на held-out Сколково\n\n"
            "Это может занять 1-5 минут..."
        )

        try:
            from scoring.retrain import retrain_with_external, prepare_external_from_db
            import asyncio

            external = await asyncio.to_thread(prepare_external_from_db)

            if not external:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Назад в админку", callback_data="admin_panel")]
                ])
                await query.message.edit_text(
                    "Нет внешних стартапов для дообучения.\n\n"
                    "Используйте /check для сбора данных по ИНН,\n"
                    "или дождитесь, пока пользователи начнут проверять стартапы.",
                    reply_markup=keyboard
                )
                return

            csv_path = str(SKOLKOVO_DB) if hasattr(SKOLKOVO_DB, '__iter__') and not isinstance(SKOLKOVO_DB, str) else "SkolkovoStartups.csv"
            if isinstance(SKOLKOVO_DB, list) and SKOLKOVO_DB:
                csv_path = "SkolkovoStartups.csv"

            result = await asyncio.to_thread(
                retrain_with_external,
                csv_path="SkolkovoStartups.csv",
                external_startups=external,
                confidence_threshold=0.8,
                min_external=10,
                dry_run=False,
            )

            status_icon = {
                "success": "Модели обновлены!",
                "rollback": "Откат: метрики упали",
                "skipped": "Пропущено",
                "dry_run": "Тестовый прогон (без сохранения)",
            }.get(result["status"], result["status"])

            text = f"🔬 ML ДООБУЧЕНИЕ\n\n"
            text += f"Статус: {status_icon}\n"
            text += f"Причина: {result['reason']}\n\n"
            text += f"Сколково: {result['n_skolkovo']} стартапов\n"
            text += f"Внешних (всего): {result['n_external_total']}\n"
            text += f"Внешних (использовано): {result['n_external_used']}\n\n"

            if result["metrics_before"]:
                text += "Метрики ДО:\n"
                for t, m in list(result["metrics_before"].items())[:3]:
                    text += f"  {t}: R2={m['r2']:.3f}\n"

            if result["metrics_after"]:
                text += "\nМетрики ПОСЛЕ:\n"
                for t, m in list(result["metrics_after"].items())[:3]:
                    text += f"  {t}: R2={m['r2']:.3f}\n"

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Назад в админку", callback_data="admin_panel")]
            ])
            await query.message.edit_text(text, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Ошибка ML дообучения: {e}")
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Назад в админку", callback_data="admin_panel")]
            ])
            await query.message.edit_text(
                f"Ошибка дообучения: {str(e)[:300]}",
                reply_markup=keyboard
            )

    @router.callback_query(F.data == "admin_tokens_users")
    async def admin_tokens_users(query: types.CallbackQuery):
        user_id = query.from_user.id
        if not await user_repository.is_admin(user_id):
            await query.answer("❌ У вас нет доступа", show_alert=True)
            return
        
        await query.answer()
        
        from config import GIGACHAT_TOKEN_PRICES
        
        # Получаем статистику по всем пользователям
        all_users_stats = await user_repository.get_all_users_token_statistics()
        
        if not all_users_stats:
            text = "📊 Статистика токенов по пользователям\n\n"
            text += "Данные отсутствуют"
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_tokens")],
                ]
            )
            await query.message.edit_text(text, reply_markup=keyboard)
            return
        
        # Группируем данные по пользователям
        users_data = {}
        for tg_user_id, model_type, tokens in all_users_stats:
            if tg_user_id not in users_data:
                users_data[tg_user_id] = {}
            users_data[tg_user_id][model_type] = tokens
        
        # Сортируем пользователей по общему количеству токенов (по убыванию)
        users_sorted = []
        for tg_user_id, models in users_data.items():
            total_tokens = sum(models.values())
            users_sorted.append((tg_user_id, models, total_tokens))
        users_sorted.sort(key=lambda x: x[2], reverse=True)
        
        text = "📊 Статистика токенов по пользователям\n"
        text += "━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for tg_user_id, models, total_tokens in users_sorted[:20]:  # Показываем топ-20
            # Рассчитываем общую стоимость для пользователя
            user_cost = 0
            for model_type, tokens in models.items():
                prices = GIGACHAT_TOKEN_PRICES.get(model_type, {"input": 0, "output": 0})
                input_tokens = int(tokens * 0.3)
                output_tokens = int(tokens * 0.7)
                cost = (input_tokens * prices["input"] + output_tokens * prices["output"]) / 1_000_000
                user_cost += cost
            
            text += f"👤 ID: {tg_user_id}\n"
            text += f"   📊 Токенов: {total_tokens:,}\n"
            
            # Детализация по моделям
            for model_type, tokens in models.items():
                model_name = {
                    "standard": "Std",
                    "pro": "Pro",
                    "max": "Max"
                }.get(model_type, model_type)
                text += f"   • {model_name}: {tokens:,}\n"
            
            text += f"   💵 Стоимость: {user_cost:.2f} ₽\n\n"
        
        if len(users_sorted) > 20:
            text += f"... и еще {len(users_sorted) - 20} пользователей\n\n"
        
        # Общая статистика
        total_all_tokens = sum(x[2] for x in users_sorted)
        total_all_cost = 0
        for _, models, _ in users_sorted:
            for model_type, tokens in models.items():
                prices = GIGACHAT_TOKEN_PRICES.get(model_type, {"input": 0, "output": 0})
                input_tokens = int(tokens * 0.3)
                output_tokens = int(tokens * 0.7)
                cost = (input_tokens * prices["input"] + output_tokens * prices["output"]) / 1_000_000
                total_all_cost += cost
        
        text += f"━━━━━━━━━━━━━━━━━━━━\n"
        text += f"👥 Всего пользователей: {len(users_sorted)}\n"
        text += f"📊 Всего токенов: {total_all_tokens:,}\n"
        text += f"💰 Общая стоимость: {total_all_cost:.2f} ₽\n"
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_tokens")],
            ]
        )
        
        await query.message.edit_text(text, reply_markup=keyboard)

