# ============================================================
#  bot/handlers/booking_handler.py — Multi-Step Booking Flow (Bilingual)
# ============================================================
import logging
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

from bot.services.database import Database
from bot.services.sheets_service import SheetsService
from bot.keyboards.menus import (
    booking_room_select_keyboard,
    booking_confirm_keyboard,
    booking_special_keyboard,
    booking_edit_menu_keyboard,
    main_menu_keyboard,
    admin_booking_action_keyboard,
)
from bot.keyboards.calendar import create_calendar

logger = logging.getLogger(__name__)

# ── Conversation States ──────────────────────────────────────────────────────
(
    NAME,
    PHONE,
    CHECKIN,
    CHECKOUT,
    ROOM_TYPE,
    GUESTS,
    SPECIAL,
    CONFIRM,
) = range(8)

DATE_FORMAT = "%d/%m/%Y"

def _kh_to_en_digits(text: str) -> str:
    """Converts Khmer Unicode digits to standard Latin digits."""
    kh_digits = "០១២៣៤៥៦៧៨៩"
    en_digits = "0123456789"
    translation_table = str.maketrans(kh_digits, en_digits)
    return text.translate(translation_table)

class BookingHandler:
    def __init__(self, db: Database, admin_ids: list[int], sheets: SheetsService):
        self.db = db
        self.admin_ids = admin_ids
        self.sheets = sheets

    async def _get_lang(self, user_id: int) -> str:
        user = await self.db.get_user(user_id)
        return user.get("language", "EN") if user else "EN"

    def _get_summary_text(self, ud: dict, lang: str) -> str:
        """Helper to generate summary text for confirmation screen."""
        ci_str = ud.get("booking_checkin", "??")
        co_str = ud.get("booking_checkout", "??")
        try:
            ci = datetime.strptime(ci_str, DATE_FORMAT)
            co = datetime.strptime(co_str, DATE_FORMAT)
            nights = max(1, (co - ci).days)
        except:
            nights = 1
            
        price = ud.get("booking_room_price", 0)
        total = nights * price
        
        # Translate special request for display
        sp_key = ud.get("booking_special", "sp_none")
        sp_display_kh = {
            "sp_decor": "ការតុបតែងបន្ទប់ (Decor)",
            "sp_towels": "កន្សែងបន្ថែម (Towels)",
            "sp_quiet": "បន្ទប់ស្ងាត់ (Quiet Room)",
            "sp_early": "ចូលមុនម៉ោង (Early Check-in)",
            "sp_none": "គ្មាន (None)"
        }
        sp_display_en = {
            "sp_decor": "Room Decoration",
            "sp_towels": "Extra Towels",
            "sp_quiet": "Quiet Room",
            "sp_early": "Early Check-in",
            "sp_none": "None"
        }
        special = sp_display_kh.get(sp_key, "គ្មាន") if lang == "KH" else sp_display_en.get(sp_key, "None")

        if lang == "KH":
            return (
                "📋 <b>សេចក្តីសង្ខេបនៃការកក់</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>ភ្ញៀវ</b>            : {ud.get('booking_name')}\n"
                f"📞 <b>ទូរស័ព្ទ</b>          : {ud.get('booking_phone')}\n"
                f"📅 <b>ថ្ងៃចូល</b>          : {ci_str}\n"
                f"📅 <b>ថ្ងៃចេញ</b>         : {co_str}\n"
                f"🌙 <b>ស្នាក់នៅ</b>        : {nights} យប់\n"
                f"🛏️ <b>បន្ទប់</b>            : {ud.get('booking_room')}\n"
                f"👥 <b>ចំនួនភ្ញៀវ</b>      : {ud.get('booking_guests')} នាក់\n"
                f"📝 <b>សំណូមពរ</b>      : {special}\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 <b>តម្លៃសរុប         : ${total} USD</b>\n\n"
                "<i>សូមបញ្ជាក់ ឬកែប្រែព័ត៌មានរបស់អ្នក:</i>"
            )
        else:
            return (
                "📋 <b>Booking Summary</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>Guest</b>          : {ud.get('booking_name')}\n"
                f"📞 <b>Phone</b>          : {ud.get('booking_phone')}\n"
                f"📅 <b>Check-in</b>       : {ci_str}\n"
                f"📅 <b>Check-out</b>      : {co_str}\n"
                f"🌙 <b>Nights</b>         : {nights}\n"
                f"🛏️ <b>Room</b>           : {ud.get('booking_room')}\n"
                f"👥 <b>Guests</b>         : {ud.get('booking_guests')}\n"
                f"📝 <b>Requests</b>       : {special}\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 <b>Total Est.       : ${total} USD</b>\n\n"
                "<i>Please confirm or edit details:</i>"
            )

    # ------------------------------------------------------------------
    # STEP 0: Entry point
    # ------------------------------------------------------------------

    async def start_booking(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        lang = await self._get_lang(query.from_user.id)
        context.user_data["lang"] = lang

        if query.data.startswith("booking_room_"):
            room_id = query.data.replace("booking_room_", "")
            context.user_data["preselected_room"] = room_id

        text = "👤 <b>ជំហានទី 1/7:</b> បញ្ចូល <b>ឈ្មោះពេញ</b> របស់អ្នក:" if lang == "KH" else "👤 <b>Step 1/7:</b> Please enter your <b>full name</b>:"
        await query.edit_message_text(text, parse_mode=ParseMode.HTML)
        return NAME

    # ------------------------------------------------------------------
    # STEP 1: Name → Ask Phone
    # ------------------------------------------------------------------

    async def get_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        name = update.message.text.strip()
        lang = context.user_data.get("lang", "EN")
        context.user_data["booking_name"] = name
        
        # If we were editing, go back to summary
        if context.user_data.get("is_editing"):
            context.user_data["is_editing"] = False
            await update.message.reply_text(self._get_summary_text(context.user_data, lang), parse_mode=ParseMode.HTML, reply_markup=booking_confirm_keyboard(lang))
            return CONFIRM

        text = f"📞 <b>ជំហានទី 2/7:</b> បញ្ចូល <b>លេខទូរស័ព្ទ</b>:" if lang == "KH" else "📞 <b>Step 2/7:</b> Please enter your <b>phone number</b>:"
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        return PHONE

    # ------------------------------------------------------------------
    # STEP 2: Phone → Ask Check-in
    # ------------------------------------------------------------------

    async def get_phone(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        raw_input = update.message.text.strip()
        lang = context.user_data.get("lang", "EN")
        
        # 1. Convert Khmer digits to English first
        raw_phone = _kh_to_en_digits(raw_input)
        
        # 2. Smart Format: Convert 0xx... to +855 xx...
        clean = raw_phone.replace(" ", "").replace("-", "")
        if clean.startswith("0") and len(clean) >= 9: formatted = f"+855 {clean[1:3]} {clean[3:6]} {clean[6:]}"
        elif clean.startswith("855") and len(clean) >= 11: formatted = f"+855 {clean[3:5]} {clean[5:8]} {clean[8:]}"
        else: formatted = raw_phone
        context.user_data["booking_phone"] = formatted

        if context.user_data.get("is_editing"):
            context.user_data["is_editing"] = False
            await update.message.reply_text(self._get_summary_text(context.user_data, lang), parse_mode=ParseMode.HTML, reply_markup=booking_confirm_keyboard(lang))
            return CONFIRM

        text = "📅 <b>ជំហានទី 3/7:</b> ជ្រើសរើស <b>ថ្ងៃចូលសម្រាក</b>:" if lang == "KH" else "📅 <b>Step 3/7:</b> Select <b>check-in date</b>:"
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=create_calendar(lang=lang))
        return CHECKIN

    # ------------------------------------------------------------------
    # STEP 3: Check-in
    # ------------------------------------------------------------------

    async def get_checkin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        data, lang = query.data, context.user_data.get("lang", "EN")

        if data.startswith("cal_nav_"):
            _, _, m, y = data.split("_")
            await query.edit_message_reply_markup(reply_markup=create_calendar(int(y), int(m), lang))
            return CHECKIN

        if data.startswith("cal_set_"):
            _, _, d, m, y = data.split("_")
            date_str = f"{int(d):02d}/{int(m):02d}/{y}"
            context.user_data["booking_checkin"] = date_str
            
            # Immediate feedback
            alert = f"✅ បានជ្រើសរើស: {date_str}" if lang == "KH" else f"✅ Selected: {date_str}"
            await query.answer(text=alert, show_alert=False)
            
            text = f"📅 <b>ថ្ងៃចូល: {date_str}</b>\n\n📅 <b>ជំហានទី 4/7:</b> ជ្រើសរើស <b>ថ្ងៃចាកចេញ</b>:" if lang == "KH" else f"📅 <b>Check-in: {date_str}</b>\n\n📅 <b>Step 4/7:</b> Select <b>check-out date</b>:"
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=create_calendar(int(y), int(m), lang))
            return CHECKOUT
        return CHECKIN

    # ------------------------------------------------------------------
    # STEP 4: Check-out
    # ------------------------------------------------------------------

    async def get_checkout(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        data, lang = query.data, context.user_data.get("lang", "EN")

        if data.startswith("cal_nav_"):
            _, _, m, y = data.split("_")
            await query.edit_message_reply_markup(reply_markup=create_calendar(int(y), int(m), lang))
            return CHECKOUT

        if data.startswith("cal_set_"):
            _, _, d, m, y = data.split("_")
            date_str = f"{int(d):02d}/{int(m):02d}/{y}"
            ci = datetime.strptime(context.user_data["booking_checkin"], DATE_FORMAT)
            co = datetime.strptime(date_str, DATE_FORMAT)
            if co <= ci:
                await query.answer("⚠️ ថ្ងៃចាកចេញត្រូវតែក្រោយថ្ងៃចូល!" if lang == "KH" else "⚠️ Check-out must be after check-in!", show_alert=True)
                return CHECKOUT
            
            context.user_data["booking_checkout"] = date_str
            
            # Immediate feedback
            alert = f"✅ បានជ្រើសរើស: {date_str}" if lang == "KH" else f"✅ Selected: {date_str}"
            await query.answer(text=alert, show_alert=False)

            if context.user_data.get("is_editing"):
                context.user_data["is_editing"] = False
                await query.edit_message_text(self._get_summary_text(context.user_data, lang), parse_mode=ParseMode.HTML, reply_markup=booking_confirm_keyboard(lang))
                return CONFIRM

            resort_data = context.bot_data.get("resort_data", {})
            await query.edit_message_text("🛏️ <b>ជំហានទី 5/7:</b> ជ្រើសរើស <b>ប្រភេទបន្ទប់</b>:", parse_mode=ParseMode.HTML, reply_markup=booking_room_select_keyboard(resort_data.get("rooms", []), lang))
            return ROOM_TYPE
        return CHECKOUT

    # ------------------------------------------------------------------
    # STEP 5: Room Type
    # ------------------------------------------------------------------

    async def get_room_type(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        lang = context.user_data.get("lang", "EN")
        if query.data == "booking_cancel": return await self.cancel(update, context)

        room_id = query.data.replace("room_", "")
        resort_data = context.bot_data.get("resort_data", {})
        room = next((r for r in resort_data.get("rooms", []) if r["id"] == room_id), None)
        if not room: return ROOM_TYPE
        
        context.user_data["booking_room"] = room["name"]
        context.user_data["booking_room_price"] = room["price_per_night"]

        if context.user_data.get("is_editing"):
            context.user_data["is_editing"] = False
            await query.edit_message_text(self._get_summary_text(context.user_data, lang), parse_mode=ParseMode.HTML, reply_markup=booking_confirm_keyboard(lang))
            return CONFIRM

        await query.edit_message_text("👥 <b>ជំហានទី 6/7:</b> តើមាន <b>ភ្ញៀវ</b> ប៉ុន្មាននាក់?", parse_mode=ParseMode.HTML)
        return GUESTS

    # ------------------------------------------------------------------
    # STEP 6: Guests
    # ------------------------------------------------------------------

    async def get_guests(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        raw_input = update.message.text.strip()
        lang = context.user_data.get("lang", "EN")
        
        # Convert Khmer digits if any
        text = _kh_to_en_digits(raw_input)
        
        if not text.isdigit(): return GUESTS
        context.user_data["booking_guests"] = int(text)

        if context.user_data.get("is_editing"):
            context.user_data["is_editing"] = False
            await update.message.reply_text(self._get_summary_text(context.user_data, lang), parse_mode=ParseMode.HTML, reply_markup=booking_confirm_keyboard(lang))
            return CONFIRM

        await update.message.reply_text("📝 <b>ជំហានទី 7/7:</b> តើមាន <b>សំណូមពរពិសេស</b>?", parse_mode=ParseMode.HTML, reply_markup=booking_special_keyboard(lang))
        return SPECIAL

    # ------------------------------------------------------------------
    # STEP 7: Special
    # ------------------------------------------------------------------

    async def get_special(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        lang = context.user_data.get("lang", "EN")
        
        # Save the key, not the English word
        context.user_data["booking_special"] = query.data

        summary = self._get_summary_text(context.user_data, lang)
        await query.edit_message_text(summary, parse_mode=ParseMode.HTML, reply_markup=booking_confirm_keyboard(lang))
        return CONFIRM

    # ------------------------------------------------------------------
    # STEP 8: Confirm / Edit Menu Logic
    # ------------------------------------------------------------------

    async def confirm_booking(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        data, lang = query.data, context.user_data.get("lang", "EN")

        if data == "booking_cancel": return await self.cancel(update, context)
        
        # SHOW EDIT MENU
        if data == "booking_edit_menu":
            text = "✏️ <b>ជ្រើសរើសព័ត៌មានដែលត្រូវកែប្រែ:</b>" if lang == "KH" else "✏️ <b>Select what you want to edit:</b>"
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=booking_edit_menu_keyboard(lang))
            return CONFIRM

        # BACK TO SUMMARY
        if data == "booking_back_to_summary":
            await query.edit_message_text(self._get_summary_text(context.user_data, lang), parse_mode=ParseMode.HTML, reply_markup=booking_confirm_keyboard(lang))
            return CONFIRM

        # HANDLE SPECIFIC EDITS
        if data.startswith("edit_"):
            context.user_data["is_editing"] = True
            field = data.replace("edit_", "")
            if field == "name":
                await query.edit_message_text("👤 បញ្ចូល <b>ឈ្មោះថ្មី</b>:" if lang == "KH" else "👤 Enter <b>new Name</b>:", parse_mode=ParseMode.HTML)
                return NAME
            elif field == "phone":
                await query.edit_message_text("📞 បញ្ចូល <b>លេខទូរស័ព្ទថ្មី</b>:" if lang == "KH" else "📞 Enter <b>new Phone</b>:", parse_mode=ParseMode.HTML)
                return PHONE
            elif field == "dates":
                await query.edit_message_text("📅 ជ្រើសរើស <b>ថ្ងៃចូលសម្រាកថ្មី</b>:" if lang == "KH" else "📅 Select <b>new Check-in date</b>:", parse_mode=ParseMode.HTML, reply_markup=create_calendar(lang=lang))
                return CHECKIN
            elif field == "room":
                resort_data = context.bot_data.get("resort_data", {})
                await query.edit_message_text("🛏️ ជ្រើសរើស <b>បន្ទប់ថ្មី</b>:" if lang == "KH" else "🛏️ Select <b>new Room type</b>:", parse_mode=ParseMode.HTML, reply_markup=booking_room_select_keyboard(resort_data.get("rooms", []), lang))
                return ROOM_TYPE
            elif field == "guests":
                await query.edit_message_text("👥 បញ្ចូល <b>ចំនួនភ្ញៀវថ្មី</b>:" if lang == "KH" else "👥 Enter <b>new number of Guests</b>:", parse_mode=ParseMode.HTML)
                return GUESTS
            elif field == "special":
                await query.edit_message_text("📝 ជ្រើសរើស <b>សំណូមពរថ្មី</b>:" if lang == "KH" else "📝 Select <b>new Special request</b>:", parse_mode=ParseMode.HTML, reply_markup=booking_special_keyboard(lang))
                return SPECIAL

        # ACTUAL CONFIRMATION
        if data == "booking_confirm":
            user, ud = update.effective_user, context.user_data
            
            # Translate key to English for the database/sheets so staff can read it too
            sp_map_staff = {"sp_decor": "Room Decor", "sp_towels": "Extra Towels", "sp_quiet": "Quiet Room", "sp_early": "Early Check-in", "sp_none": "None"}
            staff_special = sp_map_staff.get(ud.get("booking_special", "sp_none"), "None")

            bid = await self.db.create_booking(user_id=user.id, guest_name=ud["booking_name"], checkin_date=ud["booking_checkin"], checkout_date=ud["booking_checkout"], room_type=ud["booking_room"], num_guests=ud["booking_guests"], special_request=staff_special)
            await self.sheets.append_booking({"id": bid, "status": "PENDING", "guest_name": ud["booking_name"], "phone": ud["booking_phone"], "username": f"@{user.username}" if user.username else "N/A", "checkin_date": ud["booking_checkin"], "checkout_date": ud["booking_checkout"], "room_type": ud["booking_room"], "num_guests": ud["booking_guests"], "special_request": staff_special})
            
            text = f"🎉 <b>កក់ទទួលបានជោគជ័យ! (#{bid})</b>" if lang == "KH" else f"🎉 <b>Booking Success! (#{bid})</b>"
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard(lang))
            await self._notify_admins(context, bid, user, ud)
            for k in ["booking_name", "booking_phone", "booking_checkin", "booking_checkout", "booking_room", "booking_room_price", "booking_guests", "booking_special", "lang", "is_editing"]: context.user_data.pop(k, None)
            return ConversationHandler.END

        return CONFIRM

    async def _notify_admins(self, context, bid, user, ud):
        username = f"@{user.username}" if user.username else "No Username"
        
        ci = datetime.strptime(ud["booking_checkin"], DATE_FORMAT)
        co = datetime.strptime(ud["booking_checkout"], DATE_FORMAT)
        nights = max(1, (co - ci).days)
        
        sp_map_staff = {"sp_decor": "Room Decor", "sp_towels": "Extra Towels", "sp_quiet": "Quiet Room", "sp_early": "Early Check-in", "sp_none": "None"}
        staff_special = sp_map_staff.get(ud.get("booking_special", "sp_none"), "None")

        text = (
            f"🔔 <b>New Booking #{bid}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Guest: {ud.get('booking_name')}\n"
            f"🆔 User: {username}\n"
            f"📞 Phone: <code>{ud.get('booking_phone')}</code>\n\n"
            f"📅 Check-in : {ud['booking_checkin']}\n"
            f"📅 Check-out: {ud['booking_checkout']}\n"
            f"🌙 Nights   : {nights}\n"
            f"🛏️ Room     : {ud.get('booking_room')}\n"
            f"👥 Guests   : {ud.get('booking_guests')}\n"
            f"📝 Requests : {staff_special}\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        for aid in self.admin_ids:
            try: await context.bot.send_message(chat_id=aid, text=text, parse_mode=ParseMode.HTML, reply_markup=admin_booking_action_keyboard(bid))
            except: pass

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        lang = context.user_data.get("lang", "EN")
        msg = "❌ បោះបង់" if lang == "KH" else "❌ Cancelled"
        if update.callback_query: await update.callback_query.edit_message_text(msg, reply_markup=main_menu_keyboard(lang))
        else: await update.message.reply_text(msg, reply_markup=main_menu_keyboard(lang))
        return ConversationHandler.END
