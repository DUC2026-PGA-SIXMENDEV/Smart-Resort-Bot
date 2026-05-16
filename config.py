# ============================================================
#  config.py — Configuration Loader
# ============================================================
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    def __init__(self):
        self.TELEGRAM_BOT_TOKEN: str = self._require("TELEGRAM_BOT_TOKEN")
        
        # Database
        self.DATABASE_PATH: str = os.getenv("DATABASE_PATH", "resort_bot.db")
        self.RESORT_NAME: str = os.getenv("RESORT_NAME", "Paradise Resort & Spa")
        
        # Admin IDs
        admin_str = os.getenv("ADMIN_IDS", "")
        self.ADMIN_IDS: list[int] = [
            int(i.strip()) for i in admin_str.split(",") if i.strip().isdigit()
        ]

        # Google Sheets
        self.GOOGLE_SHEETS_CREDS = os.getenv("GOOGLE_SHEETS_CREDS", "credentials.json")
        self.GOOGLE_SHEETS_NAME = os.getenv("GOOGLE_SHEETS_NAME", "Resort Bookings")

    # def _require(self, name: str) -> str:
    #     value = os.getenv(name)
    #     if not value:
    #         raise EnvironmentError(f"❌ Required environment variable '{name}' is missing!")
    #     return value
