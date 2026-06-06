import json
import logging
import sys
import io
import asyncio
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import time

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
from src.services.database import Database
from src.services.sheets_service import SheetsService
from src.handlers.start_handler import StartHandler
from src.handlers.customer_handler import CustomerHandler
from src.handlers.booking_handler import (
    BookingHandler,
    NAME, PHONE, CHECKIN, CHECKOUT, ROOM_TYPE, GUESTS, SPECIAL, CONFIRM, ROOM_ID_INPUT,
)
from src.handlers.admin_handler import AdminHandler
from src.services.gspread_workflow import GspreadSheetsManager, handle_admin_checkout_callback

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


class HealthCheckHandler(BaseHTTPRequestHandler):
    """Small HTTP endpoint for Render web services running in polling mode."""

    def _send_ok(self, include_body: bool = True) -> None:
        body = b"ok\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body) if include_body else 0))
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path in {"/", "/health", "/healthz"}:
            self._send_ok()
            return
        self.send_error(404)

    def do_HEAD(self) -> None:
        if self.path in {"/", "/health", "/healthz"}:
            self._send_ok(include_body=False)
            return
        self.send_error(404)

    def log_message(self, format: str, *args: object) -> None:
        logger.debug("Health check: " + format, *args)


def start_health_server() -> None:
    """Bind Render's PORT so a polling bot can run as a web service."""
    port_value = os.getenv("PORT")
    if not port_value:
        return

    try:
        port = int(port_value)
    except ValueError:
        logger.warning("Ignoring invalid PORT value: %r", port_value)
        return

    server = ThreadingHTTPServer(("0.0.0.0", port), HealthCheckHandler)
    thread = threading.Thread(target=server.serve_forever, name="health-server", daemon=True)
    thread.start()
    logger.info("Health server listening on 0.0.0.0:%s", port)


def env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def run_bot(application: Application) -> None:
    """Run with Telegram webhooks on Render when configured, otherwise polling."""
    webhook_url = os.getenv("WEBHOOK_URL", "").strip()

    if webhook_url:
        webhook_path = os.getenv("WEBHOOK_PATH", "telegram").strip("/") or "telegram"
        try:
            port = int(os.getenv("PORT", "10000"))
        except ValueError:
            port = 10000
        public_base_url = webhook_url.rstrip("/")
        full_webhook_url = (
            public_base_url
            if public_base_url.endswith(f"/{webhook_path}")
            else f"{public_base_url}/{webhook_path}"
        )
        logger.info("Starting Telegram webhook on 0.0.0.0:%s/%s", port, webhook_path)
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=webhook_path,
            webhook_url=full_webhook_url,
            drop_pending_updates=env_flag("DROP_PENDING_UPDATES", False),
            secret_token=os.getenv("WEBHOOK_SECRET_TOKEN") or None,
        )
        return

    start_health_server()
    logger.info("Starting Telegram polling")
    application.run_polling(drop_pending_updates=env_flag("DROP_PENDING_UPDATES", True))


def ensure_main_event_loop() -> None:
    """Create a main-thread event loop for libraries that still call get_event_loop()."""
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

