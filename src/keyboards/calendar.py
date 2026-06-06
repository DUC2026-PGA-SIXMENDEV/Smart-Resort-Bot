# ============================================================
#  bot/keyboards/calendar.py — Inline Calendar Component
# ============================================================
import calendar
from datetime import datetime, timedelta
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

def create_calendar(year: int = None, month: int = None, lang: str = "EN") -> InlineKeyboardMarkup:
    """Creates a monthly calendar keyboard."""
    now = datetime.now()
    if year is None: year = now.year
    if month is None: month = now.month

    # Header: Month and Year
    month_name = calendar.month_name[month]
    if lang == "KH":
        kh_months = [
            "", "មករា", "កុម្ភៈ", "មីនា", "មេសា", "ឧសភា", "មិថុនា", 
            "កក្កដា", "សីហា", "កញ្ញា", "តុលា", "វិច្ឆិកា", "ធ្នូ"
        ]
        month_display = f"{kh_months[month]} {year}"
    else:
        month_display = f"{month_name} {year}"

    keyboard = []
    
    # Row 1: Month/Year header
    keyboard.append([InlineKeyboardButton(month_display, callback_data="ignore")])

    # Row 2: Days of week
    if lang == "KH":
        days = ["ច", "អ", "ព", "ព្រ", "សុ", "ស", "អា"]
    else:
        days = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
    keyboard.append([InlineKeyboardButton(d, callback_data="ignore") for d in days])

    # Calendar Rows
    month_calendar = calendar.monthcalendar(year, month)
    for week in month_calendar:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="ignore"))
            else:
                # Check if date is in the past
                date_obj = datetime(year, month, day)
                if date_obj.date() < now.date():
                    row.append(InlineKeyboardButton("✖️", callback_data="ignore"))
                else:
                    callback_data = f"cal_set_{day}_{month}_{year}"
                    row.append(InlineKeyboardButton(str(day), callback_data=callback_data))
        keyboard.append(row)

    # Row 3: Navigation
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    
    # Only allow going forward or current month
    nav_row = []
    if datetime(year, month, 1).date() > now.replace(day=1).date():
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"cal_nav_{prev_month}_{prev_year}"))
    else:
        nav_row.append(InlineKeyboardButton(" ", callback_data="ignore"))
        
    nav_row.append(InlineKeyboardButton("🏠 Menu", callback_data="booking_cancel"))
    nav_row.append(InlineKeyboardButton("➡️", callback_data=f"cal_nav_{next_month}_{next_year}"))
    keyboard.append(nav_row)

    return InlineKeyboardMarkup(keyboard)
