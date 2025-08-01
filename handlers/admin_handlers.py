from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from typing import List
import json
import logging
import config
from database import db
from models.schemas import AdminModel, UsageReportModel
from utils.notify import format_traffic_size, format_time_duration
from marzban_api import marzban_api
from datetime import datetime

logger = logging.getLogger(__name__)


admin_router = Router()


def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Get admin main keyboard."""
    buttons = [
        [
            InlineKeyboardButton(text=config.BUTTONS["my_info"], callback_data="my_info"),
            InlineKeyboardButton(text=config.BUTTONS["my_report"], callback_data="my_report")
        ],
        [
            InlineKeyboardButton(text=config.BUTTONS["my_users"], callback_data="my_users"),
            InlineKeyboardButton(text=config.BUTTONS["reactivate_users"], callback_data="reactivate_users")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_panel_selection_keyboard(admins: List[AdminModel]) -> InlineKeyboardMarkup:
    """Get keyboard for selecting between multiple admin panels."""
    buttons = []
    for admin in admins:
        panel_name = admin.admin_name or admin.marzban_username or f"Panel {admin.id}"
        status = "✅" if admin.is_active else "❌"
        buttons.append([
            InlineKeyboardButton(
                text=f"{status} {panel_name}",
                callback_data=f"select_panel_{admin.id}"
            )
        ])
    
    buttons.append([InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_admin_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def show_panel_selection_or_execute(callback: CallbackQuery, action_type: str):
    """Show panel selection if user has multiple panels, otherwise execute action directly."""
    admins = await db.get_admins_for_user(callback.from_user.id)
    active_admins = [admin for admin in admins if admin.is_active]
    
    if not active_admins:
        await callback.answer("شما هیچ پنل فعالی ندارید.", show_alert=True)
        return
    
    if len(active_admins) == 1:
        # Only one panel, execute action directly
        admin = active_admins[0]
        if action_type == "info":
            await show_admin_info(callback, admin)
        elif action_type == "report":
            await show_admin_report(callback, admin)
        elif action_type == "users":
            await show_admin_users(callback, admin)
        elif action_type == "reactivate":
            await show_admin_reactivate(callback, admin)
    else:
        # Multiple panels, show selection
        text = f"🔹 شما {len(active_admins)} پنل فعال دارید. کدام پنل را انتخاب می‌کنید؟\n\n"
        for admin in active_admins:
            panel_name = admin.admin_name or admin.marzban_username or f"Panel {admin.id}"
            text += f"• {panel_name}\n"
        
        # Store the action type in callback data for later use
        buttons = []
        for admin in active_admins:
            panel_name = admin.admin_name or admin.marzban_username or f"Panel {admin.id}"
            buttons.append([
                InlineKeyboardButton(
                    text=f"✅ {panel_name}",
                    callback_data=f"{action_type}_panel_{admin.id}"
                )
            ])
        
        buttons.append([InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_admin_main")])
        
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await callback.answer()


@admin_router.message(Command("start"))
async def admin_start(message: Message):
    """Start command for regular admins."""
    if message.from_user.id in config.SUDO_ADMINS:
        return  # Let sudo handler handle this
    
    # Check if user is authorized admin
    if not await db.is_admin_authorized(message.from_user.id):
        await message.answer(config.MESSAGES["unauthorized"])
        return
    
    # Get user's admin panels
    admins = await db.get_admins_for_user(message.from_user.id)
    active_admins = [admin for admin in admins if admin.is_active]
    
    welcome_message = config.MESSAGES["welcome_admin"]
    if len(active_admins) > 1:
        welcome_message += f"\n\n🔹 شما {len(active_admins)} پنل فعال دارید:"
        for admin in active_admins:
            panel_name = admin.admin_name or admin.marzban_username or f"Panel {admin.id}"
            welcome_message += f"\n• {panel_name}"
    elif len(active_admins) == 1:
        admin = active_admins[0]
        panel_name = admin.admin_name or admin.marzban_username or f"Panel {admin.id}"
        welcome_message += f"\n\n🔹 پنل فعال: {panel_name}"
    
    await message.answer(
        welcome_message,
        reply_markup=get_admin_keyboard()
    )


async def get_my_info_text(user_id: int) -> str:
    """Get admin info text. Shared logic for both callback and command handlers."""
    admin = await db.get_admin(user_id)
    if not admin:
        return "❌ ادمین یافت نشد."
    
    try:
        # Get current usage from Marzban
        admin_stats = await marzban_api.get_admin_stats(admin.username or str(admin.user_id))
        
        # Calculate usage percentages
        user_percentage = (admin_stats.total_users / admin.max_users) * 100
        traffic_percentage = (admin_stats.total_traffic_used / admin.max_total_traffic) * 100
        time_percentage = (admin_stats.total_time_used / admin.max_total_time) * 100
        
        text = f"👤 اطلاعات حساب شما:\n\n"
        text += f"📋 نام کاربری: {admin.username or 'نامشخص'}\n"
        text += f"🆔 User ID: {admin.user_id}\n"
        text += f"📅 تاریخ ایجاد: {admin.created_at}\n"
        text += f"✅ وضعیت: {'فعال' if admin.is_active else 'غیرفعال'}\n\n"
        
        text += f"📊 محدودیت‌ها و استفاده:\n\n"
        
        # Users
        user_status = "🟢" if user_percentage < 80 else "🟡" if user_percentage < 100 else "🔴"
        text += f"{user_status} کاربران: {admin_stats.total_users}/{admin.max_users} ({user_percentage:.1f}%)\n"
        
        # Traffic
        traffic_status = "🟢" if traffic_percentage < 80 else "🟡" if traffic_percentage < 100 else "🔴"
        text += f"{traffic_status} ترافیک: {await format_traffic_size(admin_stats.total_traffic_used)}/{await format_traffic_size(admin.max_total_traffic)} ({traffic_percentage:.1f}%)\n"
        
        # Time
        time_status = "🟢" if time_percentage < 80 else "🟡" if time_percentage < 100 else "🔴"
        text += f"{time_status} زمان: {await format_time_duration(admin_stats.total_time_used)}/{await format_time_duration(admin.max_total_time)} ({time_percentage:.1f}%)\n"
        
        # Warning if approaching limits
        if any(p >= 80 for p in [user_percentage, traffic_percentage, time_percentage]):
            text += f"\n⚠️ توجه: شما به محدودیت‌هایتان نزدیک شده‌اید!"
        
    except Exception as e:
        text = f"👤 اطلاعات حساب شما:\n\n"
        text += f"📋 نام کاربری: {admin.username or 'نامشخص'}\n"
        text += f"🆔 User ID: {admin.user_id}\n"
        text += f"📅 تاریخ ایجاد: {admin.created_at}\n"
        text += f"✅ وضعیت: {'فعال' if admin.is_active else 'غیرفعال'}\n\n"
        text += f"❌ خطا در دریافت آمار استفاده: {str(e)}"
    
    return text


@admin_router.callback_query(F.data == "my_info")
async def my_info_callback(callback: CallbackQuery):
    """Show admin's own information and limits."""
    if not await db.is_admin_authorized(callback.from_user.id):
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    await show_panel_selection_or_execute(callback, "info")


