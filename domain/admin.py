from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters
import logging
from datetime import datetime
from config import ADMIN_IDS, AI_MODELS
from database import db
from keyboards import get_admin_payment_keyboard

logger = logging.getLogger(__name__)

class AdminHandlers:
    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Главное меню админ-панели"""
        user_id = update.effective_user.id
        user = db.get_user(user_id)
        
        if not user or not user.is_admin:
            if update.message:
                await update.message.reply_text("❌ У вас нет доступа к админ-панели")
            else:
                await update.callback_query.edit_message_text("❌ У вас нет доступа к админ-панели")
            return

        # Получаем статистику
        conn = db._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_banned = 1')
        banned_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT SUM(total_stars_spent) FROM users')
        total_stars = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT COUNT(*) FROM ai_requests')
        total_requests = cursor.fetchone()[0]
        
        cursor.execute('SELECT SUM(tokens_used) FROM ai_requests')
        total_tokens = cursor.fetchone()[0] or 0
        
        conn.close()

        admin_text = (
            "👑 Админ-панель\n\n"
            f"📊 Основная статистика:\n"
            f"• Всего пользователей: {total_users}\n"
            f"• Заблокированных: {banned_users}\n"
            f"• Всего запросов: {total_requests}\n"
            f"• Использовано токенов: {total_tokens:,}\n"
            f"• Заработано звёзд: {total_stars} ⭐\n"
        )

        keyboard = [
            [InlineKeyboardButton("👥 Управление пользователями", callback_data="admin_users")],
            [InlineKeyboardButton("💫 Запросы на оплату", callback_data="admin_payment_requests")],
            [InlineKeyboardButton("📊 Детальная статистика", callback_data="admin_stats")],
            [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.message:
            await update.message.reply_text(admin_text, reply_markup=reply_markup)
        else:
            await update.callback_query.edit_message_text(admin_text, reply_markup=reply_markup)

    async def handle_payment_approval(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка подтверждения платежа админом"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        action, target_user_id = data.split('_', 1)
        target_user_id = int(target_user_id)
        
        target_user = db.get_user(target_user_id)
        if not target_user:
            await query.edit_message_text("❌ Пользователь не найден")
            return
        
        # Получаем pending запросы пользователя
        pending_requests = db.get_pending_payment_requests()
        user_requests = [r for r in pending_requests if r.user_id == target_user_id]
        
        if not user_requests:
            await query.edit_message_text("❌ Нет pending запросов для этого пользователя")
            return
        
        payment_request = user_requests[0]  # Берем первый pending запрос
        
        if action == "approve":
            # Подтверждаем без изменений
            success = db.update_payment_request(
                target_user_id, "approved", 
                payment_request.final_price, 0
            )
            
            if success:
                # Начисляем звезды
                target_user.balance += payment_request.final_price
                db.save_user(target_user)
                
                await query.edit_message_text(
                    f"✅ Платеж подтвержден для @{target_user.username or target_user_id}\n"
                    f"Добавлено {payment_request.final_price} ⭐ на баланс."
                )
                
                # Уведомляем пользователя
                await context.bot.send_message(
                    target_user_id,
                    f"✅ Ваш запрос на покупку подтвержден администратором!\n"
                    f"Вам добавлено {payment_request.final_price} ⭐ на баланс.\n"
                    f"Теперь ваш баланс: {target_user.balance} ⭐"
                )
        
        elif action == "free":
            # Выдаем бесплатно
            success = db.update_payment_request(
                target_user_id, "approved", 0, payment_request.original_price
            )
            
            if success:
                target_user.balance += payment_request.final_price
                db.save_user(target_user)
                
                await query.edit_message_text(
                    f"🎁 Бесплатно выдано {payment_request.final_price} ⭐ для @{target_user.username or target_user_id}"
                )
                
                await context.bot.send_message(
                    target_user_id,
                    f"🎁 Администратор выдал вам {payment_request.final_price} ⭐ бесплатно!\n"
                    f"Теперь ваш баланс: {target_user.balance} ⭐"
                )
        
        elif action == "reject":
            db.update_payment_request(target_user_id, "rejected")
            await query.edit_message_text(
                f"❌ Запрос на платеж для @{target_user.username or target_user_id} отклонен"
            )
            
            await context.bot.send_message(
                target_user_id,
                "❌ Ваш запрос на покупку отклонен администратором."
            )

    async def show_payment_requests(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать pending запросы на оплату"""
        query = update.callback_query
        await query.answer()
        
        pending_requests = db.get_pending_payment_requests()
        
        if not pending_requests:
            await query.edit_message_text("✅ Нет pending запросов на оплату")
            return
        
        text = "💫 Запросы на оплату:\n\n"
        
        for i, req in enumerate(pending_requests, 1):
            user = db.get_user(req.user_id)
            display_name = f"@{user.username}" if user and user.username else f"ID {req.user_id}"
            model_name = AI_MODELS[req.model]['name']
            
            text += (
                f"{i}. 👤 {display_name}\n"
                f"   📦 {req.package_requests} запросов ({model_name})\n"
                f"   💰 {req.final_price}⭐ (оригинал: {req.original_price}⭐)\n"
                f"   🕒 {datetime.fromtimestamp(req.created_at).strftime('%d.%m %H:%M') if req.created_at else 'N/A'}\n\n"
            )
            
            # Добавляем кнопки действий для первого запроса
            if i == 1:
                keyboard = get_admin_payment_keyboard(req.user_id)
                await query.edit_message_text(text, reply_markup=keyboard)
                return
        
        # Если запросов много, но не показали кнопки
        await query.edit_message_text(text + "\n⚠️ Используйте кнопки выше для управления")

# Глобальный экземпляр
admin_handlers = AdminHandlers()