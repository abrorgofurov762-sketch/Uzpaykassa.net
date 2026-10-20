class MockAPI:
    def __init__(self, name):
        self.name = name

    def deposit(self, *args, **kwargs):
        return {"status": "success", "message": f"{self.name} API ҳали уланмаган"}

melbet_api = MockAPI("Melbet")
betwiner_api = MockAPI("Betwiner")
winwin_api = MockAPI("Winwin")
