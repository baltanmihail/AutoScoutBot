import sqlite3
from config import USERS_DB_FILE_NAME, ADMIN_IDS
from domain.user import User
from domain.user_repository import UserRepository
from logger import logger
from datetime import datetime

TABLE_NAME = "Users"
PURCHASES_TABLE = "Purchases"
TOKEN_USAGE_TABLE = "TokenUsage"

class SQLiteUserRepositoryImpl(UserRepository):
    def __init__(self):
        super().__init__()
        self.connection = connection = sqlite3.connect(USERS_DB_FILE_NAME)
        self.cursor = connection.cursor()

        # Основная таблица пользователей
        self.cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                id INTEGER PRIMARY KEY,
                tg_user_id INTEGER UNIQUE,
                requests_standard INTEGER DEFAULT 0,
                requests_pro INTEGER DEFAULT 0,
                requests_max INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            '''
        )
        
        # Таблица покупок
        self.cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {PURCHASES_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                model_type TEXT,
                requests_amount INTEGER,
                price INTEGER,
                stars_spent INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES {TABLE_NAME}(tg_user_id)
            )
            '''
        )
        
        # Таблица использования токенов
        self.cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {TOKEN_USAGE_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                model_type TEXT,
                tokens_used INTEGER,
                request_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES {TABLE_NAME}(tg_user_id)
            )
            '''
        )
        
        self.connection.commit()
        
        # Миграция схемы базы данных
        self._migrate_database_schema()
        
        # Миграция старых данных
        self._migrate_old_data()

    def _migrate_database_schema(self):
        """Миграция схемы базы данных - добавление новых колонок"""
        try:
            # Получаем список существующих колонок
            self.cursor.execute("PRAGMA table_info(Users)")
            existing_columns = [col[1] for col in self.cursor.fetchall()]
            
            # Список колонок, которые должны быть (без DEFAULT для created_at, т.к. SQLite не поддерживает)
            required_columns = {
                "requests_standard": "INTEGER DEFAULT 0",
                "requests_pro": "INTEGER DEFAULT 0",
                "requests_max": "INTEGER DEFAULT 0",
                "is_banned": "INTEGER DEFAULT 0",
                "is_admin": "INTEGER DEFAULT 0",
                "created_at": "TIMESTAMP"  # Без DEFAULT, установим значения позже
            }
            
            # Добавляем отсутствующие колонки
            for column_name, column_type in required_columns.items():
                if column_name not in existing_columns:
                    try:
                        self.cursor.execute(f'ALTER TABLE {TABLE_NAME} ADD COLUMN {column_name} {column_type}')
                        logger.info(f"Добавлена колонка {column_name} в таблицу {TABLE_NAME}")
                    except sqlite3.OperationalError as e:
                        logger.warning(f"Не удалось добавить колонку {column_name}: {e}")
            
            self.connection.commit()
            logger.info("Миграция схемы базы данных завершена")
        except Exception as e:
            logger.error(f"Ошибка миграции схемы: {e}")

    def _migrate_old_data(self):
        """Миграция старых данных из старой схемы"""
        try:
            # Проверяем, какие колонки есть
            self.cursor.execute("PRAGMA table_info(Users)")
            columns = [col[1] for col in self.cursor.fetchall()]
            
            if "request_amount" in columns:
                # Мигрируем данные из request_amount в requests_standard
                self.cursor.execute(f'''
                    UPDATE {TABLE_NAME} 
                    SET requests_standard = request_amount 
                    WHERE requests_standard = 0 AND request_amount > 0
                ''')
                logger.info("Мигрированы данные из request_amount в requests_standard")
            
            # Устанавливаем is_admin для существующих админов (всегда проверяем)
            if "is_admin" in columns:
                for admin_id in ADMIN_IDS:
                    self.cursor.execute(f'''
                        UPDATE {TABLE_NAME} 
                        SET is_admin = 1 
                        WHERE tg_user_id = ? AND (is_admin IS NULL OR is_admin = 0)
                    ''', (admin_id,))
            
            # Устанавливаем значения по умолчанию для NULL значений
            update_parts = []
            if "requests_standard" in columns:
                update_parts.append("requests_standard = COALESCE(requests_standard, 0)")
            if "requests_pro" in columns:
                update_parts.append("requests_pro = COALESCE(requests_pro, 0)")
            if "requests_max" in columns:
                update_parts.append("requests_max = COALESCE(requests_max, 0)")
            if "is_banned" in columns:
                update_parts.append("is_banned = COALESCE(is_banned, 0)")
            if "is_admin" in columns:
                update_parts.append("is_admin = COALESCE(is_admin, 0)")
            
            if update_parts:
                self.cursor.execute(f'''
                    UPDATE {TABLE_NAME} 
                    SET {', '.join(update_parts)}
                    WHERE requests_standard IS NULL 
                       OR requests_pro IS NULL 
                       OR requests_max IS NULL 
                       OR is_banned IS NULL 
                       OR is_admin IS NULL
                ''')
            
            # Устанавливаем created_at для существующих записей, если колонка есть
            if "created_at" in columns:
                self.cursor.execute(f'''
                    UPDATE {TABLE_NAME} 
                    SET created_at = datetime('now')
                    WHERE created_at IS NULL
                ''')
            
            self.connection.commit()
            logger.info("Миграция старых данных выполнена")
        except Exception as e:
            logger.error(f"Ошибка миграции данных: {e}")
    
    async def add_available_requests(self, user_id, request_amount: int, model_type: str = "standard") -> int:
        if not (await self.user_exists(user_id)):
            logger.error(f"Пользователь с id {user_id} не существует! add_available_requests")
            return 0
        
        column_name = f"requests_{model_type}"
        
        # Проверяем наличие колонки
        if not self._check_column_exists(column_name):
            logger.error(f"Колонка {column_name} не существует!")
            return 0
        
        # Используем COALESCE для безопасности
        self.cursor.execute(
            f'UPDATE {TABLE_NAME} SET {column_name} = COALESCE({column_name}, 0) + ? WHERE tg_user_id = ?', 
            (request_amount, user_id)
        )
        self.connection.commit()

        self.cursor.execute(f'SELECT {column_name} FROM {TABLE_NAME} WHERE tg_user_id = ?', (user_id,))
        data = self.cursor.fetchone()
        new_request_amount = data[0] if data and data[0] is not None else 0
        return new_request_amount
    
    async def add_purchase(self, user_id: int, model_type: str, requests_amount: int, price: int, stars_spent: int):
        """Добавить запись о покупке"""
        self.cursor.execute(
            f'INSERT INTO {PURCHASES_TABLE} (user_id, model_type, requests_amount, price, stars_spent) VALUES (?, ?, ?, ?, ?)',
            (user_id, model_type, requests_amount, price, stars_spent)
        )
        self.connection.commit()
    
    async def get_purchases(self, user_id: int):
        """Получить историю покупок пользователя"""
        self.cursor.execute(
            f'SELECT model_type, requests_amount, price, stars_spent, created_at FROM {PURCHASES_TABLE} WHERE user_id = ? ORDER BY created_at DESC',
            (user_id,)
        )
        return self.cursor.fetchall()
    
    async def add_token_usage(self, user_id: int, model_type: str, tokens_used: int, request_text: str = ""):
        """Добавить запись об использовании токенов"""
        self.cursor.execute(
            f'INSERT INTO {TOKEN_USAGE_TABLE} (user_id, model_type, tokens_used, request_text) VALUES (?, ?, ?, ?)',
            (user_id, model_type, tokens_used, request_text[:200])
        )
        self.connection.commit()
    
    async def get_token_statistics(self, model_type: str = None):
        """Получить статистику использования токенов"""
        if model_type:
            self.cursor.execute(
                f'SELECT SUM(tokens_used) FROM {TOKEN_USAGE_TABLE} WHERE model_type = ?',
                (model_type,)
            )
        else:
            self.cursor.execute(f'SELECT model_type, SUM(tokens_used) FROM {TOKEN_USAGE_TABLE} GROUP BY model_type')
            return self.cursor.fetchall()
        
        result = self.cursor.fetchone()
        return result[0] if result and result[0] else 0
    
    async def get_user_token_statistics(self, user_id: int):
        """Получить статистику использования токенов конкретным пользователем"""
        self.cursor.execute(
            f'SELECT model_type, SUM(tokens_used) FROM {TOKEN_USAGE_TABLE} WHERE user_id = ? GROUP BY model_type',
            (user_id,)
        )
        return self.cursor.fetchall()
    
    async def get_all_users_token_statistics(self):
        """Получить статистику токенов по всем пользователям"""
        self.cursor.execute(f'''
            SELECT u.tg_user_id, t.model_type, SUM(t.tokens_used) as total_tokens
            FROM {TOKEN_USAGE_TABLE} t
            JOIN {TABLE_NAME} u ON t.user_id = u.tg_user_id
            GROUP BY u.tg_user_id, t.model_type
            ORDER BY u.tg_user_id, t.model_type
        ''')
        return self.cursor.fetchall()
    
    async def use_request(self, user_id, model_type: str = "standard"):
        if not (await self.user_exists(user_id)):
            logger.error(f"Пользователь с id {user_id} не существует! use_request")
            return
        
        if not (await self.user_have_available_requests(user_id, model_type)):
            logger.error(f"Пользователь с id {user_id} не имеет доступных запросов для модели {model_type}! use_request")
            return

        column_name = f"requests_{model_type}"
        
        # Проверяем наличие колонки
        if not self._check_column_exists(column_name):
            logger.error(f"Колонка {column_name} не существует!")
            return
        
        # Используем COALESCE для безопасности
        self.cursor.execute(
            f'UPDATE {TABLE_NAME} SET {column_name} = COALESCE({column_name}, 0) - 1 WHERE tg_user_id = ? AND COALESCE({column_name}, 0) > 0', 
            (user_id,)
        )
        self.connection.commit()

    async def add_user(self, user_id):
        if (await self.user_exists(user_id)):
            logger.info(f"Пользователь с id {user_id} уже существует")
            return
        
        user = User()
        is_admin = 1 if user_id in ADMIN_IDS else 0
        has_created_at = self._check_column_exists("created_at")
        
        if has_created_at:
            self.cursor.execute(
                f'INSERT INTO {TABLE_NAME} (tg_user_id, requests_standard, is_admin, created_at) VALUES (?, ?, ?, datetime("now"))',
                (user_id, user.available_requests_amount, is_admin)
            )
        else:
            self.cursor.execute(
                f'INSERT INTO {TABLE_NAME} (tg_user_id, requests_standard, is_admin) VALUES (?, ?, ?)',
                (user_id, user.available_requests_amount, is_admin)
            )
        self.connection.commit()
        logger.info(f"Пользователь с id {user_id} добавлен")
    
    async def user_have_available_requests(self, user_id, model_type: str = "standard") -> bool:
        return await self.available_requests_amount(user_id, model_type) > 0
    
    async def available_requests_amount(self, user_id, model_type: str = "standard") -> int:
        if not (await self.user_exists(user_id)):
            logger.error(f"Пользователь с id {user_id} не существует! available_requests_amount")
            return 0
        
        column_name = f"requests_{model_type}"
        
        # Проверяем наличие колонки
        if not self._check_column_exists(column_name):
            logger.warning(f"Колонка {column_name} не существует, возвращаем 0")
            return 0
        
        self.cursor.execute(f'SELECT COALESCE({column_name}, 0) FROM {TABLE_NAME} WHERE tg_user_id = ?', (user_id,))
        user = self.cursor.fetchone()
        request_amount = user[0] if user and user[0] is not None else 0
        return request_amount
    
    async def get_user_balance(self, user_id):
        """Получить баланс пользователя по всем моделям"""
        if not (await self.user_exists(user_id)):
            return {"standard": 0, "pro": 0, "max": 0}
        
        # Проверяем наличие колонок и используем COALESCE
        balance = {"standard": 0, "pro": 0, "max": 0}
        
        for model_type in ["standard", "pro", "max"]:
            col_name = f"requests_{model_type}"
            if self._check_column_exists(col_name):
                self.cursor.execute(
                    f'SELECT COALESCE({col_name}, 0) FROM {TABLE_NAME} WHERE tg_user_id = ?',
                    (user_id,)
                )
                result = self.cursor.fetchone()
                balance[model_type] = result[0] if result and result[0] is not None else 0
        
        return balance
    
    async def is_admin(self, user_id) -> bool:
        """Проверить, является ли пользователь админом"""
        if not (await self.user_exists(user_id)):
            return False
        
        # Проверяем наличие колонки
        if not self._check_column_exists("is_admin"):
            # Если колонки нет, проверяем по ADMIN_IDS
            return user_id in ADMIN_IDS
        
        self.cursor.execute(f'SELECT is_admin FROM {TABLE_NAME} WHERE tg_user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        return result and result[0] == 1
    
    async def is_banned(self, user_id) -> bool:
        """Проверить, забанен ли пользователь"""
        if not (await self.user_exists(user_id)):
            return False
        
        # Проверяем наличие колонки
        if not self._check_column_exists("is_banned"):
            # Если колонки нет, пользователь не забанен
            return False
        
        self.cursor.execute(f'SELECT is_banned FROM {TABLE_NAME} WHERE tg_user_id = ?', (user_id,))
        result = self.cursor.fetchone()
        return result and result[0] == 1
    
    async def ban_user(self, user_id: int):
        """Забанить пользователя"""
        if not (await self.user_exists(user_id)):
            return False
        
        # Проверяем наличие колонки
        if not self._check_column_exists("is_banned"):
            logger.warning("Колонка is_banned не существует, невозможно забанить пользователя")
            return False
        
        self.cursor.execute(f'UPDATE {TABLE_NAME} SET is_banned = 1 WHERE tg_user_id = ?', (user_id,))
        self.connection.commit()
        return True
    
    async def unban_user(self, user_id: int):
        """Разбанить пользователя"""
        if not (await self.user_exists(user_id)):
            return False
        
        # Проверяем наличие колонки
        if not self._check_column_exists("is_banned"):
            logger.warning("Колонка is_banned не существует, невозможно разбанить пользователя")
            return False
        
        self.cursor.execute(f'UPDATE {TABLE_NAME} SET is_banned = 0 WHERE tg_user_id = ?', (user_id,))
        self.connection.commit()
        return True
    
    async def give_requests(self, user_id: int, model_type: str, amount: int):
        """Выдать запросы пользователю (админ функция)"""
        return await self.add_available_requests(user_id, amount, model_type)
    
    def _check_column_exists(self, column_name: str) -> bool:
        """Проверить, существует ли колонка в таблице"""
        self.cursor.execute("PRAGMA table_info(Users)")
        columns = [col[1] for col in self.cursor.fetchall()]
        return column_name in columns
    
    async def get_all_users(self):
        """Получить список всех пользователей"""
        # Проверяем наличие колонки created_at
        has_created_at = self._check_column_exists("created_at")
        
        if has_created_at:
            self.cursor.execute(
                f'SELECT tg_user_id, requests_standard, requests_pro, requests_max, is_banned, is_admin, created_at FROM {TABLE_NAME} ORDER BY created_at DESC'
            )
        else:
            # Если колонки нет, возвращаем NULL для created_at
            self.cursor.execute(
                f'SELECT tg_user_id, requests_standard, requests_pro, requests_max, is_banned, is_admin, NULL as created_at FROM {TABLE_NAME}'
            )
        return self.cursor.fetchall()
    
    async def get_user_info(self, user_id: int):
        """Получить информацию о пользователе"""
        # Проверяем наличие колонки created_at
        has_created_at = self._check_column_exists("created_at")
        
        if has_created_at:
            self.cursor.execute(
                f'SELECT tg_user_id, requests_standard, requests_pro, requests_max, is_banned, is_admin, created_at FROM {TABLE_NAME} WHERE tg_user_id = ?',
                (user_id,)
            )
        else:
            # Если колонки нет, возвращаем NULL для created_at
            self.cursor.execute(
                f'SELECT tg_user_id, requests_standard, requests_pro, requests_max, is_banned, is_admin, NULL as created_at FROM {TABLE_NAME} WHERE tg_user_id = ?',
                (user_id,)
            )
        return self.cursor.fetchone()

    async def user_exists(self, user_id):
        self.cursor.execute(f'SELECT * FROM {TABLE_NAME} WHERE tg_user_id = ?', (user_id,))
        data = self.cursor.fetchone()
        return not (data is None)
    
    async def on_end(self):
        self.connection.close()