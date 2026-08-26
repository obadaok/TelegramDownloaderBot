"""Inline keyboard builders for the bot."""
from __future__ import annotations

from typing import List, Tuple

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb() -> InlineKeyboardMarkup:
    """Main menu keyboard."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎬 تحميل فيديو", callback_data="cmd_video"),
        InlineKeyboardButton(text="🎵 تحميل صوتي", callback_data="cmd_audio"),
    )
    builder.row(
        InlineKeyboardButton(text="📋 قائمة الانتظار", callback_data="cmd_queue"),
        InlineKeyboardButton(text="📊 حالتي", callback_data="cmd_status"),
    )
    builder.row(
        InlineKeyboardButton(text="🕐 السجل", callback_data="cmd_history"),
        InlineKeyboardButton(text="⚙️ الإعدادات", callback_data="cmd_settings"),
    )
    builder.row(
        InlineKeyboardButton(text="ℹ️ حول", callback_data="cmd_about"),
        InlineKeyboardButton(text="📖 المساعدة", callback_data="cmd_help"),
    )
    return builder.as_markup()


def quality_keyboard(qualities: List[Tuple[str, str]], kind: str = "video") -> InlineKeyboardMarkup:
    """Quality selection keyboard."""
    builder = InlineKeyboardBuilder()
    for q_id, q_label in qualities:
        builder.add(
            InlineKeyboardButton(
                text=q_label,
                callback_data=f"quality:{kind}:{q_id}",
            )
        )
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel")
    )
    return builder.as_markup()


def video_quality_kb() -> InlineKeyboardMarkup:
    qualities = [
        ("best", "⭐ الأفضل"),
        ("1080p", "1080p"),
        ("720p", "720p"),
        ("480p", "480p"),
        ("360p", "360p"),
    ]
    return quality_keyboard(qualities, "video")


def audio_quality_kb() -> InlineKeyboardMarkup:
    qualities = [
        ("best", "⭐ الأفضل"),
        ("320", "320 kbps"),
        ("192", "192 kbps"),
        ("128", "128 kbps"),
    ]
    return quality_keyboard(qualities, "audio")


def job_action_kb(job_id: int) -> InlineKeyboardMarkup:
    """Keyboard for job actions (cancel, etc)."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="❌ إلغاء",
            callback_data=f"cancel_job:{job_id}",
        )
    )
    return builder.as_markup()


def back_to_menu_kb() -> InlineKeyboardMarkup:
    """Back to main menu."""
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="cmd_menu")
    )
    return builder.as_markup()


def confirm_cancel_kb(job_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ نعم، إلغاء", callback_data=f"confirm_cancel:{job_id}"),
        InlineKeyboardButton(text="❌ لا", callback_data=f"back_job:{job_id}"),
    )
    return builder.as_markup()


def settings_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📛 تغيير الاسم", callback_data="setting_name"),
    )
    builder.row(
        InlineKeyboardButton(text="🔙 رجوع", callback_data="cmd_menu"),
    )
    return builder.as_markup()
