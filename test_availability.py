import asyncio
import logging
from config import Config
from bot.services.sheets_service import SheetsService

logging.basicConfig(level=logging.INFO, format="%(message)s")

async def debug_availability():
    config = Config()
    sheets = SheetsService(config.GOOGLE_SHEETS_CREDS, config.GOOGLE_SHEETS_NAME)
    
    print("\n" + "="*60)
    print("  DEBUG: Room Availability Check (SHEETS ONLY)")
    print("="*60)
    
    # Get inventory from Rooms sheet
    print("\n📊 STEP 1: Reading 'Available' count from Rooms sheet...")
    inventory = await sheets.get_room_inventory()
    
    if inventory:
        print("\n✅ Available rooms (from Rooms sheet, column C):")
        for room, count in inventory.items():
            status = "✅" if count > 0 else "❌"
            print(f"   {status} {room}: {count}")
    else:
        print("❌ Failed to load inventory!")
        return
    
    print("\n" + "="*60)
    print("  NOTE: Bot now uses ONLY the 'Available' column")
    print("  from Google Sheets Rooms tab. No local database")
    print("  calculations. All data fetches REAL-TIME from sheets!")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(debug_availability())

