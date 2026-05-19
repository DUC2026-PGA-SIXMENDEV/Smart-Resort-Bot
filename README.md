# 🏨 Paradise Resort Telegram Bot

A production-grade Telegram bot built for resort/hotel businesses. Handles customer  multi-step room bookings, staff admin panel, and​ two language support (English & Khmer).

---

## ✨ Features

| Feature | Description |
|---|---|
| 📋 Smart Booking | 6-step guided booking form with date validation |
| 👨‍💼 Admin Panel | Staff can confirm/decline bookings, view stats, broadcast |
| 🔔 Notifications | Instant admin alerts + guest confirmation messages |
| 🌐 Bilingual | English 🇺🇸 & Khmer 🇰🇭 language support |
| 💾 Database | Full SQLite history: users, conversations, bookings, ratings |
| 🏠 Menu Navigation | Rich inline keyboards for all resort info sections |
| ⭐ Rating System | Post-stay feedback collection |

---

## 🚀 Quick Setup (5 Minutes)

### Step 1 — Create your Telegram Bot
1. Open Telegram and message **@BotFather**
2. Send `/newbot` and follow instructions
3. Copy your **Bot Token**



### Step 2 — Find Your Admin User ID
1. Message **@userinfobot** on Telegram
2. Copy your **User ID** (a number like `123456789`)

### Step 3 — Configure `.env`
Edit the `.env` file in this folder:

```
TELEGRAM_BOT_TOKEN=your_token_from_botfather
ADMIN_IDS=your_telegram_user_id
```

### Step 4 — Run the Bot
```bash
python main.py
```

---

## 📁 Project Structure

```
Booking_bot/
├── main.py                    # 🚀 Entry point — run this
├── config.py                  # ⚙️  Environment & config loader
├── .env                       # 🔑 Your secret keys (edit this!)
├── requirements.txt           # 📦 Python dependencies
├── bot.log                    # 📋 Runtime log (auto-created)
│
├── data/
│   └── resort_data.json       # 🏨 All resort info (customize this!)
│
└── bot/
    ├── handlers/
    │   ├── start_handler.py   # 👋 /start & /help commands
    │   ├── customer_handler.py# 💬 menu navigation
    │   ├── booking_handler.py # 📋 6-step booking flow
    │   └── admin_handler.py   # 👨‍💼 Staff admin panel
    ├── services/
    │   └── database.py        # 💾 SQLite async database
    └── keyboards/
        └── menus.py           # ⌨️  All Telegram inline keyboards
```

---

## 🏨 Customizing Your Resort

Edit **`data/resort_data.json`** to update:
- Resort name, description, location, contact
- Room types, prices, amenities
- Facilities and operating hours
- Special packages and deals
- Policies (check-in, cancellation, etc.)

---

## 👨‍💼 Admin Commands (Staff Only)

| Command | Description |
|---|---|
| `/admin` | Open admin control panel |
| `/stats` | View detailed statistics |
| `/broadcast <message>` | Send message to ALL users |

**To become admin:** Add your Telegram User ID to `ADMIN_IDS` in `.env`

---

## 📋 Customer Commands

| Command | Description |
|---|---|
| `/start` | Open main menu |
| `/help` | Show help & tips |
| `/cancel` | Cancel current booking |

---

## 🔄 Bot Flow

```
Customer → /start
    → Main Menu
        ├── 🛏️ Rooms → Select room → See details → Book
        ├── 🏊 Facilities → View all facilities
        ├── 📋 Book Room → 6-step booking form
        │       ├── Step 1: Guest name
        │       ├── Step 2: Check-in date
        │       ├── Step 3: Check-out date
        │       ├── Step 4: Room type
        │       ├── Step 5: Number of guests
        │       ├── Step 6: Special requests
        │       └── → Confirm → Admin notified
        ├── 📦 Packages → View deals
        ├── 📜 Policies → View rules
        ├── 📍 Location → Map link
        ├── 📞 Contact → WhatsApp / Facebook
        └── ⭐ My Bookings → View history & rate

Admin ← 🔔 New booking notification
    → ✅ Confirm or ❌ Decline
    → Customer auto-notified
```

---

## 🛠️ Requirements

- Python 3.10+
- Telegram Bot Token 

---

