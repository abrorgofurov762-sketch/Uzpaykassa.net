import telebot
from telebot.types import Message
from database.database import db
from database.models import Payment
from api.xbet_api import xbet_api
from api.mobcash_api import melbet_api, betwiner_api, winwin_api
from api.mostbet_api import mostbet_api
from utils.validators import validate_player_id, validate_amount
from utils.keyboards import (
    get_main_menu_keyboard, get_cancel_keyboard, get_back_keyboard,
    get_admin_menu_keyboard,
)
import config
from utils.helpers import (
    generate_payment_id, generate_random_amount, get_random_card,
    create_payment_message, create_success_message,
    create_channel_payment_message,
)
from utils.state_manager import (
    deposit_states, withdrawal_states, last_menu_action, clear_user_states,
)
from config import MIN_DEPOSIT, MAX_DEPOSIT
import threading
import time
import logging

logger = logging.getLogger(__name__)


def register_deposit_handlers(bot: telebot.TeleBot):
    # Bukmeker tanlash - faqat deposit context da
    @bot.message_handler(
        func=lambda message: (
            message.text in [
                "🎯 1xBet", "🎲 Melbet", "🎰 Mostbet",
                "🎪 Betwiner", "🎨 WinWinBet"
            ]
            and last_menu_action.get(message.from_user.id) == "deposit"
        )
    )
    def select_bukmeker(message: Message):
        user_id = message.from_user.id

        if user_id in withdrawal_states:
            return
        if last_menu_action.get(user_id) != "deposit":
            return

        bukmeker = (
            message.text.replace("🎯 ", "")
            .replace("🎲 ", "")
            .replace("🎰 ", "")
            .replace("🎪 ", "")
            .replace("🎨 ", "")
        )
        deposit_states[user_id] = {
            "action": "deposit",
            "bukmeker": bukmeker,
            "step": "player_id",
        }
        bot.send_message(
            user_id,
            f"🆔 {bukmeker} ID raqamingizni kiriting:\n\n"
            "💡 Misol: 123456789",
            reply_markup=get_back_keyboard(),
        )

    @bot.message_handler(
        func=lambda message: (
            message.from_user.id in deposit_states
            and deposit_states[message.from_user.id].get("action") == "deposit"
            and deposit_states[message.from_user.id].get("step") == "player_id"
        )
    )
    def handle_player_id(message: Message):
        user_id = message.from_user.id

        if message.text == "🔙 Orqaga":
            clear_user_states(user_id)
            if user_id == getattr(config, "ADMIN_ID", None):
                bot.send_message(
                    user_id, "👨‍💼 Admin panel:",
                    reply_markup=get_admin_menu_keyboard(),
                )
            else:
                bot.send_message(
                    user_id, "🏠 Asosiy меню:",
                    reply_markup=get_main_menu_keyboard(),
                )
            return

        player_id = (message.text or "").strip()
        if not validate_player_id(player_id):
            from utils.bot_helpers import safe_send_message
            safe_send_message(
                bot, user_id,
                "❌ Noto'g'ri ID format!\n\n"
                "✅ To'g'ri format:\n"
                "• Kamida 3 ta belgi\n"
                "• Maksimal 20 ta belgi\n"
                "• Faqat raqam va harflar\n\n"
                "Qaytadan kiriting:",
            )
            return

        bukmeker = deposit_states[user_id]["bukmeker"]
        checking_msg = None
        try:
            from utils.bot_helpers import safe_send_message
            checking_msg = safe_send_message(bot, user_id, "⏳ Tekshirilmoqda...")
        except Exception:
            logger.exception("Could not send player-check message")

        def _async_check_player(u_id: int, bkm: str, p_id: str, check_msg):
            from utils.bot_helpers import safe_send_message
            try:
                player_info = check_player(bkm, p_id)

                if not player_info.get("Success"):
                    error_msg = player_info.get("error", "ID topilmadi")
                    try:
                        if check_msg:
                            bot.delete_message(u_id, check_msg.message_id)
                    except Exception:
                        pass
                    safe_send_message(
                        bot, u_id,
                        "❌ Xatolik yuz berdi!\n\n"
                        f"🔍 Sabab: {error_msg}\n\n"
                        "💡 Iltimos, ID ni to'g'ri kiriting yoki keyinroq urinib ko'ring.",
                        reply_markup=get_back_keyboard(),
                    )
                    return

                player_name = (
                    player_info.get("Name")
                    or player_info.get("name")
                    or player_info.get("player_name")
                    or ""
                )

                if bkm == "Mostbet" and not player_name:
                    try:
                        if check_msg:
                            bot.delete_message(u_id, check_msg.message_id)
                    except Exception:
                        pass
                    safe_send_message(
                        bot, u_id,
                        "❌ Mostbet API o'yinchi ismini qaytarmadi. "
                        "ID ni tekshiring yoki keyinroq urinib ko'ring.",
                        reply_markup=get_back_keyboard(),
                    )
                    return

                # Thread ichida foydalanuvchi holati o'chirilgan bo'lishi mumkin.
                current_state = deposit_states.get(u_id)
                if not current_state or current_state.get("bukmeker") != bkm:
                    return

                current_state["player_id"] = p_id
                current_state["player_info"] = player_info
                current_state["step"] = "amount"

                if not player_name:
                    player_name = "Foydalanuvchi"

                try:
                    if check_msg:
                        bot.delete_message(u_id, check_msg.message_id)
                except Exception:
                    pass
                safe_send_message(
                    bot, u_id,
                    f"👤 Foydalanuvchi: {player_name}\n\n"
                    "💰 To'lash summasini kiriting:\n\n"
                    f"💡 Minimal: {MIN_DEPOSIT:,} so'm\n"
                    f"💡 Maksimal: {MAX_DEPOSIT:,} so'm\n\n"
                    "📝 Misol: 50000",
                    reply_markup=get_back_keyboard(),
                )

            except Exception:
                logger.exception("Player ID check failed for %s", bkm)
                try:
                    if check_msg:
                        bot.delete_message(u_id, check_msg.message_id)
                except Exception:
                    pass
                safe_send_message(
                    bot, u_id,
                    "❌ Xatolik yuz berdi. Iltimos keyinroq urinib ko'ring.",
                    reply_markup=get_back_keyboard(),
                )

        threading.Thread(
            target=_async_check_player,
            args=(user_id, bukmeker, player_id, checking_msg),
            daemon=True,
        ).start()

    @bot.message_handler(
        func=lambda message: (
            message.from_user.id in deposit_states
            and deposit_states[message.from_user.id].get("action") == "deposit"
            and deposit_states[message.from_user.id].get("step") == "amount"
        )
    )
    def handle_amount(message: Message):
        from utils.bot_helpers import safe_send_message
        user_id = message.from_user.id

        if message.text == "🔙 Orqaga":
            deposit_states[user_id]["step"] = "player_id"
            bukmeker = deposit_states[user_id]["bukmeker"]
            safe_send_message(
                bot, user_id,
                f"🆔 {bukmeker} ID raqamingizni kiriting:\n\n"
                "💡 Misol: 123456789",
                reply_markup=get_back_keyboard(),
            )
            return

        amount_text = (message.text or "").strip()
        is_valid, amount = validate_amount(amount_text, MIN_DEPOSIT, MAX_DEPOSIT)
        if not is_valid:
            safe_send_message(
                bot, user_id,
                "❌ Noto'g'ri summa!\n\n"
                f"💡 Minimal: {MIN_DEPOSIT:,} so'm\n"
                f"💡 Maksimal: {MAX_DEPOSIT:,} so'm\n\n"
                "📝 Faqat raqam kiriting. Misol: 50000\n\n"
                "Qaytadan kiriting:",
            )
            return

        state = deposit_states[user_id]
        bukmeker = state["bukmeker"]
        player_id = state["player_id"]
        player_info = state.get("player_info", {"Success": True})

        opening_msg = safe_send_message(
            bot, user_id, "⏳ To'lov oynasi ochilmoqda..."
        )
        if not opening_msg:
            time.sleep(0.5)
            opening_msg = safe_send_message(
                bot, user_id, "⏳ To'lov oynasi ochilmoqda..."
            )

        process_deposit(
            bot, user_id, bukmeker, player_id, amount, player_info, opening_msg
        )
        clear_user_states(user_id)


