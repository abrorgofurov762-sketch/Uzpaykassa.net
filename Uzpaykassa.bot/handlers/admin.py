"""
Admin handlers for Uzpaykassa.net (pyTelegramBotAPI / telebot).

Important:
- This file keeps the database/API interfaces used by the existing project.
- Verify it together with database/database.py, database/models.py, utils/* and api/* before deployment.
- Admin workflow state is in memory; restart-safe payment processing requires DB-backed operation records.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, Thread

import telebot
from telebot.types import Message, CallbackQuery

from database.database import db
from database.models import Card
from utils.keyboards import (
    get_admin_menu_keyboard,
    get_main_menu_keyboard_admin,
    get_card_management_keyboard,
    get_balance_keyboard,
    get_back_keyboard,
    get_bookmakers_keyboard,
    get_admin_manual_deposit_confirm_keyboard,
)
from utils.helpers import create_balance_message, create_stats_message, log_manual_deposit
from utils.bot_helpers import safe_send_message
from utils.validators import validate_card_number, validate_amount, validate_player_id
from api.xbet_api import xbet_api
from api.mostbet_api import mostbet_api
from api.mobcash_api import melbet_api, betwiner_api, winwin_api
from handlers.deposit import execute_deposit_detailed, check_player
from config import ADMIN_ID
import config

logger = logging.getLogger(__name__)

# In-memory conversation state. It is cleared on restart; never use it as the
# only record of a financially important operation.
admin_states = {}
_state_lock = Lock()
_balance_lock = Lock()
_deposit_lock = Lock()
_deposit_in_progress = set()

MENU_BUTTONS = {
    "👨‍💼 Admin panel",
    "👤 Foydalanuvchi menyu",
    "✋ Qo'lda to'ldirish",
    "📊 Statistika",
    "📢 Xabar yuborish",
    "🔧 Bot o'chirish/yoqish",
    "💳 Karta qo'shish",
    "💰 Kassa balansi",
    "🔄 Yangilash",
    "➕ Karta qo'shish",
    "📋 Kartalar ro'yxati",
    "❌ Karta o'chirish",
    "🔙 Orqaga",
}

BOOKMAKERS = {
    "🎯 1xBet": "1xBet",
    "🎲 Melbet": "Melbet",
    "🎪 Betwiner": "Betwiner",
    "🎨 WinWinBet": "WinWinBet",
    "🎰 Mostbet": "Mostbet",
    "1xBet": "1xBet",
    "Melbet": "Melbet",
    "Betwiner": "Betwiner",
    "WinWinBet": "WinWinBet",
    "Mostbet": "Mostbet",
}


def _is_admin(user_id):
    return bool(user_id and int(user_id) == int(ADMIN_ID))


def _set_state(state):
    with _state_lock:
        admin_states[ADMIN_ID] = state


def _get_state():
    with _state_lock:
        state = admin_states.get(ADMIN_ID)
        return dict(state) if state else None


def _update_state(**kwargs):
    with _state_lock:
        if ADMIN_ID in admin_states:
            admin_states[ADMIN_ID].update(kwargs)


def _clear_state():
    with _state_lock:
        admin_states.pop(ADMIN_ID, None)


def _send(bot, chat_id, text, **kwargs):
    """Use the project's safe wrapper when possible, with a logged fallback."""
    try:
        result = safe_send_message(bot, chat_id, text, **kwargs)
        return result
    except Exception:
        logger.exception("Failed to send message to chat_id=%s", chat_id)
        try:
            return bot.send_message(chat_id, text, **kwargs)
        except Exception:
            logger.exception("Fallback send_message failed for chat_id=%s", chat_id)
            return None


def _provider_functions():
    """Single source of truth for all provider balance queries."""
    return {
        "1xBet": lambda: xbet_api.get_balance() if xbet_api else {
            "Success": False, "Error": "API mavjud emas"
        },
        "Melbet": lambda: melbet_api.get_balance() if melbet_api else {
            "Success": False, "Error": "API mavjud emas"
        },
        "Betwiner": lambda: betwiner_api.get_balance() if betwiner_api else {
            "Success": False, "Error": "API mavjud emas"
        },
        "WinWinBet": lambda: winwin_api.get_balance() if winwin_api else {
            "Success": False, "Error": "API mavjud emas"
        },
        "Mostbet": lambda: mostbet_api.get_balance() if mostbet_api else {
            "Success": False, "Error": "API mavjud emas"
        },
    }


