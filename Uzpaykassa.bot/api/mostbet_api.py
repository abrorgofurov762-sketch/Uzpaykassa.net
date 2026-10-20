"""
Mostbet API Модули (Реал сўровлар, хатоликларни ушлаш ва хавфсиз ишлаш учун тўлиқ код).
"""
import logging
import requests

logger = logging.getLogger(__name__)

class MostBetAPI:
    def __init__(self):
        self.name = "Mostbet"
        
        # 📌 1. Mostbet'дан олган реал URL манзили ва токенингизни шу ерга ёзасиз:
        self.api_url = "https://api.mostbet.com/v1"  # Mostbet берган расмий API манзили
        self.api_token = "821bc7e6-6d3a-4431-aac6-29e6be392168"  # Mostbet берган Махсус Токен

    def find_player(self, player_id: str) -> dict:
        """Foydalanuvchi ID raqamini tekshirish (Real API сўрови)"""
        try:
            url = f"{self.api_url}/player/check"
            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            }
            payload = {"player_id": player_id}
            
            # Реал серверга сўров юбориш (15 сония ичида жавоб келмаса тўхтайди)
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            
            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "Success": False,
                    "error": f"API хатолик қайтарди: {response.status_code}"
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Mostbet find_player tarmoq xatoligi: {e}")
            return {"Success": False, "error": f"Tarmoq xatoligi: {str(e)}"}
        except Exception as e:
            return {"Success": False, "error": str(e)}

    def deposit_player(self, currency: int, player_id: str, amount: float) -> dict:
        """Mostbet ҳисобига пулни автоматик ўтказиш (Реал API сўрови)"""
        try:
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
            
            # Реал серверга пул ўтказиш сўрови
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            
            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "Success": False,
                    "error": f"Depozit xatoligi, status: {response.status_code}"
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Mostbet deposit_player tarmoq xatoligi: {e}")
            return {"Success": False, "error": f"Tarmoq xatoligi: {str(e)}"}
        except Exception as e:
            return {"Success": False, "error": str(e)}

    def get_balance(self) -> dict:
        """Kassa балансини текшириш"""
        try:
            url = f"{self.api_url}/kassa/balance"
            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json()
            return {"Success": False, "Balance": 0, "Limit": 0}
            
        except Exception as e:
            return {"Success": False, "Balance": 0, "Limit": 0}

# Global obyekt (handlers/deposit.py шу орқали чақиради)
mostbet_api = MostBetAPI()
