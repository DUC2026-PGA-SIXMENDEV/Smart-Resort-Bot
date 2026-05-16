# ============================================================
#  main.py — Resort Telegram Bot Entry Point (No AI Version)
# ============================================================
import json
import logging
import sys
import io
from pathlib import Path

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import Config
from bot.services.database import Database
from bot.services.sheets_service import SheetsService
from bot.handlers.start_handler import StartHandler
from bot.handlers.customer_handler import CustomerHandler
from bot.handlers.booking_handler import (
    BookingHandler,
    NAME, PHONE, CHECKIN, CHECKOUT, ROOM_TYPE, GUESTS, SPECIAL, CONFIRM,
)
from bot.handlers.admin_handler import AdminHandler

# ── Logging Setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

RESORT_DATA_PATH = Path(__file__).parent / "data" / "resort_data.json"

def load_resort_data() -> dict:
    try:
        with open(RESORT_DATA_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.critical("❌ Failed to load resort_data.json: %s", e)
        sys.exit(1)

async def post_init(application: Application) -> None:
    db: Database = application.bot_data["db"]
    await db.initialize()
    resort_data = load_resort_data()
    application.bot_data["resort_data"] = resort_data
    resort_name = resort_data.get("resort", {}).get("name", "Resort Bot")
    # Removed automatic description to allow manual setting via @BotFather
    # await application.bot.set_my_description(f"🏨 Welcome to {resort_name}! I'm here to help you book your stay easily.")
    logger.info("✅ Bot is ready. Resort: %s", resort_name)

def build_application(config: Config) -> Application:
    db = Database(config.DATABASE_PATH)
    sheets = SheetsService(config.GOOGLE_SHEETS_CREDS, config.GOOGLE_SHEETS_NAME)

    # Initialize handlers
    start_handler    = StartHandler(db, config.RESORT_NAME)
    customer_handler = CustomerHandler(db)
    booking_handler  = BookingHandler(db, config.ADMIN_IDS, sheets)
    admin_handler    = AdminHandler(db, config.ADMIN_IDS, sheets)

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    app.bot_data["db"] = db

    # ── Booking Conversation Handler ─────────────────────────────────────────
    booking_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(booking_handler.start_booking, pattern=r"^booking_(start|room_.+)$"),
            CallbackQueryHandler(booking_handler.start_check_availability, pattern=r"^menu_availability$")
        ],
        states={
            NAME:      [MessageHandler(filters.TEXT & ~filters.COMMAND, booking_handler.get_name)],
            PHONE:     [MessageHandler(filters.TEXT & ~filters.COMMAND, booking_handler.get_phone)],
            CHECKIN:   [CallbackQueryHandler(booking_handler.get_checkin, pattern=r"^(cal_|ignore)")],
            CHECKOUT:  [CallbackQueryHandler(booking_handler.get_checkout, pattern=r"^(cal_|ignore)")],
            ROOM_TYPE: [CallbackQueryHandler(booking_handler.get_room_type, pattern=r"^(room_|booking_cancel)")],
            GUESTS:    [MessageHandler(filters.TEXT & ~filters.COMMAND, booking_handler.get_guests)],
            SPECIAL:   [CallbackQueryHandler(booking_handler.get_special, pattern=r"^sp_")],
            CONFIRM:   [CallbackQueryHandler(booking_handler.confirm_booking, pattern=r"^(booking_|edit_)")],
        },
        fallbacks=[CommandHandler("cancel", booking_handler.cancel), CommandHandler("start", booking_handler.cancel)],
        allow_reentry=True,
    )

    # ── Registration ──────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", start_handler.start))
    app.add_handler(CommandHandler("admin", admin_handler.admin_panel))
    app.add_handler(booking_conv)
    app.add_handler(CallbackQueryHandler(start_handler.set_language, pattern=r"^start_lang_"))
    app.add_handler(CallbackQueryHandler(admin_handler.handle_admin_callback, pattern=r"^admin_"))
    app.add_handler(CallbackQueryHandler(customer_handler.handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, customer_handler.handle_message))

    return app

if __name__ == "__main__":
    try:
        conf = Config()
        application = build_application(conf)
        print("\n" + "="*50 + "\n  PARADISE RESORT TELEGRAM BOT v1.1 (Lite)\n  No-AI Professional Booking System\n" + "="*50)
        application.run_polling(drop_pending_updates=True)
    except Exception as e:
        logger.error("❌ Fatal error: %s", e)
