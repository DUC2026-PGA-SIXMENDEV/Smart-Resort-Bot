"""Configuration loader."""

import base64
import json
import os
import tempfile
from pathlib import Path

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
        self.GOOGLE_SHEETS_CREDS = self._google_sheets_credentials_path()
        self.GOOGLE_SHEETS_NAME = os.getenv("GOOGLE_SHEETS_NAME", "Resort Bookings")

    def _require(self, name: str) -> str:
        value = os.getenv(name)
        if not value:
            raise EnvironmentError(f"Required environment variable '{name}' is missing.")
        return value

    def _google_sheets_credentials_path(self) -> str:
        """Return a credentials file path, materializing JSON env vars on hosted platforms."""
        credentials_json = os.getenv("GOOGLE_SHEETS_CREDS_JSON")
        credentials_b64 = os.getenv("GOOGLE_SHEETS_CREDS_B64")

        if not credentials_json and credentials_b64:
            credentials_json = base64.b64decode(credentials_b64).decode("utf-8")

        if credentials_json:
            json.loads(credentials_json)
            credentials_path = Path(tempfile.gettempdir()) / "google_sheets_credentials.json"
            credentials_path.write_text(credentials_json, encoding="utf-8")
            return str(credentials_path)

        return os.getenv("GOOGLE_SHEETS_CREDS", "credentials.json")