def check_player(bukmeker: str, player_id: str) -> dict:
    """Player ID ni tegishli bukmeker API orqali tekshirish."""
    try:
        api_by_bookmaker = {
            "1xBet": xbet_api,
            "Melbet": melbet_api,
            "Betwiner": betwiner_api,
            "WinWinBet": winwin_api,
            "Mostbet": mostbet_api,
        }
        if bukmeker not in api_by_bookmaker:
            return {"Success": False, "error": "Noma'lum bukmeker"}

        api = api_by_bookmaker[bukmeker]
        if not api:
            return {
                "Success": False,
                "error": f"{bukmeker} API mavjud emas; ID tasdiqlanmadi",
            }

        result = api.find_player(player_id)
        if not isinstance(result, dict):
            return {"Success": False, "error": "API noto'g'ri javob qaytardi"}
        if not result.get("Success"):
            return {
                "Success": False,
                "error": result.get("error") or result.get("Error") or "API xatolik",
                "warning": result.get("warning"),
            }

        name = (
            result.get("Name")
            or result.get("name")
            or result.get("player_name")
        )
        normalized = dict(result)
        normalized["UserId"] = (
            normalized.get("UserId") or normalized.get("player_id") or player_id
        )
        if name:
            normalized["Name"] = name
            normalized["name"] = name
        return normalized

    except Exception:
        logger.exception("Bookmaker player lookup failed: %s", bukmeker)
        return {"Success": False, "error": "API bilan bog'lanishda xatolik"}


