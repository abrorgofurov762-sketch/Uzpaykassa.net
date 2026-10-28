import telebot
from telebot.types import Message, ReplyKeyboardRemove
from utils.keyboards import (get_main_menu_keyboard, get_bookmakers_keyboard, 
                           get_urls_keyboard, get_apps_keyboard, get_admin_menu_keyboard)
import config
from html import escape
from database.database import db
from utils.state_manager import last_menu_action, clear_user_states

def register_menu_handlers(bot: telebot.TeleBot):
    
    @bot.message_handler(func=lambda message: message.text == "💰 Hisob to'ldirish")
    def deposit_menu(message: Message):
        user_id = message.from_user.id
        
        # Bot o'chirilgan bo'lsa va admin emas bo'lsa, bloklash
        if not config.BOT_ACTIVE and user_id != config.ADMIN_ID:
            bot.send_message(
                message.chat.id,
                "🚫 Bot hozirda texnik ishlar olib borilmoqda. Keyinroq urinib ko'ring.",
                reply_markup=ReplyKeyboardRemove()
            )
            return
        
        last_menu_action[user_id] = 'deposit'
        
        bot.send_message(
            message.chat.id,
            "🎯 Bukmekerlar ro'yxatidan birini tanlang:",
            reply_markup=get_bookmakers_keyboard()
        )
    
    @bot.message_handler(func=lambda message: message.text == "💸 Pul yechish")
    def withdrawal_menu(message: Message):
        user_id = message.from_user.id
        
        # Bot o'chirilgan bo'lsa va admin emas bo'lsa, bloklash
        if not config.BOT_ACTIVE and user_id != config.ADMIN_ID:
            bot.send_message(
                message.chat.id,
                "🚫 Bot hozirda texnik ishlar olib borilmoqda. Keyinroq urinib ko'ring.",
                reply_markup=ReplyKeyboardRemove()
            )
            return
        
        last_menu_action[user_id] = 'withdrawal'
        
        bot.send_message(
            message.chat.id,
            "🎯 Pul yechish uchun bukmekerlar ro'yxatidan birini tanlang:",
            reply_markup=get_bookmakers_keyboard()
        )
    
    @bot.message_handler(func=lambda message: message.text == "📜 Operatsiyalar tarixi")
    def operation_history(message: Message):
        """Show only the current user's recent deposits and withdrawal requests."""
        user_id = message.from_user.id
        payments = db.get_user_payments(user_id, limit=10)
        withdrawals = db.get_user_withdrawals(user_id, limit=10)
        status_labels = {
            "pending": "⏳ Кутилаяпти",
            "processing": "🔄 Жараёнда",
            "paid": "💳 Тўлов қабул қилинган",
            "paid_review": "🧑‍💼 Қўлда текширилмоқда",
            "completed": "✅ Якунланган",
            "failed": "❌ Хатолик",
            "expired": "⌛ Муддати ўтган",
            "approved": "✅ Админ тасдиқлаган",
        }
        lines = ["📜 <b>Сизнинг операциялар тарихингиз</b>", ""]
        if payments:
            lines.append("<b>💰 Депозитлар:</b>")
            for item in payments:
                status = status_labels.get(str(item.status), "❔ " + str(item.status))
                created = str(item.created_at or "")[:16]
                lines.append(
                    f"• {escape(str(item.bukmeker))} — {item.amount:,.0f} сўм\n"
                    f"  Ҳолат: {status}\n  ID: <code>{escape(str(item.payment_id))}</code>\n  {escape(created)}"
                )
        if withdrawals:
            lines.append("\n<b>💸 Пул ечиш аризалари:</b>")
            for item in withdrawals:
                status = status_labels.get(str(item.status), "❔ " + str(item.status))
                amount_text = f"{item.amount:,.0f} сўм" if item.amount is not None else "сумма кўрсатилмаган"
                created = str(item.created_at or "")[:16]
                lines.append(
                    f"• {escape(str(item.bukmeker))} — {amount_text}\n"
                    f"  Ҳолат: {status}\n  Ариза №{item.id}\n  {created}"
                )
        if not payments and not withdrawals:
            lines.append("Ҳозирча операциялар мавжуд эмас.")
        # No full card number or verification code is displayed.
        safe_lines = []
        for line in lines:
            # Keep our intentional <b> and <code> markup while escaping inserted values above.
            safe_lines.append(line)
        bot.send_message(message.chat.id, "\n".join(safe_lines), parse_mode="HTML")

    @bot.message_handler(func=lambda message: message.text == "📱 Ilovalar")
    def apps_menu(message: Message):
        user_id = message.from_user.id
        
        # Bot o'chirilgan bo'lsa va admin emas bo'lsa, bloklash
        if not config.BOT_ACTIVE and user_id != config.ADMIN_ID:
            bot.send_message(
                message.chat.id,
                "🚫 Bot hozirda texnik ishlar olib borilmoqda. Keyinroq urinib ko'ring.",
                reply_markup=ReplyKeyboardRemove()
            )
            return
        
        bot.send_message(
            message.chat.id,
            "📱 Rasmiy ilovalarni yuklab olish:",
            reply_markup=get_apps_keyboard()
        )
    
    @bot.message_handler(func=lambda message: message.text == "📞 Aloqa")
    def contact_menu(message: Message):
        user_id = message.from_user.id
        
        # Bot o'chirilgan bo'lsa va admin emas bo'lsa, bloklash
        if not config.BOT_ACTIVE and user_id != config.ADMIN_ID:
            bot.send_message(
                message.chat.id,
                "🚫 Bot hozirda texnik ishlar olib borilmoqda. Keyinroq urinib ko'ring.",
                reply_markup=ReplyKeyboardRemove()
            )
            return
        
        bot.send_message(
            message.chat.id,
            "📞 Bizning administratorlarimiz:\n\n"
            "• Texnik yordam: @admin1\n"
            "• Savollar va takliflar: @admin2\n"
            "• 24/7 onlayn yordam",
            reply_markup=get_urls_keyboard()
        )
    
    @bot.message_handler(func=lambda message: message.text == "🔙 Orqaga")
    def back_to_main(message: Message):
        user_id = message.from_user.id
        clear_user_states(user_id)
        # Admin uchun orqaga har doim admin paneliga qaytaradi
        if user_id == getattr(config, 'ADMIN_ID', None):
            bot.send_message(
                message.chat.id,
                "👨‍💼 Admin panel:",
                reply_markup=get_admin_menu_keyboard()
            )
        else:
            bot.send_message(
                message.chat.id,
                "🏠 Asosiy menyu:",
                reply_markup=get_main_menu_keyboard()
            )
