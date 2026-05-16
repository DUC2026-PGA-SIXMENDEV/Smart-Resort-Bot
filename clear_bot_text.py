import asyncio
from telegram import Bot
import os
from dotenv import load_dotenv

# Load your token
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def clear_description():
    bot = Bot(TOKEN)
    # This clears the "What can this bot do?" text
    await bot.set_my_description("")
    # This clears the profile description
    await bot.set_my_short_description("")
    print("✅ Bot description and short description have been CLEARED!")

if __name__ == "__main__":
    asyncio.run(clear_description())
