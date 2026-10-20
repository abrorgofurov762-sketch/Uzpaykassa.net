class MockAPI:
    def __init__(self, name):
        self.name = name

    def deposit(self, *args, **kwargs):
        return {"status": "success", "message": f"{self.name} API ҳали уланмаган"}

mostbet_api = MockAPI("Mostbet")