@admin_router.callback_query(F.data.startswith("info_panel_"))
async def info_panel_selected(callback: CallbackQuery):
    """Handle admin info for selected panel."""
    if not await db.is_admin_authorized(callback.from_user.id):
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    admin_id = int(callback.data.split("_")[-1])
    admin = await db.get_admin_by_id(admin_id)
    
    if not admin or admin.user_id != callback.from_user.id:
        await callback.answer("پنل یافت نشد.", show_alert=True)
        return
    
    await show_admin_info(callback, admin)


async def show_admin_info(callback: CallbackQuery, admin: AdminModel):
    """Show information for specific admin panel."""
    try:
        # Get current usage from Marzban using admin's own credentials
        admin_stats = await marzban_api.get_admin_stats_with_credentials(
            admin.marzban_username, admin.marzban_password
        )
        
        # Calculate usage percentages
        user_percentage = (admin_stats.total_users / admin.max_users) * 100 if admin.max_users > 0 else 0
        traffic_percentage = (admin_stats.total_traffic_used / admin.max_total_traffic) * 100 if admin.max_total_traffic > 0 else 0
        time_percentage = (admin_stats.total_time_used / admin.max_total_time) * 100 if admin.max_total_time > 0 else 0
        
        panel_name = admin.admin_name or admin.marzban_username or f"Panel {admin.id}"
        
        text = f"👤 اطلاعات پنل {panel_name}:\n\n"
        text += f"📋 نام کاربری مرزبان: {admin.marzban_username}\n"
        text += f"🆔 User ID: {admin.user_id}\n"
        text += f"📅 تاریخ ایجاد: {admin.created_at}\n"
        text += f"✅ وضعیت: {'فعال' if admin.is_active else 'غیرفعال'}\n\n"
        
        text += f"📊 محدودیت‌ها و استفاده (لحظه‌ای):\n\n"
        
        # Users
        user_status = "🟢" if user_percentage < 80 else "🟡" if user_percentage < 100 else "🔴"
        text += f"{user_status} کاربران: {admin_stats.total_users}/{admin.max_users} ({user_percentage:.1f}%)\n"
        
        # Traffic
        traffic_status = "🟢" if traffic_percentage < 80 else "🟡" if traffic_percentage < 100 else "🔴"
        text += f"{traffic_status} ترافیک: {await format_traffic_size(admin_stats.total_traffic_used)}/{await format_traffic_size(admin.max_total_traffic)} ({traffic_percentage:.1f}%)\n"
        
        # Time
        time_status = "🟢" if time_percentage < 80 else "🟡" if time_percentage < 100 else "🔴"
        text += f"{time_status} زمان: {await format_time_duration(admin_stats.total_time_used)}/{await format_time_duration(admin.max_total_time)} ({time_percentage:.1f}%)\n"
        
        # Warning if approaching limits
        if any(p >= 80 for p in [user_percentage, traffic_percentage, time_percentage]):
            text += f"\n⚠️ توجه: شما به محدودیت‌هایتان نزدیک شده‌اید!"
        
    except Exception as e:
        panel_name = admin.admin_name or admin.marzban_username or f"Panel {admin.id}"
        text = f"👤 اطلاعات پنل {panel_name}:\n\n"
        text += f"📋 نام کاربری مرزبان: {admin.marzban_username}\n"
        text += f"🆔 User ID: {admin.user_id}\n"
        text += f"📅 تاریخ ایجاد: {admin.created_at}\n"
        text += f"✅ وضعیت: {'فعال' if admin.is_active else 'غیرفعال'}\n\n"
        text += f"❌ خطا در دریافت آمار استفاده: {str(e)}"
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_admin_main")]
        ])
    )
    await callback.answer()


