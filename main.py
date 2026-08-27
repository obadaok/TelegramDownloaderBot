"""Main entry point for the Telegram Downloader Bot."""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.settings import settings
from src.utils import setup_logging, clean_temp_files
from src.database import init_db, close_db
from src.bot.handlers import build_bot
from src.queue import get_queue

logger = logging.getLogger(__name__)


async def health_check(request: web.Request) -> web.Response:
    """Health check endpoint for Render."""
    return web.Response(text="OK", status=200)


async def main() -> None:
    """Start the bot."""
    setup_logging()
    settings.ensure_dirs()

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Initialize queue (optional)
    try:
        queue = await get_queue()
        logger.info("Redis queue connected")
    except Exception as e:
        logger.warning("Redis not available (optional): %s", e)
        queue = None

    # Initialize bot
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode='HTML'))
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
        if settings.webhook_url:
            # Webhook mode (production/Render)
            webhook_full_url = f"{settings.webhook_url.rstrip('/')}{settings.webhook_path}"
            logger.info("Setting webhook: %s", webhook_full_url)

            await bot.set_webhook(
                url=webhook_full_url,
                secret_token=settings.webhook_secret or None,
            )

            app = web.Application()
            app.router.add_get("/health", health_check)

            SimpleRequestHandler(
                dispatcher=dp,
                bot=bot,
                secret_token=settings.webhook_secret or None,
            ).register(app, path=settings.webhook_path)

            setup_application(app, dp, bot=bot)

            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", int(settings.webhook_port))
            await site.start()
            logger.info("Webhook server started on port %s", settings.webhook_port)

            await asyncio.Event().wait()
        else:
            # Polling mode (local development)
            logger.info("Starting polling mode...")
            await dp.start_polling(bot)

    except Exception as e:
        logger.exception("Bot error: %s", e)
    finally:
        await bot.session.close()
        await close_db()
        if queue is not None:
            await queue.close()
        clean_temp_files()
        logger.info("Bot stopped cleanly")


if __name__ == "__main__":
    asyncio.run(main())