def process_deposit(
    bot: telebot.TeleBot, user_id: int, bukmeker: str,
    player_id: str, amount: float, player_info: dict, opening_msg=None
):
    """To'lov oynasini yaratish va to'lovni bazaga saqlash."""
    from utils.bot_helpers import safe_send_message

    try:
        random_addition = generate_random_amount()
        final_amount = amount + random_addition
        cards = db.get_active_cards()

        if not cards:
            safe_send_message(
                bot, user_id,
                "❌ Hozirda to'lov kartalari yangilanmoqda. Keyinroq urinib ko'ring.",
                reply_markup=get_main_menu_keyboard(),
            )
            return

        card = get_random_card(cards)
        payment_id = generate_payment_id()
        payment = Payment(
            user_id=user_id,
            bukmeker=bukmeker,
            player_id=player_id,
            amount=final_amount,
            payment_id=payment_id,
            card_last4=card.card_number[-4:],
        )

        if not db.add_payment(payment):
            safe_send_message(
                bot, user_id,
                "❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.",
                reply_markup=get_main_menu_keyboard(),
            )
            return

        payment_message = create_payment_message(
            bukmeker, player_id, card.card_number,
            final_amount, amount, payment_id, user_id,
        )

        if opening_msg:
            try:
                bot.delete_message(user_id, opening_msg.message_id)
            except Exception:
                pass

        sent_msg = safe_send_message(
            bot, user_id, payment_message,
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard(),
        )
        try:
            if sent_msg and hasattr(sent_msg, "chat") and hasattr(sent_msg, "message_id"):
                db.update_payment_message_ids(
                    payment_id, sent_msg.chat.id, sent_msg.message_id
                )
        except Exception:
            logger.exception("Could not save payment message IDs")

        # Muhim: karta to'lovi tasdiqlanmaguncha bookmaker API ga depozit yubormang.
        # Tasdiqlash admin/payment handler ichida amalga oshirilishi kerak.

    except Exception:
        logger.exception("Could not create deposit payment")
        safe_send_message(
            bot, user_id,
            "❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.",
            reply_markup=(
                get_admin_menu_keyboard()
                if user_id == getattr(config, "ADMIN_ID", None)
                else get_main_menu_keyboard()
            ),
        )


def get_balance(bukmeker: str, player_id: str = None) -> dict:
    """Bukmeker balansini olish."""
    try:
        api_by_bookmaker = {
            "1xBet": xbet_api,
            "Melbet": melbet_api,
            "Betwiner": betwiner_api,
            "WinWinBet": winwin_api,
            "Mostbet": mostbet_api,
        }
        api = api_by_bookmaker.get(bukmeker)
        if api:
            return api.get_balance()
        return {"Success": False, "Balance": 0, "Limit": 0}
    except Exception:
        logger.exception("Could not get bookmaker balance: %s", bukmeker)
        return {"Success": False, "Balance": 0, "Limit": 0}