async def get_my_report_text(user_id: int) -> str:
    """Get admin report text. Shared logic for both callback and command handlers."""
    admin = await db.get_admin(user_id)
    if not admin:
        return "❌ ادمین یافت نشد."
    
    try:
        # Get users from Marzban
        users = await marzban_api.get_users(admin.username or str(admin.user_id))
        
        # Create usage report
        current_time = datetime.now()
        total_traffic = sum(user.lifetime_used_traffic for user in users)
        active_users = [user for user in users if user.status == "active"]
        
        # Save report to database
        users_data = [
            {
                "username": user.username,
                "status": user.status,
                "used_traffic": user.lifetime_used_traffic,
                "data_limit": user.data_limit,
                "expire": user.expire
            }
            for user in users
        ]
        
        report = UsageReportModel(
            admin_user_id=admin.user_id,
            check_time=current_time,
            current_users=len(users),
            current_total_traffic=total_traffic,
            users_data=json.dumps(users_data, ensure_ascii=False)
        )
        
        await db.add_usage_report(report)
        
        # Format report message
        text = f"📈 گزارش لحظه‌ای شما:\n\n"
        text += f"🕐 زمان گزارش: {current_time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        text += f"👥 تعداد کل کاربران: {len(users)}\n"
        text += f"✅ کاربران فعال: {len(active_users)}\n"
        text += f"❌ کاربران غیرفعال: {len(users) - len(active_users)}\n\n"
        text += f"📊 مجموع ترافیک مصرفی: {await format_traffic_size(total_traffic)}\n"
        text += f"📈 میانگین ترافیک هر کاربر: {await format_traffic_size(total_traffic // max(len(users), 1))}\n\n"
        
        # Show usage percentages
        user_percentage = (len(users) / admin.max_users) * 100
        traffic_percentage = (total_traffic / admin.max_total_traffic) * 100
        
        text += f"📊 درصد استفاده از محدودیت‌ها:\n"
        text += f"👥 کاربران: {user_percentage:.1f}%\n"
        text += f"📊 ترافیک: {traffic_percentage:.1f}%\n"
        
        # Recent usage trend (if available)
        latest_report = await db.get_latest_usage_report(admin.user_id)
        if latest_report and latest_report.id != report.id:
            time_diff = (current_time - latest_report.check_time).total_seconds()
            if time_diff > 0:
                traffic_diff = total_traffic - latest_report.current_total_traffic
                user_diff = len(users) - latest_report.current_users
                
                text += f"\n📈 تغییرات از آخرین گزارش:\n"
                text += f"👥 تغییر کاربران: {user_diff:+d}\n"
                text += f"📊 ترافیک جدید: {await format_traffic_size(max(0, traffic_diff))}\n"
        
    except Exception as e:
        text = f"❌ خطا در دریافت گزارش: {str(e)}"
    
    return text


