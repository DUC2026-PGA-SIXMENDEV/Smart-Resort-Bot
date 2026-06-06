import asyncio
import logging
from config import Config
from src.services.sheets_service import SheetsService

# Setup logging
logging.basicConfig(level=logging.INFO)

async def test_inventory():
    config = Config()
    sheets = SheetsService(config.GOOGLE_SHEETS_CREDS, config.GOOGLE_SHEETS_NAME)
    
    print("\n🔍 Checking Google Sheets connection...")
    inventory = await sheets.get_room_inventory()
    
    if inventory:
        print("✅ SUCCESS! Connected to the 'Rooms' tab.")
        print("-" * 30)
        for room, count in inventory.items():
            print(f"📍 {room}: {count} rooms total")
        print("-" * 30)
    else:
        print("❌ FAILED! Could not read the 'Rooms' tab.")
        print("Please check if the tab name is exactly 'Rooms' and the headers are correct.")

if __name__ == "__main__":
    asyncio.run(test_inventory())
