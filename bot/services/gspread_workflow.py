import asyncio
import gspread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup  # type: ignore[import]
from telegram.ext import ContextTypes  # type: ignore[import]

class GspreadSheetsManager:
    def __init__(self, credentials_path: str, sheet_name: str):
        # Initialize gspread connection
        self.gc = gspread.service_account(filename=credentials_path)
        self.sh = self.gc.open(sheet_name)
        self.sheet1 = self.sh.worksheet("Sheet1")
        self.rooms_sheet = self.sh.worksheet("Rooms")

    def _clean_room_name(self, name: str) -> str:
        """Strips leading emojis/symbols so it matches Google Sheets plain text."""
        for i, char in enumerate(name):
            if char.isalnum():
                return name[i:].strip()
        return name.strip()

    def deduct_inventory(self, room_type: str) -> bool:
        """Subtracts 1 from the Available column for the given room type."""
        try:
            # Try exact match first, if not found, strip the emoji
            try:
                cell = self.rooms_sheet.find(room_type, in_column=1)
            except Exception:
                cell = None
                
            if cell is None:
                clean_room = self._clean_room_name(room_type)
                try:
                    cell = self.rooms_sheet.find(clean_room, in_column=1)
                except Exception:
                    cell = None
                    
            if cell is None:
                print(f"❌ Room type '{room_type}' not found in Rooms sheet.")
                return False
            
            # Get current available count from Column C (index 3)
            try:
                val = self.rooms_sheet.cell(cell.row, 3).value
                current_available = int(val) if val else 0
            except ValueError:
                current_available = 0
            
            # Prevent available going below 0 (Fixes the -1 bug)
            if current_available > 0:
                self.rooms_sheet.update_cell(cell.row, 3, current_available - 1)
                return True
            else:
                print(f"⚠️ Room type '{room_type}' is already at 0 availability.")
                return False
        except Exception as e:
            print(f"❌ Error deducting inventory: {e}")
            return False

    def process_checkout(self, booking_id: str, room_type: str) -> bool:
        """Updates booking status to CHECKED OUT and adds 1 back to Available."""
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
            try:
                room_cell = self.rooms_sheet.find(room_type, in_column=1)
            except Exception:
                room_cell = None
                
            if room_cell is None:
                clean_room = self._clean_room_name(room_type)
                try:
                    room_cell = self.rooms_sheet.find(clean_room, in_column=1)
                except Exception:
                    room_cell = None
                    
            if room_cell is None:
                print(f"❌ Room type '{room_type}' not found in Rooms sheet.")
                return False
                
            # Get current available count from Column C (index 3)
            try:
                c_val = self.rooms_sheet.cell(room_cell.row, 3).value
                current_available = int(c_val) if c_val else 0
            except ValueError:
                current_available = 0
                
            # Get total inventory from Column B (index 2) to ensure we don't go over max capacity
            try:
                t_val = self.rooms_sheet.cell(room_cell.row, 2).value
                total_inventory = int(t_val) if t_val else 0
            except ValueError:
                total_inventory = 0
            
            # Ensure we restore inventory even if total_inventory is empty (0)
            if total_inventory <= 0 or current_available < total_inventory:
                # Update dynamically at the found row (Raw Integer Update)
                self.rooms_sheet.update_cell(room_cell.row, 3, current_available + 1)
        except Exception as e:
            print(f"❌ Error restoring room inventory: {e}")
            return False
            
        return True


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