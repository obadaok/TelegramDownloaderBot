"""Main entry point for the Telegram Downloader Bot."""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.filters import Command

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.settings import settings
from src.utils import setup_logging, clean_temp_files
from src.database import init_db, close_db
from src.bot.handlers import build_bot
from src.queue import get_queue

logger = logging.getLogger(__name__)


async def main() -> None:
    """Start the bot."""
    setup_logging()
    settings.ensure_dirs()

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Initialize queue
    queue = await get_queue()
    logger.info("Redis queue connected")

    # Initialize bot
    bot = Bot(token=settings.bot_token, parse_mode="HTML")
    dp = Dispatcher()

    # Set commands
    commands = [
        BotCommand(command="start", description="بدء المحادثة"),
        BotCommand(command="menu", description="القائمة الرئيسية"),
        BotCommand(command="help", description="المساعدة"),
        BotCommand(command="download", description="تحميل من رابط"),
        BotCommand(command="audio", description="تحميل صوتي"),
        BotCommand(command="video", description="تحميل فيديو"),
        BotCommand(command="queue", description="قائمة الانتظار"),
        BotCommand(command="status", description="حالة التحميلات"),
        BotCommand(command="cancel", description="إلغاء مهمة"),
        BotCommand(command="history", description="السجل"),
        BotCommand(command="clear", description="مسح السجل"),
        BotCommand(command="settings", description="الإعدادات"),
        BotCommand(command="name", description="تغيير الاسم"),
        BotCommand(command="about", description="معلومات"),
    ]
    await bot.set_my_commands(commands)

    build_bot(dp, bot)

    logger.info("Bot started. Token is set. Admin IDs: %s", settings.admin_ids)

    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.exception("Bot error: %s", e)
    finally:
        await bot.session.close()
        await close_db()
        await queue.close()
        clean_temp_files()
        logger.info("Bot stopped cleanly")


if __name__ == "__main__":
    asyncio.run(main())
