# ============================================================
#  bot/services/database.py — Async SQLite Database Layer
# ============================================================
import aiosqlite
import logging
from datetime import datetime
import pytz
import asyncio
import os

logger = logging.getLogger(__name__)

# Timezone for Cambodia
KH_TZ = pytz.timezone("Asia/Phnom_Penh")
MIN_PHONE_NUMBER_LENGTH = 9
MAX_PHONE_NUMBER_LENGTH = 10


def now_kh() -> str:
    """Return current Cambodia time as ISO string."""
    return datetime.now(KH_TZ).strftime("%Y-%m-%d %H:%M:%S")


class Database:
    """
    Manages all database operations for the resort bot.
    Uses aiosqlite for non-blocking async I/O.
    Caches room availability from Google Sheets Column C for fast access.
    Periodically refreshes cache in background to stay in sync.
    """

    def __init__(self, db_path: str, sheets_service=None):
        self.db_path = db_path
        self.sheets_service = sheets_service
        
        # In-memory cache for room availability (fast access, no network calls)
        self._room_cache = {}
        self._cache_lock = asyncio.Lock()
        self._cache_refresh_task = None
        self._cache_refresh_seconds = self._get_cache_refresh_seconds()

    async def initialize(self):
        """Create all tables on first run."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript("""
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS users (
                    user_id     INTEGER PRIMARY KEY,
                    username    TEXT,
                    first_name  TEXT,
                    last_name   TEXT,
                    language    TEXT DEFAULT 'EN',
                    is_blocked  INTEGER DEFAULT 0,
                    created_at  TEXT,
                    last_seen   TEXT
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER,
                    role        TEXT,       -- 'user' or 'assistant'
                    message     TEXT,
                    created_at  TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS bookings (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id         INTEGER,
                    guest_name      TEXT,
                    guest_phone     TEXT CHECK (
                        guest_phone GLOB '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]'
                        OR guest_phone GLOB '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]'
                    ),
                    checkin_date    TEXT,
                    checkout_date   TEXT,
                    room_type       TEXT,
                    num_guests      INTEGER,
                    special_request TEXT,
                    status          TEXT DEFAULT 'PENDING',
                    admin_note      TEXT,
                    created_at      TEXT,
                    updated_at      TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS feedback (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER,
                    rating      INTEGER,
                    comment     TEXT,
                    created_at  TEXT
                );
                CREATE TABLE IF NOT EXISTS admin_notifications (
                    booking_id INTEGER,
                    admin_id   INTEGER,
                    message_id INTEGER
                );
            """)
            await db.commit()
            
            # Migration: Add guest_phone column if it doesn't exist
            async with db.execute("PRAGMA table_info(bookings)") as cursor:
                columns = await cursor.fetchall()
                column_names = [col[1] for col in columns]
                if "guest_phone" not in column_names:
                    await db.execute("ALTER TABLE bookings ADD COLUMN guest_phone TEXT")
                    await db.commit()
                    logger.info("✅ Added guest_phone column to bookings table")
        
        logger.info("✅ Database initialized at '%s'", self.db_path)
        
        # Start background cache refresh task
        self._start_cache_refresh()

    def _start_cache_refresh(self):
        """Start the background task that periodically refreshes room availability cache."""
        if self._cache_refresh_task is None or self._cache_refresh_task.done():
            self._cache_refresh_task = asyncio.create_task(self._refresh_cache_loop())
            logger.info(
                "✅ Started room availability cache refresh task (every %s seconds)",
                self._cache_refresh_seconds,
            )

    def _get_cache_refresh_seconds(self) -> int:
        try:
            return max(30, int(os.getenv("AVAILABILITY_REFRESH_SECONDS", "60")))
        except ValueError:
            return 60

    async def _refresh_cache_loop(self):
        """Background task that refreshes the room availability cache."""
        # First refresh immediately
        await self._refresh_cache_from_sheets()
        
        while True:
            try:
                await asyncio.sleep(self._cache_refresh_seconds)
                await self._refresh_cache_from_sheets()
            except asyncio.CancelledError:
                logger.info("📋 Cache refresh task stopped")
                break
            except Exception as e:
                logger.error(f"❌ Error in cache refresh loop: {e}")
                await asyncio.sleep(5)  # Wait before retrying

    async def _refresh_cache_from_sheets(self):
        """Fetch room availability from Sheets and update cache. Force fresh read each time."""
        if not self.sheets_service:
            return
        
        try:
            # Force reconnection to sheets to get fresh data (bypass any caching in gspread)
            self.sheets_service._connect()
            new_data = await self.sheets_service.get_room_inventory()
            
            async with self._cache_lock:
                if new_data:
                    self._room_cache = new_data
                    logger.info(f"🔄 Cache updated from Sheets: {self._room_cache}")
        except Exception as e:
            logger.error(f"❌ Error refreshing cache from Sheets: {e}")

    # ------------------------------------------------------------------
    # ROOM AVAILABILITY OPERATIONS (Uses Cache - Fast & Efficient)
    # ------------------------------------------------------------------

    async def get_available_rooms(self) -> dict:
        """
        Returns cached room availability from Sheets Column C.
        Cache is refreshed periodically in the background automatically.
        Instant response - NO network calls for each user request.
        """
        async with self._cache_lock:
            if not self._room_cache:
                # First time - fetch immediately and cache
                if self.sheets_service:
                    try:
                        self.sheets_service._connect()
                        self._room_cache = await self.sheets_service.get_room_inventory()
                        logger.info(f"✅ Initial cache loaded: {self._room_cache}")
                    except Exception as e:
                        logger.error(f"❌ Error loading initial cache: {e}")
                return self._room_cache
            return self._room_cache

    async def get_available_count(self, room_type: str) -> int:
        """
        Returns the available count for a specific room type from cache.
        No network calls - instant response.
        """
        inventory = await self.get_available_rooms()
        return inventory.get(room_type, 0)

    async def refresh_availability_now(self):
        """
        Force an immediate refresh of room availability from Sheets.
        Useful when admins update the sheet and need instant sync.
        """
        logger.info("🔄 Manual refresh requested...")
        await self._refresh_cache_from_sheets()
        logger.info(f"✅ Manual refresh complete: {self._room_cache}")

    async def check_availability(self, room_type: str, checkin_date: str, checkout_date: str) -> int:
        """
        Fetches available room count directly from Google Sheets "Rooms" tab Column C.
        The availability is already pre-calculated in the sheet - no additional calculations needed.
        
        Args:
            room_type: Name of the room type (e.g., 'Single Bed Room', 'Twin Room')
            checkin_date: Check-in date as string (format: 'dd/mm/yyyy') - not used, sheet value is source of truth
            checkout_date: Check-out date as string (format: 'dd/mm/yyyy') - not used, sheet value is source of truth
        
        Returns:
            Number of available rooms from Column C of the Rooms sheet
        """
        # Get available count directly from Column C in Rooms sheet
        available = await self.get_available_count(room_type)
        
        logger.debug(f"📊 {room_type}: {available} available (from Sheets Column C)")
        return available

    async def get_all_available_rooms_by_dates(self, checkin_date: str, checkout_date: str) -> dict:
        """
        Returns available room counts for ALL room types directly from Google Sheets Column C.
        The values are pre-calculated in the sheet - this just fetches them.
        """
        return await self.get_available_rooms()

    # ------------------------------------------------------------------
    # USER OPERATIONS
    # ------------------------------------------------------------------

    async def upsert_user(self, user_id: int, username: str, first_name: str, last_name: str):
        """Insert or update user record on every interaction."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO users (user_id, username, first_name, last_name, created_at, last_seen)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username   = excluded.username,
                    first_name = excluded.first_name,
                    last_name  = excluded.last_name,
                    last_seen  = excluded.last_seen
            """, (user_id, username, first_name, last_name, now_kh(), now_kh()))
            await db.commit()

    async def get_user(self, user_id: int) -> dict | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def set_user_language(self, user_id: int, language: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET language = ? WHERE user_id = ?", (language, user_id)
            )
            await db.commit()

    async def get_all_users(self) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE is_blocked = 0") as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def get_user_count(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    # ------------------------------------------------------------------
    # CONVERSATION HISTORY
    # ------------------------------------------------------------------

    async def save_message(self, user_id: int, role: str, message: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO conversations (user_id, role, message, created_at)
                VALUES (?, ?, ?, ?)
            """, (user_id, role, message, now_kh()))
            await db.commit()
    # --- Admin Notification Sync ---
    async def add_admin_notification(self, bid: int, aid: int, mid: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT INTO admin_notifications (booking_id, admin_id, message_id) VALUES (?, ?, ?)", (bid, aid, mid))
            await db.commit()

    async def get_admin_notifications(self, bid: int):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT admin_id, message_id FROM admin_notifications WHERE booking_id = ?", (bid,)) as cursor:
                return await cursor.fetchall()

    async def clear_admin_notifications(self, bid: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM admin_notifications WHERE booking_id = ?", (bid,))
            await db.commit()
    async def get_conversation_history(self, user_id: int, limit: int = 10) -> list[dict]:
        """Returns last N messages for a user (for AI context)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT role, message FROM conversations
                WHERE user_id = ?
                ORDER BY id DESC LIMIT ?
            """, (user_id, limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in reversed(rows)]

    async def clear_conversation(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM conversations WHERE user_id = ?", (user_id,)
            )
            await db.commit()

    # ------------------------------------------------------------------
    # BOOKING OPERATIONS
    # ------------------------------------------------------------------

    async def create_booking(
        self,
        user_id: int,
        guest_name: str,
        guest_phone: str,
        checkin_date: str,
        checkout_date: str,
        room_type: str,
        num_guests: int,
        special_request: str,
    ) -> int:
        """Creates a new booking and returns its ID."""
        if not (
            guest_phone.isdigit()
            and MIN_PHONE_NUMBER_LENGTH <= len(guest_phone) <= MAX_PHONE_NUMBER_LENGTH
        ):
            raise ValueError(
                f"guest_phone must be {MIN_PHONE_NUMBER_LENGTH} or {MAX_PHONE_NUMBER_LENGTH} digits"
            )

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO bookings
                    (user_id, guest_name, guest_phone, checkin_date, checkout_date,
                     room_type, num_guests, special_request, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
            """, (
                user_id, guest_name, guest_phone, checkin_date, checkout_date,
                room_type, num_guests, special_request, now_kh(), now_kh()
            ))
            await db.commit()
            return cursor.lastrowid

    async def get_booking(self, booking_id: int) -> dict | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM bookings WHERE id = ?", (booking_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def update_booking_status(self, booking_id: int, status: str, admin_note: str = ""):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE bookings
                SET status = ?, admin_note = ?, updated_at = ?
                WHERE id = ?
            """, (status, admin_note, now_kh(), booking_id))
            await db.commit()

    async def get_pending_bookings(self) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT b.*, u.username, u.first_name
                FROM bookings b
                LEFT JOIN users u ON b.user_id = u.user_id
                WHERE b.status = 'PENDING'
                ORDER BY b.created_at DESC
            """) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def get_active_bookings(self) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT b.*, u.username, u.first_name
                FROM bookings b
                LEFT JOIN users u ON b.user_id = u.user_id
                WHERE b.status IN ('CONFIRMED', 'PAID')
                ORDER BY b.created_at ASC
            """) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def get_all_bookings(self, limit: int = 20) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT b.*, u.username, u.first_name
                FROM bookings b
                LEFT JOIN users u ON b.user_id = u.user_id
                ORDER BY b.created_at DESC LIMIT ?
            """, (limit,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def get_booking_count(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM bookings") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def get_user_bookings(self, user_id: int) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM bookings WHERE user_id = ?
                ORDER BY created_at DESC LIMIT 5
            """, (user_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # FEEDBACK OPERATIONS
    # ------------------------------------------------------------------

    async def save_feedback(self, user_id: int, rating: int, comment: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO feedback (user_id, rating, comment, created_at)
                VALUES (?, ?, ?, ?)
            """, (user_id, rating, comment, now_kh()))
            await db.commit()

    async def get_average_rating(self) -> float:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT AVG(rating) FROM feedback") as cursor:
                row = await cursor.fetchone()
                return round(row[0], 1) if row and row[0] else 0.0
