import asyncio
import logging
import gspread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup  # type: ignore[import]
from telegram.ext import ContextTypes  # type: ignore[import]

logger = logging.getLogger(__name__)

class GspreadSheetsManager:
    def __init__(self, credentials_path: str, sheet_name: str):
        self.credentials_path = credentials_path
        self.sheet_name = sheet_name
        self.gc = None
        self.sh = None
        self.sheet1 = None
        self.rooms_sheet = None

    def _connect(self) -> bool:
        if self.sheet1 is not None and self.rooms_sheet is not None:
            return True

        try:
            self.gc = gspread.service_account(filename=self.credentials_path)
            self.sh = self.gc.open(self.sheet_name)
            self.sheet1 = self.sh.worksheet("Sheet1")
            self.rooms_sheet = self.sh.worksheet("Rooms")
            return True
        except Exception as e:
            logger.error("Sheets workflow connection failed: %s", e)
            return False

    def _clean_room_name(self, name: str) -> str:
        """Strips leading emojis/symbols so it matches Google Sheets plain text."""
        for i, char in enumerate(name):
            if char.isalnum():
                return name[i:].strip()
        return name.strip()

    def deduct_inventory(self, room_type: str) -> bool:
        """Subtracts 1 from the Available column for the given room type."""
        if not self._connect():
            return False

        try:
            rows = self.rooms_sheet.get_all_values()
            headers = [str(h).strip().lower() for h in rows[0]]
            
            # Find indices
            name_idx = None
            avail_idx = None
            for i, h in enumerate(headers):
                if "room type" in h or "room name" in h:
                    name_idx = i
                if "available" in h or "avail" in h:
                    avail_idx = i
            
            if name_idx is None or avail_idx is None:
                name_idx = 0
                avail_idx = 2
                
            clean_target = self._clean_room_name(room_type)
            for i, row in enumerate(rows[1:], start=2):
                if len(row) > max(name_idx, avail_idx):
                    row_room = str(row[name_idx]).strip()
                    clean_row_room = self._clean_room_name(row_room)
                    if row_room == room_type or clean_row_room == clean_target:
                        try:
                            current_available = int(str(row[avail_idx]).strip() or 0)
                            if current_available > 0:
                                self.rooms_sheet.update_cell(i, avail_idx + 1, current_available - 1)
                                return True
                            else:
                                print(f"⚠️ Room type '{room_type}' is already at 0 availability.")
                                return False
                        except ValueError:
                            pass
            print(f"❌ Room type '{room_type}' not found in Rooms sheet.")
            return False
        except Exception as e:
            print(f"❌ Error deducting inventory: {e}")
            return False

    def process_checkout(self, booking_id: str, room_type: str) -> bool:
        """Updates booking status to CHECKED OUT and adds 1 back to Available."""
        if not self._connect():
            return False

        # a) Look up Booking ID in "Sheet1" and update Status
        try:
            booking_cell = None
            try:
                booking_cell = self.sheet1.find(str(booking_id), in_column=1)
            except Exception:
                pass
            if booking_cell is not None:
                self.sheet1.update_cell(booking_cell.row, 2, "CHECKED OUT")
            else:
                print(f"⚠️ Booking ID '{booking_id}' not found in Sheet1. Still attempting to return room inventory...")
        except Exception as e:
            print(f"⚠️ Error updating Sheet1: {e}")

        # b) Look up Room Type in "Rooms" and restore availability
        try:
            rows = self.rooms_sheet.get_all_values()
            headers = [str(h).strip().lower() for h in rows[0]]
            
            # Find indices
            name_idx = None
            avail_idx = None
            total_idx = None
            for i, h in enumerate(headers):
                if "room type" in h or "room name" in h:
                    name_idx = i
                if "available" in h or "avail" in h:
                    avail_idx = i
                if "total" in h:
                    total_idx = i
            
            if name_idx is None or avail_idx is None:
                name_idx = 0
                avail_idx = 2
            if total_idx is None:
                total_idx = 1
                
            clean_target = self._clean_room_name(room_type)
            for i, row in enumerate(rows[1:], start=2):
                if len(row) > max(name_idx, avail_idx):
                    row_room = str(row[name_idx]).strip()
                    clean_row_room = self._clean_room_name(row_room)
                    if row_room == room_type or clean_row_room == clean_target:
                        try:
                            current_available = int(str(row[avail_idx]).strip() or 0)
                            total_inventory = int(str(row[total_idx]).strip() or 0) if len(row) > total_idx else 0
                            
                            if total_inventory <= 0 or current_available < total_inventory:
                                self.rooms_sheet.update_cell(i, avail_idx + 1, current_available + 1)
                                return True
                        except ValueError:
                            pass
            return False
        except Exception as e:
            print(f"❌ Error restoring room inventory: {e}")
            return False


