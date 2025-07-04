import asyncio
import logging
import os
import pytz
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import BOT_TOKEN
from handlers import register_all_handlers
from database.db import init_db, migrate_db
from middlewares import setup_middlewares
from utils.notifications import check_expired_waitlist_notifications
from utils.bot_commands import setup_bot_commands

# Ensure logs directory exists
os.makedirs('logs', exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler()
    ]
)

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Initialize scheduler with UTC timezone
scheduler = AsyncIOScheduler(timezone=pytz.UTC)

async def main():
    # Initialize database
    await init_db()

    # Migrate database schema
    await migrate_db()

    # Register all handlers
    register_all_handlers(dp)

    # Setup middlewares
    setup_middlewares(dp)

    # Setup bot commands
    await setup_bot_commands(bot)

    # Add scheduler job to check expired waitlist notifications every 30 minutes
    scheduler.add_job(
        check_expired_waitlist_notifications, 
        'interval', 
        minutes=30, 
        kwargs={'bot': bot}
    )

    # Start scheduler
    scheduler.start()

    # Log scheduler start
    logging.info("Scheduler started, checking expired waitlist notifications every 30 minutes")

    # Start polling
    await dp.start_polling(bot, skip_updates=True)

if __name__ == '__main__':
    asyncio.run(main())
