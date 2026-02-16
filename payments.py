from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, PreCheckoutQuery, LabeledPrice, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from config import REQUEST_PRICES, GIGACHAT_MODELS

from services.payments_service import PaymentsService

def get_payments_router(payments_service: PaymentsService) -> Router:
    router = Router()

    @router.message(Command("pay"))
    async def payment_menu(message: Message):
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Standard (GigaChat-Lite)", callback_data="model_standard")],
                [InlineKeyboardButton(text="Pro (GigaChat-Pro)", callback_data="model_pro")],
                [InlineKeyboardButton(text="Max (GigaChat-Max)", callback_data="model_max")],
            ]
        )
        await message.answer(
            "Выберите модель для покупки запросов:",
            reply_markup=keyboard,
        )

    @router.callback_query(F.data == "pay")
    async def payment_menu(query: CallbackQuery):
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Standard (GigaChat-Lite)", callback_data="model_standard")],
                [InlineKeyboardButton(text="Pro (GigaChat-Pro)", callback_data="model_pro")],
                [InlineKeyboardButton(text="Max (GigaChat-Max)", callback_data="model_max")],
            ]
        )
        await query.message.edit_text(
            "Выберите модель для покупки запросов:",
            reply_markup=keyboard,
        )
    
    @router.callback_query(F.data.in_(["model_standard", "model_pro", "model_max"]))
    async def select_model(query: CallbackQuery):
        model_type = query.data.replace("model_", "")
        model_name = GIGACHAT_MODELS.get(model_type, "Unknown")
        prices = REQUEST_PRICES.get(model_type, {})
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"3 запросов ({prices.get(3, 0)} звёзд)", callback_data=f"buy_{model_type}_3")],
                [InlineKeyboardButton(text=f"5 запросов ({prices.get(5, 0)} звёзд)", callback_data=f"buy_{model_type}_5")],
                [InlineKeyboardButton(text=f"10 запросов ({prices.get(10, 0)} звёзд)", callback_data=f"buy_{model_type}_10")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="pay")],
            ]
        )
        
        await query.message.edit_text(
            f"Модель: {model_name}\n\nВыберите количество запросов:",
            reply_markup=keyboard,
        )
    
    @router.callback_query(F.data.startswith("buy_"))
    async def handle_pay(query: CallbackQuery):
        """
        Отправляет пользователю счёт на оплату в Telegram Stars
        """
        parts = query.data.split("_")
        model_type = parts[1]
        request_amount = int(parts[2])
        
        price = payments_service.get_price(model_type, request_amount)
        model_name = GIGACHAT_MODELS.get(model_type, "Unknown")
        
        # Создаём список цен (для Stars должен быть только один элемент)
        prices = [LabeledPrice(label=f"{request_amount} запросов ({model_name})", amount=price)]

        await query.bot.send_invoice(
            chat_id=query.from_user.id,
            title="Покупка запросов",
            description=f"{request_amount} запросов для модели {model_name}",
            prices=prices,
            provider_token="",  # Для Stars - пустая строка
            payload=payments_service.payload_by_request_amount(model_type, request_amount),
            currency="XTR",  # Обязательно XTR для Telegram Stars
        )

    # Обработчик предварительной проверки платежа
    @router.pre_checkout_query()
    async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
        """
        Обрабатывает запрос перед оплатой.
        Здесь можно проверить корректность заказа.
        """
        # Подтверждаем платёж
        await pre_checkout_query.answer(ok=True)

    # Обработчик успешного платежа
    @router.message(F.successful_payment)
    async def process_successful_payment(message: Message):
        """
        Обрабатывает успешный платёж
        """
        payment_info = message.successful_payment
        user_id = message.from_user.id
        
        await payments_service.on_successful_payment(user_id, payment_info)
        
        model_type, bought_requests = payments_service.request_info_by_payload(payment_info.invoice_payload)
        model_name = GIGACHAT_MODELS.get(model_type, "Unknown")
        
        balance = await payments_service.user_repository.get_user_balance(user_id)
        
        await message.answer(
            f"✅ Спасибо за оплату!\n\n"
            f"💰 Сумма: {payment_info.total_amount} звёзд\n"
            f"Модель: {model_name}\n"
            f"Куплено запросов: {bought_requests}\n\n"
            f"📊 Ваш баланс:\n"
            f"• Standard: {balance['standard']} запросов\n"
            f"• Pro: {balance['pro']} запросов\n"
            f"• Max: {balance['max']} запросов"
        )

    # Команда поддержки (обязательна для ботов с платежами)
    @router.message(Command("paysupport"))
    async def pay_support(message: Message):
        """
        Команда поддержки - обязательна согласно требованиям Telegram
        """
        await message.answer(
            "💬 Поддержка платежей\n\n"
            "Если у вас возникли проблемы с оплатой, свяжитесь с поддержкой: @programming_harius"
        )
    
    return router