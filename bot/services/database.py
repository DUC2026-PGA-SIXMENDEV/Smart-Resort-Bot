# ============================================================
#  bot/services/database.py — Async SQLite Database Layer
# ============================================================
import aiosqlite
import logging
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

# Timezone for Cambodia
KH_TZ = pytz.timezone("Asia/Phnom_Penh")


def now_kh() -> str:
    """Return current Cambodia time as ISO string."""
    return datetime.now(KH_TZ).strftime("%Y-%m-%d %H:%M:%S")


class Database:
    """
    Manages all database operations for the resort bot.
    Uses aiosqlite for non-blocking async I/O.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path

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
            """)
            await db.commit()
        logger.info("✅ Database initialized at '%s'", self.db_path)

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
        checkin_date: str,
        checkout_date: str,
        room_type: str,
        num_guests: int,
        special_request: str,
    ) -> int:
        """Creates a new booking and returns its ID."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO bookings
                    (user_id, guest_name, checkin_date, checkout_date,
                     room_type, num_guests, special_request, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
            """, (
                user_id, guest_name, checkin_date, checkout_date,
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
