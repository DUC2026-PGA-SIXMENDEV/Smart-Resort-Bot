import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from src.services.database import Database
from src.services.sheets_service import SheetsService
from src.services.gspread_workflow import notify_admin_of_booking

logger = logging.getLogger(__name__)

class AdminHandler:
    def __init__(self, db: Database, admin_ids: list[int], sheets: SheetsService):
        self.db = db
        self.admin_ids = admin_ids
        self.sheets = sheets

    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Displays the main Admin Control Panel."""
        user_id = update.effective_user.id
        if user_id not in self.admin_ids:
            if update.message:
                await update.message.reply_text("⛔ Unauthorized access. You are not an admin.")
            return

        text = "👨‍💼 <b>Admin Control Panel</b>\n\nSelect an option below to manage the resort:"
        keyboard = [
            [InlineKeyboardButton("📋 View All Bookings", callback_data="admin_all_bookings")],
            [InlineKeyboardButton("⏳ Pending Bookings", callback_data="admin_pending_bookings")],
            [InlineKeyboardButton("👥 View Users", callback_data="admin_users")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if update.message:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
        elif update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")

    async def show_all_bookings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Shows recent bookings and adds 'Check-out' buttons for active ones."""
        query = update.callback_query
        bookings = await self.db.get_all_bookings(limit=15)
        
        if not bookings:
            text = "📋 <b>All Bookings</b>\n\nNo bookings found in the database."
            keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_main")]]
            await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
            return

        text = "📋 <b>Recent Bookings</b>\n\n"
        keyboard = []
        
        for b in bookings:
            status = b['status']
            b_id = b['id']
            room = b['room_type']
            guest = b['guest_name']
            
            if status in ["CONFIRMED", "PAID"]:
                emoji = "✅"
                # Add check-out button for confirmed guests
                keyboard.append([
                    InlineKeyboardButton(f"🚪 Check-out: {guest} (#{b_id})", callback_data=f"checkout_{b_id}_{room}")
                ])
            elif status == "PENDING":
                emoji = "⏳"
            elif status == "CHECKED OUT":
                emoji = "🚪"
            elif status == "DECLINED":
                emoji = "❌"
            else:
                emoji = "📝"
                
            text += f"{emoji} <b>ID:</b> {b_id} | <b>Guest:</b> {guest}\n"
            text += f"   🚪 {room} | 📅 {b['checkin_date']} - {b['checkout_date']}\n"
            text += f"   <i>Status: {status}</i>\n\n"
        
        keyboard.append([InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_main")])
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

    async def show_pending_bookings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Shows pending bookings with Approve / Decline buttons."""
        query = update.callback_query
        pending = await self.db.get_pending_bookings()
        
        if not pending:
            text = "⏳ <b>Pending Bookings</b>\n\nThere are no pending bookings requiring attention right now! 🎉"
            keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_main")]]
            await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
            return
            
        text = f"⏳ <b>Pending Bookings ({len(pending)})</b>\n\nPlease review the following:\n\n"
        keyboard = []
        
        for b in pending:
            b_id = b['id']
            text += (
                f"🆔 <b>Booking ID:</b> {b_id}\n"
                f"👤 <b>Guest:</b> {b['guest_name']}\n"
                f"📞 <b>Phone:</b> {b['guest_phone']}\n"
                f"🚪 <b>Room:</b> {b['room_type']}\n"
                f"📅 <b>Dates:</b> {b['checkin_date']} to {b['checkout_date']}\n"
                f"👥 <b>Guests:</b> {b['num_guests']}\n"
                "──────────────\n"
            )
            
            keyboard.append([
                InlineKeyboardButton(f"✅ Approve #{b_id}", callback_data=f"admin_approve_{b_id}"),
                InlineKeyboardButton(f"❌ Decline #{b_id}", callback_data=f"admin_decline_{b_id}")
            ])
                
        keyboard.append([InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_main")])
        try:
            await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        except BadRequest:
            pass  # Ignore "Message is not modified" errors

    async def show_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Displays a list of registered users."""
        query = update.callback_query
        users = await self.db.get_all_users()
        
        if not users:
            text = "👥 <b>Registered Users</b>\n\nNo users found."
        else:
            text = f"👥 <b>Registered Users (Total: {len(users)})</b>\n\n"
            for u in users[-20:]:  # Limiting to 20 so Telegram doesn't block the message
                name = u.get('first_name', '') or 'User'
                username = f" (@{u['username']})" if u.get('username') else ""
                text += f"👤 <b>{name}</b>{username}\n"
                text += f"   🆔 {u['user_id']} | 🗣️ {u.get('language', 'EN')}\n\n"
                
        keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_main")]]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

    async def handle_admin_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """The main router that catches button clicks and triggers the correct functions."""
        query = update.callback_query
        user_id = update.effective_user.id
        
        if user_id not in self.admin_ids:
            await query.answer("⛔ Unauthorized", show_alert=True)
            return

        await query.answer()

        # Route the view buttons
        if query.data == "admin_main":
            await self.admin_panel(update, context)

        elif query.data == "admin_all_bookings":
            await self.show_all_bookings(update, context)
            
        elif query.data == "admin_pending_bookings":
            await self.show_pending_bookings(update, context)
            
        elif query.data == "admin_users":
            await self.show_users(update, context)
            
        # Handle Approve & Confirm Action
        elif query.data.startswith("admin_approve_") or query.data.startswith("admin_confirm_"):
            booking_id = int(query.data.split("_")[-1])
            
            booking = await self.db.get_booking(booking_id)
            if not booking:
                await query.answer("❌ Booking not found.", show_alert=True)
                return

            room_type = booking["room_type"]
            guest_name = booking["guest_name"]
            user_id = booking["user_id"]
            
            # Deduct inventory first
            success = await notify_admin_of_booking(
                context=context,
                admin_chat_id=update.effective_chat.id, 
                booking_id=str(booking_id),
                room_type=room_type,
                guest_name=guest_name
            )
            
            if success:
                await self.db.update_booking_status(booking_id, "CONFIRMED", "Approved via Admin Panel")
                await self.sheets.update_booking_status(booking_id, "CONFIRMED")
                await query.answer(f"✅ Booking #{booking_id} Approved!", show_alert=True)

                # --- Notify Customer of Approval ---
                user = await self.db.get_user(user_id)
                lang = user.get("language", "EN") if user else "EN"
                msg = (
                    f"🎉 <b>ការកក់របស់អ្នកត្រូវបានបញ្ជាក់!</b>\n\nសូមអរគុណសម្រាប់ការកក់បន្ទប់ <b>{room_type}</b>។ យើងខ្ញុំទន្ទឹងរង់ចាំការមកដល់របស់លោកអ្នក។"
                    if lang == "KH" else
                    f"🎉 <b>Your booking is confirmed!</b>\n\nThank you for booking the <b>{room_type}</b>. We look forward to welcoming you."
                )
                try:
                    await context.bot.send_message(chat_id=user_id, text=msg, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Failed to send approval confirmation to user {user_id}: {e}")
                
                # Refresh the screen only if successful
                await self.show_pending_bookings(update, context)
            else:
                await query.answer(f"❌ Cannot approve: {room_type} is completely booked!", show_alert=True)
            
            
        # Handle Decline & Reject Action
        elif query.data.startswith("admin_decline_") or query.data.startswith("admin_reject_"):
            booking_id = int(query.data.split("_")[-1])

            # Fetch booking to get user_id and room_type for the notification
            booking = await self.db.get_booking(booking_id)
            if not booking:
                await query.answer("❌ Booking not found.", show_alert=True)
                return

            user_id = booking["user_id"]
            room_type = booking["room_type"]

            await self.db.update_booking_status(booking_id, "DECLINED", "Declined via Admin Panel")
            await self.sheets.update_booking_status(booking_id, "DECLINED")
            await query.answer(f"❌ Booking #{booking_id} Declined!", show_alert=True)

            # --- Notify Customer of Decline ---
            user = await self.db.get_user(user_id)
            lang = user.get("language", "EN") if user else "EN"
            msg = (
                f"😔 <b>ការកក់របស់អ្នកត្រូវបានបដិសេធ</b>\n\nជាអកុសល ការកក់របស់អ្នកសម្រាប់បន្ទប់ <b>{room_type}</b> មិនអាចដំណើរការបានទេ។ សូមទាក់ទងមកយើងខ្ញុំសម្រាប់ព័ត៌មានបន្ថែម។"
                if lang == "KH" else
                f"😔 <b>Your booking has been declined.</b>\n\nUnfortunately, your booking for the <b>{room_type}</b> could not be processed. Please contact us for more information."
            )
            try:
                await context.bot.send_message(chat_id=user_id, text=msg, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Failed to send decline notification to user {user_id}: {e}")
            
            # Refresh the screen
            await self.show_pending_bookings(update, context)