@admin_router.callback_query(F.data == "my_report")
async def my_report_callback(callback: CallbackQuery):
    """Show admin's detailed usage report."""
    if not await db.is_admin_authorized(callback.from_user.id):
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    await show_panel_selection_or_execute(callback, "report")


@admin_router.callback_query(F.data.startswith("report_panel_"))
async def report_panel_selected(callback: CallbackQuery):
    """Handle admin report for selected panel."""
    if not await db.is_admin_authorized(callback.from_user.id):
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    admin_id = int(callback.data.split("_")[-1])
    admin = await db.get_admin_by_id(admin_id)
    
    if not admin or admin.user_id != callback.from_user.id:
        await callback.answer("پنل یافت نشد.", show_alert=True)
        return
    
    await show_admin_report(callback, admin)


async def show_admin_report(callback: CallbackQuery, admin: AdminModel):
    """Show report for specific admin panel with real-time data."""
    try:
        # Get real-time users from Marzban using admin's own credentials
        admin_api = await marzban_api.create_admin_api(admin.marzban_username, admin.marzban_password)
        users = await admin_api.get_users()
        
        # Create usage report
        current_time = datetime.now()
        total_traffic = sum(user.used_traffic + (user.lifetime_used_traffic or 0) for user in users)
        active_users = [user for user in users if user.status == "active"]
        
        # Save report to database
        users_data = [
            {
                "username": user.username,
                "status": user.status,
                "used_traffic": user.used_traffic,
                "lifetime_used_traffic": user.lifetime_used_traffic,
                "data_limit": user.data_limit,
                "expire": user.expire,
                "admin": user.admin
            }
            for user in users
        ]
        
        report = UsageReportModel(
            admin_user_id=admin.user_id,
            check_time=current_time,
            current_users=len(users),
            current_total_traffic=total_traffic,
            users_data=json.dumps(users_data, ensure_ascii=False)
        )
        
        await db.add_usage_report(report)
        
        panel_name = admin.admin_name or admin.marzban_username or f"Panel {admin.id}"
        
        # Format report message
        text = f"📈 گزارش لحظه‌ای پنل {panel_name}:\n\n"
        text += f"🕐 زمان گزارش: {current_time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        text += f"👥 تعداد کل کاربران: {len(users)}\n"
        text += f"✅ کاربران فعال: {len(active_users)}\n"
        text += f"❌ کاربران غیرفعال: {len(users) - len(active_users)}\n\n"
        text += f"📊 مجموع ترافیک مصرفی: {await format_traffic_size(total_traffic)}\n"
        text += f"📈 میانگین ترافیک هر کاربر: {await format_traffic_size(total_traffic // max(len(users), 1))}\n\n"
        
        # Show usage percentages
        user_percentage = (len(users) / admin.max_users) * 100 if admin.max_users > 0 else 0
        traffic_percentage = (total_traffic / admin.max_total_traffic) * 100 if admin.max_total_traffic > 0 else 0
        
        text += f"📊 درصد استفاده از محدودیت‌ها:\n"
        text += f"👥 کاربران: {user_percentage:.1f}%\n"
        text += f"📊 ترافیک: {traffic_percentage:.1f}%\n"
        
        # Recent usage trend (if available)
        latest_report = await db.get_latest_usage_report(admin.user_id)
        if latest_report and latest_report.id != report.id:
            time_diff = (current_time - latest_report.check_time).total_seconds()
            if time_diff > 0:
                traffic_diff = total_traffic - latest_report.current_total_traffic
                user_diff = len(users) - latest_report.current_users
                
                text += f"\n📈 تغییرات از آخرین گزارش:\n"
                text += f"👥 تغییر کاربران: {user_diff:+d}\n"
                text += f"📊 ترافیک جدید: {await format_traffic_size(max(0, traffic_diff))}\n"
        
    except Exception as e:
        panel_name = admin.admin_name or admin.marzban_username or f"Panel {admin.id}"
        text = f"❌ خطا در دریافت گزارش پنل {panel_name}: {str(e)}"
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_admin_main")]
        ])
    )
    await callback.answer()


# Users and reactivate handlers
@admin_router.callback_query(F.data == "my_users")
async def my_users_callback(callback: CallbackQuery):
    """Show admin's users list."""
    if not await db.is_admin_authorized(callback.from_user.id):
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    await show_panel_selection_or_execute(callback, "users")


