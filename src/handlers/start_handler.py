# ============================================================
#  bot/handlers/start_handler.py — Welcome & Language Setup
# ============================================================
import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from src.services.database import Database
from src.keyboards.menus import (
    language_start_keyboard,
    main_menu_keyboard
)

logger = logging.getLogger(__name__)

class StartHandler:
    def __init__(self, db: Database, resort_name: str):
        self.db = db
        self.resort_name = resort_name

    # ------------------------------------------------------------------
    # /start — show language picker
    # ------------------------------------------------------------------

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command — Show welcome text and language selection."""
        user = update.effective_user
        
        # Register / update the user in DB
        await self.db.upsert_user(
            user_id=user.id,
            first_name=user.first_name,
            last_name=user.last_name or "",
            username=user.username or ""
        )

        # Show Language Menu
        text = (
            f"🙏 <b>ជម្រាបសួរ {user.first_name}!</b>\n"
            f"សូមស្វាគមន៍មកកាន់ {self.resort_name}។\n\n"
            "សូមជ្រើសរើសភាសារបស់អ្នក:\n"
            "Please choose your language:"
        )
        await update.message.reply_text(
            text, 
            parse_mode=ParseMode.HTML, 
            reply_markup=language_start_keyboard()
        )
        logger.info(f"User {user.id} ({user.first_name}) started the bot — showing language menu.")

    async def language(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /language command — Show language selection."""
        # Show Language Menu
        text = (
            "🌐 <b>សូមជ្រើសរើសភាសារបស់អ្នក:</b>\n\n"
            "Please choose your language:"
        )
        await update.message.reply_text(
            text, 
            parse_mode=ParseMode.HTML, 
            reply_markup=language_start_keyboard()
        )

    # ------------------------------------------------------------------
    # Language Selection Callback
    # ------------------------------------------------------------------

    async def set_language(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Processes the language selection from the start menu."""
        query = update.callback_query
        await query.answer()

        # Extract language (KH or EN)
        lang = query.data.replace("start_lang_", "")
        user_id = query.from_user.id

        # Update database - CORRECT METHOD NAME: set_user_language
        await self.db.set_user_language(user_id, lang)

        # Welcome text in chosen language
        if lang == "KH":
            welcome_text = (
                f"✅ <b>ភាសាខ្មែរត្រូវបានកំណត់!</b>\n\n"
                f"រីករាយដែលបានជួបអ្នក! នេះគឺជាម៉ឺនុយមេសម្រាប់ {self.resort_name}។ "
                "តើមានអ្វីដែលខ្ញុំអាចជួយអ្នកបាននៅថ្ងៃនេះ?"
            )
        else:
            welcome_text = (
                f"✅ <b>English Language Set!</b>\n\n"
                f"Nice to meet you! This is the main menu for {self.resort_name}. "
                "How can I assist you today?"
            )

        await query.edit_message_text(
            text=welcome_text,
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_keyboard(lang)
        )
        logger.info(f"User {user_id} selected language: {lang}")
