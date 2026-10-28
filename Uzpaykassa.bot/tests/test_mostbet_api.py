import hashlib
import hmac
import json
import os
import unittest
from unittest.mock import patch

from api.mostbet_api import MostbetAPI


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.headers = {}
        self.calls = []

    def request(self, method, url, headers=None, data=None, timeout=None):
        self.calls.append({"method": method, "url": url, "headers": headers or {}, "data": data, "timeout": timeout})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class MostbetAPITests(unittest.TestCase):
    def make_api(self, session, extra=None):
        env = {
            "MOSTBET_API_KEY": "api-key:test-key",
            "MOSTBET_API_SECRET": "test-secret",
            "MOSTBET_CASHPOINT_ID": "12345",
            "MOSTBET_API_BASE_URL": "https://apimb.com",
            "MOSTBET_CURRENCY": "UZS",
            "MOSTBET_LIVE_DEPOSITS_ENABLED": "true",
            "MOSTBET_STATUS_POLL_ATTEMPTS": "1",
            "MOSTBET_STATUS_POLL_SECONDS": "1",
        }
        if extra:
            env.update(extra)
        with patch.dict(os.environ, env, clear=False):
            return MostbetAPI(session=session)

    def test_missing_credentials_fails_closed(self):
        with patch.dict(os.environ, {"MOSTBET_API_KEY": "", "MOSTBET_API_SECRET": "", "MOSTBET_CASHPOINT_ID": ""}, clear=False):
            api = MostbetAPI(session=FakeSession([]))
        self.assertFalse(api.enabled)
        self.assertEqual(api.get_balance()["status"], "DISABLED")

    def test_live_deposit_requires_explicit_flag(self):
        session = FakeSession([])
        api = self.make_api(session, {"MOSTBET_LIVE_DEPOSITS_ENABLED": "false"})
        result = api.deposit_player(1, "774", 50000, "UZS")
        self.assertFalse(result["Success"])
        self.assertEqual(result["status"], "DISABLED")
        self.assertEqual(session.calls, [])

    def test_signature_matches_exact_body_and_path(self):
        session = FakeSession([FakeResponse({"balance": 10, "currency": "UZS"})])
        api = self.make_api(session)
        result = api.get_balance()
        self.assertTrue(result["Success"])
        call = session.calls[0]
        timestamp = call["headers"]["X-Timestamp"]
        signed = "api-key:test-key/mbc/gateway/v1/api/cashpoint/12345/balance" + timestamp
        expected = hmac.new(b"test-secret", signed.encode(), hashlib.sha3_256).hexdigest()
        self.assertEqual(call["headers"]["X-Signature"], expected)

    def test_deposit_completed_from_documented_response(self):
        session = FakeSession([
            FakeResponse({"balance": 100000, "currency": "UZS"}),
            FakeResponse({"exists": True, "name": "Test Player", "warning": None}),
            FakeResponse({"transactionId": 777, "status": "COMPLETED"}),
        ])
        api = self.make_api(session)
        result = api.deposit_player(1, "774", 50000, "UZS")
        self.assertTrue(result["Success"])
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["transactionId"], 777)
        post_call = session.calls[2]
        self.assertEqual(post_call["headers"]["X-Project"], "MBC")
        self.assertEqual(json.loads(post_call["data"].decode()), {"brandId": 1, "playerId": "774", "amount": 50000, "currency": "UZS"})

    def test_new_deposit_is_not_reported_as_completed_if_status_unavailable(self):
        session = FakeSession([
            FakeResponse({"balance": 100000, "currency": "UZS"}),
            FakeResponse({"exists": True, "name": "Test Player", "warning": None}),
            FakeResponse({"transactionId": 778, "status": "NEW"}),
            FakeResponse({"items": []}),
        ])
        api = self.make_api(session)
        result = api.deposit_player(1, "774", 50000, "UZS")
        self.assertFalse(result["Success"])
        self.assertTrue(result["Pending"])
        self.assertEqual(result["transactionId"], 778)
        self.assertEqual(result["status"], "NEW")

    def test_cashpoint_currency_mismatch_blocks_financial_post(self):
        session = FakeSession([FakeResponse({"balance": 100, "currency": "USD"})])
        api = self.make_api(session)
        result = api.deposit_player(1, "774", 50000, "UZS")
        self.assertFalse(result["Success"])
        self.assertEqual(result["error"], "CASHPOINT_CURRENCY_MISMATCH")
        self.assertEqual(len(session.calls), 1)
        self.assertFalse(any(call["method"] == "POST" for call in session.calls))

    def test_missing_cashpoint_currency_blocks_deposit_before_network(self):
        session = FakeSession([])
        api = self.make_api(session, {"MOSTBET_CURRENCY": ""})
        result = api.deposit_player(1, "774", 50000, None)
        self.assertFalse(result["Success"])
        self.assertEqual(result["error"], "INVALID_CURRENCY")
        self.assertEqual(session.calls, [])

    def test_deposit_post_timeout_is_not_retried(self):
        session = FakeSession([
            FakeResponse({"balance": 100000, "currency": "UZS"}),
            FakeResponse({"exists": True, "name": "Test Player", "warning": None}),
            __import__('requests').Timeout("simulated timeout"),
        ])
        api = self.make_api(session)
        result = api.deposit_player(1, "774", 50000, "UZS")
        self.assertFalse(result["Success"])
        self.assertTrue(result["uncertain"])
        self.assertEqual(sum(1 for call in session.calls if call["method"] == "POST"), 1)


if __name__ == "__main__":
    unittest.main()
