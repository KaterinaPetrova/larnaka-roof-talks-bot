from aiogram import Bot
from aiogram.types import BotCommand

async def setup_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="🔹 Запустить бота"),
        BotCommand(command="myevents", description="📅 Посмотреть мои регистрации"),
        BotCommand(command="admin", description="🔧 Админ-панель"),
        BotCommand(command="cancel", description="❌ Отменить текущее действие"),
        BotCommand(command="help", description="ℹ️ Помощь"),
    ]
    await bot.set_my_commands(commands)
