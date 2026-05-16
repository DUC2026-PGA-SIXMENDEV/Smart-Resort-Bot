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
            
            headers = [
                "Booking ID", "Status", "Guest Name", "Phone / WhatsApp", 
                "Telegram Username", "Check-in", "Check-out", "Room Type", 
                "Guests", "Special Requests", "Timestamp"
            ]
            
            if not self.sheet.row_values(1):
                self.sheet.insert_row(headers, 1)
            return True
        except Exception as e:
            logger.error("❌ Sheets Error: %s", e)
            return False

    async def get_room_inventory(self) -> dict:
        """Fetches total room counts from the 'Rooms' tab."""
        try:
            if not self.client: self._connect()
            sheet = self.client.open(self.sheet_name).worksheet("Rooms")
            records = sheet.get_all_records()
            # Convert list of dicts to { 'Superior Villa': 5, ... }
            return {r["Room Type"]: int(r["Total Inventory"]) for r in records}
        except Exception as e:
            logger.error(f"Error fetching room inventory: {e}")
            return {}

    async def get_occupied_count(self, room_name: str, checkin: str, checkout: str) -> int:
        """Calculates how many rooms of this type are booked during these dates in the sheet."""
        try:
            if not self.sheet: self._connect()
            records = self.sheet.get_all_records()
            
            fmt = "%d/%m/%Y"
            q_in = datetime.strptime(checkin, fmt).date()
            q_out = datetime.strptime(checkout, fmt).date()
            
            occupied = 0
            for r in records:
                if r.get("Status") not in ["CONFIRMED", "PAID"]:
                    continue
                # The room name in sheet might include emojis, we strip them or match partially
                r_room = r.get("Room Type", "")
                if room_name not in r_room:
                    continue
                    
                r_in = datetime.strptime(r["Check-in"], fmt).date()
                r_out = datetime.strptime(r["Check-out"], fmt).date()
                
                # Overlap logic
                if (q_in < r_out) and (q_out > r_in):
                    occupied += 1
            return occupied
        except Exception as e:
            logger.error(f"Error calculating occupancy: {e}")
            return 0

    async def append_booking(self, b: list):
        """b is a list matching the headers: [ID, Status, Name, Phone, User, In, Out, Room, Guests, Special, Time]"""
        try:
            if not self.sheet:
                if not self._connect(): return
            self.sheet.append_row(b)
            logger.info("✅ Booking #%s synced to Sheets.", b[0])
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
