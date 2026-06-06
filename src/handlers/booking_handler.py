# ============================================================
# bot/handlers/booking_handler.py - Booking Flow Logic
# ============================================================
import logging
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

from src.services.database import Database
from src.services.sheets_service import SheetsService
from src.keyboards.calendar import create_calendar
from src.keyboards.menus import (
    booking_room_availability_keyboard, 
    booking_special_keyboard,
    booking_confirm_keyboard,
    main_menu_keyboard,
    admin_booking_action_keyboard,
    booking_cancel_reply_keyboard,
    back_to_menu_keyboard
)

logger = logging.getLogger(__name__)

# Conversation States
NAME, PHONE, CHECKIN, CHECKOUT, ROOM_TYPE, GUESTS, SPECIAL, CONFIRM, ROOM_ID_INPUT = range(9)
DATE_FORMAT = "%d/%m/%Y"

class BookingHandler:
    def __init__(self, db: Database, admin_ids: list[int], sheets: SheetsService):
        self.db = db
        self.admin_ids = admin_ids
        self.sheets = sheets

    def _get_status_header(self, context: ContextTypes.DEFAULT_TYPE) -> str:
        """Helper to get a uniform 'You are booking a room' header banner."""
        if context.user_data.get("is_check_only"):
            return ""
        lang = context.user_data.get("lang", "EN")
        if lang == "KH":
            return "🛏️ <b>អ្នកកំពុងកក់បន្ទប់។ សូមបំពេញព័ត៌មានខាងក្រោម៖</b>\n━━━━━━━━━━━━━━━━━━\n"
        return "🛏️ <b>You are booking a room. Please fill out the form below:</b>\n━━━━━━━━━━━━━━━━━━\n"

    async def start_booking(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        if query:
            await query.answer()
            user_id = query.from_user.id
        else:
            user_id = update.effective_user.id

        user = await self.db.get_user(user_id)
        lang = user.get("language", "EN") if user else "EN"
        context.user_data["lang"] = lang 
        context.user_data["booking_data"] = {}
        context.user_data["is_editing"] = False
        context.user_data["is_check_only"] = False

        msg = self._get_status_header(context) + ("📅 <b>សូមជ្រើសរើសថ្ងៃចូលស្នាក់នៅ:</b>" if lang == "KH" else "📅 <b>Please select your Check-in date:</b>")
        if query:
            await query.edit_message_text(
                msg, 
                parse_mode=ParseMode.HTML, 
                reply_markup=create_calendar(lang=lang)
            )
        else:
            await update.message.reply_text(
                msg, 
                parse_mode=ParseMode.HTML, 
                reply_markup=create_calendar(lang=lang)
            )
        return CHECKIN

    async def start_check_availability(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        user = await self.db.get_user(user_id)
        lang = user.get("language", "EN") if user else "EN"
        context.user_data["lang"] = lang 
        context.user_data["booking_data"] = {}
        context.user_data["is_check_only"] = True
        context.user_data["is_editing"] = False

        # Show loading message first
        loading_msg = "⏳ <b>កំពុងគណនាបន្ទប់ទំនេរ... សូមរង់ចាំមួយភ្លែត</b>" if lang == "KH" else "⏳ <b>Calculating room availability... Please wait a moment</b>"
        await query.edit_message_text(loading_msg, parse_mode=ParseMode.HTML)

        # Fetch occupied dates
        occupied_map = await self.sheets.get_all_occupied_dates()
        resort_data = context.bot_data.get("resort_data", {})
        rooms = resort_data.get("rooms", [])

        title = "📅 <b>Room Availability (Occupied Dates):</b>" if lang == "EN" else "📅 <b>ស្ថានភាពបន្ទប់ (កាលបរិច្ឆេទដែលមានភ្ញៀវ):</b>"
        msg = f"{title}\n━━━━━━━━━━━━━━━━━━\n"
        
        for r in rooms:
            name = r["name"]
            rid = r["id"]
            dates = occupied_map.get(name, [])
            msg += f"🏠 <b>{name} (ID: {rid})</b>\n"
            if dates:
                msg += "❌ Occupied: " + ", ".join(dates) + "\n\n"
            else:
                msg += "✅ All dates available\n\n"

        prompt = "👉 Please click the button below to select a room by its ID:" if lang == "EN" else "👉 សូមចុចប៊ូតុងខាងក្រោមដើម្បីជ្រើសរើសបន្ទប់តាម ID:"
        msg += f"━━━━━━━━━━━━━━━━━━\n{prompt}"

        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🎯 Select Type Room", callback_data="input_room_id")]]) if lang == "EN" else \
                   InlineKeyboardMarkup([[InlineKeyboardButton("🎯 ជ្រើសរើសប្រភេទបន្ទប់", callback_data="input_room_id")]])

        await query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        return ROOM_ID_INPUT

    async def get_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        user = await self.db.get_user(user_id)
        lang = user.get("language", "EN") if user else "EN"
        context.user_data["lang"] = lang
        
        name = update.message.text.strip()
        # Delete user typed input message to clean up the chat
        try: await update.message.delete()
        except: pass

        # Check for cancel request
        if name in ["❌ Cancel Booking", "❌ បោះបង់ការកក់", "/cancel"]:
            return await self.cancel(update, context)

        # ✅ Standard Check: Name must not contain numeric characters.
        if any(char.isdigit() for char in name):
            last_msg_id = context.user_data.get("last_bot_msg_id")
            if last_msg_id:
                try: await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_msg_id)
                except: pass

            msg = self._get_status_header(context) + (
                "❌ <b>ឈ្មោះមិនអាចមានលេខទេ!</b> សូមបញ្ចូលឈ្មោះដោយប្រើតែអក្សរប៉ុណ្ណោះ។"
                if lang == "KH" else
                "❌ <b>Invalid name!</b> Name cannot include numbers. Please enter letters only."
            )
            sent_msg = await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=booking_cancel_reply_keyboard(lang))
            context.user_data["last_bot_msg_id"] = sent_msg.message_id
            return NAME
        
        # Delete the previous bot question prompt
        last_msg_id = context.user_data.get("last_bot_msg_id")
        if last_msg_id:
            try: await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_msg_id)
            except: pass
            context.user_data["last_bot_msg_id"] = None

        context.user_data["booking_data"]["booking_name"] = name
        
        if context.user_data.get("is_editing"):
            context.user_data["is_editing"] = False
            return await self.show_summary(update, context)

        msg = self._get_status_header(context) + ("📞 <b>សូមបញ្ចូលលេខទូរស័ព្ទរបស់អ្នក:</b>" if lang == "KH" else "📞 <b>Please enter your phone number:</b>")
        sent_msg = await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=booking_cancel_reply_keyboard(lang))
        context.user_data["last_bot_msg_id"] = sent_msg.message_id
        return PHONE

    async def get_phone(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        lang = context.user_data.get("lang", "EN")
        phone = update.message.text.strip()
        
        # Delete user typed input message to clean up the chat
        try: await update.message.delete()
        except: pass

        # Check for cancel request
        if phone in ["❌ Cancel Booking", "❌ បោះបង់ការកក់", "/cancel"]:
            return await self.cancel(update, context)

        # Convert Khmer digits to standard English/International digits
        khmer_digits = "០១២៣៤៥៦៧៨៩"
        english_digits = "0123456789"
        translation_table = str.maketrans(khmer_digits, english_digits)
        translated_phone = phone.translate(translation_table)

        # Phone Validation Check (strictly digits, no symbols or spaces, length >= 6)
        if not (translated_phone.isdigit() and len(translated_phone) >= 6):
            # Delete previous bot prompt if invalid
            last_msg_id = context.user_data.get("last_bot_msg_id")
            if last_msg_id:
                try: await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_msg_id)
                except: pass
                
            msg = self._get_status_header(context) + (
                "❌ <b>លេខទូរស័ព្ទមិនត្រឹមត្រូវទេ!</b> សូមបញ្ចូលតែលេខគត់សុទ្ធ គ្មាននិមិត្តសញ្ញា ឬដកឃ្លាឡើយ (ឧទាហរណ៍៖ 012345678 ឬ ០១២៣៤៥៦៧៨)៖"
                if lang == "KH" else
                "❌ <b>Invalid phone number!</b> Please enter only digits without any symbols or spaces (e.g., 012345678 or ០១២៣៤៥៦៧៨):"
            )
            sent_msg = await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=booking_cancel_reply_keyboard(lang))
            context.user_data["last_bot_msg_id"] = sent_msg.message_id
            return PHONE

        # Delete the previous bot question prompt
        last_msg_id = context.user_data.get("last_bot_msg_id")
        if last_msg_id:
            try: await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_msg_id)
            except: pass
            context.user_data["last_bot_msg_id"] = None

        context.user_data["booking_data"]["booking_phone"] = translated_phone
        
        if context.user_data.get("is_editing"):
            context.user_data["is_editing"] = False
            return await self.show_summary(update, context)

        msg = self._get_status_header(context) + ("👥 <b>តើមានភ្ញៀវប៉ុន្មាននាក់?</b>" if lang == "KH" else "👥 <b>How many guests in total?</b>")
        sent_msg = await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=booking_cancel_reply_keyboard(lang))
        context.user_data["last_bot_msg_id"] = sent_msg.message_id
        return GUESTS

    async def get_checkin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        data = query.data
        lang = context.user_data.get("lang", "EN")

        if data == "booking_cancel":
            return await self.cancel(update, context)

        if data.startswith("cal_nav_"):
            await query.answer()
            _, _, m, y = data.split("_")
            await query.edit_message_reply_markup(reply_markup=create_calendar(int(y), int(m), lang))
            return CHECKIN

        if data.startswith("cal_set_"):
            _, _, d, m, y = data.split("_")
            date_str = f"{int(d):02d}/{int(m):02d}/{y}"
            context.user_data["booking_data"]["booking_checkin"] = date_str
            
            # Interactive Pop-up Toast
            toast = f"📅 Check-in selected: {date_str}" if lang == "EN" else f"📅 បានជ្រើសរើសថ្ងៃចូល៖ {date_str}"
            await query.answer(toast)

            msg = self._get_status_header(context) + (
                f"✅ <b>Check-in: {date_str}</b>\n\n"
                "📅 <b>សូមជ្រើសរើសថ្ងៃចាកចេញ:</b>" if lang == "KH" else 
                f"✅ <b>Check-in: {date_str}</b>\n\n"
                "📅 <b>Please select your Check-out date:</b>"
            )
            await query.edit_message_text(
                msg, 
                parse_mode=ParseMode.HTML, 
                reply_markup=create_calendar(lang=lang)
            )
            return CHECKOUT
        
        await query.answer()
        return CHECKIN

    async def get_checkout(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        data = query.data
        lang = context.user_data.get("lang", "EN")

        if data == "booking_cancel":
            return await self.cancel(update, context)

        if data.startswith("cal_nav_"):
            await query.answer()
            _, _, m, y = data.split("_")
            await query.edit_message_reply_markup(reply_markup=create_calendar(int(y), int(m), lang))
            return CHECKOUT

        if data.startswith("cal_set_"):
            _, _, d, m, y = data.split("_")
            date_str = f"{int(d):02d}/{int(m):02d}/{y}"
            
            ci_str = context.user_data["booking_data"]["booking_checkin"]
            ci = datetime.strptime(ci_str, DATE_FORMAT)
            co = datetime.strptime(date_str, DATE_FORMAT)
            if co <= ci:
                msg = "❌ ថ្ងៃចេញត្រូវតែកក្រោយថ្ងៃចូល!" if lang == "KH" else "❌ Check-out must be after check-in!"
                await query.answer(msg, show_alert=True)
                return CHECKOUT

            # Interactive Pop-up Toast
            toast = f"📅 Check-out selected: {date_str}" if lang == "EN" else f"📅 បានជ្រើសរើសថ្ងៃចាកចេញ៖ {date_str}"
            await query.answer(toast)

            context.user_data["booking_data"]["booking_checkout"] = date_str

            # If room is already selected (from the Room ID flow), auto-fill name and go straight to phone
            if context.user_data["booking_data"].get("booking_room"):
                try: await query.message.delete()
                except: pass
                tg_user = query.from_user
                auto_name = (tg_user.full_name or tg_user.username or "Guest").strip()
                context.user_data["booking_data"]["booking_name"] = auto_name

                msg = self._get_status_header(context) + ("📞 <b>សូមបញ្ចូលលេខទូរស័ព្ទរបស់អ្នក:</b>" if lang == "KH" else "📞 <b>Please enter your phone number:</b>")
                sent_msg = await query.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=booking_cancel_reply_keyboard(lang))
                context.user_data["last_bot_msg_id"] = sent_msg.message_id
                return PHONE

            # Show loading message first
            loading_msg = "⏳ <b>កំពុងគណនាបន្ទប់ទំនេរ... សូមរង់ចាំមួយភ្លែត</b>" if lang == "KH" else "⏳ <b>Calculating room availability... Please wait a moment</b>"
            await query.edit_message_text(loading_msg, parse_mode=ParseMode.HTML)

            resort_data = context.bot_data.get("resort_data", {})
            rooms = resort_data.get("rooms", [])
            
            # Get check-in and checkout dates
            ci_str = context.user_data["booking_data"]["booking_checkin"]
            co_str = context.user_data["booking_data"]["booking_checkout"]
            
            # Fetch REAL-TIME available count from Google Sheets using database
            available_rooms = []
            for r in resort_data.get("rooms", []):
                name = r["name"]
                # Get available count from database (checks Sheets + accounts for bookings)
                remains = await self.db.check_availability(name, ci_str, co_str)
                
                r_copy = r.copy()
                r_copy["remains"] = remains
                r_copy["availability_text"] = f"({remains} left)" if remains > 0 else "(❌ Sold Out)"
                r_copy["is_available"] = remains > 0
                available_rooms.append(r_copy)

            msg_header = (
                f"✅ <b>Check-in:  {ci_str}</b>\n"
                f"✅ <b>Check-out: {co_str}</b>\n\n"
            )

            msg = self._get_status_header(context) + msg_header + ("🛌 <b>សូមជ្រើសរើសប្រភេទបន្ទប់:</b>" if lang == "KH" else "🛌 <b>Please select a room type:</b>")
            await query.edit_message_text(
                msg, 
                parse_mode=ParseMode.HTML, 
                reply_markup=booking_room_availability_keyboard(available_rooms, lang)
            )
            return ROOM_TYPE
        return CHECKOUT

    async def get_room_type(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        if query.data == "booking_cancel":
            return await self.cancel(update, context)

        lang = context.user_data.get("lang", "EN")
        room_id = query.data.replace("room_", "")
        resort_data = context.bot_data.get("resort_data", {})
        rooms = resort_data.get("rooms", [])
        room = next((r for r in rooms if r["id"] == room_id), None)
        
        if room:
            context.user_data["booking_data"]["booking_room_id"] = room_id
            context.user_data["booking_data"]["booking_room"] = f"{room['emoji']} {room['name']}"
            context.user_data["booking_data"]["price_per_night"] = room["price_per_night"]

        # Delete the room type calendar message to clean up the chat
        try: await query.message.delete()
        except: pass

        if context.user_data.get("is_editing"):
            context.user_data["is_editing"] = False
            return await self.show_summary(update, context)

        # Auto-fill name from Telegram profile
        tg_user = query.from_user
        auto_name = (tg_user.full_name or tg_user.username or "Guest").strip()
        context.user_data["booking_data"]["booking_name"] = auto_name

        msg = self._get_status_header(context) + ("📞 <b>សូមបញ្ចូលលេខទូរស័ព្ទរបស់អ្នក:</b>" if lang == "KH" else "📞 <b>Please enter your phone number:</b>")
        sent_msg = await query.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=booking_cancel_reply_keyboard(lang))
        context.user_data["last_bot_msg_id"] = sent_msg.message_id
        return PHONE

    async def room_type_text_blocked(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Block free text while waiting for room selection buttons."""
        try: await update.message.delete()
        except: pass
        return ROOM_TYPE

    async def checkin_text_blocked(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Block free text while waiting for check-in date selection buttons."""
        try: await update.message.delete()
        except: pass
        return CHECKIN

    async def checkout_text_blocked(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Block free text while waiting for check-out date selection buttons."""
        try: await update.message.delete()
        except: pass
        return CHECKOUT

    async def confirm_text_blocked(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Block free text while waiting for edit/confirm buttons."""
        try: await update.message.delete()
        except: pass
        return CONFIRM

    async def _auto_delete_hint(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int) -> None:
        """Legacy helper kept for compatibility; currently unused."""
        try:
            await asyncio.sleep(1.5)
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except:
            pass

    async def handle_room_id_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        lang = context.user_data.get("lang", "EN")
        
        # Delete the previous occupied dates prompt
        try: await query.message.delete()
        except: pass

        msg = "⌨️ <b>Please enter the Room ID (e.g., superior, deluxe):</b>" if lang == "EN" else "⌨️ <b>សូមបញ្ចូល Room ID (ឧទាហរណ៍: superior, deluxe):</b>"
        sent_msg = await query.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=booking_cancel_reply_keyboard(lang))
        context.user_data["last_bot_msg_id"] = sent_msg.message_id
        return ROOM_ID_INPUT

    async def get_room_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        lang = context.user_data.get("lang", "EN")
        room_id = update.message.text.strip().lower()
        
        # Delete user typed input message to clean up the chat
        try: await update.message.delete()
        except: pass

        # Check for cancel request
        if room_id in ["❌ cancel booking", "❌ បោះបង់ការកក់", "/cancel"]:
            return await self.cancel(update, context)

        resort_data = context.bot_data.get("resort_data", {})
        rooms = resort_data.get("rooms", [])
        room = next((r for r in rooms if r["id"] == room_id), None)
        
        if not room:
            # Delete previous bot prompt if invalid
            last_msg_id = context.user_data.get("last_bot_msg_id")
            if last_msg_id:
                try: await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_msg_id)
                except: pass

            msg = "❌ Invalid Room ID. Please try again:" if lang == "EN" else "❌ ID មិនត្រឹមត្រូវទេ។ សូមព្យាយាមម្តងទៀត:"
            sent_msg = await update.message.reply_text(msg, reply_markup=booking_cancel_reply_keyboard(lang))
            context.user_data["last_bot_msg_id"] = sent_msg.message_id
            return ROOM_ID_INPUT
            
        # Delete the previous bot question prompt
        last_msg_id = context.user_data.get("last_bot_msg_id")
        if last_msg_id:
            try: await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_msg_id)
            except: pass
            context.user_data["last_bot_msg_id"] = None

        context.user_data["booking_data"]["booking_room_id"] = room_id
        context.user_data["booking_data"]["booking_room"] = f"{room['emoji']} {room['name']}"
        context.user_data["booking_data"]["price_per_night"] = room["price_per_night"]

        msg = self._get_status_header(context) + ("📅 <b>សូមជ្រើសរើសថ្ងៃចូលស្នាក់នៅ:</b>" if lang == "KH" else "📅 <b>Please select your Check-in date:</b>")
        await update.message.reply_text(
            msg, 
            parse_mode=ParseMode.HTML, 
            reply_markup=create_calendar(lang=lang)
        )
        return CHECKIN

    async def get_guests(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        lang = context.user_data.get("lang", "EN")
        guests_str = update.message.text.strip()
        
        # Delete user typed input message to clean up the chat
        try: await update.message.delete()
        except: pass

        # Check for cancel request
        if guests_str in ["❌ Cancel Booking", "❌ បោះបង់ការកក់", "/cancel"]:
            return await self.cancel(update, context)

        # Convert Khmer digits to standard English/International digits
        khmer_digits = "០១២៣៤៥៦៧៨៩"
        english_digits = "0123456789"
        translation_table = str.maketrans(khmer_digits, english_digits)
        translated_guests = guests_str.translate(translation_table)

        # Guests Validation Check (must be positive integer)
        if not (translated_guests.isdigit() and int(translated_guests) > 0):
            # Delete previous bot prompt if invalid
            last_msg_id = context.user_data.get("last_bot_msg_id")
            if last_msg_id:
                try: await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_msg_id)
                except: pass

            msg = self._get_status_header(context) + (
                "❌ <b>ចំនួនភ្ញៀវមិនត្រឹមត្រូវទេ!</b> សូមបញ្ចូលចំនួនជាលេខគត់វិជ្ជមាន (ឧទាហរណ៍៖ 2 ឬ ២)៖"
                if lang == "KH" else
                "❌ <b>Invalid number of guests!</b> Please enter a valid positive number (e.g., 2 or ២):"
            )
            sent_msg = await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=booking_cancel_reply_keyboard(lang))
            context.user_data["last_bot_msg_id"] = sent_msg.message_id
            return GUESTS

        # Delete the previous bot question prompt
        last_msg_id = context.user_data.get("last_bot_msg_id")
        if last_msg_id:
            try: await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_msg_id)
            except: pass
            context.user_data["last_bot_msg_id"] = None

        context.user_data["booking_data"]["booking_guests"] = translated_guests

        if context.user_data.get("is_editing"):
            context.user_data["is_editing"] = False
            return await self.show_summary(update, context)

        msg = self._get_status_header(context) + ("📝 <b>តើលោកអ្នកមានសំណូមពរពិសេសអ្វីខ្លះ?</b>" if lang == "KH" else "📝 <b>Any special requests?</b>")
        sent_msg = await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=booking_special_keyboard(lang))
        context.user_data["last_bot_msg_id"] = sent_msg.message_id
        return SPECIAL

    async def get_special(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        lang = context.user_data.get("lang", "EN")
        request = query.data.replace("sp_", "")
        
        if request == "none":
            context.user_data["booking_data"]["booking_special"] = "None"
        else:
            mapping = {
                "decor": "Room Decoration" if lang == "EN" else "ការតុបតែងបន្ទប់",
                "towels": "Extra Towels" if lang == "EN" else "កន្សែងបន្ថែម",
                "quiet": "Quiet Room" if lang == "EN" else "បន្ទប់ស្ងាត់",
                "early": "Early Check-in" if lang == "EN" else "ចូលមុនម៉ោង"
            }
            context.user_data["booking_data"]["booking_special"] = mapping.get(request, request)

        # Clear last bot msg id since we are editing this exact message
        context.user_data["last_bot_msg_id"] = None

        # Edit the message directly to show summary and confirm buttons!
        await query.edit_message_text(
            self._get_summary_text(context.user_data["booking_data"], lang),
            parse_mode=ParseMode.HTML,
            reply_markup=booking_confirm_keyboard(lang)
        )
        return CONFIRM

    async def special_text_blocked(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Blocks text input during the Special Request step and deletes the message."""
        try:
            await update.message.delete()
        except:
            pass
        return SPECIAL
        

    async def confirm_booking(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        lang = context.user_data.get("lang", "EN")
        data = query.data

        # Handle cancel directly from summary/action buttons.
        if data == "booking_cancel":
            return await self.cancel(update, context)

        if data == "booking_edit_menu":
            from bot.keyboards.menus import booking_edit_menu_keyboard
            msg = "✏️ <b>តើអ្នកចង់កែប្រែអ្វី?</b>" if lang == "KH" else "✏️ <b>What would you like to edit?</b>"
            await query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=booking_edit_menu_keyboard(lang))
            return CONFIRM

        # --- Handle individual edits ---
        context.user_data["is_editing"] = True

        if data == "edit_name":
            msg = "👤 <b>សូមបញ្ចូលឈ្មោះថ្មី:</b>" if lang == "KH" else "👤 <b>Please enter new name:</b>"
            await query.edit_message_text(msg, parse_mode=ParseMode.HTML)
            context.user_data["last_bot_msg_id"] = query.message.message_id
            return NAME
        
        if data == "edit_phone":
            msg = "📞 <b>សូមបញ្ចូលលេខទូរស័ព្ទថ្មី:</b>" if lang == "KH" else "📞 <b>Please enter new phone number:</b>"
            await query.edit_message_text(msg, parse_mode=ParseMode.HTML)
            context.user_data["last_bot_msg_id"] = query.message.message_id
            return PHONE
        
        if data == "edit_room":
            # Show loading message first
            loading_msg = "⏳ <b>កំពុងគណនាបន្ទប់ទំនេរ... សូមរង់ចាំមួយភ្លែត</b>" if lang == "KH" else "⏳ <b>Calculating room availability... Please wait a moment</b>"
            await query.edit_message_text(loading_msg, parse_mode=ParseMode.HTML)

            # Recalculate availability for current dates
            ci_str = context.user_data["booking_data"]["booking_checkin"]
            co_str = context.user_data["booking_data"]["booking_checkout"]
            resort_data = context.bot_data.get("resort_data", {})
            
            # Fetch REAL-TIME available count using database
            available_rooms = []
            for r in resort_data.get("rooms", []):
                # Get available count from database (checks Sheets + accounts for bookings)
                remains = await self.db.check_availability(r["name"], ci_str, co_str)
                
                r_copy = r.copy()
                r_copy["remains"] = remains
                r_copy["availability_text"] = f"({remains} left)" if remains > 0 else "(❌ Sold Out)"
                r_copy["is_available"] = remains > 0
                available_rooms.append(r_copy)

            from bot.keyboards.menus import booking_room_availability_keyboard
            msg = "🛌 <b>សូមជ្រើសរើសប្រភេទបន្ទប់ថ្មី:</b>" if lang == "KH" else "🛌 <b>Please select new room type:</b>"
            await query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=booking_room_availability_keyboard(available_rooms, lang))
            return ROOM_TYPE

        if data == "edit_guests":
            msg = "👥 <b>តើមានភ្ញៀវប៉ុន្មាននាក់?</b>" if lang == "KH" else "👥 <b>How many guests in total?</b>"
            await query.edit_message_text(msg, parse_mode=ParseMode.HTML)
            context.user_data["last_bot_msg_id"] = query.message.message_id
            return GUESTS
        
        if data == "edit_special":
            from bot.keyboards.menus import booking_special_keyboard
            msg = "📝 <b>តើលោកអ្នកមានសំណូមពរពិសេសអ្វីខ្លះ?</b>" if lang == "KH" else "📝 <b>Any special requests?</b>"
            await query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=booking_special_keyboard(lang))
            return SPECIAL

        if data == "booking_back_to_summary":
            await query.edit_message_text(
                self._get_summary_text(context.user_data["booking_data"], lang),
                parse_mode=ParseMode.HTML,
                reply_markup=booking_confirm_keyboard(lang)
            )
            return CONFIRM

        if data == "booking_confirm":
            booking_data = context.user_data["booking_data"]
            username = update.effective_user.username
            if username:
                username = f"@{username}" if not username.startswith("@") else username
            else:
                username = "No Username"

            bid = await self.db.create_booking(
                user_id=update.effective_user.id,
                guest_name=booking_data["booking_name"],
                guest_phone=booking_data["booking_phone"],
                checkin_date=booking_data["booking_checkin"],
                checkout_date=booking_data["booking_checkout"],
                room_type=booking_data["booking_room"],
                num_guests=int(booking_data["booking_guests"]),
                special_request=booking_data.get("booking_special", "None")
            )
            
            try:
                await self.sheets.append_booking([
                    bid, "PENDING", booking_data["booking_name"], booking_data["booking_phone"],
                    username, booking_data["booking_checkin"],
                    booking_data["booking_checkout"], booking_data["booking_room"],
                    int(booking_data["booking_guests"]), booking_data.get("booking_special", "None"),
                    booking_data.get("booking_room_id", "N/A"),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ])
            except Exception as e:
                logger.error(f"Google Sheets Error: {e}")

            await self._notify_admins(bid, booking_data, update.effective_user, context)

            # Silent remove reply keyboard
            try:
                remove_msg = await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="🧹",
                    reply_markup=ReplyKeyboardRemove()
                )
                await remove_msg.delete()
            except:
                pass

            success_msg = (
                "🙏 <b>សូមអរគុណសម្រាប់ការកក់របស់អ្នក!</b>\n\n"
                "⏳ ការកក់របស់អ្នកត្រូវបានបញ្ជូនរួចហើយ និងកំពុងរង់ចាំការពិនិត្យ/អនុម័តពីអ្នកគ្រប់គ្រង (Admin)។ យើងខ្ញុំនឹងទាក់ទងទៅអ្នកក្នុងពេលឆាប់ៗនេះ!"
                if lang == "KH" else
                "🙏 <b>Thank you for your booking request!</b>\n\n"
                "⏳ Your booking is currently pending and waiting for admin approval. We will contact you shortly to confirm your booking!"
            )
            await query.edit_message_text(success_msg, parse_mode=ParseMode.HTML, reply_markup=back_to_menu_keyboard(lang))
            return ConversationHandler.END

    async def show_summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Helper to show summary and return CONFIRM state."""
        lang = context.user_data.get("lang", "EN")
        text = self._get_summary_text(context.user_data["booking_data"], lang)
        from bot.keyboards.menus import booking_confirm_keyboard
        
        # Delete previous bot prompt if it exists to keep chat clean
        last_msg_id = context.user_data.get("last_bot_msg_id")
        if last_msg_id:
            try: await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_msg_id)
            except: pass
            context.user_data["last_bot_msg_id"] = None
            
        if update.callback_query:
            await update.callback_query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=booking_confirm_keyboard(lang))
        else:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=booking_confirm_keyboard(lang))
        return CONFIRM

    def _get_summary_text(self, data, lang):
        d1 = datetime.strptime(data["booking_checkin"], DATE_FORMAT)
        d2 = datetime.strptime(data["booking_checkout"], DATE_FORMAT)
        nights = (d2 - d1).days
        
        # ទាញយកឈ្មោះបន្ទប់បច្ចុប្បន្ន
        room_display = data["booking_room"]
        
        # បកប្រែឈ្មោះបន្ទប់ទៅជាភាសាខ្មែរ ប្រសិនបើភ្ញៀវជ្រើសរើសភាសាខ្មែរ (KH)
        if lang == "KH":
            room_translations = {
                "Single Bed Room": "បន្ទប់គ្រែមួយ",
                "Double Room": "បន្ទប់គ្រែមួយ",
                "Twin Room": "បន្ទប់គ្រែពីរ",
                "Family Room": "បន្ទប់គ្រួសារ",
                "Standard Room": "បន្ទប់ធម្មតា",
                "Fan Room": "បន្ទប់កង្ហារ",
                "Deluxe": "បន្ទប់ប្រណិត",
                "VIP": "បន្ទប់ VIP"
            }
            # ស្វែងរកពាក្យអង់គ្លេស ហើយជំនួសដោយពាក្យខ្មែរ
            for eng, kh in room_translations.items():
                if eng in room_display:
                    room_display = room_display.replace(eng, kh)
        
        labels = {
            "KH": [("👤", "ឈ្មោះ"), ("📞", "ទូរស័ព្ទ"), ("📅", "ថ្ងៃចូល"), ("📅", "ថ្ងៃចេញ"), ("🌙", "ចំនួនយប់"), ("🛌", "បន្ទប់"), ("👥", "ភ្ញៀវ"), ("📝", "សំណូមពរ")],
            "EN": [("👤", "Name"), ("📞", "Phone"), ("📅", "In"), ("📅", "Out"), ("🌙", "Nights"), ("🛌", "Room"), ("👥", "Guests"), ("📝", "Special")]
        }
        
        cur_labels = labels[lang]
        val = [
            data["booking_name"], data["booking_phone"], data["booking_checkin"],
            data["booking_checkout"], str(nights), room_display, # ប្រើប្រាស់ឈ្មោះបន្ទប់ដែលបានបកប្រែរួច
            data["booking_guests"], data.get("booking_special", "None")
        ]
        
        header = "📋 <b>សេចក្តីសង្ខេបនៃការកក់</b>" if lang == "KH" else "📋 <b>BOOKING SUMMARY</b>"
        summary = f"{header}\n━━━━━━━━━━━━━━━━━━\n\n"
        
        for (emoji, label), v in zip(cur_labels, val):
            summary += f"{emoji} <b>{label}</b>  :  {v}\n\n"
            
        summary += "━━━━━━━━━━━━━━━━━━\n"
        return summary

    async def _notify_admins(self, bid, data, user, context):
        username = user.username
        if username:
            username = f"@{username}" if not username.startswith("@") else username
            tg_link = f"<a href='https://t.me/{username.replace('@', '')}'>{username}</a>"
        else:
            tg_link = "No Username"
        
        # Get resort contact info
        resort_data = context.bot_data.get("resort_data", {})
        resort_contact = resort_data.get("resort", {}).get("contact", {})
        resort_phone = resort_contact.get("phone", "+855 12 345 678")
        resort_email = resort_contact.get("email", "info@resort.com")
            
        text = (
            f"🔔 <b>NEW BOOKING ALERT! (# {bid})</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Guest:</b> {data['booking_name']}\n"
            f"📞 <b>Phone:</b> {data['booking_phone']}\n"
            f"🆔 <b>Telegram:</b> {tg_link}\n"
            f"🛌 <b>Room:</b> {data['booking_room']}\n"
            f"👥 <b>Guests:</b> {data['booking_guests']}\n"
            f"📅 <b>Check-in:</b> {data['booking_checkin']}\n"
            f"📅 <b>Check-out:</b> {data['booking_checkout']}\n"
            f"📝 <b>Special Request:</b> {data.get('booking_special', 'None')}\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"📞 <b>Resort Contact / ទាក់ទងរីសត:</b>\n"
            f"☎️ {resort_phone}\n"
            f"📧 {resort_email}\n\n"
            f"<i>Share with guest / ចែករំលែកឲ្យភ្ញៀវ</i>"
        )
        for aid in self.admin_ids:
            try: 
                msg = await context.bot.send_message(chat_id=aid, text=text, parse_mode=ParseMode.HTML, reply_markup=admin_booking_action_keyboard(bid))
                await self.db.add_admin_notification(bid, aid, msg.message_id)
            except: pass

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        lang = context.user_data.get("lang", "EN")
        
        # Cleanup last bot msg id if exists
        last_msg_id = context.user_data.get("last_bot_msg_id")
        if last_msg_id:
            try: await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_msg_id)
            except: pass
            context.user_data["last_bot_msg_id"] = None
            
        # Silent remove reply keyboard
        try:
            remove_msg = await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="🧹",
                reply_markup=ReplyKeyboardRemove()
            )
            await remove_msg.delete()
        except:
            pass

        text = (
            f"🙏 <b>រីករាយដែលបានជួបអ្នកម្តងទៀត!</b>\n"
            "តើមានអ្វីដែលខ្ញុំអាចជួយអ្នកបាន?"
        ) if lang == "KH" else (
            f"🙏 <b>Welcome back!</b>\n"
            "How can I assist you today?"
        )

        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard(lang))
        else:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard(lang))
        return ConversationHandler.END
