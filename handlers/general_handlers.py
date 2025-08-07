#!/usr/bin/env python3
"""
General handlers for common callbacks like start, back, etc.
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

import config
from database import db
import logging

logger = logging.getLogger(__name__)

general_router = Router()

@general_router.callback_query(F.data == "start")
async def handle_start_callback(callback: CallbackQuery, state: FSMContext):
    """Handle start callback to redirect to appropriate main menu."""
    await state.clear()  # Clear any FSM state
    
    user_id = callback.from_user.id
    
    # Check if user is sudo admin
    if user_id in config.SUDO_ADMINS:
        from handlers.sudo_handlers import get_sudo_keyboard
        await callback.message.edit_text(
            "🔐 **منوی مدیریت سودو ادمین**\n\n"
            "شما دسترسی کامل به تمام بخش‌های ربات دارید:",
            reply_markup=get_sudo_keyboard()
        )
        await callback.answer()
        return
    
    # Check if user is authorized admin
    if await db.is_admin_authorized(user_id):
        from handlers.admin_handlers import get_admin_keyboard
        await callback.message.edit_text(
            f"👋 خوش آمدید!\n\n{config.MESSAGES['welcome_admin']}",
            reply_markup=get_admin_keyboard()
        )
        await callback.answer()
        return
    
    # Unauthorized user - show sales panel
    await callback.message.edit_text(
        f"{config.MESSAGES['unauthorized']}\n\n"
        f"🛒 **می‌توانید پنل جدید خریداری کنید:**\n"
        f"با کلیک بر روی دکمه زیر، محصولات موجود را مشاهده کنید.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 خرید پنل", callback_data="buy_panel")]
        ])
    )
    await callback.answer()

@general_router.callback_query(F.data == "back_to_main")
async def handle_back_to_main(callback: CallbackQuery, state: FSMContext):
    """Handle back to main menu callback."""
    await handle_start_callback(callback, state)