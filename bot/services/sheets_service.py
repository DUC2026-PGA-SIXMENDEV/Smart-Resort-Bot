# ============================================================
#  bot/services/sheets_service.py — Google Sheets Integration
# ============================================================
import logging
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

class SheetsService:
    def __init__(self, credentials_path: str, sheet_name: str):
        self.credentials_path = credentials_path
        self.sheet_name = sheet_name
        self.client = None
        self.sheet = None

    def _connect(self):
        try:
            if not self.credentials_path or not self.sheet_name: return False
            creds = Credentials.from_service_account_file(self.credentials_path, scopes=SCOPES)
            self.client = gspread.authorize(creds)
            self.sheet = self.client.open(self.sheet_name).get_worksheet(0)
            
            # Professional Headers: No User ID, added Phone and Telegram Username
            headers = [
                "Booking ID", "Status", "Guest Name", "Phone / WhatsApp", 
                "Telegram Username", "Check-in", "Check-out", "Room Type", 
                "Guests", "Special Requests", "Timestamp"
            ]
            
            # If sheet is empty, add headers
            if not self.sheet.row_values(1):
                self.sheet.insert_row(headers, 1)
            else:
                # If headers are different, update them to match the new structure
                current_headers = self.sheet.row_values(1)
                if "Phone / WhatsApp" not in current_headers:
                    self.sheet.update("A1:K1", [headers])
                
            return True
        except Exception as e:
            logger.error("❌ Sheets Error: %s", e)
            return False

    async def append_booking(self, b: dict):
        try:
            if not self.sheet:
                if not self._connect(): return

            row = [
                b.get("id", "N/A"),
                b.get("status", "PENDING"),
                b.get("guest_name"),
                b.get("phone", "N/A"),
                b.get("username", "N/A"),
                b.get("checkin_date"),
                b.get("checkout_date"),
                b.get("room_type"),
                b.get("num_guests"),
                b.get("special_request"),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ]
            self.sheet.append_row(row)
            logger.info("✅ Booking #%s synced to Sheets.", b.get("id"))
        except Exception as e:
            logger.error("❌ Sync failed: %s", e)

    async def update_booking_status(self, booking_id: int, new_status: str):
        try:
            if not self.sheet:
                if not self._connect(): return
            cell = self.sheet.find(str(booking_id), in_column=1)
            if cell:
                self.sheet.update_cell(cell.row, 2, new_status)
        except Exception as e:
            logger.error("❌ Status update failed: %s", e)