def _fetch_balances(timeout=12):
    """Fetch provider balances concurrently. API clients must also have HTTP timeouts."""
    providers = _provider_functions()
    results = {}
    executor = ThreadPoolExecutor(max_workers=min(5, len(providers)))
    futures = {executor.submit(fn): name for name, fn in providers.items()}
    try:
        for future in as_completed(futures, timeout=timeout):
            name = futures[future]
            try:
                result = future.result()
                results[name] = result if isinstance(result, dict) else {
                    "Success": False, "Error": "API noto'g'ri javob qaytardi"
                }
            except Exception:
                logger.exception("Balance request failed: %s", name)
                results[name] = {"Success": False, "Error": "Server javob bermadi"}
    except TimeoutError:
        pass
    except Exception:
        logger.exception("Unexpected error while fetching balances")
    finally:
        for future, name in futures.items():
            if name not in results:
                future.cancel()
                results[name] = {"Success": False, "Error": "Vaqt tugadi"}
        # Do not wait for a hung provider call here. HTTP timeouts still need to
        # be configured inside each API client.
        executor.shutdown(wait=False, cancel_futures=True)
    return results


def _send_balances(bot, loading_message_id=None):
    try:
        balances = _fetch_balances()
        rendered = create_balance_message(balances)
        with _balance_lock:
            register_admin_handlers._last_balances = rendered
            register_admin_handlers._last_balances_ts = time.time()
        _send(bot, ADMIN_ID, rendered, reply_markup=get_balance_keyboard())
    except Exception:
        logger.exception("Could not build/send balance report")
        _send(bot, ADMIN_ID, "❌ Балансларни олишда хатолик юз берди.")
    finally:
        if loading_message_id:
            try:
                bot.delete_message(ADMIN_ID, loading_message_id)
            except Exception:
                logger.debug("Could not delete balance loading message", exc_info=True)