@admin_router.callback_query(F.data.startswith("users_panel_"))
async def users_panel_selected(callback: CallbackQuery):
    """Handle admin users for selected panel."""
    if not await db.is_admin_authorized(callback.from_user.id):
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    admin_id = int(callback.data.split("_")[-1])
    admin = await db.get_admin_by_id(admin_id)
    
    if not admin or admin.user_id != callback.from_user.id:
        await callback.answer("پنل یافت نشد.", show_alert=True)
        return
    
    await show_admin_users(callback, admin)


async def show_admin_users(callback: CallbackQuery, admin: AdminModel):
    """Show users list for specific admin panel."""
    try:
        # Get real-time users from Marzban using admin's own credentials
        admin_api = await marzban_api.create_admin_api(admin.marzban_username, admin.marzban_password)
        users = await admin_api.get_users()
        
        panel_name = admin.admin_name or admin.marzban_username or f"Panel {admin.id}"
        
        if not users:
            text = f"❌ هیچ کاربری در پنل {panel_name} یافت نشد."
        else:
            text = f"👥 لیست کاربران پنل {panel_name} ({len(users)} کاربر):\n\n"
            
            for i, user in enumerate(users[:20], 1):  # Show first 20 users
                status_emoji = "✅" if user.status == "active" else "❌"
                traffic_info = f"{await format_traffic_size(user.used_traffic + (user.lifetime_used_traffic or 0))}"
                
                if user.data_limit:
                    traffic_info += f"/{await format_traffic_size(user.data_limit)}"
                
                text += f"{i}. {status_emoji} {user.username}\n"
                text += f"   📊 ترافیک: {traffic_info}\n"
                
                if user.expire:
                    expire_date = datetime.fromtimestamp(user.expire)
                    text += f"   📅 انقضا: {expire_date.strftime('%Y-%m-%d')}\n"
                
                text += "\n"
            
            if len(users) > 20:
                text += f"... و {len(users) - 20} کاربر دیگر"
        
    except Exception as e:
        panel_name = admin.admin_name or admin.marzban_username or f"Panel {admin.id}"
        text = f"❌ خطا در دریافت لیست کاربران پنل {panel_name}: {str(e)}"
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_admin_main")]
        ])
    )
    await callback.answer()


@admin_router.callback_query(F.data == "reactivate_users")
async def reactivate_users_callback(callback: CallbackQuery):
    """Show admin's reactivate users option."""
    if not await db.is_admin_authorized(callback.from_user.id):
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    await show_panel_selection_or_execute(callback, "reactivate")


@admin_router.callback_query(F.data.startswith("reactivate_panel_"))
async def reactivate_panel_selected(callback: CallbackQuery):
    """Handle admin reactivate for selected panel."""
    if not await db.is_admin_authorized(callback.from_user.id):
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    admin_id = int(callback.data.split("_")[-1])
    admin = await db.get_admin_by_id(admin_id)
    
    if not admin or admin.user_id != callback.from_user.id:
        await callback.answer("پنل یافت نشد.", show_alert=True)
        return
    
    await show_admin_reactivate(callback, admin)


async def show_admin_reactivate(callback: CallbackQuery, admin: AdminModel):
    """Show reactivate users option for specific admin panel."""
    panel_name = admin.admin_name or admin.marzban_username or f"Panel {admin.id}"
    text = f"🔄 فعالسازی کاربران پنل {panel_name}\n\n"
    text += "این قابلیت به زودی اضافه خواهد شد."
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_admin_main")]
        ])
    )
    await callback.answer()


# Back to main menu handler
@admin_router.callback_query(F.data == "back_to_admin_main")
async def back_to_admin_main(callback: CallbackQuery):
    """Return to admin main menu."""
    if not await db.is_admin_authorized(callback.from_user.id):
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    # Get user's admin panels
    admins = await db.get_admins_for_user(callback.from_user.id)
    active_admins = [admin for admin in admins if admin.is_active]
    
    welcome_message = config.MESSAGES["welcome_admin"]
    if len(active_admins) > 1:
        welcome_message += f"\n\n🔹 شما {len(active_admins)} پنل فعال دارید:"
        for admin in active_admins:
            panel_name = admin.admin_name or admin.marzban_username or f"Panel {admin.id}"
            welcome_message += f"\n• {panel_name}"
    elif len(active_admins) == 1:
        admin = active_admins[0]
        panel_name = admin.admin_name or admin.marzban_username or f"Panel {admin.id}"
        welcome_message += f"\n\n🔹 پنل فعال: {panel_name}"
    
    await callback.message.edit_text(
        welcome_message,
        reply_markup=get_admin_keyboard()
    )
    await callback.answer()
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_admin_main")]
        ])
    )
    await callback.answer()


