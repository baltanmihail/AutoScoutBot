import json
from config import REQUEST_PRICES
from domain.user_repository import UserRepository


class PaymentsService:
    def __init__(self, user_repository: UserRepository):
        self.user_repository = user_repository

    def get_price(self, model_type: str, requests_amount: int) -> int:
        """Получить цену для модели и количества запросов"""
        prices = REQUEST_PRICES.get(model_type, {})
        return prices.get(requests_amount, 0)

    def payload_by_request_amount(self, model_type: str, requests_amount: int) -> str:
        extra_info = {
            "model_type": model_type,
            "requests_amount": requests_amount,
        }
        payload = json.dumps(extra_info)[:128]
        return payload

    def request_info_by_payload(self, payload: str):
        """Получить информацию о запросе из payload"""
        data = json.loads(payload)
        return data.get("model_type", "standard"), data.get("requests_amount", 0)

    async def on_successful_payment(self, user_id, payment_info):
        payload = payment_info.invoice_payload
        model_type, bought_requests = self.request_info_by_payload(payload)
        price = self.get_price(model_type, bought_requests)
        
        # Добавляем запросы
        await self.user_repository.add_available_requests(user_id, bought_requests, model_type)
        
        # Сохраняем покупку
        await self.user_repository.add_purchase(
            user_id=user_id,
            model_type=model_type,
            requests_amount=bought_requests,
            price=price,
            stars_spent=payment_info.total_amount
        )