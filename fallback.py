from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

class Fallback:
    router = Router()

    def __init__(self):
        pass
    
    @router.message(F.text & ~F.via_bot & ~F.forward_from)
    async def text_fallback(message: types.Message, state: FSMContext):
        # Универсальный обработчик текстов вне состояний
        st = await state.get_state()
        if st is None:
            await message.answer(
                "🚀 Привет! Я бот для поиска перспективных стартапов из базы Сколково.\n\n"
                "📋 Доступные команды:\n"
                "/start - Начало работы с ботом\n"
                "/analyze - Анализ базы Сколково\n"
                "/help - Показать список всех команд\n"
                "/pay - Приобрести запросы\n"
                "/paysupport - Поддержка по вопросам оплаты\n"
                "🔍 Выберите команду для продолжения:"
            )