@admin_router.callback_query(F.data == "reactivate_users")
async def reactivate_users_callback(callback: CallbackQuery):
    """Reactivate disabled users (if allowed)."""
    if not await db.is_admin_authorized(callback.from_user.id):
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    admin = await db.get_admin(callback.from_user.id)
    if not admin:
        await callback.answer("ادمین یافت نشد", show_alert=True)
        return
    
    try:
        # Get users from Marzban
        users = await marzban_api.get_users(admin.username or str(admin.user_id))
        disabled_users = [user for user in users if user.status == "disabled"]
        
        if not disabled_users:
            await callback.message.edit_text(
                "✅ همه کاربران شما فعال هستند.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_admin_main")]
                ])
            )
            await callback.answer()
            return
        
        # Check if admin still has capacity
        current_stats = await marzban_api.get_admin_stats(admin.username or str(admin.user_id))
        
        # Check limits before reactivating
        user_percentage = (current_stats.total_users / admin.max_users) * 100
        traffic_percentage = (current_stats.total_traffic_used / admin.max_total_traffic) * 100
        
        if user_percentage >= 100 or traffic_percentage >= 100:
            await callback.message.edit_text(
                "❌ شما همچنان محدودیت‌هایتان را عبور کرده‌اید.\n"
                "برای فعالسازی مجدد کاربران، ابتدا باید محدودیت‌ها رفع شوند.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_admin_main")]
                ])
            )
            await callback.answer()
            return
        
        # Reactivate users
        usernames = [user.username for user in disabled_users]
        results = await marzban_api.enable_users_batch(usernames)
        
        successful = [username for username, success in results.items() if success]
        failed = [username for username, success in results.items() if not success]
        
        text = f"🔄 نتیجه فعالسازی کاربران:\n\n"
        text += f"✅ موفق: {len(successful)} کاربر\n"
        text += f"❌ ناموفق: {len(failed)} کاربر\n\n"
        
        if successful:
            text += f"✅ کاربران فعال شده:\n"
            for username in successful[:10]:
                text += f"• {username}\n"
            if len(successful) > 10:
                text += f"... و {len(successful) - 10} کاربر دیگر\n"
        
        if failed:
            text += f"\n❌ کاربران ناموفق:\n"
            for username in failed[:5]:
                text += f"• {username}\n"
            if len(failed) > 5:
                text += f"... و {len(failed) - 5} کاربر دیگر\n"
        
    except Exception as e:
        text = f"❌ خطا در فعالسازی کاربران: {str(e)}"
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_admin_main")]
        ])
    )
    await callback.answer()


@admin_router.message(Command("گزارش_من"))
async def my_report_command(message: Message):
    """Handle /گزارش_من text command."""
    if message.from_user.id in config.SUDO_ADMINS:
        return  # Let sudo handler handle this
    
    # Check if user is authorized admin
    if not await db.is_admin_authorized(message.from_user.id):
        await message.answer(config.MESSAGES["unauthorized"])
        return
    
    text = await get_my_report_text(message.from_user.id)
    await message.answer(text, reply_markup=get_admin_keyboard())


@admin_router.message(Command("کاربران_من"))
async def my_users_command(message: Message):
    """Handle /کاربران_من text command."""
    if message.from_user.id in config.SUDO_ADMINS:
        return  # Let sudo handler handle this
    
    # Check if user is authorized admin
    if not await db.is_admin_authorized(message.from_user.id):
        await message.answer(config.MESSAGES["unauthorized"])
        return
    
    text = await get_my_users_text(message.from_user.id)
    await message.answer(text, reply_markup=get_admin_keyboard())


@admin_router.callback_query(F.data == "back_to_admin_main")
async def back_to_admin_main(callback: CallbackQuery):
    """Return to admin main menu."""
    if not await db.is_admin_authorized(callback.from_user.id):
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    await callback.message.edit_text(
        config.MESSAGES["welcome_admin"],
        reply_markup=get_admin_keyboard()
    )
    await callback.answer()