# --- TELEGRAM BOT HANDLER LOGIC ---

async def notify_admin_of_booking(context: ContextTypes.DEFAULT_TYPE, admin_chat_id: int, booking_id: str, room_type: str, guest_name: str) -> bool:
    """Trigger this when a booking is CONFIRMED."""
    sheets_manager: GspreadSheetsManager = context.bot_data.get("gspread_manager")
    
    # 1. Subtract 1 from Available in Rooms sheet (Run in thread to prevent blocking the async bot)
    success = await asyncio.to_thread(sheets_manager.deduct_inventory, room_type)

    if not success:
        await context.bot.send_message(
            chat_id=admin_chat_id,
            text=f"⚠️ <b>Failed to Confirm Booking #{booking_id}</b>\n\nRoom type <b>{room_type}</b> has 0 available inventory in Google Sheets. Cannot deduct further.",
            parse_mode="HTML"
        )
        return False

    # 2. Send message to Admin Chat with the Process Check-out button
    text = (
        f"🆕 <b>New Booking Confirmed!</b>\n"
        f"<b>Booking ID:</b> {booking_id}\n"
        f"<b>Guest:</b> {guest_name}\n"
        f"<b>Room:</b> {room_type}"
    )
    
    keyboard = [[
        InlineKeyboardButton("✅ Process Check-out", callback_data=f"checkout_{booking_id}_{room_type}")
    ], [
        InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_main")
    ]]
    
    await context.bot.send_message(
        chat_id=admin_chat_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
    )
    
    return True

async def handle_admin_checkout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Register this in your ConversationHandler/Dispatcher to handle the Admin clicking 'Process Check-out'."""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("checkout_"):
        _, booking_id, room_type = query.data.split("_", 2)
        sheets_manager: GspreadSheetsManager = context.bot_data.get("gspread_manager")
        db = context.bot_data.get("db")
        
        # Execute the checkout workflow (update status & restore inventory in a thread)
        success = await asyncio.to_thread(sheets_manager.process_checkout, booking_id, room_type)
        
        # c) Edit the admin's Telegram message to show confirmation so they can't click it twice
        if success:
            if db:
                try:
                    b_id_int = int(booking_id)
                    await db.update_booking_status(b_id_int, "CHECKED OUT", "Processed via Admin Panel")
                    await db.refresh_availability_now()
                    
                    # --- Notify Customer of Check-out ---
                    booking = await db.get_booking(b_id_int)
                    if booking:
                        user_id = booking["user_id"]
                        user = await db.get_user(user_id)
                        lang = user.get("language", "EN") if user else "EN"
                        msg = (
                            f"👋 <b>ការចាកចេញ (Check-out) ទទួលបានជោគជ័យ!</b>\n\nសូមអរគុណសម្រាប់ការស្នាក់នៅបន្ទប់ <b>{room_type}</b> ជាមួយយើងខ្ញុំ។ សូមជូនពរលោកអ្នកធ្វើដំណើរប្រកបដោយសុវត្ថិភាព ហើយសង្ឃឹមថានឹងបានជួបលោកអ្នកម្តងទៀត!"
                            if lang == "KH" else
                            f"👋 <b>Check-out Successful!</b>\n\nThank you for staying in the <b>{room_type}</b> with us. Have a safe journey, and we hope to welcome you back soon!"
                        )
                        try:
                            await context.bot.send_message(chat_id=user_id, text=msg, parse_mode="HTML")
                        except Exception as e:
                            print(f"Failed to send checkout notification to user {user_id}: {e}")
                except ValueError:
                    print(f"⚠️ Could not parse booking_id '{booking_id}' for database update.")
            new_text = f"{query.message.text}\n\n<i>✅ CHECKED OUT PROCESSED & ROOM RETURNED</i>"
            keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_main")]]
            await query.edit_message_text(text=new_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        else:
            await query.answer("❌ Failed to checkout (Not found or already max capacity)", show_alert=True)
