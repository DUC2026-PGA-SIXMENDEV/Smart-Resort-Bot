# ============================================================
#  bot/handlers/customer_handler.py — Static Info & Menus
# ============================================================
import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.services.database import Database
from bot.keyboards.calendar import create_calendar
from bot.keyboards.menus import (
    rooms_menu_keyboard,
    room_detail_keyboard,
    back_to_menu_keyboard,
    main_menu_keyboard
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
        if data == "menu_availability":
            text = "📅 <b>សូមជ្រើសរើសថ្ងៃចូលស្នាក់នៅ:</b>" if lang == "KH" else "📅 <b>Please select your Check-in date:</b>"
            # We initialize a "Check Only" session in user_data
            context.user_data["is_check_only"] = True
            context.user_data["booking_data"] = {}
            await query.edit_message_text(
                text, 
                parse_mode=ParseMode.HTML, 
                reply_markup=create_calendar(lang=lang)
            )

        elif data == "menu_rooms":
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

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle random text messages by showing main menu."""
        lang = await self._get_lang(update.effective_user.id)
        text = "🙏 សូមជ្រើសរើសជម្រើសខាងក្រោម:" if lang == "KH" else "🙏 Please choose an option from the menu below:"
        await update.message.reply_text(text, reply_markup=main_menu_keyboard(lang))
