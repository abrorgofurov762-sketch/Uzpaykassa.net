import os
import json
import hmac
import hashlib
import requests

from datetime import datetime, timezone
from urllib.parse import urlparse


class MostbetAPI:
    def __init__(self):
        self.api_key = os.getenv("MOSTBET_API_KEY", "").strip()
        self.api_secret = os.getenv("MOSTBET_API_SECRET", "").strip()
        self.cashpoint_id = os.getenv(
            "MOSTBET_CASHPOINT_ID", ""
        ).strip()

        self.base_url = os.getenv(
            "MOSTBET_API_BASE_URL",
            "https://apimb.com/mbc/gateway/v1/api/cashpoint/"
        ).rstrip("/") + "/"

        if not all([
            self.api_key,
            self.api_secret,
            self.cashpoint_id,
        ]):
            raise ValueError(
                "Mostbet API sozlamalari to'liq kiritilmagan"
            )

        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "Uzpaykassa-Bot/1.0",
        })

    def _timestamp(self):
        return datetime.now(timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    def _request(self, method, endpoint, data=None):
        """
        Mostbet API uchun imzolangan HTTP so'rovi.

        Muhim:
        - PATH to'liq API yo'li bo'lishi kerak.
        - JSON tana ixcham formatda yaratiladi.
        - Secret hech qachon HTTP sarlavhasida yuborilmaydi.
        """

        method = method.upper()
        path = (
            f"/mbc/gateway/v1/api/cashpoint/"
            f"{self.cashpoint_id}/{endpoint.lstrip('/')}"
        )

        url = self.base_url + (
            f"{self.cashpoint_id}/{endpoint.lstrip('/')}"
        )

        timestamp = self._timestamp()

        if data is None:
            body = ""
            payload = None
        else:
            body = json.dumps(
                data,
                separators=(",", ":"),
                ensure_ascii=False
            )
            payload = body.encode("utf-8")

        # Hujjatдаги тартиб:
        # API_KEY + PATH + REQUEST_BODY + TIMESTAMP
        string_to_sign = (
            self.api_key + path + body + timestamp
        )

        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha3_256
        ).hexdigest()

        headers = {
            "X-Api-Key": self.api_key,
            "X-Timestamp": timestamp,
            "X-Signature": signature,
        }

        if method == "POST":
            headers["X-Project"] = "MBC"
            headers["Content-Type"] = "application/json"

        try:
            response = self.session.request(
                method=method,
                url=url,
                headers=headers,
                data=payload,
                timeout=20,
            )

            try:
                result = response.json()
            except ValueError:
                result = {
                    "message": response.text[:500]
                }

            if not response.ok:
                return {
                    "Success": False,
                    "http_status": response.status_code,
                    "error": result,
                }

            return {
                "Success": True,
                "http_status": response.status_code,
                "data": result,
            }

        except requests.RequestException as exc:
            return {
                "Success": False,
                "error": str(exc),
            }

    def get_balance(self):
        """Cashpoint balansini olish."""
        return self._request(
            "GET",
            "balance"
        )

    def find_player(self, player_id):
        """
        Hozirча player ID текшируви амалга оширилмайди.
        Ҳужжатда тасдиқланган player lookup endpoint
        аниқланмагунча ID ҳақиқий деб қабул қилинмайди.
        """
        return {
            "Success": False,
            "error": "PLAYER_LOOKUP_NOT_CONFIGURED"
        }

    def deposit_player(self, brand_id, player_id, amount):
        """
        Хавфсизлик учун ҳозирча пул ўтказиш ўчирилган.
        API транзакциясини яратишдан олдин ботдаги
        тўлов ҳолатларини ҳам тўғрилаш керак.
        """
        return {
            "Success": False,
            "status": "DISABLED",
            "error": "LIVE_DEPOSITS_NOT_ENABLED"
        }


mostbet_api = MostbetAPI()
