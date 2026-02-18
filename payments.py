from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, PreCheckoutQuery, LabeledPrice, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from config import REQUEST_PRICES, LLM_MODELS

from services.payments_service import PaymentsService

TIER_LABELS = {
    "standard": "⚡ Gemini 3 Pro",
    "premium":  "🧠 Claude Sonnet 4.5",
    "ultra":    "💎 Claude Opus 4.6",
}

TIER_LABELS_SHORT = {
    "standard": "Gemini 3 Pro",
    "premium":  "Claude Sonnet 4.5",
    "ultra":    "Claude Opus 4.6",
}


def get_payments_router(payments_service: PaymentsService) -> Router:
    router = Router()

    def _model_keyboard():
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=TIER_LABELS["standard"], callback_data="model_standard")],
                [InlineKeyboardButton(text=TIER_LABELS["premium"],  callback_data="model_premium")],
                [InlineKeyboardButton(text=TIER_LABELS["ultra"],    callback_data="model_ultra")],
            ]
        )

    @router.message(Command("pay"))
    async def payment_menu_cmd(message: Message):
        await message.answer(
            "Выберите модель AI для покупки запросов:",
            reply_markup=_model_keyboard(),
        )

    @router.callback_query(F.data == "pay")
    async def payment_menu_btn(query: CallbackQuery):
        await query.message.edit_text(
            "Выберите модель AI для покупки запросов:",
            reply_markup=_model_keyboard(),
        )

    @router.callback_query(F.data.in_(["model_standard", "model_premium", "model_ultra"]))
    async def select_model(query: CallbackQuery):
        model_type = query.data.replace("model_", "")
        label = TIER_LABELS.get(model_type, model_type)
        prices = REQUEST_PRICES.get(model_type, {})

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"3 запроса — {prices.get(3, 0)} ⭐",
                    callback_data=f"buy_{model_type}_3",
                )],
                [InlineKeyboardButton(
                    text=f"5 запросов — {prices.get(5, 0)} ⭐",
                    callback_data=f"buy_{model_type}_5",
                )],
                [InlineKeyboardButton(
                    text=f"10 запросов — {prices.get(10, 0)} ⭐",
                    callback_data=f"buy_{model_type}_10",
                )],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="pay")],
            ]
        )

        await query.message.edit_text(
            f"Модель: <b>{label}</b>\n\nВыберите количество запросов:",
            reply_markup=keyboard,
            parse_mode="HTML",
        )

    @router.callback_query(F.data.startswith("buy_"))
    async def handle_pay(query: CallbackQuery):
        parts = query.data.split("_")
        model_type = parts[1]
        request_amount = int(parts[2])

        price = payments_service.get_price(model_type, request_amount)
        label = TIER_LABELS.get(model_type, model_type)

        prices = [LabeledPrice(label=f"{request_amount} запросов ({label})", amount=price)]

        await query.bot.send_invoice(
            chat_id=query.from_user.id,
            title="Покупка запросов",
            description=f"{request_amount} запросов для модели {label}",
            prices=prices,
            provider_token="",
            payload=payments_service.payload_by_request_amount(model_type, request_amount),
            currency="XTR",
        )

    @router.pre_checkout_query()
    async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
        await pre_checkout_query.answer(ok=True)

    @router.message(F.successful_payment)
    async def process_successful_payment(message: Message):
        payment_info = message.successful_payment
        user_id = message.from_user.id

        await payments_service.on_successful_payment(user_id, payment_info)

        model_type, bought_requests = payments_service.request_info_by_payload(payment_info.invoice_payload)
        label = TIER_LABELS.get(model_type, model_type)

        balance = await payments_service.user_repository.get_user_balance(user_id)

        await message.answer(
            f"✅ Спасибо за оплату!\n\n"
            f"💰 Сумма: {payment_info.total_amount} ⭐\n"
            f"Модель: {label}\n"
            f"Куплено запросов: {bought_requests}\n\n"
            f"📊 Ваш баланс:\n"
            f"• {TIER_LABELS_SHORT['standard']}: {balance.get('standard', 0)} запросов\n"
            f"• {TIER_LABELS_SHORT['premium']}: {balance.get('premium', 0)} запросов\n"
            f"• {TIER_LABELS_SHORT['ultra']}: {balance.get('ultra', 0)} запросов"
        )

    @router.message(Command("paysupport"))
    async def pay_support(message: Message):
        await message.answer(
            "💬 Поддержка платежей\n\n"
            "Если у вас возникли проблемы с оплатой, свяжитесь с поддержкой: @programming_harius"
        )

    return router