# Text command handlers for direct commands
@admin_router.message(Command("گزارش_من", "my_report"))
async def my_report_command(message: Message):
    """Text command handler for /گزارش_من."""
    if message.from_user.id in config.SUDO_ADMINS:
        return  # Let sudo handler handle this
    
    if not await db.is_admin_authorized(message.from_user.id):
        await message.answer(config.MESSAGES["unauthorized"])
        return
    
    admin = await db.get_admin(message.from_user.id)
    if not admin:
        await message.answer("❌ ادمین یافت نشد.")
        return
    
    try:
        # Get users from Marzban
        users = await marzban_api.get_users(admin.username or str(admin.user_id))
        
        # Create usage report
        current_time = datetime.now()
        total_traffic = sum(user.lifetime_used_traffic for user in users)
        active_users = [user for user in users if user.status == "active"]
        
        # Save report to database
        users_data = [
            {
                "username": user.username,
                "status": user.status,
                "used_traffic": user.lifetime_used_traffic,
                "data_limit": user.data_limit,
                "expire": user.expire
            }
            for user in users
        ]
        
        report = UsageReportModel(
            admin_user_id=admin.user_id,
            check_time=current_time,
            current_users=len(users),
            current_total_traffic=total_traffic,
            users_data=json.dumps(users_data, ensure_ascii=False)
        )
        
        await db.add_usage_report(report)
        
        # Format report message
        text = f"📈 گزارش لحظه‌ای شما:\n\n"
        text += f"🕐 زمان گزارش: {current_time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        text += f"👥 تعداد کل کاربران: {len(users)}\n"
        text += f"✅ کاربران فعال: {len(active_users)}\n"
        text += f"❌ کاربران غیرفعال: {len(users) - len(active_users)}\n\n"
        text += f"📊 مجموع ترافیک مصرفی: {await format_traffic_size(total_traffic)}\n"
        text += f"📈 میانگین ترافیک هر کاربر: {await format_traffic_size(total_traffic // max(len(users), 1))}\n\n"
        
        # Show usage percentages
        user_percentage = (len(users) / admin.max_users) * 100
        traffic_percentage = (total_traffic / admin.max_total_traffic) * 100
        
        text += f"📊 درصد استفاده از محدودیت‌ها:\n"
        text += f"👥 کاربران: {user_percentage:.1f}%\n"
        text += f"📊 ترافیک: {traffic_percentage:.1f}%\n"
        
        # Recent usage trend (if available)
        latest_report = await db.get_latest_usage_report(admin.user_id)
        if latest_report and latest_report.id != report.id:
            time_diff = (current_time - latest_report.check_time).total_seconds()
            if time_diff > 0:
                traffic_diff = total_traffic - latest_report.current_total_traffic
                user_diff = len(users) - latest_report.current_users
                
                text += f"\n📈 تغییرات از آخرین گزارش:\n"
                text += f"👥 تغییر کاربران: {user_diff:+d}\n"
                text += f"📊 ترافیک جدید: {await format_traffic_size(max(0, traffic_diff))}\n"
        
    except Exception as e:
        text = f"❌ خطا در دریافت گزارش: {str(e)}"
    
    await message.answer(text, reply_markup=get_admin_keyboard())


@admin_router.message(Command("کاربران_من", "my_users"))
async def my_users_command(message: Message):
    """Text command handler for /کاربران_من."""
    if message.from_user.id in config.SUDO_ADMINS:
        return  # Let sudo handler handle this
    
    if not await db.is_admin_authorized(message.from_user.id):
        await message.answer(config.MESSAGES["unauthorized"])
        return
    
    admin = await db.get_admin(message.from_user.id)
    if not admin:
        await message.answer("❌ ادمین یافت نشد.")
        return
    
    try:
        # Get users from Marzban
        users = await marzban_api.get_users(admin.username or str(admin.user_id))
        
        if not users:
            text = "❌ کاربری یافت نشد."
        else:
            text = f"👥 لیست کاربران شما ({len(users)} کاربر):\n\n"
            
            for i, user in enumerate(users[:20], 1):  # Show first 20 users
                status_emoji = "✅" if user.status == "active" else "❌"
                traffic_info = f"{await format_traffic_size(user.lifetime_used_traffic)}"
                
                if user.data_limit:
                    traffic_info += f"/{await format_traffic_size(user.data_limit)}"
                
                text += f"{i}. {status_emoji} {user.username}\n"
                text += f"   📊 ترافیک: {traffic_info}\n"
                
                if user.expire:
                    expire_date = datetime.fromtimestamp(user.expire)
                    text += f"   📅 انقضا: {expire_date.strftime('%Y-%m-%d')}\n"
                
                text += "\n"
            
            if len(users) > 20:
                text += f"... و {len(users) - 20} کاربر دیگر"
        
    except Exception as e:
        text = f"❌ خطا در دریافت لیست کاربران: {str(e)}"
    
    await message.answer(text, reply_markup=get_admin_keyboard())