def register_admin_handlers(bot: telebot.TeleBot):
    """Register all admin handlers. Call this once during bot startup."""

    @bot.message_handler(
        func=lambda m: _is_admin(getattr(getattr(m, "from_user", None), "id", None))
        and m.text == "👨‍💼 Admin panel",
        content_types=["text"],
    )
    def admin_panel(message: Message):
        _clear_state()
        _send(bot, message.chat.id, "👨‍💼 Admin panel:", reply_markup=get_admin_menu_keyboard())

    @bot.message_handler(
        func=lambda m: _is_admin(getattr(getattr(m, "from_user", None), "id", None))
        and m.text == "👤 Foydalanuvchi menyu",
        content_types=["text"],
    )
    def user_menu(message: Message):
        _clear_state()
        _send(bot, message.chat.id, "👤 Foydalanuvchi menyusi:",
              reply_markup=get_main_menu_keyboard_admin())

    @bot.message_handler(
        func=lambda m: _is_admin(getattr(getattr(m, "from_user", None), "id", None))
        and m.text == "✋ Qo'lda to'ldirish",
        content_types=["text"],
    )
    def manual_deposit_start(message: Message):
        _set_state({"action": "manual_deposit", "step": "bukmeker"})
        _send(bot, message.chat.id, "Bukmekerlardan birini tanlang:",
              reply_markup=get_bookmakers_keyboard())

    @bot.message_handler(
        func=lambda m: _is_admin(getattr(getattr(m, "from_user", None), "id", None))
        and m.text == "📊 Statistika",
        content_types=["text"],
    )
    def show_stats(message: Message):
        try:
            users_count = db.get_users_count()
            # The existing helper's other arguments are kept compatible.
            # Replace zeros only after the database exposes real daily metrics.
            text = create_stats_message(users_count, 0, 0)
            _send(bot, message.chat.id, text)
        except Exception:
            logger.exception("Failed to load admin statistics")
            _send(bot, message.chat.id, "❌ Статистикани олишда хатолик юз берди.")

    @bot.message_handler(
        func=lambda m: _is_admin(getattr(getattr(m, "from_user", None), "id", None))
        and m.text == "📢 Xabar yuborish",
        content_types=["text"],
    )
    def broadcast_start(message: Message):
        _set_state({"action": "broadcast"})
        _send(bot, message.chat.id,
              "📢 Барча фойдаланувчиларга юбориладиган матн, расм ёки видеони юборинг.",
              reply_markup=get_back_keyboard())

    @bot.message_handler(
        func=lambda m: _is_admin(getattr(getattr(m, "from_user", None), "id", None))
        and m.text == "🔧 Bot o'chirish/yoqish",
        content_types=["text"],
    )
    def toggle_bot(message: Message):
        try:
            config.BOT_ACTIVE = not bool(getattr(config, "BOT_ACTIVE", True))
            status = "✅ ёқилди" if config.BOT_ACTIVE else "❌ ўчирилди"
            _send(bot, message.chat.id, f"🔧 Бот {status}")
        except Exception:
            logger.exception("Failed to toggle bot status")
            _send(bot, message.chat.id, "❌ Бот ҳолатини ўзгартириб бўлмади.")

    @bot.message_handler(
        func=lambda m: _is_admin(getattr(getattr(m, "from_user", None), "id", None))
        and m.text == "💳 Karta qo'shish",
        content_types=["text"],
    )
    def card_management(message: Message):
        _clear_state()
        _send(bot, message.chat.id, "💳 Карта бошқаруви:",
              reply_markup=get_card_management_keyboard())

    @bot.message_handler(
        func=lambda m: _is_admin(getattr(getattr(m, "from_user", None), "id", None))
        and m.text == "💰 Kassa balansi",
        content_types=["text"],
    )
    def show_balance(message: Message):
        ttl = max(0, int(getattr(config, "BALANCE_CACHE_SECONDS", 5)))
        with _balance_lock:
            cached = getattr(register_admin_handlers, "_last_balances", None)
            cached_at = getattr(register_admin_handlers, "_last_balances_ts", 0)
        if cached and time.time() - cached_at < ttl:
            _send(bot, message.chat.id, cached, reply_markup=get_balance_keyboard())
            return
        loading = bot.send_message(
            message.chat.id, "🔄 Баланслар олинмоқда, илтимос кутинг...",
            reply_markup=get_balance_keyboard()
        )
        Thread(target=_send_balances, args=(bot, loading.message_id), daemon=True).start()

    @bot.message_handler(
        func=lambda m: _is_admin(getattr(getattr(m, "from_user", None), "id", None))
        and m.text == "🔄 Yangilash",
        content_types=["text"],
    )
    def refresh_balance(message: Message):
        with _balance_lock:
            register_admin_handlers._last_balances_ts = 0
        try:
            loading = bot.send_message(
                message.chat.id, "🔄 Баланс янгиланмоқда...",
                reply_markup=get_balance_keyboard()
            )
            Thread(target=_send_balances, args=(bot, loading.message_id), daemon=True).start()
        except Exception:
            logger.exception("Failed to start balance refresh")
            _send(bot, message.chat.id, "❌ Балансни янгилашни бошлаб бўлмади.")

    @bot.message_handler(
        func=lambda m: _is_admin(getattr(getattr(m, "from_user", None), "id", None))
        and m.text == "➕ Karta qo'shish",
        content_types=["text"],
    )
    def add_card_start(message: Message):
        _set_state({"action": "add_card", "step": "card_number"})
        _send(bot, message.chat.id, "💳 Карта рақамини киритинг (16 та рақам):",
              reply_markup=get_back_keyboard())

    @bot.message_handler(
        func=lambda m: _is_admin(getattr(getattr(m, "from_user", None), "id", None))
        and m.text == "📋 Kartalar ro'yxati",
        content_types=["text"],
    )
    def list_cards(message: Message):
        try:
            cards = db.get_active_cards() or []
            if not cards:
                text = "❌ Актив карталар йўқ."
            else:
                text = "💳 Актив карталар:\n\n" + "\n".join(
                    f"{i}. ****{str(card.card_number)[-4:]}"
                    for i, card in enumerate(cards, 1)
                )
            _send(bot, message.chat.id, text)
        except Exception:
            logger.exception("Failed to list cards")
            _send(bot, message.chat.id, "❌ Карталар рўйхатини олишда хатолик.")

    @bot.message_handler(
        func=lambda m: _is_admin(getattr(getattr(m, "from_user", None), "id", None))
        and m.text == "❌ Karta o'chirish",
        content_types=["text"],
    )
    def delete_card_start(message: Message):
        try:
            cards = db.get_active_cards() or []
            if not cards:
                _send(bot, message.chat.id, "❌ Ўчириш учун актив карта йўқ.")
                return
            _set_state({"action": "delete_card"})
            # Do not display complete card numbers in chat.
            text = "❌ Ўчириш учун картанинг 16 хонали рақамини киритинг:\n\n"
            text += "\n".join(
                f"{i}. ****{str(card.card_number)[-4:]}"
                for i, card in enumerate(cards, 1)
            )
            _send(bot, message.chat.id, text, reply_markup=get_back_keyboard())
        except Exception:
            logger.exception("Failed to start card deletion")
            _send(bot, message.chat.id, "❌ Карталарни олишда хатолик.")

    # Text state handler is registered after the explicit menu handlers above.
    @bot.message_handler(
        func=lambda m: _is_admin(getattr(getattr(m, "from_user", None), "id", None))
        and bool(_get_state()),
        content_types=["text"],
    )
    def handle_admin_state_text(message: Message):
        text = (message.text or "").strip()
        state = _get_state()
        if not state:
            return

        if text == "🔙 Orqaga":
            _clear_state()
            _send(bot, message.chat.id, "👨‍💼 Admin panel:",
                  reply_markup=get_admin_menu_keyboard())
            return

        # Explicit menu handlers above should take precedence; this fallback
        # avoids interpreting menu labels as card numbers/broadcast content.
        if text in MENU_BUTTONS:
            _clear_state()
            _send(bot, message.chat.id, "Амали бекор қилинди.",
                  reply_markup=get_admin_menu_keyboard())
            return

        action = state.get("action")
        if action == "manual_deposit":
            handle_manual_deposit(bot, message)
        elif action == "add_card":
            handle_add_card(bot, message)
        elif action == "delete_card":
            handle_delete_card(bot, message)
        elif action == "broadcast":
            handle_broadcast(bot, message)
        else:
            _clear_state()
            _send(bot, message.chat.id, "❌ Ҳолат яроқсиз. Қайтадан бошланг.",
                  reply_markup=get_admin_menu_keyboard())

    @bot.message_handler(
        func=lambda m: _is_admin(getattr(getattr(m, "from_user", None), "id", None))
        and bool(_get_state()),
        content_types=["photo", "video", "document", "animation"],
    )
    def handle_admin_state_media(message: Message):
        state = _get_state()
        if state and state.get("action") == "broadcast":
            handle_broadcast(bot, message)
        else:
            _send(bot, message.chat.id, "❌ Бу босқичда фақат матн қабул қилинади.")

    @bot.callback_query_handler(
        func=lambda call: call.data in {"admin_md_confirm", "admin_md_cancel"}
    )
    def admin_manual_deposit_callback(call: CallbackQuery):
        if not call.from_user or not _is_admin(call.from_user.id):
            try:
                bot.answer_callback_query(call.id, "Сизда рухсат йўқ", show_alert=True)
            except Exception:
                logger.debug("Could not answer unauthorized callback", exc_info=True)
            return

        state = _get_state()
        if not state or state.get("action") != "manual_deposit" or state.get("step") != "confirm":
            try:
                bot.answer_callback_query(call.id, "Операция ҳолати топилмади.", show_alert=True)
            except Exception:
                pass
            return

        if call.data == "admin_md_cancel":
            try:
                if call.message:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
            except Exception:
                logger.debug("Could not delete cancelled deposit prompt", exc_info=True)
            _clear_state()
            try:
                bot.answer_callback_query(call.id, "Бекор қилинди")
            except Exception:
                pass
            _send(bot, ADMIN_ID, "❌ Операция бекор қилинди.",
                  reply_markup=get_admin_menu_keyboard())
            return

        # Prevent two quick clicks in this process. Durable idempotency must
        # still be implemented in the provider/database layer.
        with _deposit_lock:
            if ADMIN_ID in _deposit_in_progress:
                try:
                    bot.answer_callback_query(call.id, "Операция аллақачон бажарилмоқда.")
                except Exception:
                    pass
                return
            _deposit_in_progress.add(ADMIN_ID)

        try:
            bot.answer_callback_query(call.id, "⏳ Операция бошланди...")
        except Exception:
            pass

        def run_deposit():
            try:
                # Re-read state before execution.
                current = _get_state()
                if not current or current.get("step") != "confirm":
                    _send(bot, ADMIN_ID, "❌ Операция ҳолати ўзгарган. Қайта текширинг.")
                    return

                bookmaker = current.get("bukmeker")
                player_id = current.get("player_id")
                amount = current.get("amount")
                player_info = current.get("player_info") or {}
                if not bookmaker or not player_id or not amount:
                    _send(bot, ADMIN_ID, "❌ Операция маълумотлари тўлиқ эмас.")
                    return

                try:
                    result = execute_deposit_detailed(
                        bookmaker, player_id, amount, player_info
                    )
                    if not isinstance(result, dict):
                        result = {"Success": False, "Error": "API жавоби нотўғри"}
                except Exception as exc:
                    logger.exception("Manual deposit API call failed")
                    result = {"Success": False, "Error": str(exc)}

                try:
                    log_manual_deposit({
                        "bukmeker": bookmaker,
                        "player_id": player_id,
                        "amount": amount,
                        "result": result,
                    })
                except Exception:
                    logger.exception("Could not write manual deposit log")

                status = str(result.get("status") or result.get("Status") or "").upper()
                success_flag = result.get("Success", result.get("success", False))
                succeeded = bool(success_flag) and status == "COMPLETED"

                try:
                    if call.message:
                        bot.delete_message(call.message.chat.id, call.message.message_id)
                except Exception:
                    logger.debug("Could not delete deposit confirmation prompt", exc_info=True)

                if succeeded:
                    balance = 0
                    limit = 0
                    try:
                        from handlers.deposit import get_balance
                        info = get_balance(bookmaker, player_id)
                        if isinstance(info, dict) and info.get("Success"):
                            balance = info.get("Balance", 0) or 0
                            limit = info.get("Limit", 0) or 0
                    except Exception:
                        logger.exception("Could not retrieve player balance after deposit")

                    player_name = player_info.get("Name") or player_info.get("name") or "—"
                    success_text = (
                        "✅ Операция муваффақиятли якунланди!\n\n"
                        f"Букмскер: {bookmaker}\n"
                        f"ID: {player_id}\n"
                        f"Фойдаланувчи: {player_name}\n"
                        f"Сумма: {amount:,.0f} сўм\n\n"
                        f"Баланс: {balance:,.0f} сўм\n"
                        f"Лимит: {limit:,.0f} сўм"
                    )
                    _send(bot, ADMIN_ID, success_text)
                    channel_id = getattr(config, "NOTIFICATION_CHANNEL_ID", None)
                    if channel_id:
                        _send(bot, channel_id, success_text + "\n\n(Қўлда тўлдирилди)")
                else:
                    error = (
                        result.get("Error") or result.get("error")
                        or result.get("Message") or result.get("message")
                        or "Номаълум хатолик"
                    )
                    _send(
                        bot, ADMIN_ID,
                        "❌ Операция муваффақиятли якунлангани тасдиқланмади.\n\n"
                        f"Букмскер: {bookmaker}\nID: {player_id}\n"
                        f"Сумма: {amount:,.0f} сўм\nСабаб: {error}\n\n"
                        "Агар провайдерда операция амалга ошган бўлиши мумкин бўлса, "
                        "қайта босишдан олдин провайдер журналини текширинг."
                    )
            finally:
                _clear_state()
                with _deposit_lock:
                    _deposit_in_progress.discard(ADMIN_ID)
                _send(bot, ADMIN_ID, "👨‍💼 Admin panel:",
                      reply_markup=get_admin_menu_keyboard())

        Thread(target=run_deposit, daemon=True).start()


