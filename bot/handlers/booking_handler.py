# ============================================================
#  bot/handlers/booking_handler.py — Booking Flow Logic
# ============================================================
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

from bot.services.database import Database
from bot.services.sheets_service import SheetsService
from bot.keyboards.calendar import create_calendar
from bot.keyboards.menus import (
    booking_room_availability_keyboard, 
    booking_special_keyboard,
    booking_confirm_keyboard,
    main_menu_keyboard,
    admin_booking_action_keyboard
)

logger = logging.getLogger(__name__)

# Conversation States
NAME, PHONE, CHECKIN, CHECKOUT, ROOM_TYPE, GUESTS, SPECIAL, CONFIRM = range(8)
DATE_FORMAT = "%d/%m/%Y"

class BookingHandler:
    def __init__(self, db: Database, admin_ids: list[int], sheets: SheetsService):
        self.db = db
        self.admin_ids = admin_ids
        self.sheets = sheets

    async def start_booking(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        user = await self.db.get_user(user_id)
        lang = user.get("language", "EN") if user else "EN"
        context.user_data["lang"] = lang 
        context.user_data["booking_data"] = {}
        context.user_data["is_editing"] = False
        context.user_data["is_check_only"] = False

        if query.data.startswith("booking_room_"):
            room_id = query.data.replace("booking_room_", "")
            resort_data = context.bot_data.get("resort_data", {})
            rooms = resort_data.get("rooms", [])
            room = next((r for r in rooms if r["id"] == room_id), None)
            if room:
                context.user_data["booking_data"]["booking_room_id"] = room_id
                context.user_data["booking_data"]["booking_room"] = f"{room['emoji']} {room['name']}"
                context.user_data["booking_data"]["price_per_night"] = room["price_per_night"]

        msg = "👤 <b>សូមបញ្ចូលឈ្មោះរបស់អ្នក:</b>" if lang == "KH" else "👤 <b>Please enter your full name:</b>"
        await query.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return NAME

    async def start_check_availability(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """New entrance: Skip name/phone and go straight to dates."""
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        user = await self.db.get_user(user_id)
        lang = user.get("language", "EN") if user else "EN"
        context.user_data["lang"] = lang 
        context.user_data["booking_data"] = {}
        context.user_data["is_check_only"] = True
        context.user_data["is_editing"] = False

        msg = "📅 <b>សូមជ្រើសរើសថ្ងៃចូលស្នាក់នៅ:</b>" if lang == "KH" else "📅 <b>Please select your Check-in date:</b>"
        await query.message.reply_text(
            msg, 
            parse_mode=ParseMode.HTML, 
            reply_markup=create_calendar(lang=lang)
        )
        return CHECKIN

    async def get_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        user = await self.db.get_user(user_id)
        lang = user.get("language", "EN") if user else "EN"
        context.user_data["lang"] = lang
        
        name = update.message.text
        context.user_data["booking_data"]["booking_name"] = name
        
        if context.user_data.get("is_editing"):
            context.user_data["is_editing"] = False
            return await self.show_summary(update, context)

        msg = "📞 <b>សូមបញ្ចូលលេខទូរស័ព្ទរបស់អ្នក:</b>" if lang == "KH" else "📞 <b>Please enter your phone number:</b>"
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return PHONE

    async def get_phone(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        lang = context.user_data.get("lang", "EN")
        phone = update.message.text
        context.user_data["booking_data"]["booking_phone"] = phone
        
        if context.user_data.get("is_editing"):
            context.user_data["is_editing"] = False
            return await self.show_summary(update, context)

        msg = "📅 <b>សូមជ្រើសរើសថ្ងៃចូលស្នាក់នៅ:</b>" if lang == "KH" else "📅 <b>Please select your Check-in date:</b>"
        await update.message.reply_text(
            msg, 
            parse_mode=ParseMode.HTML, 
            reply_markup=create_calendar(lang=lang)
        )
        return CHECKIN

    async def get_checkin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        data = query.data
        lang = context.user_data.get("lang", "EN")

        if data.startswith("cal_nav_"):
            _, _, m, y = data.split("_")
            await query.edit_message_reply_markup(reply_markup=create_calendar(int(y), int(m), lang))
            return CHECKIN

        if data.startswith("cal_set_"):
            _, _, d, m, y = data.split("_")
            date_str = f"{int(d):02d}/{int(m):02d}/{y}"
            context.user_data["booking_data"]["booking_checkin"] = date_str
            
            msg = (
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
        return CHECKIN

    async def get_checkout(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        data = query.data
        lang = context.user_data.get("lang", "EN")

        if data.startswith("cal_nav_"):
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
                msg = "❌ ថ្ងៃចេញត្រូវតែក្រោយថ្ងៃចូល!" if lang == "KH" else "❌ Check-out must be after check-in!"
                await query.answer(msg, show_alert=True)
                return CHECKOUT

            context.user_data["booking_data"]["booking_checkout"] = date_str
            
            resort_data = context.bot_data.get("resort_data", {})
            rooms = resort_data.get("rooms", [])
            inventory = await self.sheets.get_room_inventory()
            
            available_rooms = []
            for r in resort_data.get("rooms", []):
                name = r["name"]
                # Flexible name matching
                total = inventory.get(name, 0)
                if total == 0:
                    # Try common spelling variations
                    if "Bungalow" in name: total = inventory.get(name.replace("Bungalow", "Bungalov"), 0)
                    if "Bungalov" in name: total = inventory.get(name.replace("Bungalov", "Bungalow"), 0)
                
                occupied = await self.sheets.get_occupied_count(name, ci_str, date_str)
                remains = total - occupied
                r_copy = r.copy()
                r_copy["remains"] = remains
                r_copy["availability_text"] = f"({remains} left)" if remains > 0 else "(❌ Sold Out)"
                r_copy["is_available"] = remains > 0
                available_rooms.append(r_copy)

            msg_header = (
                f"✅ <b>Check-in:  {ci_str}</b>\n"
                f"✅ <b>Check-out: {date_str}</b>\n\n"
            )

            if "booking_room_id" in context.user_data["booking_data"]:
                room_name = context.user_data["booking_data"]["booking_room"].split(" ", 1)[1]
                total = inventory.get(room_name, 0)
                occupied = await self.sheets.get_occupied_count(room_name, ci_str, date_str)
                if total - occupied <= 0:
                    msg = msg_header + "⚠️ <b>បន្ទប់ដែលអ្នកបានជ្រើសរើសគឺពេញហើយសម្រាប់ថ្ងៃនេះ។ សូមជ្រើសរើសបន្ទប់ផ្សេងទៀត:</b>" if lang == "KH" else \
                          msg_header + "⚠️ <b>Your selected room is SOLD OUT for these dates. Please choose another:</b>"
                    del context.user_data["booking_data"]["booking_room_id"]
                else:
                    msg = msg_header + ("👥 <b>តើមានភ្ញៀវប៉ុន្មាននាក់?</b>" if lang == "KH" else "👥 <b>How many guests in total?</b>")
                    await query.edit_message_text(msg, parse_mode=ParseMode.HTML)
                    return GUESTS

            msg = msg_header + ("🛏️ <b>សូមជ្រើសរើសប្រភេទបន្ទប់:</b>" if lang == "KH" else "🛏️ <b>Please select a room type:</b>")
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

        if context.user_data.get("is_editing"):
            context.user_data["is_editing"] = False # Proceed to full booking
            return await self.show_summary(update, context)

        # If they came from "Check Availability", we now need their name/phone to continue
        if context.user_data.get("is_check_only"):
            context.user_data["is_check_only"] = False # Proceed to full booking
            msg = "👤 <b>សូមបញ្ចូលឈ្មោះរបស់អ្នកដើម្បីបន្តការកក់:</b>" if lang == "KH" else "👤 <b>Please enter your full name to continue booking:</b>"
            await query.message.reply_text(msg, parse_mode=ParseMode.HTML)
            return NAME

        msg = "👥 <b>តើមានភ្ញៀវប៉ុន្មាននាក់?</b>" if lang == "KH" else "👥 <b>How many guests in total?</b>"
        await query.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return GUESTS

    async def get_guests(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        lang = context.user_data.get("lang", "EN")
        context.user_data["booking_data"]["booking_guests"] = update.message.text

        if context.user_data.get("is_editing"):
            context.user_data["is_editing"] = False
            return await self.show_summary(update, context)

        msg = "📝 <b>តើលោកអ្នកមានសំណូមពរពិសេសអ្វីខ្លះ?</b>" if lang == "KH" else "📝 <b>Any special requests?</b>"
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=booking_special_keyboard(lang))
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

        await query.message.reply_text(
            self._get_summary_text(context.user_data["booking_data"], lang),
            parse_mode=ParseMode.HTML,
            reply_markup=booking_confirm_keyboard(lang)
        )
        return CONFIRM

    async def confirm_booking(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        lang = context.user_data.get("lang", "EN")
        data = query.data

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
            return NAME
        
        if data == "edit_phone":
            msg = "📞 <b>សូមបញ្ចូលលេខទូរស័ព្ទថ្មី:</b>" if lang == "KH" else "📞 <b>Please enter new phone number:</b>"
            await query.edit_message_text(msg, parse_mode=ParseMode.HTML)
            return PHONE
        
        if data == "edit_dates":
            msg = "📅 <b>សូមជ្រើសរើសថ្ងៃចូលស្នាក់នៅថ្មី:</b>" if lang == "KH" else "📅 <b>Please select new Check-in date:</b>"
            await query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=create_calendar(lang=lang))
            return CHECKIN
        
        if data == "edit_room":
            # Recalculate availability for current dates
            ci_str = context.user_data["booking_data"]["booking_checkin"]
            co_str = context.user_data["booking_data"]["booking_checkout"]
            resort_data = context.bot_data.get("resort_data", {})
            inventory = await self.sheets.get_room_inventory()
            
            available_rooms = []
            for r in resort_data.get("rooms", []):
                occupied = await self.sheets.get_occupied_count(r["name"], ci_str, co_str)
                remains = inventory.get(r["name"], 0) - occupied
                r_copy = r.copy()
                r_copy["availability_text"] = f"({remains} left)" if remains > 0 else "(❌ Sold Out)"
                r_copy["is_available"] = remains > 0
                available_rooms.append(r_copy)

            from bot.keyboards.menus import booking_room_availability_keyboard
            msg = "🛏️ <b>សូមជ្រើសរើសប្រភេទបន្ទប់ថ្មី:</b>" if lang == "KH" else "🛏️ <b>Please select new room type:</b>"
            await query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=booking_room_availability_keyboard(available_rooms, lang))
            return ROOM_TYPE

        if data == "edit_guests":
            msg = "👥 <b>តើមានភ្ញៀវប៉ុន្មាននាក់?</b>" if lang == "KH" else "👥 <b>How many guests in total?</b>"
            await query.edit_message_text(msg, parse_mode=ParseMode.HTML)
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
                    booking_data["booking_guests"], booking_data.get("booking_special", "None"),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ])
            except Exception as e:
                logger.error(f"Google Sheets Error: {e}")

            await self._notify_admins(bid, booking_data, update.effective_user, context)
            success_msg = "🙏 <b>សូមអរគុណសម្រាប់ការកក់!</b>" if lang == "KH" else "🙏 <b>Thank you for your booking!</b>"
            await query.edit_message_text(success_msg, parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard(lang))
            return ConversationHandler.END

    async def show_summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Helper to show summary and return CONFIRM state."""
        lang = context.user_data.get("lang", "EN")
        text = self._get_summary_text(context.user_data["booking_data"], lang)
        from bot.keyboards.menus import booking_confirm_keyboard
        
        if update.callback_query:
            await update.callback_query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=booking_confirm_keyboard(lang))
        else:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=booking_confirm_keyboard(lang))
        return CONFIRM

    def _get_summary_text(self, data, lang):
        d1 = datetime.strptime(data["booking_checkin"], DATE_FORMAT)
        d2 = datetime.strptime(data["booking_checkout"], DATE_FORMAT)
        nights = (d2 - d1).days
        labels = {
            "KH": ["ឈ្មោះ", "ទូរស័ព្ទ", "ថ្ងៃចូល", "ថ្ងៃចេញ", "ចំនួនយប់", "បន្ទប់", "ភ្ញៀវ", "សំណូមពរ"],
            "EN": ["Name", "Phone", "In", "Out", "Nights", "Room", "Guests", "Special"]
        }
        cur_labels = labels[lang]
        val = [
            data["booking_name"], data["booking_phone"], data["booking_checkin"],
            data["booking_checkout"], str(nights), data["booking_room"],
            data["booking_guests"], data.get("booking_special", "None")
        ]
        header = "📝 <b>សេចក្តីសង្ខេបនៃការកក់</b>" if lang == "KH" else "📝 <b>BOOKING SUMMARY</b>"
        summary = f"{header}\n━━━━━━━━━━━━━━━━━━━━\n"
        for l, v in zip(cur_labels, val):
            padding = " " * (12 - len(l))
            summary += f"<b>{l}{padding}:</b> {v}\n"
        summary += "━━━━━━━━━━━━━━━━━━━━\n"
        return summary

    async def _notify_admins(self, bid, data, user, context):
        username = user.username
        if username:
            username = f"@{username}" if not username.startswith("@") else username
            tg_link = f"<a href='https://t.me/{username.replace('@', '')}'>{username}</a>"
        else:
            tg_link = "No Username"
            
        text = (
            f"🔔 <b>NEW BOOKING ALERT! (# {bid})</b>\n"
            f"👤 <b>Guest:</b> {data['booking_name']}\n"
            f"📞 <b>Phone:</b> {data['booking_phone']}\n"
            f"🆔 <b>Telegram:</b> {tg_link}\n"
            f"🛏️ <b>Room:</b> {data['booking_room']}\n"
            f"📅 <b>Check-in:</b> {data['booking_checkin']}\n"
            f"📅 <b>Check-out:</b> {data['booking_checkout']}"
        )
        for aid in self.admin_ids:
            try: 
                msg = await context.bot.send_message(chat_id=aid, text=text, parse_mode=ParseMode.HTML, reply_markup=admin_booking_action_keyboard(bid))
                await self.db.add_admin_notification(bid, aid, msg.message_id)
            except: pass

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        lang = context.user_data.get("lang", "EN")
        msg = "❌ ការកក់ត្រូវបានបោះបង់" if lang == "KH" else "❌ Booking cancelled."
        if update.callback_query:
            await update.callback_query.message.reply_text(msg, reply_markup=main_menu_keyboard(lang))
        else:
            await update.message.reply_text(msg, reply_markup=main_menu_keyboard(lang))
        return ConversationHandler.END
