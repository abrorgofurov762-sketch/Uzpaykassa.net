import os
import json
import hmac
import hashlib
import requests

from datetime import datetime, timezone
from urllib.parse import urlencode


class MostbetAPI:
    def __init__(self):
        self.api_key = os.getenv(
            "MOSTBET_API_KEY", ""
        ).strip()

        self.api_secret = os.getenv(
            "MOSTBET_API_SECRET", ""
        ).strip()

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
        return datetime.now(
            timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S")

    def _request(
        self,
        method,
        endpoint,
        data=None,
        params=None
    ):
        method = method.upper()

        path = (
            f"/mbc/gateway/v1/api/cashpoint/"
            f"{self.cashpoint_id}/"
            f"{endpoint.lstrip('/')}"
        )

        # URL parametrlarini imzoga ham qo'shamiz.
        query_string = urlencode(params or {})

        if query_string:
            path += "?" + query_string

        url = self.base_url + (
            f"{self.cashpoint_id}/"
            f"{endpoint.lstrip('/')}"
        )

        if query_string:
            url += "?" + query_string

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

        string_to_sign = (
            self.api_key
            + path
            + body
            + timestamp
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

        except requests.RequestException:
            return {
                "Success": False,
                "error": "API_CONNECTION_ERROR",
            }

    def get_balance(self):
        return self._request(
            "GET",
            "balance"
        )

    def find_player(self, player_id):
        """
        Mostbet ID raqamini tekshiradi
        va mavjud bo'lsa, o'yinchi ismini oladi.
        """

        player_id = str(player_id).strip()

        if not player_id:
            return {
                "Success": False,
                "error": "PLAYER_ID_EMPTY"
            }

        result = self._request(
            "GET",
            "player/name",
            params={
                "brandId": 1,
                "clientId": player_id,
            }
        )

        if not result.get("Success"):
            return {
                "Success": False,
                "error": result.get("error"),
                "http_status": result.get("http_status"),
            }

        player_data = result.get("data", {})

        if not isinstance(player_data, dict):
            return {
                "Success": False,
                "error": "INVALID_API_RESPONSE"
            }

        # Tekshirish xizmati mavjud bo'lmasa,
        # ID noto'g'ri deb noto'g'ri xulosa qilmaymiz.
        if player_data.get("warning"):
            return {
                "Success": False,
                "error": "PLAYER_VERIFICATION_UNAVAILABLE",
                "warning": player_data.get("warning"),
            }

        if player_data.get("exists") is not True:
            return {
                "Success": False,
                "error": "PLAYER_NOT_FOUND"
            }

        player_name = player_data.get("name")

        if not player_name:
            return {
                "Success": False,
                "error": "PLAYER_NAME_NOT_RETURNED"
            }

        return {
            "Success": True,
            "player_id": player_id,
            "name": player_name,
        }

    def deposit_player(
        self,
        brand_id,
        player_id,
        amount,
        currency
    ):
        """
        Jonli pul o'tkazish hozircha o'chirilgan.
        Xavfsizlik tekshiruvlaridan keyin alohida yoqiladi.
        """

        return {
            "Success": False,
            "status": "DISABLED",
            "error": "LIVE_DEPOSITS_NOT_ENABLED"
        }


mostbet_api = MostbetAPI()