def handle_manual_deposit(bot: telebot.TeleBot, message: Message):
    state = _get_state()
    if not state:
        return

    step = state.get("step")
    text = (message.text or "").strip()

    if text == "🔙 Orqaga":
        _clear_state()
        _send(bot, ADMIN_ID, "👨‍💼 Admin panel:",
              reply_markup=get_admin_menu_keyboard())
        return

    if step == "bukmeker":
        chosen = BOOKMAKERS.get(text)
        if not chosen:
            _send(bot, ADMIN_ID, "❌ Нотўғри танлов. Тугмалардан бирини танланг:",
                  reply_markup=get_bookmakers_keyboard())
            return
        _update_state(bukmeker=chosen, step="player_id")
        _send(bot, ADMIN_ID, f"🆔 {chosen} ID рақамини киритинг:",
              reply_markup=get_back_keyboard())

    elif step == "player_id":
        player_id = text
        if not validate_player_id(player_id):
            _send(bot, ADMIN_ID, "❌ ID формати нотўғри. Қайта киритинг:",
                  reply_markup=get_back_keyboard())
            return
        current = _get_state() or {}
        bookmaker = current.get("bukmeker")
        try:
            info = check_player(bookmaker, player_id)
        except Exception:
            logger.exception("Player lookup failed for bookmaker=%s", bookmaker)
            _send(bot, ADMIN_ID, "❌ ID текширишда сервер хатолиги. Қайта уриниб кўринг.")
            return
        if not isinstance(info, dict) or not info.get("Success"):
            error = (info or {}).get("Error") or (info or {}).get("Message") or "Фойдаланувчи топилмади"
            _send(bot, ADMIN_ID, f"❌ {bookmaker} да ID тасдиқланмади.\nСабаб: {error}\nҚайта киритинг:")
            return
        _update_state(player_id=player_id, player_info=info, step="amount")
        name = info.get("Name") or info.get("name") or ""
        _send(bot, ADMIN_ID, f"💰 Суммани киритинг (сўм){f' — {name}' if name else ''}:",
              reply_markup=get_back_keyboard())

    elif step == "amount":
        valid, amount = validate_amount(text, 1000, 50000000)
        if not valid:
            _send(bot, ADMIN_ID, "❌ Сумма нотўғри. 1 000 дан 50 000 000 сўмгача киритинг:")
            return
        current = _get_state() or {}
        info = current.get("player_info") or {}
        name = info.get("Name") or info.get("name") or "—"
        summary = (
            "📦 Тўлдириш маълумотлари:\n\n"
            f"🏷 Букмскер: {current.get('bukmeker')}\n"
            f"🆔 ID: {current.get('player_id')}\n"
            f"👤 Фойдаланувчи: {name}\n"
            f"💰 Сумма: {amount:,.0f} сўм\n\n"
            "Давом этиш учун тасдиқланг ёки бекор қилинг."
        )
        _update_state(amount=amount, step="confirm")
        try:
            bot.send_message(
                ADMIN_ID, summary,
                reply_markup=get_admin_manual_deposit_confirm_keyboard()
            )
        except Exception:
            logger.exception("Could not send manual-deposit confirmation prompt")
            _clear_state()
            _send(bot, ADMIN_ID, "❌ Тасдиқлаш ойнасини юбориб бўлмади. Қайтадан бошланг.",
                  reply_markup=get_admin_menu_keyboard())

    elif step == "confirm":
        _send(bot, ADMIN_ID, "ℹ️ Тасдиқлаш ёки бекор қилиш учун пастдаги тугмалардан фойдаланинг.")


