# ============================================================
#  bot/handlers/customer_handler.py — Static Info & Menus
# ============================================================
import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from src.services.database import Database
from src.keyboards.calendar import create_calendar
from src.keyboards.menus import (
    rooms_menu_keyboard,
    room_detail_keyboard,
    back_to_menu_keyboard,
    main_menu_keyboard,
    language_keyboard
)

logger = logging.getLogger(__name__)

class CustomerHandler:
    def __init__(self, db: Database):
        self.db = db

    async def _get_lang(self, user_id: int) -> str:
        """Helper to get user's language from DB."""
        user = await self.db.get_user(user_id)
        return user.get("language", "EN") if user else "EN"

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user_id = query.from_user.id
        lang = await self._get_lang(user_id)
        resort_data = context.bot_data.get("resort_data", {})

        # --- Menu Navigation ---
        if data == "menu_rooms":
            text = "🛏️ <b>ប្រភេទបន្ទប់របស់យើង:</b>" if lang == "KH" else "🛏️ <b>Our Room Types:</b>"
            await query.edit_message_text(
                text, 
                parse_mode=ParseMode.HTML, 
                reply_markup=rooms_menu_keyboard(resort_data.get("rooms", []), lang)
            )

        elif data.startswith("room_detail_"):
            room_id = data.replace("room_detail_", "")
            room = next((r for r in resort_data.get("rooms", []) if r["id"] == room_id), None)
            if room:
                desc = room["description_kh"] if lang == "KH" else room["description_en"]
                text = (
                    f"{room['emoji']} <b>{room['name']}</b>\n"
                    f"💰 <b>Price:</b> ${room['price_per_night']}/night\n\n"
                    f"{desc}"
                )
                await query.edit_message_text(
                    text, 
                    parse_mode=ParseMode.HTML, 
                    reply_markup=room_detail_keyboard(room_id, lang)
                )

        elif data == "menu_facilities":
            f = resort_data.get("facilities", {})
            title = "🏨 <b>សេវាកម្ម និងសម្ភារៈរីសត:</b>" if lang == "KH" else "🏨 <b>Resort Facilities:</b>"
            items = f.get("list_kh" if lang == "KH" else "list_en", [])
            text = f"{title}\n\n" + "\n".join([f"• {i}" for i in items])
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=back_to_menu_keyboard(lang))

        elif data == "menu_location":
            loc = resort_data.get("location", {})
            title = "📍 <b>ទីតាំងរបស់យើង:</b>" if lang == "KH" else "📍 <b>Our Location:</b>"
            address = loc.get("address_kh" if lang == "KH" else "address_en", "")
            text = f"{title}\n\n{address}"
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=back_to_menu_keyboard(lang))

        elif data == "menu_contact":
            c = resort_data.get("contact", {})
            title = "📞 <b>ទំនាក់ទំនងមកយើងខ្ញុំ:</b>" if lang == "KH" else "📞 <b>Contact Us:</b>"
            text = (
                f"{title}\n\n"
                f"📱 <b>Phone:</b> {c.get('phone')}\n"
                f"📧 <b>Email:</b> {c.get('email')}\n"
                f"🌐 <b>Website:</b> {c.get('website')}"
            )
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=back_to_menu_keyboard(lang))

        elif data == "menu_policies":
            p = resort_data.get("policies", {})
            title = "📜 <b>គោលការណ៍រីសត:</b>" if lang == "KH" else "📜 <b>Resort Policies:</b>"
            # We'll show a few key policies
            p_text = f"{title}\n\n"
            if lang == "KH":
                p_text += f"• ចូលស្នាក់នៅ: {p.get('check_in')}\n• ចាកចេញ: {p.get('check_out')}"
            else:
                p_text += "• Check-in: 2:00 PM\n• Check-out: 12:00 PM"
            
            await query.edit_message_text(p_text, parse_mode=ParseMode.HTML, reply_markup=back_to_menu_keyboard(lang))

        elif data == "menu_back":
            text = (
                f"🙏 <b>រីករាយដែលបានជួបអ្នកម្តងទៀត!</b>\n"
                "តើមានអ្វីដែលខ្ញុំអាចជួយអ្នកបាន?"
            ) if lang == "KH" else (
                f"🙏 <b>Welcome back!</b>\n"
                "How can I assist you today?"
            )
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard(lang))

        elif data == "menu_language":
            text = (
                "🌐 <b>សូមជ្រើសរើសភាសារបស់អ្នក:</b>\n\n"
                "Please choose your language:"
            )
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=language_keyboard()
            )

        elif data.startswith("lang_"):
            new_lang = data.replace("lang_", "")
            await self.db.set_user_language(user_id, new_lang)
            resort_name = resort_data.get("resort", {}).get("name", "Resort")
            text = (
                f"✅ <b>ភាសាខ្មែរត្រូវបានកំណត់!</b>\n\n"
                f"រីករាយដែលបានជួបអ្នក! នេះគឺជាម៉ឺនុយមេសម្រាប់ {resort_name}។ "
                "តើមានអ្វីដែលខ្ញុំអាចជួយអ្នកបាននៅថ្ងៃនេះ?"
            ) if new_lang == "KH" else (
                f"✅ <b>English Language Set!</b>\n\n"
                f"Nice to meet you! This is the main menu for {resort_name}. "
                "How can I assist you today?"
            )
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=main_menu_keyboard(new_lang)
            )

        elif data == "menu_mybookings":
            bookings = await self.db.get_user_bookings(user_id)
            if not bookings:
                text = (
                    "📋 <b>អ្នក​មិនមានការកក់ណាមួយនៅឡើយទេ</b>\n\n"
                    "សូមចុចប៊ូតុងខាងក្រោមដើម្បីចាប់ផ្តើមកក់បន្ទប់។"
                ) if lang == "KH" else (
                    "📋 <b>You have no bookings yet</b>\n\n"
                    "Click the button below to start booking a room."
                )
            else:
                header = "📋 <b>ការកក់របស់ខ្ញុំ:</b>\n\n" if lang == "KH" else "📋 <b>My Bookings:</b>\n\n"
                text = header
                for i, b in enumerate(bookings, 1):
                    status_text = b.get("status", "PENDING")
                    if lang == "KH":
                        status_display = "✅ បានបញ្ជាក់" if status_text == "CONFIRMED" else \
                                       "✅ បានបង់ប្រាក់" if status_text == "PAID" else \
                                       "⏳ រង់ចាំ" if status_text == "PENDING" else status_text
                    else:
                        status_display = "✅ Confirmed" if status_text == "CONFIRMED" else \
                                       "✅ Paid" if status_text == "PAID" else \
                                       "⏳ Pending" if status_text == "PENDING" else status_text
                    
                    if lang == "KH":
                        text += (
                            f"<b>ការកក់ #{i}</b>\n"
                            f"ឈ្មោះ: {b.get('guest_name', 'N/A')}\n"
                            f"បន្ទប់: {b.get('room_type', 'N/A')}\n"
                            f"ចូល: {b.get('checkin_date', 'N/A')}\n"
                            f"ចេញ: {b.get('checkout_date', 'N/A')}\n"
                            f"ស្ថានភាព: {status_display}\n\n"
                        )
                    else:
                        text += (
                            f"<b>Booking #{i}</b>\n"
                            f"Name: {b.get('guest_name', 'N/A')}\n"
                            f"Room: {b.get('room_type', 'N/A')}\n"
                            f"Check-in: {b.get('checkin_date', 'N/A')}\n"
                            f"Check-out: {b.get('checkout_date', 'N/A')}\n"
                            f"Status: {status_display}\n\n"
                        )
            
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=back_to_menu_keyboard(lang))

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle random text messages by silently deleting them to force button use."""
        try:
            await update.message.delete()
        except:
            pass
            
    
