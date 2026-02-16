from typing import Dict
from domain.user import User
from domain.user_repository import UserRepository


class DummyUserRepositoryImpl(UserRepository):
    def __init__(self):
        super().__init__()
        self.users = dict[str, User]()

    async def add_available_requests(self, user_id, request_amount: int) -> int:
        self.users[user_id].available_requests_amount += request_amount
    
    async def use_request(self, user_id):
        self.users[user_id].available_requests_amount -= 1

    async def add_user(self, user_id):
        if not (user_id in self.users.keys()):
            self.users[user_id] = User() 
    
    async def user_have_available_requests(self, user_id) -> bool:
        return self.users[user_id].available_requests_amount > 0
    
    async def available_requests_amount(self, user_id) -> int:
        return self.users[user_id].available_requests_amount

    async def on_end(self):
        pass