def handle_add_card(bot: telebot.TeleBot, message: Message):
    text = (message.text or "").strip()
    if text == "🔙 Orqaga":
        _clear_state()
        _send(bot, ADMIN_ID, "👨‍💼 Admin panel:",
              reply_markup=get_admin_menu_keyboard())
        return

    card_number = text.replace(" ", "").replace("-", "")
    if not validate_card_number(card_number):
        _send(bot, ADMIN_ID, "❌ Карта рақами нотўғри. 16 та рақам киритинг:",
              reply_markup=get_back_keyboard())
        return

    try:
        added = db.add_card(Card(card_number=card_number))
    except Exception:
        logger.exception("Could not add card")
        _send(bot, ADMIN_ID, "❌ Базада карта қўшишда хатолик юз берди.")
        return

    _clear_state()
    if added:
        _send(bot, ADMIN_ID, f"✅ Карта қўшилди: ****{card_number[-4:]}",
              reply_markup=get_admin_menu_keyboard())
    else:
        _send(bot, ADMIN_ID, "❌ Карта қўшилмади. У аввал қўшилган бўлиши мумкин.",
              reply_markup=get_admin_menu_keyboard())


def handle_delete_card(bot: telebot.TeleBot, message: Message):
    text = (message.text or "").strip()
    if text == "🔙 Orqaga":
        _clear_state()
        _send(bot, ADMIN_ID, "👨‍💼 Admin panel:",
              reply_markup=get_admin_menu_keyboard())
        return

    card_number = text.replace(" ", "").replace("-", "")
    if not validate_card_number(card_number):
        _send(bot, ADMIN_ID, "❌ Карта рақами нотўғри. Ўчириш учун тўлиқ 16 хонали рақамни киритинг:",
              reply_markup=get_back_keyboard())
        return

    try:
        deleted = db.delete_card(card_number)
    except Exception:
        logger.exception("Could not delete card")
        _send(bot, ADMIN_ID, "❌ Базада картани ўчиришда хатолик юз берди.")
        return

    _clear_state()
    if deleted:
        _send(bot, ADMIN_ID, f"✅ Карта ўчирилди: ****{card_number[-4:]}",
              reply_markup=get_admin_menu_keyboard())
    else:
        _send(bot, ADMIN_ID, "❌ Карта топилмади ёки аввал ўчирилган.",
              reply_markup=get_admin_menu_keyboard())


