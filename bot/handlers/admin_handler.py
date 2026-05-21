# ============================================================
#  bot/handlers/admin_handler.py — Staff Admin Panel
# ============================================================
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatAction

from bot.services.database import Database
from bot.services.sheets_service import SheetsService
from bot.keyboards.menus import admin_panel_keyboard, admin_booking_action_keyboard, main_menu_keyboard, start_again_keyboard

logger = logging.getLogger(__name__)

STATUS_EMOJI = {
    "PENDING": "⏳",
    "CONFIRMED": "✅",
    "DECLINED": "❌",
    "CANCELLED": "🚫",
}


def _is_admin(user_id: int, admin_ids: list[int]) -> bool:
    return user_id in admin_ids


class AdminHandler:
    def __init__(self, db: Database, admin_ids: list[int], sheets: SheetsService):
        self.db = db
        self.admin_ids = admin_ids
        self.sheets = sheets

    def _check_admin(self, update: Update) -> bool:
        return _is_admin(update.effective_user.id, self.admin_ids)

    # ------------------------------------------------------------------
    # ADMIN PANEL ENTRY
    # ------------------------------------------------------------------

    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show admin panel. /admin command."""
        if not self._check_admin(update):
            await update.message.reply_text("⛔ Access denied. Admin only.")
            return

        pending = await self.db.get_pending_bookings()
        total_users = await self.db.get_user_count()
        total_bookings = await self.db.get_booking_count()
        avg_rating = await self.db.get_average_rating()

        text = (
            "🏨 <b>Admin Control Panel</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"👥 <b>Total Users:</b>    {total_users}\n"
            f"📋 <b>Total Bookings:</b> {total_bookings}\n"
            f"⏳ <b>Pending:</b>        {len(pending)}\n"
            f"⭐ <b>Avg Rating:</b>     {avg_rating}/5.0\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "<i>Select an action below:</i>"
        )
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=admin_panel_keyboard(),
        )

    # ------------------------------------------------------------------
    # SHOW STATS
    # ------------------------------------------------------------------

    async def show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show detailed statistics. /stats command."""
        if not self._check_admin(update):
            await update.message.reply_text("⛔ Access denied.")
            return

        total_users = await self.db.get_user_count()
        total_bookings = await self.db.get_booking_count()
        pending = await self.db.get_pending_bookings()
        avg_rating = await self.db.get_average_rating()
        all_bookings = await self.db.get_all_bookings(limit=100)

        confirmed = sum(1 for b in all_bookings if b["status"] == "CONFIRMED")
        declined = sum(1 for b in all_bookings if b["status"] == "DECLINED")

        text = (
            "📊 <b>Resort Bot Statistics</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 Total Users:      {total_users}\n"
            f"📋 Total Bookings:   {total_bookings}\n"
            f"⏳ Pending:          {len(pending)}\n"
            f"✅ Confirmed:        {confirmed}\n"
            f"❌ Declined:         {declined}\n"
            f"⭐ Average Rating:   {avg_rating}/5.0\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    # ------------------------------------------------------------------
    # BROADCAST
    # ------------------------------------------------------------------

    async def broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Broadcast a message to all users. /broadcast <message>"""
        if not self._check_admin(update):
            await update.message.reply_text("⛔ Access denied.")
            return

        if not context.args:
            await update.message.reply_text(
                "📢 *Broadcast Usage:*\n"
                "`/broadcast Your message here`\n\n"
                "This will send the message to ALL bot users.",
                parse_mode=ParseMode.HTML,
            )
            return

        broadcast_text = " ".join(context.args)
        users = await self.db.get_all_users()
        sent = 0
        failed = 0

        status_msg = await update.message.reply_text(
            f"📢 Broadcasting to {len(users)} users..."
        )

        for user in users:
            try:
                await context.bot.send_message(
                    chat_id=user["user_id"],
                    text=(
                        f"📢 *Message from {context.bot_data.get('resort_data', {}).get('resort', {}).get('name', 'Resort Management')}*\n\n"
                        f"{broadcast_text}"
                    ),
                    parse_mode=ParseMode.HTML,
                    reply_markup=main_menu_keyboard(),
                )
                sent += 1
            except Exception as e:
                logger.warning("Broadcast failed for user %s: %s", user["user_id"], e)
                failed += 1

        await status_msg.edit_text(
            f"📢 *Broadcast Complete*\n\n"
            f"✅ Sent: {sent}\n"
            f"❌ Failed: {failed}",
            parse_mode=ParseMode.HTML,
        )

    # ------------------------------------------------------------------
    # CALLBACK HANDLER (Admin actions on bookings)
    # ------------------------------------------------------------------

    async def handle_admin_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle admin button presses on booking notifications."""
        query = update.callback_query
        await query.answer()

        if not _is_admin(query.from_user.id, self.admin_ids):
            await query.answer("⛔ Admin only!", show_alert=True)
            return

        data = query.data

        if data == "admin_pending":
            await self._show_pending_bookings(query)
        elif data == "admin_all_bookings":
            await self._show_all_bookings(query)
        elif data == "admin_stats":
            await self._show_stats_inline(query)
        elif data.startswith("admin_confirm_"):
            booking_id = int(data.split("_")[2])
            await self._confirm_booking(query, context, booking_id)
        elif data.startswith("admin_decline_"):
            booking_id = int(data.split("_")[2])
            await self._decline_booking(query, context, booking_id)
        elif data.startswith("admin_view_"):
            booking_id = int(data.split("_")[2])
            await self._view_booking(query, booking_id)

    async def _show_pending_bookings(self, query):
        bookings = await self.db.get_pending_bookings()
        if not bookings:
            await query.edit_message_text(
                "⏳ *Pending Bookings*\n\nNo pending bookings at the moment! 🎉",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back", callback_data="admin_back")
                ]]),
            )
            return

        lines = [f"⏳ <b>Pending Bookings ({len(bookings)})</b>\n"]
        for b in bookings[:10]:  # Show max 10
            lines.append(
                f"<b>#{b['id']}</b> — {b['guest_name']}\n"
                f"   {b['room_type']} | {b['checkin_date']} → {b['checkout_date']}\n"
            )
        lines.append("<i>Use the buttons in each notification to confirm/decline.</i>")

        await query.edit_message_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="admin_back")
            ]]),
        )

    async def _show_all_bookings(self, query):
        bookings = await self.db.get_all_bookings(limit=10)
        if not bookings:
            await query.edit_message_text("No bookings found.", reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="admin_back")
            ]]))
            return

        lines = ["📋 <b>Recent Bookings</b>\n"]
        for b in bookings:
            emoji = STATUS_EMOJI.get(b["status"], "❓")
            lines.append(
                f"{emoji} <b>#{b['id']}</b> — {b['guest_name']}\n"
                f"   {b['room_type']} | {b['checkin_date']} → {b['checkout_date']}\n"
            )

        await query.edit_message_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="admin_back")
            ]]),
        )

    async def _show_stats_inline(self, query):
        total_users = await self.db.get_user_count()
        total_bookings = await self.db.get_booking_count()
        pending = await self.db.get_pending_bookings()
        avg_rating = await self.db.get_average_rating()

        text = (
            "📊 <b>Bot Statistics</b>\n"
            f"👥 Users: {total_users}\n"
            f"📋 Bookings: {total_bookings}\n"
            f"⏳ Pending: {len(pending)}\n"
            f"⭐ Rating: {avg_rating}/5.0"
        )
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="admin_back")
            ]]),
        )

    async def _confirm_booking(self, query, context, booking_id: int):
        booking = await self.db.get_booking(booking_id)
        if not booking:
            await query.answer("Booking not found!", show_alert=True)
            return

        # Update DB and Sheet
        admin_name = query.from_user.first_name
        await self.db.update_booking_status(booking_id, "CONFIRMED", f"Confirmed by {admin_name}")
        await self.sheets.update_booking_status(booking_id, "CONFIRMED")
        
        # Decrease room available count
        await self.sheets.decrease_room_available(booking["room_type"])
        
        # Get resort contact phone
        resort_data = context.bot_data.get("resort_data", {})
        resort_contact = resort_data.get("resort", {}).get("contact", {})
        resort_phone = resort_contact.get("phone", "+855 12 345 678")
        resort_email = resort_contact.get("email", "info@resort.com")
        
        # Sync all admin messages
        notifs = await self.db.get_admin_notifications(booking_id)
        for aid, mid in notifs:
            try:
                # We update the original message text for all admins
                new_text = (
                    f"✅ <b>Booking #{booking_id} CONFIRMED by {admin_name}</b>\n\n"
                    f"👤 <b>Guest:</b> {booking['guest_name']}\n"
                    f"� <b>Phone:</b> {booking['guest_phone']}\n"
                    f"�🛏️ <b>Room:</b> {booking['room_type']}\n"
                    f"📅 <b>Check-in:</b> {booking['checkin_date']}\n"
                    f"📅 <b>Check-out:</b> {booking['checkout_date']}\n"
                    f"👥 <b>Guests:</b> {booking['num_guests']}\n\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📞 <b>Contact for Changes / ទាក់ទងសម្រាប់ការផ្លាស់ប្តូរ:</b>\n"
                    f"☎️ {resort_phone}\n"
                    f"📧 {resort_email}\n\n"
                    f"<i>Share with guest if any changes needed / ចែករំលែកលេខនេះដល់ភ្ញៀវប្រសិនបើមានការផ្លាស់ប្តូរ</i>"
                )
                await context.bot.edit_message_text(
                    chat_id=aid, message_id=mid, text=new_text, parse_mode=ParseMode.HTML, reply_markup=None
                )
            except: pass
            
        await self.db.clear_admin_notifications(booking_id)

        # Notify guest
        try:
            user = await self.db.get_user(booking["user_id"])
            lang = user.get("language", "EN") if user else "EN"
            
            # Get resort contact info
            resort_data = context.bot_data.get("resort_data", {})
            resort_contact = resort_data.get("resort", {}).get("contact", {})
            resort_phone = resort_contact.get("phone", "+855 12 345 678")
            resort_email = resort_contact.get("email", "info@resort.com")
            
            if lang == "KH":
                success_text = (
                    "🎉 <b>ការកក់របស់អ្នកទទួលបានជោគជ័យ!</b>\n\n"
                    "សូមអរគុណសម្រាប់ការគាំទ្រ Paradise Resort យើងទន្ទឹងរង់ចាំទទួលស្វាគមន៍អ្នក! 🌴\n\n"
                    f"👤 ឈ្មោះ: {booking['guest_name']}\n"
                    f"🛏️ បន្ទប់: {booking['room_type']}\n"
                    f"📅 ថ្ងៃចូល: {booking['checkin_date']}\n"
                    f"📅 ថ្ងៃចេញ: {booking['checkout_date']}\n\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📞 <b>ទាក់ទងសម្រាប់ការផ្លាស់ប្តូរ:</b>\n"
                    f"☎️ {resort_phone}\n"
                    f"📧 {resort_email}"
                )
            else:
                success_text = (
                    "🎉 <b>Your Booking is Success!</b>\n\n"
                    "Thank you for support Paradise Resort, We look forward to welcoming you! 🌴\n\n"
                    f"👤 Name: {booking['guest_name']}\n"
                    f"🛏️ Room: {booking['room_type']}\n"
                    f"📅 Check-in: {booking['checkin_date']}\n"
                    f"📅 Check-out: {booking['checkout_date']}\n\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📞 <b>Contact for Changes:</b>\n"
                    f"☎️ {resort_phone}\n"
                    f"📧 {resort_email}"
                )

            await context.bot.send_message(
                chat_id=booking["user_id"],
                text=success_text,
                parse_mode=ParseMode.HTML,
                reply_markup=start_again_keyboard(lang),
            )
        except Exception as e:
            logger.error("Failed to notify guest %s: %s", booking["user_id"], e)

    async def _decline_booking(self, query, context, booking_id: int):
        booking = await self.db.get_booking(booking_id)
        if not booking:
            await query.answer("Booking not found!", show_alert=True)
            return

        # Update DB and Sheet
        admin_name = query.from_user.first_name
        await self.db.update_booking_status(booking_id, "DECLINED", f"Declined by {admin_name}")
        await self.sheets.update_booking_status(booking_id, "DECLINED")
        
        # Get resort contact phone
        resort_data = context.bot_data.get("resort_data", {})
        resort_contact = resort_data.get("resort", {}).get("contact", {})
        resort_phone = resort_contact.get("phone", "+855 12 345 678")
        resort_email = resort_contact.get("email", "info@resort.com")
        
        # Sync all admin messages
        notifs = await self.db.get_admin_notifications(booking_id)
        for aid, mid in notifs:
            try:
                new_text = (
                    f"❌ <b>Booking #{booking_id} DECLINED by {admin_name}</b>\n\n"
                    f"👤 <b>Guest:</b> {booking['guest_name']}\n"
                    f"� <b>Phone:</b> {booking['guest_phone']}\n"
                    f"�🛏️ <b>Room:</b> {booking['room_type']}\n"
                    f"📅 <b>Check-in:</b> {booking['checkin_date']}\n"
                    f"📅 <b>Check-out:</b> {booking['checkout_date']}\n"
                    f"👥 <b>Guests:</b> {booking['num_guests']}\n\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📞 <b>Contact for Rescheduling / ទាក់ទងដើម្បីកក់ឡើងវិញ:</b>\n"
                    f"☎️ {resort_phone}\n"
                    f"📧 {resort_email}\n\n"
                    f"<i>Guest should contact to reschedule / ភ្ញៀវគួរតែទាក់ទងដើម្បីកក់ឡើងវិញ</i>"
                )
                await context.bot.edit_message_text(
                    chat_id=aid, message_id=mid, text=new_text, parse_mode=ParseMode.HTML, reply_markup=None
                )
            except: pass
            
        await self.db.clear_admin_notifications(booking_id)

        # Notify guest
        try:
            user = await self.db.get_user(booking["user_id"])
            lang = user.get("language", "EN") if user else "EN"
            
            # Get resort contact info
            resort_data = context.bot_data.get("resort_data", {})
            resort_contact = resort_data.get("resort", {}).get("contact", {})
            resort_phone = resort_contact.get("phone", "+855 12 345 678")
            resort_email = resort_contact.get("email", "info@resort.com")
            
            decline_text = (
                (
                    f"😔 <b>ព័ត៌មានអំពីការកក់ (#{booking_id})</b>\n\n"
                    "សូមអភ័យទោស! យើងមិនអាចបញ្ជាក់ការកក់សម្រាប់កាលបរិច្ឆេទដែលអ្នកបានជ្រើសរើសបានទេ។\n\n"
                    "មូលហេតុអាចបណ្តាលមកពីបន្ទប់ពេញ ឬមិនមានបន្ទប់ទំនេរ។\n\n"
                    "សូមទាក់ទងមកយើងខ្ញុំដើម្បីស្វែងរកជម្រើសផ្សេង៖\n"
                    f"📞 {resort_phone}\n"
                    f"📧 {resort_email}\n\n"
                    "សូមអរគុណ និងសូមអភ័យទោសចំពោះភាពមិនងាយស្រួលនេះ 🙏"
                )
                if lang == "KH" else
                (
                    f"😔 <b>Booking Update (#{booking_id})</b>\n\n"
                    "Unfortunately, we are unable to confirm your booking for the requested dates.\n\n"
                    "This may be due to room unavailability.\n\n"
                    "Please contact us to find an alternative:\n"
                    f"📞 {resort_phone}\n"
                    f"📧 {resort_email}\n\n"
                    "We apologize for the inconvenience! 🙏"
                )
            )
            await context.bot.send_message(
                chat_id=booking["user_id"],
                text=decline_text,
                parse_mode=ParseMode.HTML,
                reply_markup=start_again_keyboard(lang),
            )
        except Exception as e:
            logger.error("Failed to notify guest %s: %s", booking["user_id"], e)

    async def _view_booking(self, query, booking_id: int):
        booking = await self.db.get_booking(booking_id)
        if not booking:
            await query.answer("Booking not found!", show_alert=True)
            return

        emoji = STATUS_EMOJI.get(booking["status"], "❓")
        text = (
            f"🔍 <b>Booking #{booking_id} Details</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"{emoji} <b>Status:</b>       {booking['status']}\n"
            f"👤 <b>Guest:</b>        {booking['guest_name']}\n"
            f"📅 <b>Check-in:</b>    {booking['checkin_date']}\n"
            f"📅 <b>Check-out:</b>   {booking['checkout_date']}\n"
            f"🛏️ <b>Room:</b>         {booking['room_type']}\n"
            f"👥 <b>Guests:</b>       {booking['num_guests']}\n"
            f"📝 <b>Requests:</b>    {booking['special_request'] or 'None'}\n"
            f"🕐 <b>Created:</b>     {booking['created_at']}\n"
        )
        if booking.get("admin_note"):
            text += f"📌 <b>Note:</b>         {booking['admin_note']}\n"

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=admin_booking_action_keyboard(booking_id),
        )
