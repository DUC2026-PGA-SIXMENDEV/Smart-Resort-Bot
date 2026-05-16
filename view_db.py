# ============================================================
#  view_db.py — Resort Bot Database Viewer
#  Run this anytime to inspect your bot's data:
#       python view_db.py
# ============================================================
import sqlite3
import sys
import os
from datetime import datetime

DB_PATH = "resort_bot.db"

# ── ANSI Colors for Windows Terminal ────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BLUE   = "\033[94m"
GRAY   = "\033[90m"
WHITE  = "\033[97m"

STATUS_COLOR = {
    "PENDING":   YELLOW,
    "CONFIRMED": GREEN,
    "DECLINED":  RED,
    "CANCELLED": GRAY,
}


def color(text, c): return f"{c}{text}{RESET}"
def bold(text):     return f"{BOLD}{text}{RESET}"
def header(title):
    print()
    print(color("=" * 60, CYAN))
    print(color(f"  {title}", BOLD + CYAN))
    print(color("=" * 60, CYAN))


def connect():
    if not os.path.exists(DB_PATH):
        print(color(f"\n❌ Database not found: {DB_PATH}", RED))
        print(color("   Run the bot first to create the database.\n", YELLOW))
        sys.exit(1)
    return sqlite3.connect(DB_PATH)


def show_summary(conn):
    header("📊  DATABASE SUMMARY")
    cur = conn.cursor()

    users     = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    bookings  = cur.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
    pending   = cur.execute("SELECT COUNT(*) FROM bookings WHERE status='PENDING'").fetchone()[0]
    confirmed = cur.execute("SELECT COUNT(*) FROM bookings WHERE status='CONFIRMED'").fetchone()[0]
    declined  = cur.execute("SELECT COUNT(*) FROM bookings WHERE status='DECLINED'").fetchone()[0]
    messages  = cur.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
    avg_row   = cur.execute("SELECT AVG(rating) FROM feedback").fetchone()[0]
    avg_rating = f"{avg_row:.1f}" if avg_row else "No ratings yet"

    print(f"\n  {color('👥 Total Users:',     CYAN)}       {bold(users)}")
    print(f"  {color('📋 Total Bookings:',   CYAN)}    {bold(bookings)}")
    print(f"  {color('⏳ Pending:',          YELLOW)}       {bold(pending)}")
    print(f"  {color('✅ Confirmed:',         GREEN)}      {bold(confirmed)}")
    print(f"  {color('❌ Declined:',          RED)}       {bold(declined)}")
    print(f"  {color('💬 Total Messages:',   BLUE)}    {bold(messages)}")
    print(f"  {color('⭐ Average Rating:',   YELLOW)}    {bold(avg_rating)}")


def show_users(conn):
    header("👥  REGISTERED USERS")
    cur = conn.cursor()
    rows = cur.execute("""
        SELECT user_id, username, first_name, last_name, language, created_at, last_seen
        FROM users ORDER BY created_at DESC
    """).fetchall()

    if not rows:
        print(color("\n  No users yet.\n", GRAY))
        return

    print(f"\n  {'ID':<12} {'Name':<20} {'Username':<18} {'Lang':<6} {'Last Seen'}")
    print(color("  " + "-" * 72, GRAY))
    for r in rows:
        uid, uname, fname, lname, lang, created, last = r
        name = f"{fname or ''} {lname or ''}".strip() or "—"
        uname = f"@{uname}" if uname else "—"
        last = last or created or "—"
        lang_str = color(lang, GREEN if lang == "EN" else YELLOW)
        print(f"  {color(str(uid), CYAN):<20} {name:<20} {uname:<18} {lang_str:<15} {color(last, GRAY)}")