def handle_broadcast(bot: telebot.TeleBot, message: Message):
    """Send a text/photo/video/document/animation to all registered users."""
    if (message.text or "").strip() == "🔙 Orqaga":
        _clear_state()
        _send(bot, ADMIN_ID, "👨‍💼 Admin panel:",
              reply_markup=get_admin_menu_keyboard())
        return

    try:
        users = db.get_all_users() or []
    except Exception:
        logger.exception("Could not fetch users for broadcast")
        _clear_state()
        _send(bot, ADMIN_ID, "❌ Фойдаланувчилар рўйхатини олишда хатолик.")
        return

    if not users:
        _clear_state()
        _send(bot, ADMIN_ID, "❌ Фойдаланувчилар йўқ.",
              reply_markup=get_admin_menu_keyboard())
        return

    if not (message.text or message.photo or message.video or message.document or message.animation):
        _send(bot, ADMIN_ID, "❌ Матн, расм, видео, ҳужжат ёки GIF юборинг.")
        return

    status_msg = _send(bot, ADMIN_ID, f"📤 Хабар юборилмоқда: 0/{len(users)}")
    success = 0
    failed = 0

    for index, user in enumerate(users, start=1):
        user_id = getattr(user, "user_id", None)
        if not user_id:
            failed += 1
            continue
        try:
            if message.photo:
                bot.send_photo(user_id, message.photo[-1].file_id, caption=message.caption or "")
            elif message.video:
                bot.send_video(user_id, message.video.file_id, caption=message.caption or "")
            elif message.document:
                bot.send_document(user_id, message.document.file_id, caption=message.caption or "")
            elif message.animation:
                bot.send_animation(user_id, message.animation.file_id, caption=message.caption or "")
            else:
                bot.send_message(user_id, message.text)
            success += 1
        except Exception as exc:
            failed += 1
            # Avoid noisy logs for blocked/deleted accounts, but retain the reason.
            logger.info("Broadcast failed for user_id=%s: %s", user_id, exc)

        # Conservative delay helps reduce Telegram flood limits.
        time.sleep(0.04)
        if status_msg and (index % 10 == 0 or index == len(users)):
            try:
                bot.edit_message_text(
                    f"📤 Хабар юборилмоқда: {index}/{len(users)}\n"
                    f"✅ Юборилди: {success}\n❌ Хатолик: {failed}",
                    ADMIN_ID, status_msg.message_id
                )
            except Exception:
                logger.debug("Could not update broadcast progress", exc_info=True)

    _clear_state()
    _send(
        bot, ADMIN_ID,
        f"✅ Хабар юбориш тугади.\n\nЖами: {len(users)}\n"
        f"Муваффақиятли: {success}\nХатолик: {failed}",
        reply_markup=get_admin_menu_keyboard()
    )
