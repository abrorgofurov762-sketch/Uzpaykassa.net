"""
To'lov detektori - to'lov guruhidan kelgan xabarlarni aniqlash va qayta ishlash

To'lov formati: PAYMENT|summa|karta_oxirgi_4_raqam
Misol: PAYMENT|50000|8012

Funksiyalar:
- To'lov xabarini parse qilish
- Kutilayotgan to'lovlar bilan solishtirish
- To'lovni tasdiqlash va statusni yangilash
- Karta raqamini validatsiya va formatlash
"""

import re
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import config

class PaymentDetector:
    """
    To'lov guruhidan kelgan xabarlarni avtomatik aniqlash va qayta ishlash
    
    Attributes:
        db: Database manager instance
        PAYMENT_PATTERN: Regex pattern to'lov xabarini aniqlash uchun
    """
    
    # To'lov pattern - har qanday joyda paydo bo'lishi mumkin
    # Summa: raqamlar (vergul yoki nuqta bilan kasrli)
    # Karta: oxirgi 4 ta raqam
    # Eslatma: ba'zi xabarlar pipe belgisi (|) o'rniga boshqa unicode variantlardan foydalanishi mumkin,
    # shuning uchun parse jarayonida oldin normalizatsiya qilish va oxirgi 4 raqamni pipe'dan keyin matn ichidan izlash kerak.
    PAYMENT_PATTERN = r'PAYMENT\|\s*(\d+(?:[.,]\d+)?)\s*\|\s*(?:.*?(\d{4}))'
    PAYMENT_RE = re.compile(PAYMENT_PATTERN, re.IGNORECASE)
    
    def __init__(self, db_manager):
        """
        PaymentDetector ni initsializatsiya qilish
        
        Args:
            db_manager: Database manager instance
        """
        self.db = db_manager
    
    def parse_payment_message(self, message_text: str) -> Optional[Dict[str, Any]]:
        """
        To'lov xabarini parse qilish va ma'lumotlarni ajratish
        
        Args:
            message_text: Telegram guruhidan kelgan xabar matni
            
        Format: PAYMENT|summa|karta_oxirgi_4_raqam
        Misol: 
            - "PAYMENT|50000|8012" → {'amount': 50000.0, 'card_last4': '8012', ...}
            - "To'lov: PAYMENT|3613.50|8012" → {'amount': 3613.5, 'card_last4': '8012', ...}
            
        Returns:
            Dict yoki None:
            - {'amount': float, 'card_last4': str, 'raw_message': str}
            - None (agar format noto'g'ri bo'lsa)
        """
        try:
            # Normalize common unicode variants and non-breaking spaces
            raw = (message_text or '')
            raw = raw.replace('\u00A0', ' ')
            raw = raw.replace('\u00A6', '|')
            raw = raw.replace('\uFF5C', '|')
            raw = raw.replace('¦', '|')
            raw = raw.replace('｜', '|')
            raw = raw.replace('\u2016', '|')
            cleaned_text = raw.strip()

            # 1) Old style explicit PAYMENT|amount|last4
            match = self.PAYMENT_RE.search(cleaned_text)
            if match:
                amount_str = match.group(1).strip()
                # Treat comma as a thousands separator when exactly three digits
                # follow it (e.g. 50,000); otherwise treat it as a decimal mark.
                if ',' in amount_str and '.' not in amount_str:
                    left, right = amount_str.rsplit(',', 1)
                    amount_str = (left + right) if len(right) == 3 else (left + '.' + right)
                amount = float(amount_str)
                card_last4 = match.group(2)

                return {
                    'amount': amount,
                    'card_last4': card_last4,
                    'raw_message': message_text
                }

            # Agar PAYMENT token bor, lekin parse bo'lmasa, debug uchun konsolga yozamiz
            try:
                if 'PAYMENT' in cleaned_text.upper() and not match:
                    print(f"[payment_detector] PAYMENT token topildi, lekin regex parse bo'lmadi: {cleaned_text}")
            except Exception:
                pass

            # 2) More human-friendly formats, e.g. lines like:
            #    "Summa: 3,630 so'm" and "Karta: **** **** **** 8012"
            #    We try to extract both amount and last4 when possible.
            summa_re = re.compile(r"(?i)\b(?:summa|сумма)[:\s]*([\d\s\.,]+)")
            card_re = re.compile(r"(?i)\b(?:karta|kartasi|карта|карты|card|cardno|cardnr|№)[:\s\-]*[^\d]*(\d{4})\b")

            amount_match = summa_re.search(cleaned_text)
            card_match = card_re.search(cleaned_text)

            if amount_match and card_match:
                # Normalize amount: remove spaces and thousands separators
                raw_amount = amount_match.group(1)
                # Keep digits and dot; remove commas and spaces used as thousand separators
                amount_digits = re.sub(r"[\s,]", "", raw_amount)
                amount_digits = re.sub(r"[^\d.]", "", amount_digits)
                if not amount_digits:
                    return None
                amount = float(amount_digits)
                card_last4 = card_match.group(1)

                return {
                    'amount': amount,
                    'card_last4': card_last4,
                    'raw_message': message_text
                }

            # No generic-number fallback: matching an arbitrary 4-digit number in
            # an unrelated message could credit the wrong user's payment request.

            return None
        except (ValueError, AttributeError):
            return None
        except Exception:
            return None
    
    def find_matching_payment(self, parsed_payment: Dict[str, Any], tolerance: float = None) -> Optional[Any]:
        """
        Kelgan to'lovni kutilayotgan to'lovlar bilan solishtirish - TEZ VA ANIQ
        
        Args:
            parsed_payment: Parse qilingan to'lov ma'lumotlari
            tolerance: Summa farqi tolerantligi (default: 0 - aniq match)
            
        Returns:
            Payment object yoki None
        """
        try:
            amount = float(parsed_payment['amount'])
            card_last4 = str(parsed_payment['card_last4'])

            # Aniq match - toleransiz (tezroq)
            tol = tolerance if tolerance is not None else 0.0
            
            # Database'dan aniq match qidirish
            candidates = self.db.get_pending_payments_by_card_and_amount(card_last4, amount, tol)
            
            # A payment notification is not enough to identify a unique customer
            # when multiple pending requests share the same card suffix and amount.
            # Never guess based on recency; leave ambiguous cases for manual review.
            if len(candidates) == 1:
                return candidates[0]
            if len(candidates) > 1:
                print(
                    "[payment_detector] Ambiguous match: "
                    f"{len(candidates)} pending payments for card ****{card_last4} "
                    f"and amount {amount}; manual review required."
                )
            return None
            
        except Exception:
            return None

            if not matches:
                return None
            
        except Exception:
            return None
    
    def process_payment(self, payment_data: Dict, parsed_payment: Dict) -> bool:
        """
        To'lovni qayta ishlash va tasdiqlash
        
        Args:
            payment_data: Payment object yoki dict
            parsed_payment: Parse qilingan to'lov ma'lumotlari
            
        Process:
            1. Payment ID ni olish
            2. DB'da statusni 'completed' ga o'zgartirish
            
        Returns:
            True (muvaffaqiyatli) yoki False (xato)
        """
        try:
            # payment_data Payment object yoki dict bo'lishi mumkin
            payment_id = getattr(payment_data, 'payment_id', None) or payment_data.get('payment_id')
            
            if not payment_id:
                return False
            
            # This confirms only that a bank/payment notification was matched.
            # Bookmaker credit must be confirmed separately by its provider API.
            return bool(self.db.update_payment_status(payment_id, 'paid'))
            
        except (AttributeError, TypeError):
            return False
        except Exception:
            return False
    
    def handle_payment_message(self, message_text: str) -> Optional[Dict]:
        """
        To'lov xabarini to'liq qayta ishlash (pipeline)
        
        Args:
            message_text: Telegram guruhidan kelgan xabar
            
        Pipeline:
            1. Xabarni parse qilish
            2. Kutilayotgan to'lovlardan qidirish
            3. To'lovni tasdiqlash
            
        Returns:
            Payment object (muvaffaqiyatli) yoki None (xato/topilmadi)
        """
        # 1️⃣ Parse qilish
        parsed = self.parse_payment_message(message_text)
        if not parsed:
            return None
        
        # 2️⃣ Mos to'lovni qidirish
        payment = self.find_matching_payment(parsed)
        if not payment:
            return None
        
        # 3️⃣ To'lovni tasdiqlash
        success = self.process_payment(payment, parsed)
        if success:
            return payment
        
        return None
    
    def validate_card_number(self, card_number: str) -> bool:
        """
        Karta raqamini validatsiya qilish
        
        Args:
            card_number: Karta raqami (16 ta raqam, probel bilan yoki probelsiz)
            
        Qoidalar:
            - Uzunligi 16 ta raqam
            - Uzcard: 8600, 9860
            - Visa: 4
            - MasterCard: 5
            
        Returns:
            True (to'g'ri) yoki False (noto'g'ri)
        """
        # Barcha raqam bo'lmagan belgilarni olib tashlash
        cleaned = re.sub(r'\D', '', card_number)
        
        # Uzunlik tekshiruvi
        if len(cleaned) != 16:
            return False
        
        # Prefix tekshiruvi
        valid_prefixes = ['8600', '9860', '4', '5']
        
        if not any(cleaned.startswith(prefix) for prefix in valid_prefixes):
            return False
        
        return True
    
    def format_card_number(self, card_number: str) -> str:
        """
        Karta raqamini formatlash (4-4-4-4 formatda)
        
        Args:
            card_number: Karta raqami
            
        Returns:
            Formatlangan karta raqami (masalan: "8600 1234 5678 9012")
        """
        # Faqat raqamlarni qoldirish
        cleaned = re.sub(r'\D', '', card_number)
        
        if len(cleaned) == 16:
            return f"{cleaned[0:4]} {cleaned[4:8]} {cleaned[8:12]} {cleaned[12:16]}"
        
        return cleaned
    
    def mask_card_number(self, card_number: str) -> str:
        """
        Karta raqamini maskirovka qilish (xavfsizlik uchun)
        
        Args:
            card_number: Karta raqami
            
        Returns:
            Maskirovka qilingan karta (masalan: "**** **** **** 9012")
        """
        # Faqat raqamlarni qoldirish
        cleaned = re.sub(r'\D', '', card_number)
        
        if len(cleaned) == 16:
            return f"**** **** **** {cleaned[-4:]}"
        
        return "****"