def show_bookings(conn, limit=20):
    header("📋  BOOKINGS")
    cur = conn.cursor()
    rows = cur.execute(f"""
        SELECT b.id, b.guest_name, b.checkin_date, b.checkout_date,
               b.room_type, b.num_guests, b.special_request,
               b.status, b.admin_note, b.created_at,
               u.first_name, u.username
        FROM bookings b
        LEFT JOIN users u ON b.user_id = u.user_id
        ORDER BY b.created_at DESC LIMIT {limit}
    """).fetchall()

    if not rows:
        print(color("\n  No bookings yet.\n", GRAY))
        return

    for r in rows:
        bid, name, cin, cout, room, guests, special, status, note, created, fname, uname = r
        sc = STATUS_COLOR.get(status, WHITE)
        tg = f"@{uname}" if uname else (fname or "—")

        print(f"\n  {color(f'Booking #{bid}', BOLD + CYAN)}  {color(f'[{status}]', sc)}")
        print(f"  {color('Guest:',    GRAY)} {name}  {color(f'(Telegram: {tg})', GRAY)}")
        print(f"  {color('Room:',     GRAY)} {room}  |  Guests: {guests}")
        print(f"  {color('Check-in:', GRAY)} {cin}  →  Check-out: {cout}")
        if special and special != "None":
            print(f"  {color('Requests:', GRAY)} {special}")
        if note:
            print(f"  {color('Admin Note:', YELLOW)} {note}")
        print(f"  {color('Created:', GRAY)} {created}")
        print(color("  " + "─" * 58, GRAY))


def show_conversations(conn, limit=20):
    header("💬  RECENT CONVERSATIONS")
    cur = conn.cursor()
    rows = cur.execute(f"""
        SELECT c.user_id, u.first_name, c.role, c.message, c.created_at
        FROM conversations c
        LEFT JOIN users u ON c.user_id = u.user_id
        ORDER BY c.id DESC LIMIT {limit}
    """).fetchall()

    if not rows:
        print(color("\n  No conversations yet.\n", GRAY))
        return

    for uid, fname, role, msg, ts in rows:
        name  = fname or str(uid)
        trunc = (msg[:80] + "...") if len(msg) > 80 else msg
        if role == "user":
            label = color(f"  [{name}]", GREEN)
        else:
            label = color("  [Bot]",    BLUE)
        print(f"{label} {color(ts, GRAY)}")
        print(f"    {trunc}\n")


def show_feedback(conn):
    header("⭐  CUSTOMER RATINGS & FEEDBACK")
    cur = conn.cursor()
    rows = cur.execute("""
        SELECT f.rating, f.comment, f.created_at, u.first_name
        FROM feedback f
        LEFT JOIN users u ON f.user_id = u.user_id
        ORDER BY f.created_at DESC
    """).fetchall()

    if not rows:
        print(color("\n  No feedback yet.\n", GRAY))
        return

    for rating, comment, ts, fname in rows:
        stars = "⭐" * rating
        name = fname or "Anonymous"
        print(f"\n  {stars}  {color(name, CYAN)}  {color(ts, GRAY)}")
        if comment:
            print(f"  {comment}")
    print()


def main():
    # Enable ANSI on Windows
    if sys.platform == "win32":
        os.system("color")

    print(color("\n" + "=" * 60, CYAN))
    print(color("  RESORT BOT — DATABASE VIEWER", BOLD + WHITE))
    print(color(f"  Database: {os.path.abspath(DB_PATH)}", GRAY))
    print(color("=" * 60, CYAN))

    conn = connect()

    # Parse optional argument: --section
    args = sys.argv[1:]
    section = args[0] if args else "all"

    if section in ("all", "summary"):
        show_summary(conn)
    if section in ("all", "users"):
        show_users(conn)
    if section in ("all", "bookings"):
        show_bookings(conn)
    if section in ("all", "chat", "conversations"):
        show_conversations(conn)
    if section in ("all", "feedback", "ratings"):
        show_feedback(conn)

    conn.close()
    print(color("\n  Done. Press Enter to exit.", GRAY))
    input()


if __name__ == "__main__":
    main()