@admin_router.message(Command("اطلاعات_من", "my_info"))
async def my_info_command(message: Message):
    """Text command handler for /اطلاعات_من."""
    if message.from_user.id in config.SUDO_ADMINS:
        return  # Let sudo handler handle this
        
    if not await db.is_admin_authorized(message.from_user.id):
        await message.answer(config.MESSAGES["unauthorized"])
        return
    
    admin = await db.get_admin(message.from_user.id)
    if not admin:
        await message.answer("❌ ادمین یافت نشد.")
        return
    
    try:
        # Get current usage from Marzban
        admin_stats = await marzban_api.get_admin_stats(admin.username or str(admin.user_id))
        
        # Calculate usage percentages
        user_percentage = (admin_stats.total_users / admin.max_users) * 100
        traffic_percentage = (admin_stats.total_traffic_used / admin.max_total_traffic) * 100
        time_percentage = (admin_stats.total_time_used / admin.max_total_time) * 100
        
        text = f"👤 اطلاعات حساب شما:\n\n"
        text += f"📋 نام کاربری: {admin.username or 'نامشخص'}\n"
        text += f"🆔 User ID: {admin.user_id}\n"
        text += f"📅 تاریخ ایجاد: {admin.created_at}\n"
        text += f"✅ وضعیت: {'فعال' if admin.is_active else 'غیرفعال'}\n\n"
        
        text += f"📊 محدودیت‌ها و استفاده:\n\n"
        
        # Users
        user_status = "🟢" if user_percentage < 80 else "🟡" if user_percentage < 100 else "🔴"
        text += f"{user_status} کاربران: {admin_stats.total_users}/{admin.max_users} ({user_percentage:.1f}%)\n"
        
        # Traffic
        traffic_status = "🟢" if traffic_percentage < 80 else "🟡" if traffic_percentage < 100 else "🔴"
        text += f"{traffic_status} ترافیک: {await format_traffic_size(admin_stats.total_traffic_used)}/{await format_traffic_size(admin.max_total_traffic)} ({traffic_percentage:.1f}%)\n"
        
        # Time
        time_status = "🟢" if time_percentage < 80 else "🟡" if time_percentage < 100 else "🔴"
        text += f"{time_status} زمان: {await format_time_duration(admin_stats.total_time_used)}/{await format_time_duration(admin.max_total_time)} ({time_percentage:.1f}%)\n"
        
        # Warning if approaching limits
        if any(p >= 80 for p in [user_percentage, traffic_percentage, time_percentage]):
            text += f"\n⚠️ توجه: شما به محدودیت‌هایتان نزدیک شده‌اید!"
        
    except Exception as e:
        text = f"👤 اطلاعات حساب شما:\n\n"
        text += f"📋 نام کاربری: {admin.username or 'نامشخص'}\n"
        text += f"🆔 User ID: {admin.user_id}\n"
        text += f"📅 تاریخ ایجاد: {admin.created_at}\n"
        text += f"✅ وضعیت: {'فعال' if admin.is_active else 'غیرفعال'}\n\n"
        text += f"❌ خطا در دریافت آمار استفاده: {str(e)}"
    
    await message.answer(text, reply_markup=get_admin_keyboard())


@admin_router.message(StateFilter(None), F.text & ~F.text.startswith('/'))
async def admin_unhandled_text(message: Message, state: FSMContext):
    """Handle unhandled text messages for regular admin users when NOT in FSM state."""
    if message.from_user.id in config.SUDO_ADMINS:
        return  # Let sudo handler handle this
    
    if not await db.is_admin_authorized(message.from_user.id):
        return  # Let unauthorized handler handle this
    
    # This handler should only be called when user is NOT in any FSM state
    current_state = await state.get_state()
    if current_state:
        logger.error(f"admin_unhandled_text called for user {message.from_user.id} in state {current_state} - this should not happen with StateFilter(None)")
        return
    
    logger.info(f"Admin user {message.from_user.id} sent unhandled text: {message.text}")
    
    # Show admin menu with a helpful message
    await message.answer(
        "👋 شما ادمین معمولی هستید.\n\n"
        "📋 دستورات موجود:\n"
        "• /گزارش_من - گزارش استفاده\n"
        "• /کاربران_من - لیست کاربران\n"
        "• /اطلاعات_من - اطلاعات حساب\n"
        "• /start - منوی اصلی\n\n"
        "یا از دکمه‌های زیر استفاده کنید:",
        reply_markup=get_admin_keyboard()
    )