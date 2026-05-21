# Google Sheets Room Availability Integration - Update Summary

## Overview
The booking system now fetches **real-time room availability** directly from Google Sheets instead of storing data locally. The system automatically queries the "Rooms" tab to get current available room counts and accounts for existing bookings.

## Changes Made

### 1. **database.py** - Added Room Availability Methods
- **Modified Constructor**: `Database` now accepts `sheets_service` parameter
- **New Methods Added**:
  - `get_available_rooms()` - Fetches all room inventory from Sheets
  - `get_available_count(room_type)` - Gets available count for a specific room
  - `check_availability(room_type, checkin_date, checkout_date)` - Calculates available rooms accounting for bookings
  - `get_all_available_rooms_by_dates(checkin_date, checkout_date)` - Gets availability for all rooms in a date range

### 2. **main.py** - Connected Database to Sheets Service
```python
db = Database(config.DATABASE_PATH)
sheets = SheetsService(config.GOOGLE_SHEETS_CREDS, config.GOOGLE_SHEETS_NAME)
db.sheets_service = sheets  # Link sheets service to database
```

### 3. **booking_handler.py** - Updated Availability Queries
- **Line ~295**: Updated `get_checkout()` method to use `await self.db.check_availability()`
- **Line ~587**: Updated `confirm_booking()` method to use `await self.db.check_availability()`
- Changed from: `inventory = await self.sheets.get_room_inventory()` (raw counts)
- Changed to: `remains = await self.db.check_availability(name, ci_str, co_str)` (smart calculation)

## How It Works

### Room Availability Flow:
1. User selects check-in and check-out dates
2. System calls `db.check_availability()` for each room type
3. Database fetches:
   - **Total inventory** from Google Sheets "Rooms" tab (Column C: Available)
   - **Booked count** from Google Sheets "Sheet1" tab (bookings with status CONFIRMED/PAID)
4. Returns: `available = total - booked`
5. UI displays available room counts with "(X left)" or "(❌ Sold Out)"

### Google Sheets Structure:
- **"Rooms" Tab** (Used for Inventory):
  - Column A: Room Type (e.g., "Single Bed Room", "Twin Room", "Family Room", "VIP Room / Deluxe")
  - Column B: Total Inventory
  - Column C: Available (THIS IS THE SOURCE OF TRUTH)

- **"Sheet1" Tab** (Used for Bookings):
  - Column G: Room Type (matched with available rooms)
  - Column B: Status (CONFIRMED/PAID = booked)
  - Column E: Check-in Date
  - Column F: Check-out Date

## Benefits

✅ **Real-time Data**: No more stale data - always fetches from Sheets  
✅ **Automatic Sync**: No need to manually update or store room counts  
✅ **Accurate Availability**: Accounts for existing bookings automatically  
✅ **No Local Storage**: Room inventory no longer stored in project files  
✅ **Dynamic Updates**: When admins update Sheets, changes reflect immediately  

## Key Functions

### Get Room Availability
```python
# Get available rooms for specific dates
availability = await db.check_availability("Single Bed Room", "20/05/2026", "22/05/2026")
# Returns: 3 (for example, if 2 are booked)

# Get all rooms availability for a date range
all_availability = await db.get_all_available_rooms_by_dates("20/05/2026", "22/05/2026")
# Returns: {"Single Bed Room": 3, "Twin Room": 4, "Family Room": 5, ...}
```

## Testing

To verify the integration is working:
1. Run the bot: `python main.py`
2. Start a booking conversation
3. Select check-in and check-out dates
4. Check that room availability displays correctly (from Sheets)
5. Update availability in Sheets "Rooms" tab
6. Start a new booking - you should see the updated counts

## Notes

- The system maintains backward compatibility with `resort_data.json` for room descriptions and amenities
- Actual room counts ONLY come from Google Sheets now
- Booking calculations properly handle date overlaps (inclusive/exclusive logic)
- Timezone: Cambodia (Asia/Phnom_Penh) is used for all timestamps
