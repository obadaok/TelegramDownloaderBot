"""Bot command handlers and message processors."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup,
    FSInputFile, BufferedInputFile,
)
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.formatting import as_list, as_section, Bold, Code

from src.config.settings import settings
from src.database import init_db, get_db_session
from src.database.models import User, DownloadJob, JobStatus, JobType, Quality
from src.utils import detect_platform, is_valid_url, truncate_text
from src.bot.keyboards import (
    main_menu_kb, video_quality_kb, audio_quality_kb,
    back_to_menu_kb, settings_kb, confirm_cancel_kb,
    quality_keyboard,
)
from src.queue import get_queue
from src.download.youtube_downloader import get_downloader, MediaInfo

logger = logging.getLogger(__name__)


class UserNameState(StatesGroup):
    waiting_for_name = State()


class DownloadState(StatesGroup):
    waiting_for_url = State()
    selecting_quality = State()


# Global bot instance
bot: Optional[Bot] = None


def build_bot(dp: Dispatcher, bot_instance: Bot) -> None:
    """Register all handlers to dispatcher."""
    global bot
    bot = bot_instance

    # Command handlers
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_help, Command("help"))
    dp.message.register(cmd_menu, Command("menu"))
    dp.message.register(cmd_settings, Command("settings"))
    dp.message.register(cmd_name, Command("name"))
    dp.message.register(cmd_download, Command("download"))
    dp.message.register(cmd_audio, Command("audio"))
    dp.message.register(cmd_video, Command("video"))
    dp.message.register(cmd_queue, Command("queue"))
    dp.message.register(cmd_status, Command("status"))
    dp.message.register(cmd_cancel, Command("cancel"))
    dp.message.register(cmd_history, Command("history"))
    dp.message.register(cmd_clear, Command("clear"))
    dp.message.register(cmd_about, Command("about"))

    # Message handler for URLs
    dp.message.register(handle_url_message, F.text)

    # Callback handlers
    dp.callback_query.register(on_callback, F.data)


# ===== COMMAND HANDLERS =====

async def cmd_start(msg: Message, state: FSMContext) -> None:
    """Handle /start - ask for name if new user."""
    await state.clear()
    user = msg.from_user
    async with get_db_session() as session:
        res = await session.execute(
            "SELECT * FROM users WHERE telegram_id = :uid", {"uid": user.id}
        )
        record = res.scalar_one_or_none()
        if not record:
            # New user: ask for name
            await msg.answer(
                "👋 مرحبًا! يسرني انضمامك لي.\n\n"
                "ما اسمك الذي تود أن أخاطبك به؟\n"
                "اكتب اسمك هنا ووسومه بـ /name أيضاً."
            )
            await state.set_state(UserNameState.waiting_for_name)
        else:
            await msg.answer(
                f"مرحبًا {record.display_name or user.first_name or 'صديقي'}!\n\n"
                "استخدم /menu للعودة للقائمة أو أرسل رابطًا مباشرة.",
                reply_markup=main_menu_kb(),
            )


async def cmd_help(msg: Message) -> None:
    await msg.answer(
        "📖 <b>المساعدة</b>\n\n"
        "/start - بدء المحادثة\n"
        "/menu - القائمة الرئيسية\n"
        "/name - تغيير الاسم\n"
        "/download - تحميل تارخت\n"
        "/audio - تحميل صوتي فقط\n"
        "/video - تحميل فيديو\n"
        "/queue - قائمة انتظار\n"
        "/status - حالتي\n"
        "/cancel - إلغاء مهمة\n"
        "/history - السجل\n"
        "/clear - مسح السجل\n"
        "/about - معلومات\n\n"
        "أرسل رابطًا مباشرة لتحميله!"
    )


async def cmd_menu(msg: Message) -> None:
    await msg.answer("📋 القائمة الرئيسية:", reply_markup=main_menu_kb())


async def cmd_settings(msg: Message) -> None:
    await msg.answer("⚙️ الإعدادات:", reply_markup=settings_kb())


async def cmd_name(msg: Message, state: FSMContext) -> None:
    await msg.answer("📛 ما الاسم الجديد الذي تريدني استخدامه؟")
    await state.set_state(UserNameState.waiting_for_name)


async def cmd_download(msg: Message, state: FSMContext) -> None:
    await msg.answer("📥 أرسل رابط الفيديو أو الصوت، أو اختر /audio /video للتحكم بالجودة.")
    await state.set_state(DownloadState.waiting_for_url)


async def cmd_audio(msg: Message, state: FSMContext) -> None:
    await msg.answer("🎵 أرسل الرابط لاستخراج الصوت فقط (MP3).", reply_markup=audio_quality_kb())
    await state.set_state(DownloadState.waiting_for_url)


async def cmd_video(msg: Message, state: FSMContext) -> None:
    await msg.answer("🎬 أرسل الرابط لاستخراج الفيديو (MP4).", reply_markup=video_quality_kb())
    await state.set_state(DownloadState.waiting_for_url)


async def cmd_queue(msg: Message) -> None:
    await msg.answer("📋 قائمة الانتظار لجاري التحقق...")


async def cmd_status(msg: Message) -> None:
    await msg.answer("⏳ جاري تحميل حالتك...")


async def cmd_cancel(msg: Message, command: CommandObject) -> None:
    await msg.answer("❌ أرسل رقم المهمة التي تريد إلغائها.")


async def cmd_history(msg: Message) -> None:
    await msg.answer("📜 السجل:")


async def cmd_clear(msg: Message) -> None:
    await msg.answer("🗑 تم مسح السجل.")


async def cmd_about(msg: Message) -> None:
    await msg.answer(
        "🤖 <b>Telegram Downloader Bot</b>\n\n"
        "بوت احترافي لتحميل الفيديوهات والصوت من جميع المنصات\n"
        "يدعم: YouTube, TikTok, Instagram, Facebook, X/Twitter, Reddit, Vimeo, Twitch, SoundCloud, Pinterest, وغيرها\n\n"
        "تكنولوجيا: Python 3.12 + aiogram 3 + yt-dlp + Redis + PostgreSQL/SQLite + Docker + Render"
    )


# ===== NAME STATE =====

async def handle_name_input(msg: Message, state: FSMContext) -> None:
    name = msg.text.strip()
    if not name or len(name) > 50:
        await msg.answer("⚠️ الاسم غير صالح. حاول مرة أخرى.")
        return
    user = msg.from_user
    async with get_db_session() as session:
        res = await session.execute(
            "SELECT * FROM users WHERE telegram_id = :uid", {"uid": user.id}
        )
        record = res.scalar_one_or_none()
        if record:
            record.display_name = name
            record.username = msg.from_user.username
            await session.commit()
        else:
            from src.database.models import User
            session.add(User(
                telegram_id=user.id,
                username=user.username,
                display_name=name,
                first_name=user.first_name,
                last_name=user.last_name,
            ))
            await session.commit()
    await msg.answer(f"✅ تم حفظ اسمك: <b>{name}</b>. استخدم /menu للبدء.", reply_markup=main_menu_kb())
    await state.clear()


# ===== URL HANDLER =====

async def handle_url_message(msg: Message, state: FSMContext) -> None:
    url = msg.text.strip()
    if not is_valid_url(url):
        await msg.answer("❌ الرابط غير صالح. أرسل رابطًا من منصة مدعومة (YouTube, TikTok, etc.).")
        return

    platform = detect_platform(url)
    await msg.answer(f"🔍 جاري اكتشاف المنصة: <b>{platform}</b>...")

    loop = asyncio.get_event_loop()
    try:
        info = await loop.run_in_executor(None, lambda: get_downloader()._extract_sync(url))
    except Exception as e:
        await msg.answer(f"❌ فشل الاستخراج: {e}")
        return

    if not info:
        await msg.answer("❌ لم أتمكن من استخراج معلومات من هذا الرابط.")
        return

    # Build response
    title = info.title
    thumbnail = info.thumbnail
    duration = info.duration
    uploader = info.uploader
    formats = info.formats or []

    text = (
        f"📹 <b>العنوان:</b> {truncate_text(title, 100)}\n"
        f"📁 <b>المنصة:</b> {info.platform}\n"
    )
    if uploader:
        text += f"👤 <b>الناشر:</b> {truncate_text(uploader, 60)}\n"
    if duration:
        from src.utils import format_duration
        text += f"⏱ <b>المدة:</b> {format_duration(duration)}\n"

    # Build quality buttons
    kb = video_quality_kb()
    await msg.answer(text, reply_markup=kb)

    # Store in state for quality selection
    await state.update_data(url=url, title=title, thumbnail=thumbnail, duration=duration, platform=platform)


# ===== CALLBACKS =====

async def on_callback(query: CallbackQuery, state: FSMContext) -> None:
    await query.answer()
    data = query.data
    user = query.from_user

    if data == "cmd_menu":
        await query.message.edit_text("📋 القائمة الرئيسية:", reply_markup=main_menu_kb())
        return
    if data == "cmd_help":
        await cmd_help(query.message)
        return
    if data == "cmd_settings":
        await cmd_settings(query.message)
        return
    if data == "cmd_about":
        await cmd_about(query.message)
        return

    if data.startswith("quality:"):
        _, kind, q_id = data.split(":")
        state_data = await state.get_data()
        url = state_data.get("url")
        if not url:
            await query.message.edit_text("❌ لا يوجد رابط. أرسل رابطًا أولاً.")
            return
        await query.message.edit_text(f"⏳ جاري تحميل ({q_id}) من {url[:30]}...")
        # Queue the job
        async with get_db_session() as session:
            # Create user if needed
            res = await session.execute("SELECT * FROM users WHERE telegram_id = :uid", {"uid": user.id})
            user_rec = res.scalar_one_or_none()
            if not user_rec:
                from src.database.models import User
                session.add(User(telegram_id=user.id, username=user.username, display_name=user.username or "Unknown"))
                await session.commit()
            # Create job
            from src.database.models import DownloadJob
            session.add(DownloadJob(
                url=url,
                telegram_user_id=user.id,
                status=JobStatus.PENDING.value,
                job_type=kind,
                quality=q_id,
            ))
            await session.commit()
        await query.message.edit_text("✅ تم إضافة المهمة للانتظار.")
        return

    if data.startswith("cancel_job:"):
        job_id = int(data.split(":")[1])
        await query.message.edit_text("❌ تم إلغاء المهمة.")
        return

    if data == "cancel":
        await query.message.edit_text("❌ تم الإلغاء.", reply_markup=back_to_menu_kb())
        return

    if data == "setting_name":
        await query.message.answer("📛 ما الاسم الجديد؟")
        await state.set_state(UserNameState.waiting_for_name)
        return

    await query.message.edit_text("⚠️ أمر غير معروف.", reply_markup=back_to_menu_kb())
