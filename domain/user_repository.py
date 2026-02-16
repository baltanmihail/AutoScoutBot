from abc import ABCMeta, abstractmethod

class UserRepository():
    __metaclass__=ABCMeta

    @abstractmethod
    async def add_available_requests(user_id, request_amount: int, model_type: str = "standard") -> int:
        pass
    
    @abstractmethod
    async def use_request(user_id, model_type: str = "standard"):
        pass
    
    @abstractmethod
    async def add_user(user_id):
        pass

    @abstractmethod
    async def user_have_available_requests(user_id, model_type: str = "standard") -> bool:
        pass

    @abstractmethod
    async def available_requests_amount(user_id, model_type: str = "standard") -> int:
        pass
    
    @abstractmethod
    async def on_end():
        pass
    
    # Новые методы для расширенной функциональности
    @abstractmethod
    async def add_purchase(user_id: int, model_type: str, requests_amount: int, price: int, stars_spent: int):
        pass
    
    @abstractmethod
    async def get_purchases(user_id: int):
        pass
    
    @abstractmethod
    async def add_token_usage(user_id: int, model_type: str, tokens_used: int, request_text: str = ""):
        pass
    
    @abstractmethod
    async def get_token_statistics(model_type: str = None):
        pass
    
    @abstractmethod
    async def get_user_balance(user_id):
        pass
    
    @abstractmethod
    async def is_admin(user_id) -> bool:
        pass
    
    @abstractmethod
    async def is_banned(user_id) -> bool:
        pass
    
    @abstractmethod
    async def ban_user(user_id: int):
        pass
    
    @abstractmethod
    async def unban_user(user_id: int):
        pass
    
    @abstractmethod
    async def give_requests(user_id: int, model_type: str, amount: int):
        pass
    
    @abstractmethod
    async def get_all_users():
        pass
    
    @abstractmethod
    async def get_user_info(user_id: int):
        pass