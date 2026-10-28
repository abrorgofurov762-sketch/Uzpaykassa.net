import telebot
from telebot.types import CallbackQuery
from database.database import db
from utils.keyboards import get_main_menu_keyboard
from config import ADMIN_ID

def register_payment_handlers(bot: telebot.TeleBot):
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("approve_withdrawal_"))
    def approve_withdrawal(call: CallbackQuery):
        """Pul yechishni tasdiqlash; faqat admin va faqat pending ariza uchun."""
        try:
            if not call.from_user or call.from_user.id != ADMIN_ID:
                bot.answer_callback_query(call.id, "Sizda ruxsat yo'q", show_alert=True)
                return
            withdrawal_id = int(call.data.replace("approve_withdrawal_", ""))

            # A repeated callback must not approve the same request twice.
            if db.update_withdrawal_status(withdrawal_id, "approved", expected_status="pending"):
                bot.edit_message_text(
                    "✅ Pul yechish tasdiqlandi!",
                    call.message.chat.id,
                    call.message.message_id
                )
            else:
                bot.answer_callback_query(call.id, "❌ Xatolik yuz berdi!")
                
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Xatolik: {str(e)}")
    # cancel_payment callback handler moved to handlers/deposit.register_cancel_callback
    # to avoid duplicate handlers and keep logic in one place.
