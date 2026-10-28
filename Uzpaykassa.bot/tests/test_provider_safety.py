import os
import unittest
from unittest.mock import patch


class ProviderSafetyTests(unittest.TestCase):
    def test_mostbet_api_can_initialize_without_credentials_and_fails_closed(self):
        # Import inside patched environment so no real credentials are required.
        with patch.dict(os.environ, {
            "MOSTBET_API_KEY": "",
            "MOSTBET_API_SECRET": "",
            "MOSTBET_CASHPOINT_ID": "",
        }, clear=False):
            from api.mostbet_api import MostbetAPI
            api = MostbetAPI()
            self.assertFalse(api.enabled)
            result = api._request("GET", "health")
            self.assertFalse(result["Success"])
            self.assertEqual(result["status"], "DISABLED")

    def test_live_mostbet_deposit_requires_explicit_enable_flag(self):
        from api.mostbet_api import MostbetAPI
        with patch.dict(os.environ, {
            "MOSTBET_API_KEY": "api-key:test",
            "MOSTBET_API_SECRET": "secret",
            "MOSTBET_CASHPOINT_ID": "12345",
            "MOSTBET_LIVE_DEPOSITS_ENABLED": "false",
            "MOSTBET_CURRENCY": "UZS",
        }, clear=False):
            api = MostbetAPI()
            result = api.deposit_player(brand_id=1, player_id="774", amount=1000, currency="UZS")
        self.assertFalse(result["Success"])
        self.assertEqual(result["status"], "DISABLED")


if __name__ == "__main__":
    unittest.main()
