#!/usr/bin/env python3
"""
Reward handlers for giving rewards to all users on the panel
"""

import asyncio
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import config
from database import db
from marzban_api import marzban_api
from models.schemas import LogModel
import logging

logger = logging.getLogger(__name__)

class RewardUsersStates(StatesGroup):
    waiting_for_reward_type = State()
    waiting_for_reward_amount = State()
    waiting_for_confirmation = State()

reward_router = Router()

@reward_router.callback_query(F.data == "reward_users")
async def reward_users_start(callback: CallbackQuery, state: FSMContext):
    """Start reward users process."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    await state.set_state(RewardUsersStates.waiting_for_reward_type)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⏰ اضافه کردن زمان", callback_data="reward_time"),
            InlineKeyboardButton(text="📊 اضافه کردن حجم", callback_data="reward_traffic")
        ],
        [
            InlineKeyboardButton(text="❌ لغو", callback_data="back_to_main")
        ]
    ])
    
    await callback.message.edit_text(
        "🎁 **پاداش دادن به تمام کاربران**\n\n"
        "نوع پاداش را انتخاب کنید:",
        reply_markup=keyboard
    )
    await callback.answer()


@reward_router.callback_query(F.data.startswith("reward_"))
async def reward_type_selected(callback: CallbackQuery, state: FSMContext):
    """Handle reward type selection."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    reward_type = callback.data.split("_")[1]  # time or traffic
    await state.update_data(reward_type=reward_type)
    await state.set_state(RewardUsersStates.waiting_for_reward_amount)
    
    if reward_type == "time":
        prompt_text = (
            "⏰ **اضافه کردن زمان**\n\n"
            "مقدار زمان اضافی را وارد کنید:\n\n"
            "**نمونه‌ها:**\n"
            "• `2` (دو روز)\n"
            "• `7` (یک هفته)\n"
            "• `30` (یک ماه)\n\n"
            "تعداد روز را وارد کنید:"
        )
    else:  # traffic
        prompt_text = (
            "📊 **اضافه کردن حجم**\n\n"
            "مقدار حجم اضافی را وارد کنید:\n\n"
            "**نمونه‌ها:**\n"
            "• `2` (دو گیگابایت)\n"
            "• `5` (پنج گیگابایت)\n"
            "• `10` (ده گیگابایت)\n\n"
            "تعداد گیگابایت را وارد کنید:"
        )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ لغو", callback_data="reward_users")]
    ])
    
    await callback.message.edit_text(prompt_text, reply_markup=keyboard)
    await callback.answer()


@reward_router.message(RewardUsersStates.waiting_for_reward_amount)
async def reward_amount_received(message: Message, state: FSMContext):
    """Handle reward amount input."""
    if message.from_user.id not in config.SUDO_ADMINS:
        await message.answer("غیرمجاز")
        return
    
    try:
        amount = float(message.text.strip())
        if amount <= 0:
            await message.answer("⚠️ مقدار باید بیشتر از صفر باشد. لطفاً مجدداً وارد کنید:")
            return
        
        data = await state.get_data()
        reward_type = data.get('reward_type')
        
        await state.update_data(amount=amount)
        await state.set_state(RewardUsersStates.waiting_for_confirmation)
        
        if reward_type == "time":
            amount_text = f"{int(amount)} روز"
            icon = "⏰"
        else:
            amount_text = f"{amount} گیگابایت"
            icon = "📊"
        
        confirmation_text = (
            f"🎁 **تأیید پاداش کاربران**\n\n"
            f"{icon} **نوع پاداش:** {'زمان' if reward_type == 'time' else 'حجم'}\n"
            f"📈 **مقدار:** {amount_text}\n\n"
            f"⚠️ **هشدار:**\n"
            f"• این پاداش به **تمام کاربران فعال** روی پنل اعمال می‌شود\n"
            f"• این عمل غیرقابل برگشت است\n\n"
            f"آیا مطمئن هستید؟"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ تأیید و اعمال", callback_data="confirm_reward"),
                InlineKeyboardButton(text="❌ لغو", callback_data="reward_users")
            ]
        ])
        
        await message.answer(confirmation_text, reply_markup=keyboard)
        
    except ValueError:
        await message.answer("⚠️ لطفاً یک عدد معتبر وارد کنید:")