def monitor_payment(
    bot: telebot.TeleBot, user_id: int, payment_id: str, bukmeker: str,
    player_id: str, final_amount: float, player_info: dict
):
    """
    Eski monitoring funksiyasi. Eslatma: uni avtomatik ishga tushirishdan oldin
    admin tasdig'i va bookmaker transaction-status tekshiruvi ulanishi kerak.
    """
    from utils.bot_helpers import safe_send_message

    try:
        time.sleep(300)
        payment = db.get_payment_by_id(payment_id)
        if not payment or payment.status != "pending":
            return

        result = execute_deposit_detailed(
            bukmeker, player_id, final_amount, player_info
        )
        status = str(result.get("status", "")).upper()

        # "NEW"/"PENDING" API so'rov qabul qilinganini anglatishi mumkin,
        # lekin pul hisobga tushganini tasdiqlamaydi.
        if result.get("Success") and status == "COMPLETED":
            db.update_payment_status(payment_id, "completed")
            safe_send_message(
                bot, user_id,
                create_success_message(bukmeker, player_id, final_amount),
                reply_markup=get_main_menu_keyboard(),
            )
        elif status in ("NEW", "PENDING", "PROCESSING", "IN_PROGRESS"):
            # Noaniq holatda failed/completed deb belgilamaymiz.
            safe_send_message(
                bot, user_id,
                "⏳ So'rov qabul qilindi, lekin depozit yakunlangani hali tasdiqlanmadi. "
                "Iltimos, hisobingizni tekshirmaguncha qayta to'lov yubormang.",
                reply_markup=get_main_menu_keyboard(),
            )
        else:
            db.update_payment_status(payment_id, "failed")
            safe_send_message(
                bot, user_id,
                "❌ Depozit API tomonidan tasdiqlanmadi. Admin bilan bog'laning; "
                "qayta yuborishdan oldin operatsiya holatini tekshirish kerak.",
                reply_markup=get_main_menu_keyboard(),
            )
    except Exception:
        logger.exception("Payment monitor failed for %s", payment_id)


def execute_deposit(
    bukmeker: str, player_id: str, amount: float, player_info: dict
) -> bool:
    """
    Faqat yakuniy COMPLETED holati True qaytaradi.
    API javobidagi Success=True ning o'zi pul hisobga tushganini anglatmasligi mumkin.
    """
    result = execute_deposit_detailed(bukmeker, player_id, amount, player_info)
    return bool(
        result.get("Success")
        and str(result.get("status", "")).upper() == "COMPLETED"
    )


def execute_deposit_detailed(
    bukmeker: str, player_id: str, amount: float, player_info: dict
) -> dict:
    """Admin uchun batafsil depozit natijasi."""
    try:
        if bukmeker == "1xBet":
            return xbet_api.deposit_add(player_id, amount) if xbet_api else {
                "Success": False, "Error": "1xBet API mavjud emas"
            }
        if bukmeker == "Melbet":
            return melbet_api.deposit_add(player_id, amount) if melbet_api else {
                "Success": False, "Error": "Melbet API mavjud emas"
            }
        if bukmeker == "Betwiner":
            return betwiner_api.deposit_add(player_id, amount) if betwiner_api else {
                "Success": False, "Error": "Betwiner API mavjud emas"
            }
        if bukmeker == "WinWinBet":
            return winwin_api.deposit_add(player_id, amount) if winwin_api else {
                "Success": False, "Error": "WinWinBet API mavjud emas"
            }
        if bukmeker == "Mostbet":
            if not mostbet_api:
                return {
                    "Success": False, "status": "ERROR",
                    "Error": "Mostbet API sozlanmagan",
                }

            # API docs asosidagi deposit_player metodi.
            # NEW/PENDING holatini completed deb ko'rsatmaymiz.
            result = mostbet_api.deposit_player(
                brand_id=1,
                player_id=str(player_id),
                amount=int(amount),
                currency="UZS",
            )
            if not isinstance(result, dict):
                return {
                    "Success": False, "status": "ERROR",
                    "Error": "Mostbet API noto'g'ri javob qaytardi",
                }

            result = dict(result)
            status = str(result.get("status") or result.get("Status") or "").upper()
            result["status"] = status or "UNKNOWN"
            result["Success"] = (
                bool(result.get("Success"))
                and result["status"] == "COMPLETED"
            )
            if result["status"] in ("NEW", "PENDING", "PROCESSING", "IN_PROGRESS"):
                result.setdefault(
                    "Error",
                    "So'rov qabul qilindi, ammo depozit yakunlangani hali tasdiqlanmagan",
                )
            return result

        return {"Success": False, "status": "ERROR", "Error": "Noma'lum bukmeker"}
    except Exception as exc:
        logger.exception("Deposit API failed: %s", bukmeker)
        return {"Success": False, "status": "ERROR", "Error": str(exc)}


def register_cancel_callback(bot: telebot.TeleBot):
    @bot.callback_query_handler(func=lambda call: call.data == "cancel_payment")
    def cancel_payment_callback(call):
        user_id = call.from_user.id
        clear_user_states(user_id)

        try:
            bot.edit_message_text(
                "To'lovni bekor qildingiz.\nQayta urinib ko'ring: /start",
                call.message.chat.id,
                call.message.message_id,
            )
        except Exception:
            pass

        try:
            bot.answer_callback_query(call.id, "To'lov bekor qilindi")
        except Exception:
            pass

        bot.send_message(
            user_id,
            "🏠 Asosiy menyu. Buyruqni tanlang:",
            reply_markup=get_main_menu_keyboard(),
        )
