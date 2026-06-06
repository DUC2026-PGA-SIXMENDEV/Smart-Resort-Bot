# ============================================================
#  bot/keyboards/menus.py — Bilingual Keyboard Menus
# ============================================================
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup

def language_start_keyboard() -> InlineKeyboardMarkup:
    """First-run language selection — Khmer and English in one row."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇰🇭  ភាសាខ្មែរ",  callback_data="start_lang_KH"),
            InlineKeyboardButton("🇺🇸  English",    callback_data="start_lang_EN"),
        ]
    ])

def language_keyboard() -> InlineKeyboardMarkup:
    """In-app language change — side-by-side."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇰🇭  ភាសាខ្មែរ",  callback_data="lang_KH"),
            InlineKeyboardButton("🇺🇸  English",    callback_data="lang_EN"),
        ]
    ])

def main_menu_keyboard(lang: str = "EN") -> InlineKeyboardMarkup:
    """Main menu — simplified, no AI."""
    if lang == "KH":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 កក់បន្ទប់ឥឡូវនេះ", callback_data="booking_start")],
            [
                InlineKeyboardButton("🛏️ ប្រភេទបន្ទប់",   callback_data="menu_rooms"),
                InlineKeyboardButton("🏨 សេវាកម្មរីសត",   callback_data="menu_facilities")
            ],
            [
                InlineKeyboardButton("📍 ទីតាំង",       callback_data="menu_location"),
                InlineKeyboardButton("📞 ទំនាក់ទំនង",   callback_data="menu_contact")
            ],
            [
                InlineKeyboardButton("⭐ ការកក់របស់ខ្ញុំ", callback_data="menu_mybookings"),
                InlineKeyboardButton("📜 គោលការណ៍",     callback_data="menu_policies")
            ],
            [InlineKeyboardButton("🌐 ប្តូរភាសា (Language)", callback_data="menu_language")]
        ])
    else:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Book a Room Now", callback_data="booking_start")],
            [
                InlineKeyboardButton("🛏️ Our Rooms",      callback_data="menu_rooms"),
                InlineKeyboardButton("🏨 Resort Facilities", callback_data="menu_facilities")
            ],
            [
                InlineKeyboardButton("📍 Location",      callback_data="menu_location"),
                InlineKeyboardButton("📞 Contact Us",    callback_data="menu_contact")
            ],
            [
                InlineKeyboardButton("⭐ My Bookings",    callback_data="menu_mybookings"),
                InlineKeyboardButton("📜 Policies",       callback_data="menu_policies")
            ],
            [InlineKeyboardButton("🌐 Change Language",   callback_data="menu_language")]
        ])

def rooms_menu_keyboard(rooms: list, lang: str = "EN") -> InlineKeyboardMarkup:
    # 2x2 Grid for the Room Gallery
    buttons = []
    row = []
    for i, r in enumerate(rooms):
        label = f"{r['emoji']} {r['name']}"
        row.append(InlineKeyboardButton(label, callback_data=f"room_detail_{r['id']}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    
    back_label = "🔙 ត្រឡប់ក្រោយ" if lang == "KH" else "🔙 Back to Menu"
    buttons.append([InlineKeyboardButton(back_label, callback_data="menu_back")])
    return InlineKeyboardMarkup(buttons)

def room_detail_keyboard(room_id: str, lang: str = "EN") -> InlineKeyboardMarkup:
    if lang == "KH":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 កក់បន្ទប់នេះ", callback_data=f"booking_room_{room_id}")],
            [InlineKeyboardButton("🔙 ត្រឡប់ក្រោយ", callback_data="menu_rooms")]
        ])
    else:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Book This Room", callback_data=f"booking_room_{room_id}")],
            [InlineKeyboardButton("🔙 Back to Rooms",  callback_data="menu_rooms")]
        ])

def back_to_menu_keyboard(lang: str = "EN") -> InlineKeyboardMarkup:
    label = "🏠 ត្រឡប់ទៅម៉ឺនុយ" if lang == "KH" else "🏠 Back to Main Menu"
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data="menu_back")]])

