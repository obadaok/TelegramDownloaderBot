"""Bot command handlers and message processors."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    Message, CallbackQuery,
    FSInputFile, BufferedInputFile,
)
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, delete

from src.config.settings import settings
from src.database import get_db_session
from src.database.models import User, DownloadJob, JobStatus, JobType
from src.utils import (
    detect_platform, is_valid_url, truncate_text,
    format_size, format_duration,
)
from src.bot.keyboards import (
    main_menu_kb, video_quality_kb, audio_quality_kb,
    back_to_menu_kb, settings_kb,
)
from src.download.youtube_downloader import get_downloader

logger = logging.getLogger(__name__)

# Bot instance (set by build_bot)
_bot: Optional[Bot] = None


class UserNameState(StatesGroup):
    waiting_for_name = State()


class DownloadState(StatesGroup):
    waiting_for_url = State()
    selecting_quality = State()


def build_bot(dp: Dispatcher, bot: Bot) -> None:
    """Register all handlers to dispatcher."""
    global _bot
    _bot = bot

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

    # Name input (must come BEFORE generic URL handler)
    dp.message.register(
        handle_name_input,
        UserNameState.waiting_for_name,
        F.text,
    )

    # URL handler for any text message
    dp.message.register(handle_url_message, F.text)

    dp.callback_query.register(on_callback, F.data)


# ===== Helpers =====

async def _get_or_create_user(tg_user) -> User:
    async with get_db_session() as session:
        res = await session.execute(
            select(User).where(User.telegram_id == tg_user.id)
        )
        user = res.scalar_one_or_none()
        if not user:
            user = User(
                telegram_id=tg_user.id,
                username=tg_user.username,
                display_name=tg_user.first_name or tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user


def _progress_bar(percent: float, length: int = 10) -> str:
    """Sudanese-flavoured progress bar ▰ ▱"""
    filled = int(length * percent / 100)
    filled = max(0, min(length, filled))
    return "▰" * filled + "▱" * (length - filled)


# ===== COMMAND HANDLERS =====

async def cmd_start(msg: Message, state: FSMContext) -> None:
    """Handle /start."""
    await state.clear()
    user = await _get_or_create_user(msg.from_user)

    if user.display_name:
        await msg.answer(
            f"يا مرحبا {user.display_name} 💛\n\n"
            "أنا ثونة، بوت التحميل بتاعك.\n"
            "أرسلّي أي رابط فيديو أو أغنية، وأنا أنزّلهولك!\n\n"
            "أو افتحي القائمة: /menu",
            reply_markup=main_menu_kb(),
        )
    else:
        await msg.answer(
            "أهلا بيكِ يا غالية 🌸\n\n"
            "أنا ثونة — بوت تحميل فيديوهات وأغانيات.\n"
            "بس قبل ما نبدأ، شني اسمك؟ (أكتبيهولي)",
        )
        await state.set_state(UserNameState.waiting_for_name)


async def cmd_help(msg: Message) -> None:
    await msg.answer(
        "📖 <b>مساعدة ثونة</b>\n\n"
        "• أرسلّي أي رابط وبس!\n\n"
        "<b>الأوامر:</b>\n"
        "/start — بداية المحادثة\n"
        "/menu — القائمة الرئيسية\n"
        "/name — تغيير اسمك\n"
        "/download — تحميل رابط\n"
        "/audio — أغنية MP3\n"
        "/video — فيديو MP4\n"
        "/history — سجل التنزيلات\n"
        "/clear — مسح السجل\n"
        "/about — عنّي\n\n"
        "أي حاجة عايزاها أنا موجودة 💛",
    )


async def cmd_menu(msg: Message) -> None:
    await msg.answer("📋 القائمة الرئيسية بتاعتي:", reply_markup=main_menu_kb())


async def cmd_settings(msg: Message) -> None:
    await msg.answer("⚙️ الإعدادات بتاعتي:", reply_markup=settings_kb())


async def cmd_name(msg: Message, state: FSMContext) -> None:
    await msg.answer("شني الاسم الجديد عايزاني أناديك بيهو؟ 🌸")
    await state.set_state(UserNameState.waiting_for_name)


async def cmd_download(msg: Message, state: FSMContext) -> None:
    await msg.answer("أرسلّي الرابط عايزاهو، وبعدين هي تتحمل 😊")
    await state.set_state(DownloadState.waiting_for_url)


async def cmd_audio(msg: Message, state: FSMContext) -> None:
    await msg.answer(
        "🎵 أرسلّي الرابط، وأنا أطلّع ليك منهو أغنية MP3",
        reply_markup=audio_quality_kb(),
    )
    await state.set_state(DownloadState.waiting_for_url)


async def cmd_video(msg: Message, state: FSMContext) -> None:
    await msg.answer(
        "🎬 أرسلّي الرابط، وأنا أنزّل ليك الفيديو MP4",
        reply_markup=video_quality_kb(),
    )
    await state.set_state(DownloadState.waiting_for_url)


async def cmd_queue(msg: Message) -> None:
    async with get_db_session() as session:
        res = await session.execute(
            select(DownloadJob)
            .where(
                DownloadJob.telegram_user_id == msg.from_user.id,
                DownloadJob.status.in_([
                    JobStatus.PENDING.value,
                    JobStatus.PROCESSING.value,
                ]),
            )
            .order_by(DownloadJob.created_at.desc())
            .limit(10)
        )
        jobs = res.scalars().all()

    if not jobs:
        await msg.answer("ماف أي مهام جاية الآن — كلها واضحة ✅")
        return

    text = "📋 <b>مهام قيد التنفيذ:</b>\n\n"
    for j in jobs:
        text += (
            f"▸ <code>{truncate_text(j.title or j.url, 40)}</code>\n"
            f"  {j.job_type} • {j.quality} • {j.status}\n\n"
        )
    await msg.answer(text)


async def cmd_status(msg: Message) -> None:
    async with get_db_session() as session:
        res = await session.execute(
            select(DownloadJob)
            .where(DownloadJob.telegram_user_id == msg.from_user.id)
            .order_by(DownloadJob.created_at.desc())
            .limit(1)
        )
        job = res.scalar_one_or_none()

    if not job:
        await msg.answer("لسه ما نزلتي أي حاجة. أرسلّي رابطًا! 💛")
        return

    status_emoji = {
        JobStatus.COMPLETED.value: "✅",
        JobStatus.FAILED.value: "❌",
        JobStatus.PROCESSING.value: "⏳",
        JobStatus.PENDING.value: "🕐",
        JobStatus.CANCELLED.value: "⛔",
    }.get(job.status, "❓")

    text = (
        f"{status_emoji} <b>آخر مهمة:</b>\n"
        f"▸ <code>{truncate_text(job.title or job.url, 50)}</code>\n"
        f"▸ حالة: {job.status}\n"
    )
    if job.file_size:
        text += f"▸ حجم: {format_size(job.file_size)}\n"
    if job.error_message:
        text += f"▸ سبب الفشل: {truncate_text(job.error_message, 60)}\n"

    await msg.answer(text)


async def cmd_cancel(msg: Message, command: CommandObject) -> None:
    await msg.answer("❌ مش حيفوتني، بس أرسلّي رقم المهمة عايزة تلغيها.")


async def cmd_history(msg: Message) -> None:
    async with get_db_session() as session:
        res = await session.execute(
            select(DownloadJob)
            .where(DownloadJob.telegram_user_id == msg.from_user.id)
            .order_by(DownloadJob.created_at.desc())
            .limit(10)
        )
        jobs = res.scalars().all()

    if not jobs:
        await msg.answer("لسه ما عندك سجل تنزيلات. جرّبي أرسلّي رابطًا 📥")
        return

    text = "📜 <b>سجل تنزيلاتك:</b>\n\n"
    for j in jobs:
        emoji = "✅" if j.status == JobStatus.COMPLETED.value else "❌"
        text += (
            f"{emoji} {truncate_text(j.title or j.url, 35)}\n"
            f"   {j.job_type} • {j.quality} • {j.status}\n\n"
        )
    await msg.answer(text, reply_markup=main_menu_kb())


async def cmd_clear(msg: Message) -> None:
    async with get_db_session() as session:
        await session.execute(
            delete(DownloadJob).where(
                DownloadJob.telegram_user_id == msg.from_user.id,
                DownloadJob.status.in_([
                    JobStatus.COMPLETED.value,
                    JobStatus.FAILED.value,
                ]),
            )
        )
        await session.commit()
    await msg.answer("🗑 مسحت سجل التنزيلات القديمة ✨", reply_markup=main_menu_kb())


async def cmd_about(msg: Message) -> None:
    await msg.answer(
        "🤖 <b>ثونة</b>\n\n"
        "أنا بوت سوادني بتحمّل ليك فيديوهات وأغانيات من أي منصة 🌍\n"
        "YouTube • TikTok • Instagram • Facebook • X • Reddit • Vimeo • Twitch • SoundCloud • Pinterest وأكتر\n\n"
        "💛 أنزّل بجودة عالية، وأنا دايماً في الخدمة!\n"
        "أرسلّي رابط أي حاجة وجرّبي 😊",
    )


# ===== NAME STATE =====

async def handle_name_input(msg: Message, state: FSMContext) -> None:
    name = msg.text.strip()
    if not name or len(name) > 50:
        await msg.answer("⚠️ الاسم ده مش مناسب. جرّبي تاني 🌸")
        return

    user = await _get_or_create_user(msg.from_user)
    async with get_db_session() as session:
        res = await session.execute(
            select(User).where(User.telegram_id == msg.from_user.id)
        )
        u = res.scalar_one_or_none()
        if u:
            u.display_name = name
            u.username = msg.from_user.username
            u.updated_at = datetime.now(timezone.utc)
            await session.commit()

    await msg.answer(
        f"تمام يا {name}! 💛\nحفظت اسمك. /menu للقائمة، أو أرسلّي رابطًا!",
        reply_markup=main_menu_kb(),
    )
    await state.clear()


# ===== URL HANDLER =====

async def handle_url_message(msg: Message, state: FSMContext) -> None:
    url = msg.text.strip()

    if not is_valid_url(url):
        await msg.answer(
            "❌ الرابط ده مش واضح لي.\n"
            "أرسلّي رابط من أي منصة — YouTube, TikTok, Insta, whatever 🌸",
            reply_markup=main_menu_kb(),
        )
        return

    platform = detect_platform(url)
    status_msg = await msg.answer(
        f"🔍 شايفة المنصة: <b>{platform}</b>\n"
        "جارية أتحقق من المعلومات... ✨"
    )

    try:
        info = await get_downloader().extract_info(url)
    except Exception as e:
        logger.exception("Extract error for %s", url)
        err = str(e).lower()
        if "unsupported url" in err:
            await status_msg.edit_text(
                "❌ النوع ده من الروابط ما مدعوم 😔\n\n"
                "لو ده تيك توك *صور* (slideshow) — ما بقدر أنزّلها.\n"
                "جرّبي رابط *فيديو* عادي (فيه /video/ في الرابط)."
            )
        elif "tiktok" in url.lower() and "unexpected" in err:
            await status_msg.edit_text(
                "❌ تيك توك حظر الطلب من السيرفر 😔\n\n"
                "دي مشكلة معروفة في yt-dlp مع تيك توك.\n"
                "جرّبي لاحقاً أو استخدمي رابط يوتيوب — شغال 💯."
            )
        else:
            await status_msg.edit_text(
                f"❌ ما قادرة أستخرج معلومات 😔\n"
                f"السبب: <code>{truncate_text(str(e), 120)}</code>\n\n"
                f"جرّبي رابط تاني."
            )
        return

    if not info:
        await status_msg.edit_text(
            "❌ ما قادرة أستخرج معلومات من الرابط ده 😔\n"
            "تأكدّي الرابط صحيح أو جرّبي واحد تاني."
        )
        return

    # Build info text
    title = info.title
    text = (
        f"📹 <b>{truncate_text(title, 100)}</b>\n"
        f"📁 {platform}\n"
    )
    if info.uploader:
        text += f"👤 {truncate_text(info.uploader, 60)}\n"
    if info.duration:
        text += f"⏱ {format_duration(info.duration)}\n"

    # Show info as text (simple & safe — no delete/edit race conditions)
    try:
        await status_msg.edit_text(
            text + f"\nاختياري الجودة عايزاها 👇",
            reply_markup=video_quality_kb(),
        )
    except TelegramBadRequest:
        # Message was deleted or edited elsewhere — send a fresh one
        status_msg = await msg.answer(
            text + f"\nاختياري الجودة عايزاها 👇",
            reply_markup=video_quality_kb(),
        )

    await state.update_data(
        url=url,
        title=title,
        platform=platform,
        thumbnail=info.thumbnail,
        duration=info.duration,
        status_msg_id=status_msg.message_id,
        chat_id=msg.chat.id,
    )


# ===== CALLBACKS =====

async def on_callback(query: CallbackQuery, state: FSMContext) -> None:
    try:
        await query.answer()
    except Exception:
        pass  # Already answered or expired
    data = query.data
    user = query.from_user

    # Main menu callbacks — use safe edit (fallback to new message)
    if data == "cmd_menu":
        try:
            await query.message.edit_text(
                "📋 القائمة الرئيسية بتاعتي:",
                reply_markup=main_menu_kb(),
            )
        except TelegramBadRequest:
            await query.message.answer("📋 القائمة الرئيسية بتاعتي:", reply_markup=main_menu_kb())
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
    if data == "cmd_video":
        await query.message.answer(
            "🎬 أرسلّي رابط الفيديو:",
            reply_markup=back_to_menu_kb(),
        )
        return
    if data == "cmd_audio":
        await query.message.answer(
            "🎵 أرسلّي رابط الأغنية:",
            reply_markup=back_to_menu_kb(),
        )
        return
    if data == "cmd_queue":
        await cmd_queue(query.message)
        return
    if data == "cmd_status":
        await cmd_status(query.message)
        return
    if data == "cmd_history":
        await cmd_history(query.message)
        return
    if data == "cancel":
        try:
            await query.message.edit_text(
                "❌ فسخنا أمر التنزيل.",
                reply_markup=back_to_menu_kb(),
            )
        except TelegramBadRequest:
            pass
        await state.clear()
        return
    if data == "setting_name":
        await query.message.answer("شني الاسم الجديد عايزاني أناديك بيهو؟ 🌸")
        await state.set_state(UserNameState.waiting_for_name)
        return

    # Quality selection → start download
    if data.startswith("quality:"):
        await _handle_quality_selection(query, state)
        return

    if data.startswith("cancel_job:"):
        job_id = int(data.split(":")[1])
        try:
            await query.message.edit_text(
                "⛔ فسخت المهمة بنجاح.",
                reply_markup=back_to_menu_kb(),
            )
        except TelegramBadRequest:
            pass
        return

    try:
        await query.message.edit_text(
            "⚠️ حاجة مش معروفة، جرّبي تاني.",
            reply_markup=back_to_menu_kb(),
        )
    except TelegramBadRequest:
        pass


async def _handle_quality_selection(query: CallbackQuery, state: FSMContext) -> None:
    kind_and_q = query.data.split(":")
    kind = kind_and_q[1] if len(kind_and_q) >= 2 else "video"
    quality = kind_and_q[2] if len(kind_and_q) >= 3 else "best"

    state_data = await state.get_data()
    url = state_data.get("url")
    title = state_data.get("title", "Unknown")
    thumbnail = state_data.get("thumbnail")
    duration = state_data.get("duration")

    if not url:
        try:
            await query.message.edit_text(
                "❌ مش شايفة الرابط. أرسلّي أول حاجة رابطًا.",
                reply_markup=back_to_menu_kb(),
            )
        except TelegramBadRequest:
            pass
        return

    # Create job
    user = await _get_or_create_user(query.from_user)
    async with get_db_session() as session:
        job = DownloadJob(
            url=url,
            telegram_user_id=query.from_user.id,
            platform=detect_platform(url),
            title=title,
            thumbnail_url=thumbnail,
            duration=float(duration) if duration else None,
            job_type=kind,
            quality=quality,
            status=JobStatus.PROCESSING.value,
            created_at=datetime.now(timezone.utc),
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = job.id

        # Save old job IDs to clear later if needed
        async with get_db_session() as s2:
            res = await s2.execute(
                select(DownloadJob).where(
                    DownloadJob.telegram_user_id == query.from_user.id,
                    DownloadJob.status == JobStatus.PROCESSING.value,
                    DownloadJob.id != job_id,
                )
            )
            old = res.scalars().all()
            for o in old:
                o.status = JobStatus.CANCELLED.value
            await s2.commit()

    # Download with progress
    progress_text = (
        f"⏳ جارية أنزّل ليك...\n"
        f"📹 {truncate_text(title, 60)}\n"
        f"🎯 {quality}\n\n"
        f"{_progress_bar(0)} 0%\n"
        f"⬇️ جارية الاستعداد..."
    )
    try:
        await query.message.edit_text(progress_text)
        progress_msg_id = query.message.message_id
    except TelegramBadRequest:
        # Message was deleted by a duplicate webhook — send fresh progress msg
        prog_msg = await query.message.answer(progress_text)
        if prog_msg:
            progress_msg_id = prog_msg.message_id
        else:
            progress_msg_id = query.message.message_id

    kind_str = "video" if kind == "video" else "audio"

    # The event loop the download callbacks will be sent to
    main_loop = asyncio.get_event_loop()

    progress_ctx = {
        "pct": -1,
        "chat_id": query.message.chat.id,
        "msg_id": progress_msg_id,  # Use safe message id
        "title": title,
        "quality": quality,
    }

    async def _send_progress(pct: int, speed: str, eta: str, downloaded: str):
        ctx = progress_ctx
        if pct == ctx["pct"] or pct - ctx["pct"] < 10:
            return
        ctx["pct"] = pct
        try:
            await _bot.edit_message_text(
                chat_id=ctx["chat_id"],
                message_id=ctx["msg_id"],
                text=(
                    f"⏳ جارية أنزّل ليك...\n"
                    f"📹 {truncate_text(ctx['title'], 60)}\n"
                    f"🎯 {ctx['quality']}\n\n"
                    f"{_progress_bar(pct)} {pct}%\n"
                    f"⬇️ {downloaded} @ {speed}\n"
                    f"⏱ متبقي: {eta}"
                ),
            )
        except TelegramBadRequest:
            pass

    def _hook(d):
        """Called by yt-dlp from a different thread — schedule progress update."""
        try:
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes") or 0
                speed = d.get("_speed_str", "N/A").strip()
                eta = d.get("_eta_str", "N/A").strip()
                if total > 0:
                    pct = min(int(downloaded / total * 100), 100)
                    asyncio.run_coroutine_threadsafe(
                        _send_progress(pct, speed, eta, format_size(downloaded)),
                        main_loop,
                    )
            elif d.get("status") == "finished":
                asyncio.run_coroutine_threadsafe(
                    _send_progress(100, "تم!", "لحظات...", "جاري الإرسال"),
                    main_loop,
                )
        except Exception:
            pass

    try:
        downloader = get_downloader()
        file_path = await downloader.download(
            url=url,
            job_id=job_id,
            quality=quality,
            kind=kind_str,
            progress_hook=_hook,
        )

        if not file_path or not Path(file_path).exists():
            raise RuntimeError("التحميل ما اكتمل — مش قادرة ألقى الملف")

        file_size = os.path.getsize(file_path)

        # Check Telegram file size limit
        if file_size > settings.max_file_size_mb * 1024 * 1024:
            raise RuntimeError(
                f"الملف كبير زيادة ({format_size(file_size)}). "
                f"الحد الأقصى {settings.max_file_size_mb}MB."
            )

        # Update job
        async with get_db_session() as session:
            res = await session.execute(
                select(DownloadJob).where(DownloadJob.id == job_id)
            )
            job = res.scalar_one_or_none()
            if job:
                job.status = JobStatus.COMPLETED.value
                job.file_path = file_path
                job.file_size = file_size
                job.progress = 100.0
                job.completed_at = datetime.now(timezone.utc)
                await session.commit()

        # Notify: sending file
        try:
            await _bot.edit_message_text(
                chat_id=progress_ctx["chat_id"],
                message_id=progress_ctx["msg_id"],
                text=(
                    f"📤 جارية أرسل ليك {truncate_text(title, 60)}...\n"
                    f"{_progress_bar(100)} 100%"
                ),
            )
        except TelegramBadRequest:
            pass

        filename = Path(file_path).name
        file_input = FSInputFile(file_path, filename=filename)

        if kind_str == "audio":
            await query.message.answer_audio(
                audio=file_input,
                caption=(
                    f"✅ تمام يا {query.from_user.first_name or 'غالية'}!\n"
                    f"🎵 {truncate_text(title, 80)}\n"
                    f"💾 {format_size(file_size)} • MP3\n\n"
                    f"أنا ثونة، دايماً في الخدمة 💛"
                ),
            )
        else:
            await query.message.answer_video(
                video=file_input,
                caption=(
                    f"✅ تمام يا {query.from_user.first_name or 'غالية'}!\n"
                    f"📹 {truncate_text(title, 80)}\n"
                    f"💾 {format_size(file_size)} • {quality}\n\n"
                    f"أنا ثونة، دايماً في الخدمة 💛"
                ),
            )

        # Mark done in the progress message
        try:
            await _bot.edit_message_text(
                chat_id=progress_ctx["chat_id"],
                message_id=progress_ctx["msg_id"],
                text="✅ التنزيل اكتمل بنجاح! 😊",
            )
        except TelegramBadRequest:
            pass

        # Clean up file
        try:
            Path(file_path).unlink(missing_ok=True)
        except OSError:
            pass

    except Exception as e:
        logger.exception("Download failed for job %d (url=%s)", job_id, url)
        error_msg = str(e)[:200]
        async with get_db_session() as session:
            res = await session.execute(
                select(DownloadJob).where(DownloadJob.id == job_id)
            )
            job = res.scalar_one_or_none()
            if job:
                job.status = JobStatus.FAILED.value
                job.error_message = error_msg
                await session.commit()

        try:
            await _bot.edit_message_text(
                chat_id=progress_ctx["chat_id"],
                message_id=progress_ctx["msg_id"],
                text=(
                    f"❌ ما قادرة أكمل التنزيل 😔\n"
                    f"السبب: {truncate_text(error_msg, 100)}\n\n"
                    f"جرّبي رابط تاني أو غير الجودة."
                ),
                reply_markup=back_to_menu_kb(),
            )
        except TelegramBadRequest:
            # Fallback: send new message if the old one is gone
            try:
                await query.message.answer(
                    f"❌ ما قادرة أكمل التنزيل 😔\n"
                    f"السبب: {truncate_text(error_msg, 100)}\n\n"
                    f"جرّبي رابط تاني أو غير الجودة.",
                    reply_markup=back_to_menu_kb(),
                )
            except TelegramBadRequest:
                pass
    finally:
        await state.clear()
