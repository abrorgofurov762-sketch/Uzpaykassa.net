"""Safe placeholder for an API provider not yet integrated.

All operations fail closed: no fake success and no balance mutation.
Replace this adapter only after obtaining the provider's official API docs.
"""

class DisabledProviderAPI:
    def __init__(self, provider_name: str):
        self.provider_name = provider_name

    def _unavailable(self):
        return {"Success": False, "Error": f"{self.provider_name} API is not configured"}

    def find_player(self, *args, **kwargs):
        return self._unavailable()

    def get_balance(self, *args, **kwargs):
        return self._unavailable()

    def deposit_add(self, *args, **kwargs):
        return self._unavailable()

    def deposit_player(self, *args, **kwargs):
        return self._unavailable()

    def deposit_payout(self, *args, **kwargs):
        return self._unavailable()

    def withdraw_subtract(self, *args, **kwargs):
        return self._unavailable()
class DisabledProviderAPI:
    def __init__(self, provider_name: str):
        self.provider_name = provider_name

    def _unavailable(self):
        return {
            "Success": False,
            "Error": f"{self.provider_name} API is not configured",
            "ErrorCode": "PROVIDER_DISABLED",
            "Retryable": False
        }

    def find_player(self, *args, **kwargs):
        return self._unavailable()

    def get_balance(self, *args, **kwargs):
        return self._unavailable()

    def deposit_add(self, *args, **kwargs):
        return self._unavailable()

    def deposit_player(self, *args, **kwargs):
        return self._unavailable()

    def deposit_payout(self, *args, **kwargs):
        return self._unavailable()

    def withdraw_subtract(self, *args, **kwargs):
        return self._unavailable()
