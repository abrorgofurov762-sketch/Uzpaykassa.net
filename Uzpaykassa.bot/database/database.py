"""
Database boshqaruv tizimi - SQLite orqali barcha ma'lumotlarni boshqarish

Tables:
- users: Foydalanuvchilar
- payments: To'lovlar (depozitlar)
- withdrawals: Pul yechish arizalari
- cards: Karta ma'lumotlari

Features:
- Thread-safe operatsiyalar (threading.Lock)
- Auto-migration (ustunlar qo'shish)
- CRUD operatsiyalari barcha jadvallar uchun
"""

import sqlite3
import os
from typing import List, Optional
from datetime import datetime, timedelta
from .models import User, Payment, Withdrawal, Card
from config import DATABASE_PATH
import threading

class Database:
    """
    To'liq database boshqaruv tizimi
    
    Attributes:
        db_path: SQLite database fayl yo'li
        lock: Thread-safe operatsiyalar uchun Lock
        has_updated_at: payments jadvalida updated_at ustuni mavjudligi
        has_message_columns: payment message id ustunlari mavjudligi
    """
    
    def __init__(self):
        self.db_path = DATABASE_PATH
        self.lock = threading.Lock()
        # Keep a runtime flag whether the payments table contains updated_at column
        self.has_updated_at = False
        self.init_database()
    
    def init_database(self):
        """Database va jadvallarni yaratish"""
        # Support a mounted Render disk path such as /var/data/bot_database.db.
        parent = os.path.dirname(os.path.abspath(self.db_path))
        os.makedirs(parent, exist_ok=True)
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.execute("PRAGMA busy_timeout = 10000")
            cursor = conn.cursor()
            
            # Users jadvali
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    phone TEXT,
                    first_name TEXT,
                    is_admin BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Payments jadvali
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    bukmeker TEXT,
                    player_id TEXT,
                    amount REAL,
                    payment_id TEXT UNIQUE,
                    card_last4 TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    payment_chat_id INTEGER,
                    payment_message_id INTEGER,
                    deposit_amount REAL,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # Indexlar - tez qidiruv uchun
            try:
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_payments_card_amount ON payments(card_last4, amount, status)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_payments_created ON payments(created_at)')
            except Exception:
                pass
            cursor.execute("PRAGMA table_info(payments)")
            cols = [r[1] for r in cursor.fetchall()]
            # updated_at column
            if 'updated_at' in cols:
                self.has_updated_at = True
            else:
                try:
                    cursor.execute("ALTER TABLE payments ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                    conn.commit()
                    self.has_updated_at = True
                except Exception:
                    # If ALTER TABLE fails for any reason, set flag False; code will fallback at runtime
                    self.has_updated_at = False

            # ensure new message id columns exist in legacy DBs; try to add them if missing
            if 'payment_chat_id' in cols and 'payment_message_id' in cols:
                self.has_message_columns = True
            else:
                try:
                    cursor.execute("ALTER TABLE payments ADD COLUMN payment_chat_id INTEGER")
                    cursor.execute("ALTER TABLE payments ADD COLUMN payment_message_id INTEGER")
                    conn.commit()
                    self.has_message_columns = True
                except Exception:
                    # ignore if ALTER TABLE not supported on older DB file
                    self.has_message_columns = False

            # Keep the original bookmaker amount separate from the bank amount.
            cursor.execute("PRAGMA table_info(payments)")
            payment_cols = [r[1] for r in cursor.fetchall()]
            if 'deposit_amount' not in payment_cols:
                try:
                    cursor.execute("ALTER TABLE payments ADD COLUMN deposit_amount REAL")
                    conn.commit()
                except Exception:
                    pass
            
            # Withdrawals jadvali
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS withdrawals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    bukmeker TEXT,
                    player_id TEXT,
                    card_number TEXT,
                    code TEXT,
                    amount REAL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # Cards jadvali
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    card_number TEXT UNIQUE,
                    card_name TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
    
    # ==================== USER METHODS ====================
    
    def add_user(self, user: User) -> bool:
        """Foydalanuvchi qo'shish"""
        with self.lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO users 
                        (user_id, username, phone, first_name, is_admin)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (user.user_id, user.username, user.phone, 
                         user.first_name, user.is_admin))
                    conn.commit()
                    return True
            except Exception:
                return False
    
    def get_user(self, user_id: int) -> Optional[User]:
        """Foydalanuvchini olish"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
                row = cursor.fetchone()
                if row:
                    return User(row[0], row[1], row[2], row[3], row[4])
                return None
        except Exception:
            return None
    
    def update_user_phone(self, user_id: int, phone: str) -> bool:
        """Foydalanuvchi telefon raqamini yangilash"""
        with self.lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE users SET phone = ? WHERE user_id = ?
                    ''', (phone, user_id))
                    conn.commit()
                    return True
            except Exception:
                return False
    
    def get_all_users(self) -> List[User]:
        """Barcha foydalanuvchilarni olish"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM users')
                rows = cursor.fetchall()
                users = []
                for row in rows:
                    users.append(User(row[0], row[1], row[2], row[3], row[4]))
                return users
        except Exception:
            return []
    
    def get_users_count(self) -> int:
        """Foydalanuvchilar sonini olish"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM users')
                return cursor.fetchone()[0]
        except Exception:
            return 0
    
    # ==================== PAYMENT METHODS ====================
    
    def add_payment(self, payment: Payment) -> bool:
        """To'lov qo'shish"""
        with self.lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    # Insert depending on whether DB has message id columns (legacy DBs may not)
                    if getattr(self, 'has_message_columns', False):
                        cursor.execute('''
                            INSERT INTO payments 
                            (user_id, bukmeker, player_id, amount, payment_id, card_last4, status, payment_chat_id, payment_message_id, deposit_amount)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (payment.user_id, payment.bukmeker, payment.player_id,
                             payment.amount, payment.payment_id, payment.card_last4, 
                             payment.status, payment.payment_chat_id, payment.payment_message_id, payment.deposit_amount))
                    else:
                        cursor.execute('''
                            INSERT INTO payments 
                            (user_id, bukmeker, player_id, amount, payment_id, card_last4, status, deposit_amount)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (payment.user_id, payment.bukmeker, payment.player_id,
                             payment.amount, payment.payment_id, payment.card_last4, 
                             payment.status, payment.deposit_amount))
                    conn.commit()
                    return True
            except sqlite3.IntegrityError:
                return False
            except Exception:
                return False
    
    def get_payment_by_id(self, payment_id: str) -> Optional[Payment]:
        """Payment ID bo'yicha to'lovni olish"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM payments WHERE payment_id = ?', (payment_id,))
                row = cursor.fetchone()
                if row:
                    payment = Payment(row[1], row[2], row[3], row[4], row[5], row[6])
                    payment.status = row[7]
                    payment.created_at = row[8]
                    try:
                        payment.deposit_amount = row[12]
                    except Exception:
                        pass
                    # optional columns
                    try:
                        payment.updated_at = row[9]
                    except Exception:
                        pass
                    try:
                        payment.payment_chat_id = row[10]
                        payment.payment_message_id = row[11]
                    except Exception:
                        pass
                    return payment
                return None
        except Exception:
            return None
    
    def update_payment_status(self, payment_id: str, status: str) -> bool:
        """To'lov statusini yangilash; faqat ma'lum status qiymatlariga ruxsat."""
        allowed_statuses = {"pending", "processing", "paid", "paid_review", "completed", "failed", "expired"}
        if not payment_id or status not in allowed_statuses:
            return False
        with self.lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    # Use prepared SQL depending on whether updated_at exists
                    if getattr(self, 'has_updated_at', False):
                        try:
                            cursor.execute('''
                                UPDATE payments 
                                SET status = ?, updated_at = CURRENT_TIMESTAMP 
                                WHERE payment_id = ?
                            ''', (status, payment_id))
                        except sqlite3.OperationalError as e:
                            # In case the column was removed/absent unexpectedly, fallback and update flag
                            if 'no such column' in str(e):
                                self.has_updated_at = False
                                cursor.execute('''
                                    UPDATE payments 
                                    SET status = ? 
                                    WHERE payment_id = ?
                                ''', (status, payment_id))
                            else:
                                raise
                    else:
                        cursor.execute('''
                            UPDATE payments 
                            SET status = ? 
                            WHERE payment_id = ?
                        ''', (status, payment_id))
                    changed = cursor.rowcount
                    conn.commit()
                    return changed > 0
            except Exception:
                return False

    def transition_payment_status(self, payment_id: str, expected_status: str, new_status: str) -> bool:
        """Atomically change a payment status only if it is still in expected_status.

        This prevents duplicate bank-notification messages or concurrent workers from
        processing the same pending payment more than once.
        """
        allowed = {"pending", "processing", "paid", "paid_review", "completed", "failed", "expired"}
        if not payment_id or expected_status not in allowed or new_status not in allowed:
            return False
        with self.lock:
            try:
                with sqlite3.connect(self.db_path, timeout=10) as conn:
                    cursor = conn.cursor()
                    if getattr(self, "has_updated_at", False):
                        cursor.execute(
                            "UPDATE payments SET status = ?, updated_at = CURRENT_TIMESTAMP "
                            "WHERE payment_id = ? AND status = ?",
                            (new_status, payment_id, expected_status),
                        )
                    else:
                        cursor.execute(
                            "UPDATE payments SET status = ? WHERE payment_id = ? AND status = ?",
                            (new_status, payment_id, expected_status),
                        )
                    conn.commit()
                    return cursor.rowcount == 1
            except Exception:
                return False

    def update_payment_message_ids(self, payment_id: str, chat_id: int, message_id: int) -> bool:
        """Save the chat_id and message_id of the payment message so we can edit/remove keyboard later."""
        with self.lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    try:
                        cursor.execute('''
                            UPDATE payments
                            SET payment_chat_id = ?, payment_message_id = ?
                            WHERE payment_id = ?
                        ''', (chat_id, message_id, payment_id))
                    except sqlite3.OperationalError:
                        # If DB doesn't have columns, ignore
                        return False
                    conn.commit()
                    return True
            except Exception:
                return False
    
    def get_recent_pending_payments(self, since_time: datetime) -> List[Payment]:
        """5 daqiqa ichidagi pending to'lovlarni olish"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                time_str = since_time.strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute('''
                    SELECT * FROM payments 
                    WHERE status = 'pending' 
                    AND datetime(created_at) >= datetime(?) 
                    ORDER BY created_at DESC
                ''', (time_str,))
                
                rows = cursor.fetchall()
                payments = []
                
                for row in rows:
                    payment = Payment(row[1], row[2], row[3], row[4], row[5], row[6])
                    payment.status = row[7]
                    payment.created_at = row[8]
                    try:
                        payment.deposit_amount = row[12]
                    except Exception:
                        pass
                    try:
                        payment.updated_at = row[9]
                    except Exception:
                        pass
                    try:
                        payment.payment_chat_id = row[10]
                        payment.payment_message_id = row[11]
                    except Exception:
                        pass
                    payments.append(payment)
                
                return payments
                
        except Exception:
            return []
    
    def expire_old_pending_payments(self, before_time: datetime) -> int:
        """5 daqiqadan oshgan pending to'lovlarni expired qilish"""
        with self.lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    time_str = before_time.strftime('%Y-%m-%d %H:%M:%S')
                    if getattr(self, 'has_updated_at', False):
                        try:
                            cursor.execute('''
                                UPDATE payments 
                                SET status = 'expired', updated_at = CURRENT_TIMESTAMP 
                                WHERE status = 'pending' 
                                AND datetime(created_at) < datetime(?)
                            ''', (time_str,))
                        except sqlite3.OperationalError as e:
                            if 'no such column' in str(e):
                                self.has_updated_at = False
                                cursor.execute('''
                                    UPDATE payments 
                                    SET status = 'expired' 
                                    WHERE status = 'pending' 
                                    AND datetime(created_at) < datetime(?)
                                ''', (time_str,))
                            else:
                                raise
                    else:
                        cursor.execute('''
                            UPDATE payments 
                            SET status = 'expired' 
                            WHERE status = 'pending' 
                            AND datetime(created_at) < datetime(?)
                        ''', (time_str,))
                    
                    expired_count = cursor.rowcount
                    conn.commit()
                    
                    return expired_count
                    
            except Exception:
                return 0
    
    def count_payments_by_status(self, status: str) -> int:
        """Status bo'yicha to'lovlarni sanash"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT COUNT(*) FROM payments WHERE status = ?
                ''', (status,))
                return cursor.fetchone()[0]
        except Exception:
            return 0

    def get_pending_payments(self) -> List[Payment]:
        """Barcha pending holatidagi to'lovlarni olish"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM payments WHERE status = "pending" ORDER BY created_at DESC')
                rows = cursor.fetchall()
                payments = []

                for row in rows:
                    payment = Payment(row[1], row[2], row[3], row[4], row[5], row[6])
                    payment.status = row[7]
                    payment.created_at = row[8]
                    try:
                        payment.deposit_amount = row[12]
                    except Exception:
                        pass
                    try:
                        payment.updated_at = row[9]
                    except Exception:
                        pass
                    try:
                        payment.payment_chat_id = row[10]
                        payment.payment_message_id = row[11]
                    except Exception:
                        pass
                    payments.append(payment)

                return payments
        except Exception:
            return []

    def get_pending_payments_by_card_and_amount(self, card_last4: str, amount: float, tolerance: float = 5.0) -> List[Payment]:
        """Fast query: return pending payments that match last4 and amount within tolerance."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Use ABS(amount - ?) <= ? to match nearby amounts (SQLite supports ABS)
                cursor.execute('''
                    SELECT * FROM payments
                    WHERE status = 'pending' AND card_last4 = ? AND ABS(amount - ?) <= ?
                    ORDER BY created_at DESC
                    LIMIT 10
                ''', (card_last4, amount, tolerance))
                rows = cursor.fetchall()
                payments = []
                for row in rows:
                    payment = Payment(row[1], row[2], row[3], row[4], row[5], row[6])
                    payment.status = row[7]
                    payment.created_at = row[8]
                    try:
                        payment.deposit_amount = row[12]
                    except Exception:
                        pass
                    try:
                        payment.updated_at = row[9]
                    except Exception:
                        pass
                    try:
                        payment.payment_chat_id = row[10]
                        payment.payment_message_id = row[11]
                    except Exception:
                        pass
                    payments.append(payment)
                return payments
        except Exception:
            return []
    
    def get_user_payments(self, user_id: int, limit: int = 10) -> List[Payment]:
        """Foydalanuvchi to'lovlarini olish"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM payments 
                    WHERE user_id = ? 
                    ORDER BY created_at DESC 
                    LIMIT ?
                ''', (user_id, limit))
                
                rows = cursor.fetchall()
                payments = []
                
                for row in rows:
                    payment = Payment(row[1], row[2], row[3], row[4], row[5], row[6])
                    payment.status = row[7]
                    payment.created_at = row[8]
                    try:
                        payment.deposit_amount = row[12]
                    except Exception:
                        pass
                    try:
                        payment.updated_at = row[9]
                    except Exception:
                        pass
                    try:
                        payment.payment_chat_id = row[10]
                        payment.payment_message_id = row[11]
                    except Exception:
                        pass
                    payments.append(payment)
                
                return payments
                
        except Exception:
            return []

    def get_payments_by_player_id(self, bukmeker: str, player_id: str, limit: int = 10) -> List[Payment]:
        """Return recent payments that match bukmeker and player_id."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM payments 
                    WHERE bukmeker = ? AND player_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                ''', (bukmeker, player_id, limit))
                rows = cursor.fetchall()
                payments = []
                for row in rows:
                    payment = Payment(row[1], row[2], row[3], row[4], row[5], row[6])
                    payment.status = row[7]
                    payment.created_at = row[8]
                    try:
                        payment.deposit_amount = row[12]
                    except Exception:
                        pass
                    try:
                        payment.updated_at = row[9]
                    except Exception:
                        pass
                    try:
                        payment.payment_chat_id = row[10]
                        payment.payment_message_id = row[11]
                    except Exception:
                        pass
                    payments.append(payment)
                return payments
        except Exception:
            return []
    
    def get_today_payments_sum(self) -> float:
        """Bugungi to'lovlar yig'indisi"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT SUM(amount) FROM payments 
                    WHERE DATE(created_at) = DATE('now') 
                    AND status = 'completed'
                ''')
                
                result = cursor.fetchone()[0]
                return result if result else 0.0
                
        except Exception:
            return 0.0
    
    # ==================== WITHDRAWAL METHODS ====================
    
    def add_withdrawal(self, withdrawal: Withdrawal) -> bool:
        """Pul yechish so'rovini qo'shish"""
        with self.lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO withdrawals 
                        (user_id, bukmeker, player_id, card_number, code, amount, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (withdrawal.user_id, withdrawal.bukmeker, withdrawal.player_id,
                         withdrawal.card_number, withdrawal.code, withdrawal.amount, 
                         withdrawal.status))
                    conn.commit()
                    return cursor.lastrowid
            except Exception:
                return False
    
    def get_pending_withdrawals(self) -> List[Withdrawal]:
        """Pending yechishlarni olish"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM withdrawals WHERE status = "pending"')
                rows = cursor.fetchall()
                withdrawals = []
                
                for row in rows:
                    withdrawal = Withdrawal(row[1], row[2], row[3], row[4], row[5])
                    # row layout: (id, user_id, bukmeker, player_id, card_number, code, amount, status)
                    withdrawal.amount = row[6]
                    withdrawal.status = row[7]
                    withdrawal.id = row[0]
                    withdrawals.append(withdrawal)
                
                return withdrawals
        except Exception:
            return []

    def get_withdrawal_by_id(self, withdrawal_id: int) -> Optional[Withdrawal]:
        """Return a Withdrawal object by id or None if not found."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM withdrawals WHERE id = ?', (int(withdrawal_id),))
                row = cursor.fetchone()
                if not row:
                    return None

                # row layout: (id, user_id, bukmeker, player_id, card_number, code, amount, status, created_at)
                withdrawal = Withdrawal(row[1], row[2], row[3], row[4], row[5])
                withdrawal.amount = row[6]
                withdrawal.status = row[7]
                try:
                    withdrawal.created_at = row[8]
                except Exception:
                    pass
                withdrawal.id = row[0]
                return withdrawal
        except Exception:
            return None
    
    def get_user_withdrawals(self, user_id: int, limit: int = 10) -> List[Withdrawal]:
        """Return a user's recent withdrawal requests, newest first.

        Sensitive fields (full card number and verification code) are loaded for
        internal model compatibility but must never be shown in user-facing history.
        """
        try:
            safe_limit = max(1, min(int(limit), 50))
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM withdrawals WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
                    (int(user_id), safe_limit),
                )
                rows = cursor.fetchall()
                withdrawals = []
                for row in rows:
                    withdrawal = Withdrawal(row[1], row[2], row[3], row[4], row[5])
                    withdrawal.amount = row[6]
                    withdrawal.status = row[7]
                    try:
                        withdrawal.created_at = row[8]
                    except (IndexError, TypeError):
                        pass
                    withdrawal.id = row[0]
                    withdrawals.append(withdrawal)
                return withdrawals
        except Exception:
            return []

    def update_withdrawal_status(
        self, withdrawal_id: int, status: str, expected_status: Optional[str] = None
    ) -> bool:
        """Update withdrawal status; optionally require a specific current status.

        The conditional form is used for one-time admin confirmations so a repeated
        callback cannot complete and notify the same withdrawal twice.
        """
        allowed = {"pending", "approved", "completed", "failed"}
        allowed_transitions = {
            "pending": {"approved", "completed", "failed"},
            "approved": {"completed", "failed"},
            "completed": set(),
            "failed": set(),
        }
        if status not in allowed or (expected_status is not None and expected_status not in allowed):
            return False
        if expected_status is not None and status not in allowed_transitions[expected_status]:
            return False
        with self.lock:
            try:
                with sqlite3.connect(self.db_path, timeout=10) as conn:
                    cursor = conn.cursor()
                    if expected_status is None:
                        # Avoid moving terminal states backwards when callers omit expected_status.
                        valid_sources = [src for src, targets in allowed_transitions.items() if status in targets]
                        if not valid_sources:
                            return False
                        placeholders = ",".join("?" for _ in valid_sources)
                        cursor.execute(
                            f"UPDATE withdrawals SET status = ? WHERE id = ? AND status IN ({placeholders})",
                            (status, int(withdrawal_id), *valid_sources),
                        )
                    else:
                        cursor.execute(
                            "UPDATE withdrawals SET status = ? WHERE id = ? AND status = ?",
                            (status, int(withdrawal_id), expected_status),
                        )
                    conn.commit()
                    return cursor.rowcount == 1
            except Exception:
                return False
    
    # ==================== CARD METHODS ====================
    
    def add_card(self, card: Card) -> bool:
        """Karta qo'shish"""
        with self.lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO cards (card_number, card_name, is_active)
                        VALUES (?, ?, ?)
                    ''', (card.card_number, card.card_name, card.is_active))
                    conn.commit()
                    return True
            except sqlite3.IntegrityError:
                return False
            except Exception:
                return False
    
    def get_active_cards(self) -> List[Card]:
        """Aktiv kartalarni olish"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM cards WHERE is_active = TRUE')
                rows = cursor.fetchall()
                cards = []
                
                for row in rows:
                    card = Card(row[1], row[2])
                    # row layout: (id, card_number, card_name, is_active)
                    card.is_active = bool(row[3])
                    card.id = row[0]
                    cards.append(card)
                
                return cards
        except Exception:
            return []
    
    def get_all_cards(self) -> List[Card]:
        """Barcha kartalarni olish"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM cards')
                rows = cursor.fetchall()
                cards = []
                
                for row in rows:
                    card = Card(row[1], row[2])
                    # row layout: (id, card_number, card_name, is_active)
                    card.is_active = bool(row[3])
                    card.id = row[0]
                    cards.append(card)
                
                return cards
        except Exception:
            return []
    
    def delete_card(self, card_number: str) -> bool:
        """Kartani o'chirish"""
        with self.lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('DELETE FROM cards WHERE card_number = ?', (card_number,))
                    conn.commit()
                    return True
            except Exception:
                return False
    
    def toggle_card_status(self, card_number: str) -> bool:
        """Karta statusini o'zgartirish"""
        with self.lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE cards 
                        SET is_active = NOT is_active 
                        WHERE card_number = ?
                    ''', (card_number,))
                    conn.commit()
                    return True
            except Exception:
                return False

# Global database instance
db = Database()

