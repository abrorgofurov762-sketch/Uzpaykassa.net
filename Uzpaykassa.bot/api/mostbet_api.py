"""Mostbet Cash API client based on the supplied Agent FAQ PDF.

Financial POST requests are never automatically retried. A timeout after a POST is
reported as UNKNOWN so an operator can reconcile it through transaction history.
Live deposits require MOSTBET_LIVE_DEPOSITS_ENABLED=true and valid cashpoint
credentials. The provider documentation describes live API only (no sandbox).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

FINAL_STATUSES = {"COMPLETED", "NEW_ERROR", "CANCELED", "EXPIRED"}
NONFINAL_STATUSES = {"NEW", "ACCEPTED", "PROCESSING", "PROCESSING_ERROR"}


class MostbetAPI:
    def __init__(self, session: Optional[requests.Session] = None):
        self.api_key = os.getenv("MOSTBET_API_KEY", "").strip()
        self.api_secret = os.getenv("MOSTBET_API_SECRET", "").strip()
        self.cashpoint_id = os.getenv("MOSTBET_CASHPOINT_ID", "").strip()
        # Must be explicitly set to the currency enabled for this cashpoint.
        self.currency = os.getenv("MOSTBET_CURRENCY", "").strip().upper()
        self.base_url = os.getenv("MOSTBET_API_BASE_URL", "https://apimb.com").strip().rstrip("/")
        # Backwards-compatible normalization for the older full-path env value.
        for suffix in ("/mbc/gateway/v1/api/cashpoint", "/mbc/gateway/v1/api/cashpoint/"):
            if self.base_url.endswith(suffix.rstrip("/")):
                self.base_url = self.base_url[: -len(suffix.rstrip("/"))]
                break
        self.enabled = bool(self.api_key.startswith("api-key:") and self.api_secret and self.cashpoint_id)
        self.live_deposits_enabled = os.getenv("MOSTBET_LIVE_DEPOSITS_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
        self.timeout = max(3, min(int(os.getenv("MOSTBET_API_TIMEOUT", "15")), 45))
        self.status_poll_seconds = max(1, min(int(os.getenv("MOSTBET_STATUS_POLL_SECONDS", "3")), 10))
        self.status_poll_attempts = max(1, min(int(os.getenv("MOSTBET_STATUS_POLL_ATTEMPTS", "8")), 20))
        self.session = session or requests.Session()
        self.session.headers.update({"Accept": "application/json", "User-Agent": "Uzpaykassa-Bot/1.1"})

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    def _disabled(self, reason: str = "MOSTBET_API_NOT_CONFIGURED") -> Dict[str, Any]:
        return {"Success": False, "status": "DISABLED", "error": reason}

    def _request(self, method: str, path: str, data: Optional[dict] = None,
                 params: Optional[dict] = None, project: bool = False) -> Dict[str, Any]:
        if not self.enabled:
            return self._disabled()
        method = method.upper()
        if not path.startswith("/"):
            path = "/" + path
        # Query string must be identical in URL and signature. Use insertion order.
        query = urlencode(params or {})
        signed_path = path + ("?" + query if query else "")
        url = self.base_url + signed_path
        timestamp = self._timestamp()
        if data is None:
            body_text = ""
            body_bytes = None
        else:
            body_text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
            body_bytes = body_text.encode("utf-8")
        sign_text = self.api_key + signed_path + body_text + timestamp
        signature = hmac.new(self.api_secret.encode("utf-8"), sign_text.encode("utf-8"), hashlib.sha3_256).hexdigest()
        headers = {"X-Api-Key": self.api_key, "X-Timestamp": timestamp, "X-Signature": signature}
        if project:
            headers["X-Project"] = "MBC"
        if data is not None:
            headers["Content-Type"] = "application/json"
        try:
            response = self.session.request(method, url, headers=headers, data=body_bytes, timeout=self.timeout)
        except requests.RequestException as exc:
            # Do not expose credentials or raw request data in logs/results.
            logger.warning("Mostbet API network error (%s %s): %s", method, path, type(exc).__name__)
            return {"Success": False, "status": "UNKNOWN" if method == "POST" else "ERROR",
                    "error": "API_CONNECTION_ERROR", "uncertain": method == "POST"}
        try:
            payload = response.json()
        except (ValueError, requests.exceptions.JSONDecodeError):
            payload = {"message": (response.text or "")[:300]}
        if not response.ok:
            logger.warning("Mostbet API HTTP error %s on %s %s", response.status_code, method, path)
            return {"Success": False, "http_status": response.status_code,
                    "status": str(payload.get("status", "ERROR")).upper() if isinstance(payload, dict) else "ERROR",
                    "error": payload, "traceId": payload.get("traceId") if isinstance(payload, dict) else None}
        if not isinstance(payload, dict):
            return {"Success": False, "status": "UNKNOWN", "error": "INVALID_API_RESPONSE", "uncertain": method == "POST"}
        return {"Success": True, "http_status": response.status_code, "data": payload}

    def _v1(self, endpoint: str) -> str:
        return f"/mbc/gateway/v1/api/cashpoint/{self.cashpoint_id}/{endpoint.lstrip('/')}"

    def get_balance(self) -> Dict[str, Any]:
        result = self._request("GET", self._v1("balance"))
        if not result.get("Success"):
            return result
        data = result.get("data", {})
        if "balance" not in data or "currency" not in data:
            return {"Success": False, "status": "UNKNOWN", "error": "INVALID_BALANCE_RESPONSE"}
        return {"Success": True, "Balance": data["balance"], "Currency": data["currency"], "data": data}

    def find_player(self, player_id: str) -> Dict[str, Any]:
        player_id = str(player_id or "").strip()
        if not player_id or len(player_id) > 64:
            return {"Success": False, "error": "INVALID_PLAYER_ID"}
        result = self._request("GET", self._v1("player/name"), params={"brandId": 1, "clientId": player_id})
        if not result.get("Success"):
            return {"Success": False, "error": result.get("error", "PLAYER_LOOKUP_FAILED"), "http_status": result.get("http_status")}
        data = result["data"]
        if data.get("exists") is not True:
            return {"Success": False, "error": "PLAYER_NOT_FOUND", "warning": data.get("warning")}
        return {"Success": True, "player_id": player_id, "name": data.get("name", ""), "Name": data.get("name", ""), "data": data}

    def get_transaction_history(self, date_start: str, date_end: str, brand_id: int = 1,
                                player_id: Optional[str] = None, transaction_id: Optional[int] = None) -> Dict[str, Any]:
        for value in (date_start, date_end):
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value or "")):
                return {"Success": False, "error": "INVALID_DATE_FORMAT"}
        params = {"dateStart": date_start, "dateEnd": date_end}
        if brand_id is not None:
            params["brandId"] = int(brand_id)
        if player_id is not None:
            params["playerId"] = str(player_id)
        if transaction_id is not None:
            params["transactionId"] = int(transaction_id)
        path = f"/mbc/gateway/v2/api/cashpoint/{self.cashpoint_id}/transactions/list/all"
        result = self._request("GET", path, params=params)
        if not result.get("Success"):
            return result
        items = result["data"].get("items")
        if not isinstance(items, list):
            return {"Success": False, "status": "UNKNOWN", "error": "INVALID_TRANSACTION_HISTORY_RESPONSE"}
        return {"Success": True, "items": items, "data": result["data"]}

    def get_transaction_status(self, transaction_id: int) -> Dict[str, Any]:
        """Look up one transaction in documented v2 history; no undocumented endpoint used."""
        now = datetime.now(timezone.utc).date()
        result = self.get_transaction_history((now - timedelta(days=1)).isoformat(), now.isoformat(), transaction_id=transaction_id)
        if not result.get("Success"):
            return result
        matches = [x for x in result["items"] if str(x.get("transactionId")) == str(transaction_id)]
        if len(matches) != 1:
            return {"Success": False, "status": "UNKNOWN", "error": "TRANSACTION_NOT_FOUND_OR_AMBIGUOUS", "transactionId": transaction_id}
        item = matches[0]
        status = str(item.get("status", "UNKNOWN")).upper()
        return {"Success": status == "COMPLETED", "status": status, "transactionId": transaction_id, "data": item}

    def deposit_player(self, brand_id: int, player_id: str, amount: int, currency: Optional[str] = None) -> Dict[str, Any]:
        """Create a Mostbet deposit once, then reconcile status using transaction history.

        No automatic retry is performed for financial POST requests. Currency must be
        confirmed for the configured cashpoint before enabling live deposits.
        """
        if not self.enabled:
            return self._disabled()
        if not self.live_deposits_enabled:
            return self._disabled("LIVE_DEPOSITS_NOT_ENABLED; set MOSTBET_LIVE_DEPOSITS_ENABLED=true after cashpoint verification")
        try:
            brand_id = int(brand_id)
            amount = int(amount)
        except (TypeError, ValueError):
            return {"Success": False, "status": "ERROR", "error": "INVALID_AMOUNT_OR_BRAND"}
        player_id = str(player_id or "").strip()
        currency = str(currency or self.currency).upper().strip()
        if brand_id != 1:
            return {"Success": False, "status": "ERROR", "error": "MOSTBET_BRAND_ID_MUST_BE_1"}
        if not player_id or len(player_id) > 64 or not re.fullmatch(r"[A-Za-z0-9_-]+", player_id):
            return {"Success": False, "status": "ERROR", "error": "INVALID_PLAYER_ID"}
        if amount <= 0:
            return {"Success": False, "status": "ERROR", "error": "AMOUNT_MUST_BE_POSITIVE_INTEGER"}
        if not re.fullmatch(r"[A-Z]{3}", currency):
            return {"Success": False, "status": "ERROR", "error": "INVALID_CURRENCY"}
        # Verify the configured currency against the cashpoint before any financial POST.
        # This is a safety check, not proof that every player/account accepts the currency.
        cashpoint = self.get_balance()
        if not cashpoint.get("Success"):
            return {"Success": False, "status": "NOT_CREATED", "error": "CASHPOINT_PREFLIGHT_FAILED",
                    "details": cashpoint.get("error", "BALANCE_CHECK_FAILED")}
        cashpoint_currency = str(cashpoint.get("Currency", "")).upper().strip()
        if cashpoint_currency != currency:
            return {"Success": False, "status": "NOT_CREATED", "error": "CASHPOINT_CURRENCY_MISMATCH",
                    "configured_currency": currency, "cashpoint_currency": cashpoint_currency}
        # Player lookup prevents avoidable wrong-ID operations, but provider may still reject.
        player = self.find_player(player_id)
        if not player.get("Success"):
            return {"Success": False, "status": "NOT_CREATED", "error": "PLAYER_CHECK_FAILED", "details": player.get("error")}
        body = {"brandId": 1, "playerId": player_id, "amount": amount, "currency": currency}
        created = self._request("POST", self._v1("player/deposit"), data=body, project=True)
        if not created.get("Success"):
            # POST timeout is ambiguous; never repeat it automatically.
            return {"Success": False, "status": created.get("status", "UNKNOWN"),
                    "error": created.get("error", "DEPOSIT_REQUEST_FAILED"),
                    "uncertain": bool(created.get("uncertain")), "reconciliation_required": bool(created.get("uncertain"))}
        data = created.get("data", {})
        tx_id = data.get("transactionId")
        status = str(data.get("status", "UNKNOWN")).upper()
        if not tx_id:
            return {"Success": False, "status": "UNKNOWN", "error": "TRANSACTION_ID_MISSING", "reconciliation_required": True}
        if status == "COMPLETED":
            return {"Success": True, "status": status, "transactionId": tx_id, "data": data}
        # The docs say NEW is only accepted/created, not final. Poll history for the exact ID.
        for attempt in range(self.status_poll_attempts):
            if attempt:
                time.sleep(self.status_poll_seconds)
            current = self.get_transaction_status(int(tx_id))
            if not current.get("Success") and current.get("status") == "UNKNOWN" and current.get("error") == "TRANSACTION_NOT_FOUND_OR_AMBIGUOUS":
                continue
            if current.get("status") in FINAL_STATUSES:
                return {"Success": current["status"] == "COMPLETED", "status": current["status"],
                        "transactionId": tx_id, "data": current.get("data"),
                        "error": None if current["status"] == "COMPLETED" else "DEPOSIT_FINALIZED_WITH_ERROR"}
        return {"Success": False, "Pending": True, "status": status if status in NONFINAL_STATUSES else "PROCESSING",
                "transactionId": tx_id, "error": "DEPOSIT_STATUS_NOT_FINAL; manual reconciliation may be required"}

    def list_cashout_requests(self, page: int = 1, size: int = 10, search_string: Optional[str] = None) -> Dict[str, Any]:
        if int(page) < 1 or int(size) < 1 or int(size) > 100:
            return {"Success": False, "error": "INVALID_PAGINATION"}
        params = {"page": int(page), "size": int(size)}
        if search_string:
            params["searchString"] = str(search_string)[:100]
        result = self._request("GET", self._v1("player/cashout/list/page"), params=params)
        if not result.get("Success"):
            return result
        data = result["data"]
        if not isinstance(data.get("items"), list):
            return {"Success": False, "error": "INVALID_CASHOUT_LIST_RESPONSE"}
        return {"Success": True, "items": data["items"], "totalCount": data.get("totalCount", len(data["items"]))}

    def confirm_cashout(self, transaction_id: int, code: str) -> Dict[str, Any]:
        """Confirm a provider-originated cashout request using its transaction ID + SMS code.

        This is not wired into the bot's current card-withdrawal workflow, which is a
        different process and must not be treated as Mostbet Cash API confirmation.
        """
        try:
            transaction_id = int(transaction_id)
        except (TypeError, ValueError):
            return {"Success": False, "status": "ERROR", "error": "INVALID_TRANSACTION_ID"}
        code = str(code or "").strip()
        if transaction_id <= 0 or not code or len(code) > 32:
            return {"Success": False, "status": "ERROR", "error": "INVALID_CASHOUT_CONFIRMATION_DATA"}
        result = self._request("POST", self._v1("player/cashout/confirmation"),
                               data={"code": code, "transactionId": transaction_id}, project=True)
        if not result.get("Success"):
            return {"Success": False, "status": result.get("status", "UNKNOWN"), "error": result.get("error"),
                    "uncertain": bool(result.get("uncertain")), "reconciliation_required": bool(result.get("uncertain"))}
        data = result.get("data", {})
        status = str(data.get("status", "UNKNOWN")).upper()
        if status == "COMPLETED":
            return {"Success": True, "status": status, "transactionId": data.get("transactionId", transaction_id), "data": data}
        # No repeat of confirmation POST. Reconcile only through the documented history GET.
        tx_id = data.get("transactionId", transaction_id)
        for attempt in range(self.status_poll_attempts):
            if attempt:
                time.sleep(self.status_poll_seconds)
            current = self.get_transaction_status(int(tx_id))
            if current.get("status") in FINAL_STATUSES:
                final_status = current["status"]
                return {"Success": final_status == "COMPLETED", "status": final_status,
                        "transactionId": tx_id, "data": current.get("data"),
                        "error": None if final_status == "COMPLETED" else "CASHOUT_FINALIZED_WITH_ERROR"}
        return {"Success": False, "Pending": True, "status": status,
                "transactionId": tx_id, "data": data,
                "error": "CASHOUT_STATUS_NOT_FINAL; manual reconciliation may be required"}


mostbet_api = MostbetAPI()
