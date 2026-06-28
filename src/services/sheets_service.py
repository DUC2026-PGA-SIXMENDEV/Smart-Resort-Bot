# ============================================================
#  bot/services/sheets_service.py — Google Sheets Integration
# ============================================================
import logging
import asyncio
import gspread
import asyncio
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
            # Explicitly connect to 'Sheet1' for bookings
            self.sheet = self.client.open(self.sheet_name).worksheet("Sheet1")
            
            headers = [
                "Booking ID", "Status", "Guest Name", "Phone / WhatsApp", 
                "Telegram Username", "Check-in", "Check-out", "Room Type", 
                "Guests", "Special Requests", "Room ID", "Timestamp"
            ]
            
            if not self.sheet.row_values(1):
                self.sheet.insert_row(headers, 1)
            return True
        except Exception as e:
            logger.error("❌ Sheets Error: %s", e)
            return False

    async def get_all_occupied_dates(self) -> dict:
        """Returns a dict mapping room names to lists of occupied date ranges."""
        try:
            if not self.sheet: self._connect()
            records = await asyncio.to_thread(self.sheet.get_all_records)
            
            occupied_map = {}
            for r in records:
                if r.get("Status") not in ["CONFIRMED", "PAID"]:
                    continue
                room = r.get("Room Type", "Unknown")
                checkin = r.get("Check-in")
                checkout = r.get("Check-out")
                if room and checkin and checkout:
                    if room not in occupied_map:
                        occupied_map[room] = []
                    occupied_map[room].append(f"{checkin} to {checkout}")
            return occupied_map
        except Exception as e:
            logger.error(f"Error fetching all occupied dates: {e}")
            return {}

    async def get_room_inventory(self) -> dict:
        """Fetches available room counts from the 'Rooms' tab (Non-blocking)."""
        try:
            if not self.client: self._connect()
            
            # Run blocking call in a separate thread to prevent lag for other users
            def fetch_data():
                sheet = self.client.open(self.sheet_name).worksheet("Rooms")
                return sheet.get_all_values()
            
            rows = await asyncio.to_thread(fetch_data)
            if not rows: return {}

            # Parse headers and find column indices
            headers = [str(h).strip().lower() for h in rows[0]]
            
            # Find column indices with flexible matching
            name_idx = None
            avail_idx = None
            
            for i, header in enumerate(headers):
                if "room type" in header or "room name" in header:
                    name_idx = i
                if "available" in header or "avail" in header:
                    avail_idx = i
            
            # Fallback to positional columns if header matching fails
            if name_idx is None or avail_idx is None:
                if len(rows[0]) >= 3:
                    name_idx = 0  # Column A: Room Type
                    avail_idx = 2  # Column C: Available
                    logger.warning("⚠️ Using positional columns (A, C) instead of header matching")
                else:
                    logger.error("❌ Could not find 'Room Type' or 'Available' columns in 'Rooms' tab.")
                    return {}

            inventory = {}
            for row in rows[1:]:  # Skip the header row
                if len(row) > max(name_idx, avail_idx):
                    name = str(row[name_idx]).strip()
                    avail = str(row[avail_idx]).strip()
                    if name:
                        try:
                            inventory[name] = int(avail)
                            logger.debug(f"✓ {name}: {avail} available")
                        except:
                            inventory[name] = 0
            
            logger.info(f"📊 Loaded inventory: {inventory}")
            return inventory
        except Exception as e:
            logger.error(f"Error fetching room inventory: {e}")
            return {}

    async def get_occupied_count(self, room_name: str, checkin: str, checkout: str) -> int:
        """Calculates how many rooms are booked (Non-blocking)."""
        try:
            if not self.sheet: self._connect()
            records = await asyncio.to_thread(self.sheet.get_all_records)
            
            fmt = "%d/%m/%Y"
            q_in = datetime.strptime(checkin, fmt).date()
            q_out = datetime.strptime(checkout, fmt).date()
            
            occupied = 0
            for r in records:
                if r.get("Status") not in ["CONFIRMED", "PAID"]:
                    continue
                r_room = r.get("Room Type", "")
                if room_name not in r_room:
                    continue
                    
                try:
                    r_in = datetime.strptime(r["Check-in"], fmt).date()
                    r_out = datetime.strptime(r["Check-out"], fmt).date()
                    if (q_in < r_out) and (q_out > r_in):
                        occupied += 1
                except: continue
            return occupied
        except Exception as e:
            logger.error(f"Error calculating occupancy: {e}")
            return 0

    async def get_bookings_during(self, checkin: str, checkout: str) -> list[dict]:
        """Fetches all sheet records and filters down to those overlapping with the requested date range."""
        try:
            if not self.sheet: self._connect()
            records = await asyncio.to_thread(self.sheet.get_all_records)
            
            fmt = "%d/%m/%Y"
            q_in = datetime.strptime(checkin, fmt).date()
            q_out = datetime.strptime(checkout, fmt).date()
            
            active_bookings = []
            for r in records:
                if r.get("Status") not in ["CONFIRMED", "PAID"]:
                    continue
                try:
                    r_in = datetime.strptime(r["Check-in"], fmt).date()
                    r_out = datetime.strptime(r["Check-out"], fmt).date()
                    if (q_in < r_out) and (q_out > r_in):
                        active_bookings.append(r)
                except: continue
            return active_bookings
        except Exception as e:
            logger.error(f"Error fetching bookings during range: {e}")
            return []

    async def append_booking(self, b: list):
        """Appends a booking row (Non-blocking)."""
        try:
            if not self.sheet:
                if not self._connect(): return
            await asyncio.to_thread(self.sheet.append_row, b)
            logger.info("✅ Booking #%s synced to Sheets.", b[0])
        except Exception as e:
            logger.error("❌ Sync failed: %s", e)

    async def update_booking_status(self, booking_id: int, new_status: str):
        """Updates status (Non-blocking)."""
        try:
            if not self.sheet:
                if not self._connect(): return
            
            def do_update():
                rows = self.sheet.get_all_values()
                target_id = str(booking_id).strip()
                matches = []

                for row_number, row in enumerate(rows[1:], start=2):
                    if row and str(row[0]).strip() == target_id:
                        status = str(row[1]).strip().upper() if len(row) > 1 else ""
                        matches.append((row_number, status))

                if not matches:
                    logger.warning("Booking ID %s not found in Sheets.", booking_id)
                    return

                preferred_statuses = {
                    "CONFIRMED": {"PENDING"},
                    "DECLINED": {"PENDING"},
                    "CHECKED OUT": {"CONFIRMED", "PAID"},
                }.get(new_status, set())

                row_to_update = None
                if preferred_statuses:
                    for row_number, status in reversed(matches):
                        if status in preferred_statuses:
                            row_to_update = row_number
                            break

                if row_to_update is None:
                    row_to_update = matches[-1][0]

                self.sheet.update_cell(row_to_update, 2, new_status)
                logger.info(
                    "Updated Sheets booking #%s row %s to %s.",
                    booking_id,
                    row_to_update,
                    new_status,
                )
            
            await asyncio.to_thread(do_update)
        except Exception as e:
            logger.error("❌ Status update failed: %s", e)

    async def decrease_room_available(self, room_name: str) -> bool:
        """Decrease 'Available' count in Rooms sheet when booking confirmed (Non-blocking)."""
        try:
            if not self.client: self._connect()
            
            def do_update():
                rooms_sheet = self.client.open(self.sheet_name).worksheet("Rooms")
                rows = rooms_sheet.get_all_values()
                
                headers = [str(h).strip() for h in rows[0]]
                try:
                    name_idx = headers.index("Room Type")
                    avail_idx = headers.index("Available")
                except ValueError:
                    logger.error("❌ 'Room Type' or 'Available' column missing in 'Rooms' tab.")
                    return False
                
                for i, row in enumerate(rows[1:], start=2):
                    if len(row) > max(name_idx, avail_idx):
                        if str(row[name_idx]).strip() == room_name.strip():
                            try:
                                current = int(str(row[avail_idx]).strip() or 0)
                                new_count = max(0, current - 1)
                                rooms_sheet.update_cell(i, avail_idx + 1, new_count)
                                logger.info(f"✅ Room '{room_name}' available decreased to {new_count}")
                                return True
                            except: pass
                return False
            
            return await asyncio.to_thread(do_update)
        except Exception as e:
            logger.error(f"❌ Failed to decrease room available: {e}")
            return False

    async def increase_room_available(self, room_name: str) -> bool:
        """Increase 'Available' count in Rooms sheet when checkout happens (Non-blocking)."""
        try:
            if not self.client: self._connect()
            
            def do_update():
                rooms_sheet = self.client.open(self.sheet_name).worksheet("Rooms")
                rows = rooms_sheet.get_all_values()
                
                headers = [str(h).strip() for h in rows[0]]
                try:
                    name_idx = headers.index("Room Type")
                    avail_idx = headers.index("Available")
                    total_idx = headers.index("Total Inventory")
                except ValueError:
                    logger.error("❌ Required columns missing in 'Rooms' tab.")
                    return False
                
                for i, row in enumerate(rows[1:], start=2):
                    if len(row) > max(name_idx, avail_idx, total_idx):
                        if str(row[name_idx]).strip() == room_name.strip():
                            try:
                                current = int(str(row[avail_idx]).strip() or 0)
                                total = int(str(row[total_idx]).strip() or 0)
                                new_count = min(total, current + 1)  # Don't exceed total
                                rooms_sheet.update_cell(i, avail_idx + 1, new_count)
                                logger.info(f"✅ Room '{room_name}' available increased to {new_count}")
                                return True
                            except: pass
                return False
            
            return await asyncio.to_thread(do_update)
        except Exception as e:
            logger.error(f"❌ Failed to increase room available: {e}")
            return False

    async def sync_checkout_availability(self):
        """Check for past checkouts and increase room availability accordingly (Non-blocking)."""
        try:
            if not self.sheet: self._connect()
            records = await asyncio.to_thread(self.sheet.get_all_records)
            
            today = datetime.now().date()
            fmt = "%d/%m/%Y"
            
            # Track rooms with past checkouts
            rooms_to_increase = {}
            for r in records:
                if r.get("Status") not in ["CONFIRMED", "PAID"]:
                    continue
                
                checkout_str = r.get("Check-out", "")
                if checkout_str:
                    try:
                        checkout_date = datetime.strptime(checkout_str, fmt).date()
                        if checkout_date <= today:  # Past checkout date
                            room_name = r.get("Room Type", "")
                            if room_name:
                                rooms_to_increase[room_name] = rooms_to_increase.get(room_name, 0) + 1
                    except: pass
            
            # Increase availability for rooms with past checkouts
            for room_name, count in rooms_to_increase.items():
                for _ in range(count):
                    await self.increase_room_available(room_name)
                    
        except Exception as e:
            logger.error(f"❌ Failed to sync checkout availability: {e}")
