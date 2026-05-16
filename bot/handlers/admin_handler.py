# ============================================================
#  bot/handlers/admin_handler.py — Staff Admin Panel
# ============================================================
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatAction

from bot.services.database import Database
from bot.services.sheets_service import SheetsService
from bot.keyboards.menus import admin_panel_keyboard, admin_booking_action_keyboard, main_menu_keyboard

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
        await self.db.update_booking_status(booking_id, "CONFIRMED", "Confirmed by staff.")
        await self.sheets.update_booking_status(booking_id, "CONFIRMED")
        await query.edit_message_text(
            f"✅ *Booking #{booking_id} CONFIRMED*\n\n"
            f"Guest: {booking['guest_name']}\n"
            f"Room: {booking['room_type']}\n"
            f"Check-in: {booking['checkin_date']}",
            parse_mode=ParseMode.HTML,
        )

        # Notify guest
        try:
            await context.bot.send_message(
                chat_id=booking["user_id"],
                text=(
                    f"🎉 *Your Booking is CONFIRMED! (#{booking_id})*\n\n"
                    f"👤 Name: {booking['guest_name']}\n"
                    f"🛏️ Room: {booking['room_type']}\n"
                    f"📅 Check-in: {booking['checkin_date']}\n"
                    f"📅 Check-out: {booking['checkout_date']}\n"
                    f"👥 Guests: {booking['num_guests']}\n\n"
                    "We look forward to welcoming you! 🌴\n\n"
                    "📞 For any changes: +855 12 345 678"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=main_menu_keyboard(),
            )
        except Exception as e:
            logger.error("Failed to notify guest %s: %s", booking["user_id"], e)

    async def _decline_booking(self, query, context, booking_id: int):
        booking = await self.db.get_booking(booking_id)
        if not booking:
            await query.answer("Booking not found!", show_alert=True)
            return

        # Update DB and Sheet
        await self.db.update_booking_status(booking_id, "DECLINED", "Declined by staff.")
        await self.sheets.update_booking_status(booking_id, "DECLINED")
        await query.edit_message_text(
            f"❌ *Booking #{booking_id} DECLINED*\n\n"
            f"Guest: {booking['guest_name']}\n"
            f"Room: {booking['room_type']}",
            parse_mode=ParseMode.HTML,
        )

        # Notify guest
        try:
            await context.bot.send_message(
                chat_id=booking["user_id"],
                text=(
                    f"😔 <b>Booking Update (#{booking_id})</b>\n\n"
                    f"Unfortunately, we are unable to confirm your booking for the requested dates.\n\n"
                    "This may be due to room unavailability.\n\n"
                    "Please contact us to find an alternative:\n"
                    "📞 +855 12 345 678\n"
                    "📧 info@paradiseresort.com.kh\n\n"
                    "We apologize for the inconvenience! 🙏"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=main_menu_keyboard(),
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
