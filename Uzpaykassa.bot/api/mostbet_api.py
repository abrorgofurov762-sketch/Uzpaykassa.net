"""
Mostbet API Модули (Тест ва Реал режимни қўллаб-қувватлайдиган код).
"""
import logging
import requests

logger = logging.getLogger(__name__)

class MostBetAPI:
    def __init__(self):
        self.name = "Mostbet"
        
        Ҳозирча тест/фиктив манзил тургани учун код автоматик равишда хатосиз ишлайди
        self.api_url = "821bc7e6-6d3a-4431-aac6-29e6be392168"
        self.api_token = "e8258b3f-99b1-4c9f-a07d-653b81376390"

    def find_player(self, player_id: str) -> dict:
        """Foydalanuvchi ID raqamini tekshirish"""
        try:
             Агар ҳали реал API уланмаган бўлса (тест режим):
            if "mostbet.com" in self.api_url or "SIZNING" in self.api_token:
                if player_id and len(str(player_id)) >= 3:
                    return {
                        "Success": True,
                        "UserId": str(player_id),
                        "Name": "Mostbet Player (Test)"
                    }
                return {"Success": False, "error": "Bunday ID raqam topilmadi"}

             Реал API сўрови (агар кейинчалик ҳақиқий манзил қўйсангиз ишлайди)
            url = f"{self.api_url}/player/check"
            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            }
            response = requests.post(url, json={"player_id": player_id}, headers=headers, timeout=15)
            if response.status_code == 200:
                return response.json()
            return {"Success": False, "error": f"API xatoligi: {response.status_code}"}
                
        except Exception as e:
            return {"Success": False, "error": str(e)}

    def deposit_player(self, currency: int, player_id: str, amount: float) -> dict:
        """Mostbet ҳисобига пулни автоматик ўтказиш"""
        try:
             Агар ҳали реал API уланмаган бўлса (тест режим):
            if "mostbet.com" in self.api_url or "SIZNING" in self.api_token:
                return {
                    "Success": False,  # deposit.py мантиғига кўра False = муваффақиятли ўтди
                    "status": "success",
                    "message": f"Mostbet ID {player_id} ga {amount} so'm avtomatik o'tkazildi (Test)"
                }

             Реал API сўрови
            url = f"{self.api_url}/deposit/add"
            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            }
            payload = {
                "currency": currency,
                "player_id": player_id,
                "amount": amount
            }
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            if response.status_code == 200:
                return response.json()
            return {"Success": False, "error": f"Depozit xatoligi: {response.status_code}"}
                
        except Exception as e:
            return {"Success": True, "error": str(e)}

    def get_balance(self) -> dict:
        """Kassa балансини текшириш"""
        try:
            if "mostbet.com" in self.api_url:
                return {"Success": True, "Balance": 5000000.0, "Limit": 10000000.0}
            
            url = f"{self.api_url}/kassa/balance"
            headers = {"Authorization": f"Bearer {self.api_token}"}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json()
            return {"Success": False, "Balance": 0, "Limit": 0}
        except Exception:
            return {"Success": False, "Balance": 0, "Limit": 0}

 Global obyekt
mostbet_api = MostBetAPI()
