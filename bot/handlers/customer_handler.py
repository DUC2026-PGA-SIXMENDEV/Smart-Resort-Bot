# ============================================================
#  bot/handlers/customer_handler.py — Customer Menu (Simplified)
# ============================================================
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatAction

from bot.services.database import Database
from bot.keyboards.menus import (
    main_menu_keyboard,
    rooms_menu_keyboard,
    room_detail_keyboard,
    language_keyboard,
    back_to_menu_keyboard,
)

logger = logging.getLogger(__name__)

def _h(text: str) -> str:
    """Escape special HTML characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class CustomerHandler:
    def __init__(self, db: Database):
        self.db = db

    async def _get_lang(self, user_id: int) -> str:
        user = await self.db.get_user(user_id)
        return user.get("language", "EN") if user else "EN"

    # ------------------------------------------------------------------
    # CALLBACK QUERY ROUTER
    # ------------------------------------------------------------------

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        resort_data = context.bot_data.get("resort_data", {})
        lang = await self._get_lang(query.from_user.id)

        if data == "menu_back":
            await self._show_main_menu(query, resort_data, lang)
        elif data == "menu_rooms":
            await self._show_rooms(query, resort_data, lang)
        elif data == "menu_facilities":
            await self._show_facilities(query, resort_data, lang)
        elif data == "menu_packages":
            await self._show_packages(query, resort_data, lang)
        elif data == "menu_policies":
            await self._show_policies(query, resort_data, lang)
        elif data == "menu_location":
            await self._show_location(query, resort_data, lang)
        elif data == "menu_contact":
            await self._show_contact(query, resort_data, lang)
        elif data == "menu_mybookings":
            await self._show_my_bookings(query, lang)
        elif data == "menu_language":
            await self._show_language_select(query)
        elif data.startswith("lang_"):
            new_lang = data.split("_")[1]
            await self._set_language(query, new_lang)
        elif data.startswith("room_detail_"):
            room_id = data.replace("room_detail_", "")
            await self._show_room_detail(query, resort_data, room_id, lang)

    # ------------------------------------------------------------------
    # FREE-TEXT MESSAGE HANDLER (Manual Response Prompt)
    # ------------------------------------------------------------------

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        message = update.message.text.strip()
        lang = await self._get_lang(user.id)

        await self.db.upsert_user(
            user.id, user.username or "", user.first_name or "", user.last_name or ""
        )
        await self.db.save_message(user.id, "user", message)

        if lang == "KH":
            text = (
                "🙏 <b>សូមអរគុណសម្រាប់ការផ្ញើសារ!</b>\n\n"
                "ប្រសិនបើលោកអ្នកមានសំណួរអ្វីផ្សេង សូមទំនាក់ទំនងមកកាន់ពួកយើងដោយផ្ទាល់តាមរយៈប៊ូតុងខាងក្រោម ឬប្រើប្រាស់ម៉ឺនុយដើម្បីកក់បន្ទប់។"
            )
            contact_btn = "📞 ទំនាក់ទំនងបុគ្គលិក"
            menu_btn = "🏠 ម៉ឺនុយចម្បង"
        else:
            text = (
                "🙏 <b>Thank you for your message!</b>\n\n"
                "If you have any questions, please contact our staff directly using the buttons below or use the menu to book a room."
            )
            contact_btn = "📞 Contact Staff"
            menu_btn = "🏠 Main Menu"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(contact_btn, callback_data="menu_contact")],
            [InlineKeyboardButton(menu_btn, callback_data="menu_back")]
        ])

        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

    # ------------------------------------------------------------------
    # MENU SECTIONS
    # ------------------------------------------------------------------

    async def _show_main_menu(self, query, resort_data: dict, lang: str):
        resort = resort_data.get("resort", {})
        name = _h(resort.get("name", "Our Resort"))
        if lang == "KH":
            text = f"🏨 <b>{name}</b> — ម៉ឺនុយ​ចម្បង\n\nតើខ្ញុំអាចជួយលោកអ្នកបានដោយរបៀបណា?"
        else:
            text = f"🏨 <b>{name}</b> — Main Menu\n\nHow can I assist you today?"
        await query.edit_message_text(text, parse_mode=ParseMode.HTML,
                                      reply_markup=main_menu_keyboard(lang))

    async def _show_rooms(self, query, resort_data: dict, lang: str):
        rooms = resort_data.get("rooms", [])
        title = "🛏️ <b>បន្ទប់សំណាក់របស់យើង</b>\n\nជ្រើសរើសបន្ទប់ដើម្បីមើលព័ត៌មានលម្អិត:" \
                if lang == "KH" else \
                "🛏️ <b>Our Room Types</b>\n\nChoose a room to see full details:"
        await query.edit_message_text(title, parse_mode=ParseMode.HTML,
                                      reply_markup=rooms_menu_keyboard(rooms, lang))

    async def _show_room_detail(self, query, resort_data: dict, room_id: str, lang: str):
        rooms = resort_data.get("rooms", [])
        room = next((r for r in rooms if r["id"] == room_id), None)
        if not room:
            await query.edit_message_text("Room not found.", reply_markup=back_to_menu_keyboard(lang))
            return

        amenities = "\n".join(f"  ✓ {_h(a)}" for a in room["amenities"])
        if lang == "KH":
            text = (
                f"{room['emoji']} <b>{_h(room['name'])}</b>\n\n"
                f"💰 <b>តម្លៃ:</b> ${room['price_per_night']}/យប់\n"
                f"👥 <b>សម្រាប់:</b> រហូតដល់ {room['capacity']} នាក់\n"
                f"📐 <b>ទំហំ:</b> {room['size_sqm']} m²\n"
                f"🛏️ <b>គ្រែ:</b> {_h(room['bed_type'])}\n\n"
                f"📝 <b>ការពិពណ៌នា:</b>\n{_h(room['description'])}\n\n"
                f"✨ <b>សម្ភារៈ:</b>\n{amenities}"
            )
        else:
            text = (
                f"{room['emoji']} <b>{_h(room['name'])}</b>\n\n"
                f"💰 <b>Price:</b> ${room['price_per_night']}/night\n"
                f"👥 <b>Capacity:</b> Up to {room['capacity']} guests\n"
                f"📐 <b>Size:</b> {room['size_sqm']} m²\n"
                f"🛏️ <b>Bed Type:</b> {_h(room['bed_type'])}\n\n"
                f"📝 <b>Description:</b>\n{_h(room['description'])}\n\n"
                f"✨ <b>Amenities:</b>\n{amenities}"
            )
        await query.edit_message_text(text, parse_mode=ParseMode.HTML,
                                      reply_markup=room_detail_keyboard(room_id, lang))

    async def _show_facilities(self, query, resort_data: dict, lang: str):
        facilities = resort_data.get("facilities", [])
        title = "🏨 <b>សេវាកម្ម និងទីសម្រន់</b>" if lang == "KH" else \
                "🏨 <b>Resort Facilities &amp; Services</b>"
        hours_label = "ម៉ោង" if lang == "KH" else "Hours"
        lines = [title + "\n"]
        for f in facilities:
            lines.append(f"{f['emoji']} <b>{_h(f['name'])}</b>")
            lines.append(f"   🕐 {hours_label}: {_h(f['hours'])}")
            lines.append(f"   {_h(f['description'])}\n")
        await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML,
                                      reply_markup=back_to_menu_keyboard(lang))

    async def _show_packages(self, query, resort_data: dict, lang: str):
        packages = resort_data.get("packages", [])
        title = "📦 <b>កញ្ចប់ពិសេស</b>" if lang == "KH" else "📦 <b>Special Packages &amp; Deals</b>"
        includes_label = "រួមបញ្ចូល:" if lang == "KH" else "Includes:"
        contact_note = "<i>ទំនាក់ទំនងយើងដើម្បីកក់!</i>" if lang == "KH" else \
                       "<i>Contact us to book a package!</i>"
        lines = [title + "\n"]
        for p in packages:
            lines.append(f"<b>{_h(p['name'])}</b>")
            lines.append(f"💰 {_h(p['price'])}")
            lines.append(includes_label)
            for item in p["includes"]:
                lines.append(f"  ✓ {_h(item)}")
            lines.append("")
        lines.append(contact_note)
        book_label = "📋 កក់ឥឡូវ" if lang == "KH" else "📋 Book Now"
        back_label = "🔙 ត្រឡប់" if lang == "KH" else "🔙 Back"
        await query.edit_message_text(
            "\n".join(lines), parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(book_label, callback_data="booking_start")],
                [InlineKeyboardButton(back_label, callback_data="menu_back")],
            ]))

    async def _show_policies(self, query, resort_data: dict, lang: str):
        policies = resort_data.get("policies", {})
        policy_labels_kh = {
            "check_in":     "🕐 ម៉ោងចូល",
            "check_out":    "🕑 ម៉ោងចាកចេញ",
            "cancellation": "❌ ការបោះបង់",
            "children":     "👶 កុមារ",
            "pets":         "🐾 សត្វចិញ្ចឹម",
            "smoking":      "🚬 ការជក់បារី",
            "payment":      "💳 ការទូទាត់",
            "deposit":      "🏦 ប្រាក់បញ្ញើ",
            "age":          "🔞 អាយុ",
        }
        policy_labels_en = {
            "check_in":     "🕐 Check-In",
            "check_out":    "🕑 Check-Out",
            "cancellation": "❌ Cancellation",
            "children":     "👶 Children",
            "pets":         "🐾 Pets",
            "smoking":      "🚬 Smoking",
            "payment":      "💳 Payment",
            "deposit":      "🏦 Deposit",
            "age":          "🔞 Age Requirement",
        }
        labels = policy_labels_kh if lang == "KH" else policy_labels_en
        title = "📜 <b>គោលការណ៍របស់រីសត</b>" if lang == "KH" else "📜 <b>Resort Policies</b>"
        lines = [title + "\n"]
        for key, label in labels.items():
            if key in policies:
                lines.append(f"<b>{label}:</b>\n{_h(policies[key])}\n")
        await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML,
                                      reply_markup=back_to_menu_keyboard(lang))

    async def _show_location(self, query, resort_data: dict, lang: str):
        resort = resort_data.get("resort", {})
        loc = resort.get("location", {})
        nearby = "\n".join(f"  📌 {_h(n)}" for n in loc.get("nearby", []))
        maps_url = loc.get("google_maps", "")
        if lang == "KH":
            text = (
                f"📍 <b>ទីតាំងរបស់យើង</b>\n\n"
                f"🏠 {_h(loc.get('address', 'N/A'))}\n\n"
                f"<b>ទីតាំងជិតៗ:</b>\n{nearby}\n\n"
                f'<a href="{maps_url}">📌 បើក Google Maps</a>'
            )
            map_btn = "🗺️ Google Maps"
            back_btn = "🔙 ត្រឡប់"
        else:
            text = (
                f"📍 <b>Our Location</b>\n\n"
                f"🏠 {_h(loc.get('address', 'N/A'))}\n\n"
                f"<b>Nearby Landmarks:</b>\n{nearby}\n\n"
                f'<a href="{maps_url}">📌 Open in Google Maps</a>'
            )
            map_btn = "🗺️ Google Maps"
            back_btn = "🔙 Back"
        await query.edit_message_text(text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(map_btn,  url=maps_url)],
                [InlineKeyboardButton(back_btn, callback_data="menu_back")],
            ]))

    async def _show_contact(self, query, resort_data: dict, lang: str):
        resort = resort_data.get("resort", {})
        contact = resort.get("contact", {})
        name = _h(resort.get("name", "Us"))
        if lang == "KH":
            text = (
                f"📞 <b>ទំនាក់ទំនង {name}</b>\n\n"
                f"📱 <b>ទូរស័ព្ទ / WhatsApp:</b> {_h(contact.get('phone', 'N/A'))}\n"
                f"📧 <b>អ៊ីម៉ែល:</b> {_h(contact.get('email', 'N/A'))}\n"
                f"📘 <b>Facebook:</b> {_h(contact.get('facebook', 'N/A'))}\n"
                f"📸 <b>Instagram:</b> {_h(contact.get('instagram', 'N/A'))}\n\n"
                f"🕐 <b>បន្ទប់ទទួលភ្ញៀវ:</b> បើក 24 ម៉ោង"
            )
        else:
            text = (
                f"📞 <b>Contact {name}</b>\n\n"
                f"📱 <b>Phone / WhatsApp:</b> {_h(contact.get('phone', 'N/A'))}\n"
                f"📧 <b>Email:</b> {_h(contact.get('email', 'N/A'))}\n"
                f"📘 <b>Facebook:</b> {_h(contact.get('facebook', 'N/A'))}\n"
                f"📸 <b>Instagram:</b> {_h(contact.get('instagram', 'N/A'))}\n\n"
                f"🕐 <b>Front Desk:</b> Open 24 hours"
            )
        buttons = []
        if contact.get("whatsapp"):
            wa_num = contact["whatsapp"].replace("+", "").replace(" ", "")
            buttons.append([InlineKeyboardButton("💬 WhatsApp", url=f"https://wa.me/{wa_num}")])
        if contact.get("facebook"):
            buttons.append([InlineKeyboardButton("📘 Facebook", url=contact["facebook"])])
        back_label = "🔙 ត្រឡប់" if lang == "KH" else "🔙 Back"
        buttons.append([InlineKeyboardButton(back_label, callback_data="menu_back")])
        await query.edit_message_text(text, parse_mode=ParseMode.HTML,
                                      reply_markup=InlineKeyboardMarkup(buttons))

    async def _show_my_bookings(self, query, lang: str):
        user_id = query.from_user.id
        bookings = await self.db.get_user_bookings(user_id)
        if lang == "KH":
            no_booking_text = "⭐ <b>ការកក់របស់ខ្ញុំ</b>\n\nអ្នកមិនទាន់មានការកក់នៅឡើយ។"
            new_book_label = "📋 កក់ឥឡូវ"
            back_label = "🔙 ត្រឡប់"
            title = "⭐ <b>ការកក់របស់ខ្ញុំ</b>\n"
        else:
            no_booking_text = "⭐ <b>My Bookings</b>\n\nYou don't have any bookings yet."
            new_book_label = "📋 New Booking"
            back_label = "🔙 Back"
            title = "⭐ <b>My Bookings</b>\n"

        if not bookings:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(new_book_label, callback_data="booking_start")],
                [InlineKeyboardButton(back_label, callback_data="menu_back")],
            ])
            await query.edit_message_text(no_booking_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
            return

        status_emoji = {"PENDING": "⏳", "CONFIRMED": "✅", "DECLINED": "❌", "CANCELLED": "🚫"}
        status_kh = {"PENDING": "កំពុងរង់ចាំ", "CONFIRMED": "បានបញ្ជាក់", "DECLINED": "បានបដិសេធ", "CANCELLED": "បានបោះបង់"}
        lines = [title]
        for b in bookings:
            emoji = status_emoji.get(b["status"], "❓")
            status_str = status_kh.get(b["status"], b["status"]) if lang == "KH" else b["status"]
            lines.append(f"{emoji} <b>Booking #{b['id']}</b>\n   បន្ទប់: {_h(b['room_type'])}\n   ស្ថានភាព: {status_str}\n")
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(new_book_label, callback_data="booking_start")],
            [InlineKeyboardButton(back_label, callback_data="menu_back")],
        ])
        await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=keyboard)

    async def _show_language_select(self, query):
        await query.edit_message_text("🌐 <b>Select language / ជ្រើសរើសភាសា:</b>",
                                      parse_mode=ParseMode.HTML, reply_markup=language_keyboard())

    async def _set_language(self, query, lang: str):
        user_id = query.from_user.id
        await self.db.set_user_language(user_id, lang)
        msg = "✅ ភាសាត្រូវបានកំណត់ជា <b>ខ្មែរ</b>! 🇰🇭" if lang == "KH" else "✅ Language set to <b>English</b>! 🇺🇸"
        await query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=back_to_menu_keyboard(lang))
