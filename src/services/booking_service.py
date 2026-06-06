from datetime import datetime

from src.services.database import Database
from src.services.sheets_service import SheetsService

DATE_FORMAT = "%d/%m/%Y"


class BookingService:
    def __init__(self, db: Database, sheets: SheetsService):
        self.db = db
        self.sheets = sheets

    async def get_available_rooms(self, rooms: list[dict], checkin: str, checkout: str) -> list[dict]:
        inventory = await self.sheets.get_room_inventory()
        available_rooms = []

        for room in rooms:
            name = room["name"]
            total = self._get_inventory_total(inventory, name)
            occupied = await self.sheets.get_occupied_count(name, checkin, checkout)
            remains = total - occupied

            room_copy = room.copy()
            room_copy["remains"] = remains
            room_copy["availability_text"] = f"({remains} left)" if remains > 0 else "(❌ Sold Out)"
            room_copy["is_available"] = remains > 0
            available_rooms.append(room_copy)

        return available_rooms

    async def create_pending_booking(self, user_id: int, username: str | None, booking_data: dict) -> int:
        booking_id = await self.db.create_booking(
            user_id=user_id,
            guest_name=booking_data["booking_name"],
            checkin_date=booking_data["booking_checkin"],
            checkout_date=booking_data["booking_checkout"],
            room_type=booking_data["booking_room"],
            num_guests=int(booking_data["booking_guests"]),
            special_request=booking_data.get("booking_special", "None"),
        )

        await self.sheets.append_booking(
            self.build_sheet_row(booking_id, self.format_username(username), booking_data)
        )
        return booking_id

    def build_sheet_row(self, booking_id: int, username: str, booking_data: dict) -> list:
        return [
            booking_id,
            "PENDING",
            booking_data["booking_name"],
            booking_data["booking_phone"],
            username,
            booking_data["booking_checkin"],
            booking_data["booking_checkout"],
            booking_data["booking_room"],
            booking_data["booking_guests"],
            booking_data.get("booking_special", "None"),
            booking_data.get("booking_room_id", "N/A"),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ]

    def build_summary_text(self, data: dict, lang: str) -> str:
        checkin = datetime.strptime(data["booking_checkin"], DATE_FORMAT)
        checkout = datetime.strptime(data["booking_checkout"], DATE_FORMAT)
        nights = (checkout - checkin).days
        labels = {
            "KH": ["ឈ្មោះ", "ទូរស័ព្ទ", "ថ្ងៃចូល", "ថ្ងៃចេញ", "ចំនួនយប់", "បន្ទប់", "ភ្ញៀវ", "សំណូមពរ"],
            "EN": ["Name", "Phone", "In", "Out", "Nights", "Room", "Guests", "Special"],
        }
        values = [
            data["booking_name"],
            data["booking_phone"],
            data["booking_checkin"],
            data["booking_checkout"],
            str(nights),
            data["booking_room"],
            data["booking_guests"],
            data.get("booking_special", "None"),
        ]
        header = "📝 <b>សេចក្តីសង្ខេបនៃការកក់</b>" if lang == "KH" else "📝 <b>BOOKING SUMMARY</b>"
        summary = f"{header}\n━━━━━━━━━━━━━━━━━━━━\n"
        for label, value in zip(labels[lang], values):
            padding = " " * max(0, 12 - len(label))
            summary += f"<b>{label}{padding}:</b> {value}\n"
        summary += "━━━━━━━━━━━━━━━━━━━━\n"
        return summary

    def get_special_request_label(self, request: str, lang: str) -> str:
        if request == "none":
            return "None"

        mapping = {
            "decor": "Room Decoration" if lang == "EN" else "ការតុបតែងបន្ទប់",
            "towels": "Extra Towels" if lang == "EN" else "កន្សែងបន្ថែម",
            "quiet": "Quiet Room" if lang == "EN" else "បន្ទប់ស្ងាត់",
            "early": "Early Check-in" if lang == "EN" else "ចូលមុនម៉ោង",
        }
        return mapping.get(request, request)

    def format_username(self, username: str | None) -> str:
        if not username:
            return "No Username"
        return username if username.startswith("@") else f"@{username}"

    def _get_inventory_total(self, inventory: dict, room_name: str) -> int:
        total = inventory.get(room_name, 0)
        if total:
            return total
        if "Bungalow" in room_name:
            return inventory.get(room_name.replace("Bungalow", "Bungalov"), 0)
        if "Bungalov" in room_name:
            return inventory.get(room_name.replace("Bungalov", "Bungalow"), 0)
        return 0