def start_again_keyboard(lang: str = "EN") -> InlineKeyboardMarkup:
    label = "🔄 ចាប់ផ្តើមឡើងវិញ" if lang == "KH" else "🔄 Start Again"
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data="menu_back")]])
def booking_room_availability_keyboard(rooms_with_status: list, lang: str = "EN") -> InlineKeyboardMarkup:
    """Shows one room per row with language-specific labels and availability."""
    buttons = []

    kh_name_by_id = {
        "superior": "\u1794\u1793\u17d2\u1791\u1794\u17cb\u1782\u17d2\u179a\u17c2\u1798\u17bd\u1799",
        "deluxe": "\u1794\u1793\u17d2\u1791\u1794\u17cb\u1782\u17d2\u179a\u17c2\u1796\u17b8\u179a",
        "family": "\u1794\u1793\u17d2\u1791\u1794\u17cb\u1782\u17d2\u179a\u17bd\u179f\u17b6\u179a",
        "executive": "\u1794\u1793\u17d2\u1791\u1794\u17cb VIP",
    }
    kh_name_by_en = {
        "Single Bed Room": "\u1794\u1793\u17d2\u1791\u1794\u17cb\u1782\u17d2\u179a\u17c2\u1798\u17bd\u1799",
        "Twin Room": "\u1794\u1793\u17d2\u1791\u1794\u17cb\u1782\u17d2\u179a\u17c2\u1796\u17b8\u179a",
        "Family Room": "\u1794\u1793\u17d2\u1791\u1794\u17cb\u1782\u17d2\u179a\u17bd\u179f\u17b6\u179a",
        "VIP Room / Deluxe": "\u1794\u1793\u17d2\u1791\u1794\u17cb VIP",
    }

    for r in rooms_with_status:
        count = int(r.get("remains", 0))
        en_name = str(r.get("name", "")).strip()
        rid = str(r.get("id", "")).strip().lower()
        kh_name = kh_name_by_id.get(rid) or kh_name_by_en.get(en_name, en_name)

        if lang == "KH":
            name_text = kh_name
            status_text = f"\u1791\u17c6\u1793\u17c1\u179a {count}" if count > 0 else "\u17a2\u179f\u17cb\u1794\u1793\u17d2\u1791\u1794\u17cb"
        else:
            name_text = en_name
            status_text = f"{count} available" if count > 0 else "Sold out"

        if r.get("is_available"):
            label = f"{r['emoji']} {name_text} [{status_text}]"
            buttons.append([InlineKeyboardButton(label, callback_data=f"room_{r['id']}")])
        else:
            label = f"\U0001F6AB {name_text} [{status_text}]"
            buttons.append([InlineKeyboardButton(label, callback_data="ignore")])

    return InlineKeyboardMarkup(buttons)
def booking_confirm_keyboard(lang: str = "EN") -> InlineKeyboardMarkup:
    if lang == "KH":
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ បញ្ជាក់ការកក់", callback_data="booking_confirm"),
                InlineKeyboardButton("✏️ កែប្រែព័ត៌មាន", callback_data="booking_edit_menu")
            ],
            [InlineKeyboardButton("❌ បោះបង់",      callback_data="booking_cancel")]
        ])
    else:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Confirm Booking", callback_data="booking_confirm"),
                InlineKeyboardButton("✏️ Edit Details",    callback_data="booking_edit_menu")
            ],
            [InlineKeyboardButton("❌ Cancel",          callback_data="booking_cancel")]
        ])

def booking_edit_menu_keyboard(lang: str = "EN") -> InlineKeyboardMarkup:
    if lang == "KH":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 ឈ្មោះ", callback_data="edit_name"), InlineKeyboardButton("📞 ទូរស័ព្ទ", callback_data="edit_phone")],
            [InlineKeyboardButton("🛏️ ប្រភេទបន្ទប់", callback_data="edit_room"), InlineKeyboardButton("👥 ភ្ញៀវ", callback_data="edit_guests")],
            [InlineKeyboardButton("📝 សំណូមពរ", callback_data="edit_special")],
            [InlineKeyboardButton("🔙 ត្រឡប់ក្រោយ", callback_data="booking_back_to_summary")]
        ])
    else:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 Name", callback_data="edit_name"), InlineKeyboardButton("📞 Phone", callback_data="edit_phone")],
            [InlineKeyboardButton("🛏️ Room", callback_data="edit_room"), InlineKeyboardButton("👥 Guests", callback_data="edit_guests")],
            [InlineKeyboardButton("📝 Special", callback_data="edit_special")],
            [InlineKeyboardButton("🔙 Back to Summary", callback_data="booking_back_to_summary")]
        ])

def booking_special_keyboard(lang: str = "EN") -> InlineKeyboardMarkup:
    if lang == "KH":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🌹 ការតុបតែងបន្ទប់ (Decor)", callback_data="sp_decor")],
            [InlineKeyboardButton("🛁 កន្សែងបន្ថែម (Extra Towels)", callback_data="sp_towels")],
            [InlineKeyboardButton("🤫 បន្ទប់ស្ងាត់ (Quiet Room)", callback_data="sp_quiet")],
            [InlineKeyboardButton("⏰ ចូលមុនម៉ោង (Early Check-in)", callback_data="sp_early")],
            [InlineKeyboardButton("✨ គ្មាន (None / Skip)", callback_data="sp_none")]
        ])
    else:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🌹 Room Decoration", callback_data="sp_decor")],
            [InlineKeyboardButton("🛁 Extra Towels",     callback_data="sp_towels")],
            [InlineKeyboardButton("🤫 Quiet Room",       callback_data="sp_quiet")],
            [InlineKeyboardButton("⏰ Early Check-in",   callback_data="sp_early")],
            [InlineKeyboardButton("✨ None / Skip",      callback_data="sp_none")]
        ])

def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 View All Bookings", callback_data="admin_bookings_all")],
        [InlineKeyboardButton("⏳ Pending Bookings",  callback_data="admin_bookings_pending")],
        [InlineKeyboardButton("👥 View Users",        callback_data="admin_users_list")],
        [InlineKeyboardButton("🏠 Main Menu",         callback_data="menu_back")]
    ])

def admin_booking_action_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f"admin_confirm_{booking_id}"),
            InlineKeyboardButton("❌ Decline", callback_data=f"admin_decline_{booking_id}")
        ]
    ])

def booking_cancel_reply_keyboard(lang: str = "EN") -> ReplyKeyboardMarkup:
    """A clean Reply Keyboard with a single Cancel button to freeze active text inputs."""
    button_text = "❌ Cancel Booking" if lang == "EN" else "❌ បោះបង់ការកក់"
    return ReplyKeyboardMarkup(
        [[button_text]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