def load_resort_data() -> dict:
    try:
        with open(RESORT_DATA_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.critical("Failed to load resort_data.json: %s", e)
        sys.exit(1)

async def post_init(application: Application) -> None:
    db: Database = application.bot_data["db"]
    await db.initialize()
    resort_data = load_resort_data()
    application.bot_data["resort_data"] = resort_data
    resort_name = resort_data.get("resort", {}).get("name", "Resort Bot")
    # Removed automatic description to allow manual setting via @BotFather
    # await application.bot.set_my_description(f"🏨 Welcome to {resort_name}! I'm here to help you book your stay easily.")
    
    # Schedule daily checkout sync (run in background, don't wait for it)
    sheets: SheetsService = application.bot_data.get("sheets")
    if sheets and application.job_queue:
        # Run in background without blocking bot startup
        asyncio.create_task(sheets.sync_checkout_availability())
        # Then run daily at 1 AM UTC
        application.job_queue.run_daily(sheets.sync_checkout_availability, time(1, 0), name="sync_checkouts")
        logger.info("✅ Checkout sync job scheduled (daily at 1:00 UTC)")
    
    logger.info("✅ Bot is ready. Resort: %s", resort_name)

def build_application(config: Config) -> Application:
    db = Database(config.DATABASE_PATH)
    sheets = SheetsService(config.GOOGLE_SHEETS_CREDS, config.GOOGLE_SHEETS_NAME)
    gspread_manager = GspreadSheetsManager(config.GOOGLE_SHEETS_CREDS, config.GOOGLE_SHEETS_NAME)
    
    # Pass sheets_service to database for live room availability fetching
    db.sheets_service = sheets

    # Initialize handlers
    start_handler    = StartHandler(db, config.RESORT_NAME)
    customer_handler = CustomerHandler(db)
    booking_handler  = BookingHandler(db, config.ADMIN_IDS, sheets)
    admin_handler    = AdminHandler(db, config.ADMIN_IDS, sheets)

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    app.bot_data["db"] = db
    app.bot_data["sheets"] = sheets
    app.bot_data["gspread_manager"] = gspread_manager

    # ── Booking Conversation Handler ─────────────────────────────────────────
    booking_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(booking_handler.start_booking, pattern=r"^(booking_start|menu_booking|booking|booking_room_.+)$"),
            CallbackQueryHandler(booking_handler.start_check_availability, pattern=r"^(check_availability|menu_check)$"),
            CommandHandler("booking", booking_handler.start_booking)
        ],
        states={
            NAME:      [MessageHandler(filters.TEXT & ~filters.COMMAND, booking_handler.get_name)],
            PHONE:     [MessageHandler(filters.TEXT & ~filters.COMMAND, booking_handler.get_phone)],
            CHECKIN:   [
                CallbackQueryHandler(booking_handler.get_checkin, pattern=r"^(cal_|ignore|booking_cancel)"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, booking_handler.checkin_text_blocked),
            ],
            CHECKOUT:  [
                CallbackQueryHandler(booking_handler.get_checkout, pattern=r"^(cal_|ignore|booking_cancel)"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, booking_handler.checkout_text_blocked),
            ],
            ROOM_TYPE: [
                CallbackQueryHandler(booking_handler.get_room_type, pattern=r"^(room_|booking_cancel)"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, booking_handler.room_type_text_blocked),
            ],
            GUESTS:    [MessageHandler(filters.TEXT & ~filters.COMMAND, booking_handler.get_guests)],
            SPECIAL:   [
                CallbackQueryHandler(booking_handler.get_special, pattern=r"^sp_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, booking_handler.special_text_blocked),
            ],
            CONFIRM:   [
                CallbackQueryHandler(booking_handler.confirm_booking, pattern=r"^(booking_|edit_)"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, booking_handler.confirm_text_blocked),
            ],
            ROOM_ID_INPUT: [
                CallbackQueryHandler(booking_handler.handle_room_id_callback, pattern=r"^input_room_id$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, booking_handler.get_room_id)
            ],
        },
        fallbacks=[CommandHandler("cancel", booking_handler.cancel), CommandHandler("start", booking_handler.cancel)],
        allow_reentry=True,
    )

    # ── Registration ──────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", start_handler.start))
    app.add_handler(CommandHandler("admin", admin_handler.admin_panel))
    app.add_handler(CommandHandler("language", start_handler.language))
    app.add_handler(booking_conv)
    app.add_handler(CallbackQueryHandler(start_handler.set_language, pattern=r"^start_lang_"))
    app.add_handler(CallbackQueryHandler(admin_handler.handle_admin_callback, pattern=r"^admin_"))
    app.add_handler(CallbackQueryHandler(handle_admin_checkout_callback, pattern=r"^checkout_"))
    app.add_handler(CallbackQueryHandler(customer_handler.handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, customer_handler.handle_message))

    return app

if __name__ == "__main__":
    try:
        ensure_main_event_loop()
        conf = Config()
        application = build_application(conf)
        print("\n" + "="*50 + "\n  PARADISE RESORT TELEGRAM BOT v1.1 (Lite)\n  No-AI Professional Booking System\n" + "="*50)
        run_bot(application)
    except Exception as e:
        logger.exception("Fatal error: %s", e)
        sys.exit(1)
