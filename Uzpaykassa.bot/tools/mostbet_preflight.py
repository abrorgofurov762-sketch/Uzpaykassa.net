"""Read-only Mostbet Cash API preflight. NEVER creates deposits or payouts.

Run from the repository root after setting MOSTBET_API_KEY,
MOSTBET_API_SECRET, MOSTBET_CASHPOINT_ID, and MOSTBET_CURRENCY=UZS.
Optionally pass a test player ID as the first CLI argument to check lookup.
"""
from __future__ import annotations

import os
import sys

from api.mostbet_api import MostbetAPI


def main() -> int:
    required = ("MOSTBET_API_KEY", "MOSTBET_API_SECRET", "MOSTBET_CASHPOINT_ID")
    missing = [name for name in required if not os.getenv(name, "").strip()]
    if missing:
        print("FAIL: missing environment variables: " + ", ".join(missing))
        return 2

    configured_currency = os.getenv("MOSTBET_CURRENCY", "").strip().upper()
    if configured_currency != "UZS":
        print("FAIL: set MOSTBET_CURRENCY=UZS for this preflight")
        return 2

    api = MostbetAPI()
    if not api.enabled:
        print("FAIL: API credentials are not in the expected format/configuration")
        return 2

    print("Checking API credentials and cashpoint balance (read-only)...")
    balance = api.get_balance()
    if not balance.get("Success"):
        print("FAIL: cashpoint balance request failed; error=" + str(balance.get("error", "API_ERROR")))
        print("No financial operation was sent.")
        return 1

    currency = str(balance.get("Currency", "")).strip().upper()
    if currency != "UZS":
        print("FAIL: cashpoint currency mismatch; API returned " + (currency or "<empty>"))
        print("No financial operation was sent.")
        return 1

    print("PASS: API authentication/request succeeded.")
    print("PASS: cashpoint reports currency UZS.")

    if len(sys.argv) > 1:
        player_id = sys.argv[1].strip()
        print("Checking player lookup (read-only)...")
        player = api.find_player(player_id)
        if not player.get("Success"):
            print("FAIL: player lookup failed; error=" + str(player.get("error", "PLAYER_LOOKUP_FAILED")))
            print("No financial operation was sent.")
            return 1
        print("PASS: player lookup succeeded.")

    print("PREFLIGHT PASSED. This did not send a deposit or payout and does not prove live money movement.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