@reward_router.callback_query(F.data == "confirm_reward")
async def confirm_reward(callback: CallbackQuery, state: FSMContext):
    """Apply reward to all users."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    data = await state.get_data()
    reward_type = data.get('reward_type')
    amount = data.get('amount')
    
    if not reward_type or not amount:
        await callback.answer("خطا در دریافت اطلاعات", show_alert=True)
        return
    
    # Show processing message
    await callback.message.edit_text(
        "⏳ **در حال اعمال پاداش...**\n\n"
        "لطفاً منتظر بمانید..."
    )
    
    try:
        # Get all users from Marzban using sudo admin credentials
        total_users = 0
        successful_rewards = 0
        failed_rewards = 0
        
        # Use main admin API
        users = await marzban_api.get_users()
        total_users = len(users)
        
        for user in users:
            try:
                if user.status != "active":
                    continue
                
                # Prepare update data
                update_data = {}
                
                if reward_type == "time":
                    # Add days to expiry
                    if user.expire:
                        new_expire = user.expire + (amount * 24 * 3600)  # Convert days to seconds
                    else:
                        # If no expiry, set to amount days from now
                        new_expire = datetime.now().timestamp() + (amount * 24 * 3600)
                    update_data["expire"] = int(new_expire)
                
                elif reward_type == "traffic":
                    # Add GB to data limit
                    additional_bytes = int(amount * 1024 * 1024 * 1024)  # Convert GB to bytes
                    if user.data_limit:
                        new_limit = user.data_limit + additional_bytes
                    else:
                        new_limit = additional_bytes
                    update_data["data_limit"] = new_limit
                
                # Apply update
                success = await marzban_api.modify_user(user.username, update_data)
                if success:
                    successful_rewards += 1
                else:
                    failed_rewards += 1
                    
                # Small delay to avoid overwhelming the API
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error rewarding user {user.username}: {e}")
                failed_rewards += 1
        
        # Clear state
        await state.clear()
        
        # Show results
        if reward_type == "time":
            reward_text = f"{int(amount)} روز"
            icon = "⏰"
        else:
            reward_text = f"{amount} گیگابایت"
            icon = "📊"
        
        result_text = (
            f"🎉 **پاداش اعمال شد**\n\n"
            f"{icon} **نوع پاداش:** {'زمان' if reward_type == 'time' else 'حجم'}\n"
            f"📈 **مقدار:** {reward_text}\n\n"
            f"📊 **نتایج:**\n"
            f"• مجموع کاربران: {total_users}\n"
            f"• موفقیت‌آمیز: {successful_rewards}\n"
            f"• ناموفق: {failed_rewards}\n\n"
            f"✅ پاداش به تمام کاربران فعال اعمال شد!"
        )
        
        await callback.message.edit_text(
            result_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_main")]
            ])
        )
        
        # Log the action
        log_entry = LogModel(
            admin_id=0,  # System action
            action="reward_all_users",
            details=f"Rewarded all users with {reward_text} ({reward_type}). Success: {successful_rewards}, Failed: {failed_rewards}",
            timestamp=datetime.now().timestamp()
        )
        await db.add_log(log_entry)
        
    except Exception as e:
        logger.error(f"Error applying rewards: {e}")
        await callback.message.edit_text(
            f"❌ **خطا در اعمال پاداش**\n\n"
            f"مشکل: {str(e)}\n\n"
            f"لطفاً مجدداً تلاش کنید.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_main")]
            ])
        )
        await state.clear()
    
    await callback.answer()