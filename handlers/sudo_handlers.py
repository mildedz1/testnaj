from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from typing import List
import logging
import asyncio
import config
from database import db
from models.schemas import AdminModel, LogModel
from utils.notify import (
    notify_admin_added, notify_admin_removed, format_traffic_size, format_time_duration,
    gb_to_bytes, days_to_seconds, bytes_to_gb, seconds_to_days
)
from marzban_api import marzban_api
from datetime import datetime

logger = logging.getLogger(__name__)


class AddAdminStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_admin_name = State()
    waiting_for_marzban_username = State()
    waiting_for_marzban_password = State()
    waiting_for_traffic_volume = State()
    waiting_for_max_users = State()
    waiting_for_validity_period = State()
    waiting_for_confirmation = State()


class EditPanelStates(StatesGroup):
    waiting_for_traffic_volume = State()
    waiting_for_validity_period = State()
    waiting_for_confirmation = State()


class AddExistingAdminStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_marzban_username = State()
    waiting_for_marzban_password = State()
    waiting_for_confirmation = State()


class EditAdminLimitsStates(StatesGroup):
    waiting_for_admin_selection = State()
    waiting_for_limit_type = State()
    waiting_for_new_value = State()
    waiting_for_confirmation = State()

class RewardUsersStates(StatesGroup):
    waiting_for_reward_type = State()
    waiting_for_reward_amount = State()
    waiting_for_confirmation = State()


sudo_router = Router()


def get_progress_indicator(current_step: int, total_steps: int = 7) -> str:
    """Generate a visual progress indicator."""
    filled = "🟢"
    current = "🔵" 
    empty = "⚪"
    
    indicators = []
    for i in range(1, total_steps + 1):
        if i < current_step:
            indicators.append(filled)
        elif i == current_step:
            indicators.append(current)
        else:
            indicators.append(empty)
    
    return "".join(indicators) + f" ({current_step}/{total_steps})"


def get_sudo_keyboard() -> InlineKeyboardMarkup:
    """Get sudo admin main keyboard."""
    buttons = [
        [
            InlineKeyboardButton(text=config.BUTTONS["add_admin"], callback_data="add_admin"),
            InlineKeyboardButton(text=config.BUTTONS["add_existing_admin"], callback_data="add_existing_admin")
        ],
        [
            InlineKeyboardButton(text=config.BUTTONS["remove_admin"], callback_data="remove_admin"),
            InlineKeyboardButton(text=config.BUTTONS["activate_admin"], callback_data="activate_admin")
        ],
        [
            InlineKeyboardButton(text=config.BUTTONS["edit_panel"], callback_data="edit_panel"),
            InlineKeyboardButton(text=config.BUTTONS["admin_status"], callback_data="admin_status")
        ],
        [
            InlineKeyboardButton(text="📊 ویرایش محدودیت‌ها", callback_data="edit_admin_limits"),
            InlineKeyboardButton(text="🎁 پاداش کاربران", callback_data="reward_users")
        ],
        [
            InlineKeyboardButton(text="🛒 مدیریت فروش", callback_data="sales_management"),
            InlineKeyboardButton(text=config.BUTTONS["list_admins"], callback_data="list_admins")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_list_keyboard(admins: List[AdminModel], action: str) -> InlineKeyboardMarkup:
    """Get keyboard with admin list for selection - grouped by user_id for better display."""
    buttons = []
    
    if action == "edit_limits":
        # For edit_limits, show individual admins (panels) instead of grouping by user
        for admin in admins:
            display_name = admin.admin_name or admin.marzban_username or f"ID: {admin.user_id}"
            status = "✅" if admin.is_active else "❌"
            
            buttons.append([
                InlineKeyboardButton(
                    text=f"{status} {display_name}",
                    callback_data=f"{action}_{admin.id}"
                )
            ])
    else:
        # Group admins by user_id for other actions
        user_panels = {}
        for admin in admins:
            if admin.user_id not in user_panels:
                user_panels[admin.user_id] = []
            user_panels[admin.user_id].append(admin)
        
        # Create buttons for each user (showing number of panels)
        for user_id, user_admins in user_panels.items():
            # Get user display info from first admin
            first_admin = user_admins[0]
            display_name = first_admin.username or f"ID: {user_id}"
            
            # Count active/inactive panels
            active_panels = len([a for a in user_admins if a.is_active])
            total_panels = len(user_admins)
            
            # Show status based on whether user has any active panels
            status = "✅" if active_panels > 0 else "❌"
            
            panel_info = f"({active_panels}/{total_panels} پنل)" if total_panels > 1 else ""
            
            buttons.append([
                InlineKeyboardButton(
                    text=f"{status} {display_name} {panel_info}",
                    callback_data=f"{action}_{user_id}"
                )
            ])
    
    buttons.append([InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_panel_list_keyboard(admins: List[AdminModel], action: str) -> InlineKeyboardMarkup:
    """Get keyboard with individual panel list for selection."""
    buttons = []
    
    # Create buttons for each individual panel
    for admin in admins:
        # Get display info
        display_name = admin.admin_name or admin.username or f"ID: {admin.user_id}"
        panel_name = admin.marzban_username or f"Panel-{admin.id}"
        
        # Show status
        status = "✅" if admin.is_active else "❌"
        
        # Include traffic and time limits for editing context
        from utils.notify import bytes_to_gb, seconds_to_days
        traffic_gb = bytes_to_gb(admin.max_total_traffic)
        time_days = seconds_to_days(admin.max_total_time)
        
        button_text = f"{status} {display_name} ({panel_name}) - {traffic_gb}GB/{time_days}د"
        
        buttons.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"{action}_{admin.id}"
            )
        ])
    
    buttons.append([InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@sudo_router.message(Command("start"))
async def sudo_start(message: Message):
    """Start command for sudo users."""
    if message.from_user.id not in config.SUDO_ADMINS:
        await message.answer(config.MESSAGES["unauthorized"])
        return
    
    await message.answer(
        config.MESSAGES["welcome_sudo"],
        reply_markup=get_sudo_keyboard()
    )


@sudo_router.callback_query(F.data == "add_admin")
async def add_admin_callback(callback: CallbackQuery, state: FSMContext):
    """Start adding new admin process."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    # Clear any existing state first
    current_state = await state.get_state()
    logger.info(f"User {callback.from_user.id} clearing previous state before add_admin: {current_state}")
    await state.clear()
    
    logger.info(f"Starting comprehensive add admin process for sudo user {callback.from_user.id}")
    
    await callback.message.edit_text(
        "🆕 **افزودن ادمین جدید**\n\n"
        f"{get_progress_indicator(1)}\n"
        "📝 **مرحله ۱ از ۷: User ID**\n\n"
        "لطفاً User ID (آیدی تلگرام) کاربری که می‌خواهید ادمین کنید را ارسال کنید:\n\n"
        "🔍 **نکته:** User ID باید یک عدد صحیح باشد\n"
        "📋 **مثال:** `123456789`\n\n"
        "💡 **راهنما:** برای یافتن User ID می‌توانید از ربات‌های مخصوص یا دستور /start در ربات‌ها استفاده کنید.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=config.BUTTONS["cancel"], callback_data="back_to_main")]
        ])
    )
    
    # Set initial state for the add admin process
    logger.info(f"User {callback.from_user.id} transitioning to state: AddAdminStates.waiting_for_user_id")
    await state.set_state(AddAdminStates.waiting_for_user_id)
    
    # Log state change
    current_state = await state.get_state()
    logger.info(f"User {callback.from_user.id} state set to: {current_state}")
    
    await callback.answer()


@sudo_router.callback_query(F.data == "add_existing_admin")
async def add_existing_admin_callback(callback: CallbackQuery, state: FSMContext):
    """Start adding existing admin process."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    # Clear any existing state first
    current_state = await state.get_state()
    logger.info(f"User {callback.from_user.id} clearing previous state before add_existing_admin: {current_state}")
    await state.clear()
    
    logger.info(f"Starting add existing admin process for sudo user {callback.from_user.id}")
    
    await callback.message.edit_text(
        "🔄 **افزودن ادمین قبلی**\n\n"
        "این بخش برای اضافه کردن ادمین‌هایی است که روی سرور مرزبان موجود هستند اما در دیتابیس ربات ثبت نشده‌اند.\n\n"
        "📝 **مرحله ۱ از ۴: User ID**\n\n"
        "لطفاً User ID (آیدی تلگرام) ادمین را ارسال کنید:\n\n"
        "🔍 **نکته:** User ID باید یک عدد صحیح باشد\n"
        "📋 **مثال:** `123456789`",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=config.BUTTONS["cancel"], callback_data="back_to_main")]
        ])
    )
    
    # Set initial state for the add existing admin process
    logger.info(f"User {callback.from_user.id} transitioning to state: AddExistingAdminStates.waiting_for_user_id")
    await state.set_state(AddExistingAdminStates.waiting_for_user_id)
    
    # Log state change
    current_state = await state.get_state()
    logger.info(f"User {callback.from_user.id} state set to: {current_state}")
    
    await callback.answer()


@sudo_router.message(AddAdminStates.waiting_for_user_id, F.text)
async def process_admin_user_id(message: Message, state: FSMContext):
    """Process admin user ID input."""
    user_id = message.from_user.id
    current_state = await state.get_state()
    logger.info(f"FSM handler 'process_admin_user_id' activated for user {user_id}, current state: {current_state}, message: {message.text}")
    
    # Verify user is sudo admin
    if user_id not in config.SUDO_ADMINS:
        logger.warning(f"Non-sudo user {user_id} attempted admin addition")
        await message.answer("⛔ شما مجاز به انجام این عمل نیستید.")
        await state.clear()
        return
    
    try:
        admin_user_id = int(message.text.strip())
        logger.info(f"User {user_id} entered admin user ID: {admin_user_id}")
        
        # Check how many panels this user already has
        existing_admins = await db.get_admins_for_user(admin_user_id)
        if existing_admins:
            logger.info(f"User {admin_user_id} already has {len(existing_admins)} panel(s), creating additional panel")
            await message.answer(
                f"ℹ️ **اطلاع: پنل اضافی**\n\n"
                f"این کاربر قبلاً {len(existing_admins)} پنل دارد.\n"
                f"پنل جدید به عنوان پنل اضافی ایجاد می‌شود.\n\n"
                f"📋 پنل‌های موجود:\n" + 
                '\n'.join([f"• {admin.admin_name or admin.marzban_username}" for admin in existing_admins[:3]]) +
                (f"\n• ... و {len(existing_admins)-3} پنل دیگر" if len(existing_admins) > 3 else "")
            )
        
        # Save the user ID to state data
        await state.update_data(user_id=admin_user_id)
        
        # Move to next step
        await message.answer(
            f"✅ **User ID دریافت شد:** `{admin_user_id}`\n\n"
            f"{get_progress_indicator(2)}\n"
            "📝 **مرحله ۲ از ۷: نام ادمین**\n\n"
            "لطفاً نام کامل ادمین را وارد کنید:\n\n"
            "📋 **مثال:** `احمد محمدی` یا `مدیر شعبه شمال`\n\n"
            "💡 **نکته:** این نام برای شناسایی ادمین در پنل استفاده می‌شود."
        )
        
        # Change state to waiting for admin name
        logger.info(f"User {user_id} transitioning from waiting_for_user_id to waiting_for_admin_name")
        await state.set_state(AddAdminStates.waiting_for_admin_name)
        
        # Log state change
        current_state = await state.get_state()
        logger.info(f"User {user_id} state changed to: {current_state}")
        
    except ValueError:
        logger.warning(f"User {user_id} entered invalid user ID: {message.text}")
        await message.answer(
            "❌ **فرمت User ID اشتباه است!**\n\n"
            "🔢 لطفاً یک عدد صحیح وارد کنید.\n"
            "📋 **مثال:** `123456789`"
        )
    except Exception as e:
        logger.error(f"Error processing user ID from {user_id}: {e}")
        await message.answer(
            "❌ **خطا در پردازش User ID**\n\n"
            "لطفاً مجدداً تلاش کنید یا /start را بزنید."
        )
        await state.clear()


@sudo_router.message(AddAdminStates.waiting_for_admin_name, F.text)
async def process_admin_name(message: Message, state: FSMContext):
    """Process admin name input."""
    user_id = message.from_user.id
    current_state = await state.get_state()
    logger.info(f"FSM handler 'process_admin_name' activated for user {user_id}, current state: {current_state}, message: {message.text}")
    
    # Verify user is sudo admin
    if user_id not in config.SUDO_ADMINS:
        logger.warning(f"Non-sudo user {user_id} attempted admin addition")
        await message.answer("⛔ شما مجاز به انجام این عمل نیستید.")
        await state.clear()
        return
    
    try:
        admin_name = message.text.strip()
        
        # Validate admin name
        if len(admin_name) < 2:
            await message.answer(
                "❌ **نام خیلی کوتاه است!**\n\n"
                "لطفاً نام کامل ادمین را وارد کنید (حداقل ۲ کاراکتر):"
            )
            return
        
        if len(admin_name) > 100:
            await message.answer(
                "❌ **نام خیلی طولانی است!**\n\n"
                "لطفاً نامی کوتاه‌تر وارد کنید (حداکثر ۱۰۰ کاراکتر):"
            )
            return
        
        # Save admin name to state data
        await state.update_data(admin_name=admin_name)
        
        logger.info(f"User {user_id} entered admin name: {admin_name}")
        
        # Move to next step
        await message.answer(
            f"✅ **نام ادمین دریافت شد:** `{admin_name}`\n\n"
            "📝 **مرحله ۳ از ۷: Username مرزبان**\n\n"
            "لطفاً Username برای پنل مرزبان وارد کنید:\n\n"
            "📋 **مثال:** `admin_ahmad` یا `manager_north`\n\n"
            "⚠️ **نکات مهم:**\n"
            "• فقط از حروف انگلیسی، اعداد و خط تیره استفاده کنید\n"
            "• Username نباید قبلاً در مرزبان وجود داشته باشد\n"
            "• حداقل ۳ کاراکتر باشد"
        )
        
        # Change state to waiting for marzban username
        await state.set_state(AddAdminStates.waiting_for_marzban_username)
        
        # Log state change
        current_state = await state.get_state()
        logger.info(f"User {user_id} state changed to: {current_state}")
        
    except Exception as e:
        logger.error(f"Error processing admin name from {user_id}: {e}")
        await message.answer(
            "❌ **خطا در پردازش نام ادمین**\n\n"
            "لطفاً مجدداً تلاش کنید یا /start را بزنید."
        )
        await state.clear()


@sudo_router.message(AddAdminStates.waiting_for_marzban_username, F.text)
async def process_marzban_username(message: Message, state: FSMContext):
    """Process Marzban username input."""
    user_id = message.from_user.id
    current_state = await state.get_state()
    logger.info(f"FSM handler 'process_marzban_username' activated for user {user_id}, current state: {current_state}, message: {message.text}")
    
    # Verify user is sudo admin
    if user_id not in config.SUDO_ADMINS:
        logger.warning(f"Non-sudo user {user_id} attempted admin addition")
        await message.answer("⛔ شما مجاز به انجام این عمل نیستید.")
        await state.clear()
        return
    
    try:
        marzban_username = message.text.strip()
        
        # Validate username format
        import re
        if not re.match(r'^[a-zA-Z0-9_-]{3,50}$', marzban_username):
            await message.answer(
                "❌ **فرمت Username اشتباه است!**\n\n"
                "⚠️ **شرایط Username:**\n"
                "• فقط حروف انگلیسی، اعداد، خط تیره (-) و زیرخط (_)\n"
                "• حداقل ۳ و حداکثر ۵۰ کاراکتر\n"
                "• بدون فاصله\n\n"
                "📋 **مثال صحیح:** `admin_ahmad` یا `manager123`"
            )
            return
        
        # Check if username exists in Marzban
        username_exists = await marzban_api.admin_exists(marzban_username)
        if username_exists:
            await message.answer(
                "❌ **Username تکراری است!**\n\n"
                "این Username قبلاً در پنل مرزبان استفاده شده است.\n\n"
                "💡 لطفاً Username متفاوتی انتخاب کنید:"
            )
            return
        
        # Save marzban username to state data
        await state.update_data(marzban_username=marzban_username)
        
        logger.info(f"User {user_id} entered marzban username: {marzban_username}")
        
        # Move to next step
        await message.answer(
            f"✅ **Username مرزبان دریافت شد:** `{marzban_username}`\n\n"
            "📝 **مرحله ۴ از ۷: Password مرزبان**\n\n"
            "لطفاً Password برای پنل مرزبان وارد کنید:\n\n"
            "🔐 **نکات امنیتی:**\n"
            "• حداقل ۸ کاراکتر\n"
            "• ترکیبی از حروف بزرگ، کوچک، اعداد\n"
            "• استفاده از علائم نگارشی توصیه می‌شود\n\n"
            "📋 **مثال:** `MyPass123!` یا `Secure@2024`"
        )
        
        # Change state to waiting for marzban password
        await state.set_state(AddAdminStates.waiting_for_marzban_password)
        
        # Log state change
        current_state = await state.get_state()
        logger.info(f"User {user_id} state changed to: {current_state}")
        
    except Exception as e:
        logger.error(f"Error processing marzban username from {user_id}: {e}")
        await message.answer(
            "❌ **خطا در پردازش Username**\n\n"
            "لطفاً مجدداً تلاش کنید یا /start را بزنید."
        )
        await state.clear()


@sudo_router.message(AddAdminStates.waiting_for_marzban_password, F.text)
async def process_marzban_password(message: Message, state: FSMContext):
    """Process Marzban password input."""
    user_id = message.from_user.id
    current_state = await state.get_state()
    logger.info(f"FSM handler 'process_marzban_password' activated for user {user_id}, current state: {current_state}")
    
    # Verify user is sudo admin
    if user_id not in config.SUDO_ADMINS:
        logger.warning(f"Non-sudo user {user_id} attempted admin addition")
        await message.answer("⛔ شما مجاز به انجام این عمل نیستید.")
        await state.clear()
        return
    
    try:
        marzban_password = message.text.strip()
        
        # Validate password strength
        if len(marzban_password) < 8:
            await message.answer(
                "❌ **Password خیلی ضعیف است!**\n\n"
                "Password باید حداقل ۸ کاراکتر باشد.\n\n"
                "💡 لطفاً Password قوی‌تری وارد کنید:"
            )
            return
        
        if len(marzban_password) > 100:
            await message.answer(
                "❌ **Password خیلی طولانی است!**\n\n"
                "Password نباید بیش از ۱۰۰ کاراکتر باشد.\n\n"
                "💡 لطفاً Password کوتاه‌تری وارد کنید:"
            )
            return
        
        # Basic password strength check
        has_upper = any(c.isupper() for c in marzban_password)
        has_lower = any(c.islower() for c in marzban_password)
        has_digit = any(c.isdigit() for c in marzban_password)
        
        if not (has_upper or has_lower or has_digit):
            await message.answer(
                "⚠️ **Password ضعیف است!**\n\n"
                "برای امنیت بیشتر، Password باید شامل:\n"
                "• حروف بزرگ یا کوچک\n"
                "• اعداد\n\n"
                "🤔 آیا می‌خواهید همین Password را استفاده کنید؟\n"
                "💡 برای ادامه همین Password را مجدد ارسال کنید، یا Password جدیدی وارد کنید."
            )
            return
        
        # Save marzban password to state data
        await state.update_data(marzban_password=marzban_password)
        
        logger.info(f"User {user_id} entered marzban password (length: {len(marzban_password)})")
        
        # Move to next step
        await message.answer(
            f"✅ **Password دریافت شد** (طول: {len(marzban_password)} کاراکتر)\n\n"
            "📝 **مرحله ۵ از ۷: حجم ترافیک**\n\n"
            "لطفاً حداکثر حجم ترافیک مجاز را به گیگابایت وارد کنید:\n\n"
            "📋 **مثال‌ها:**\n"
            "• `100` برای ۱۰۰ گیگابایت\n"
            "• `50.5` برای ۵۰.۵ گیگابایت\n"
            "• `1000` برای ۱ ترابایت\n\n"
            "💡 **نکته:** عدد اعشاری هم قابل قبول است"
        )
        
        # Change state to waiting for traffic volume
        await state.set_state(AddAdminStates.waiting_for_traffic_volume)
        
        # Log state change
        current_state = await state.get_state()
        logger.info(f"User {user_id} state changed to: {current_state}")
        
    except Exception as e:
        logger.error(f"Error processing marzban password from {user_id}: {e}")
        await message.answer(
            "❌ **خطا در پردازش Password**\n\n"
            "لطفاً مجدداً تلاش کنید یا /start را بزنید."
        )
        await state.clear()


@sudo_router.message(AddAdminStates.waiting_for_traffic_volume, F.text)
async def process_traffic_volume(message: Message, state: FSMContext):
    """Process traffic volume input."""
    user_id = message.from_user.id
    current_state = await state.get_state()
    logger.info(f"FSM handler 'process_traffic_volume' activated for user {user_id}, current state: {current_state}, message: {message.text}")
    
    # Verify user is sudo admin
    if user_id not in config.SUDO_ADMINS:
        logger.warning(f"Non-sudo user {user_id} attempted admin addition")
        await message.answer("⛔ شما مجاز به انجام این عمل نیستید.")
        await state.clear()
        return
    
    try:
        traffic_gb = float(message.text.strip())
        
        # Validate traffic volume
        if traffic_gb <= 0:
            await message.answer(
                "❌ **حجم ترافیک نامعتبر!**\n\n"
                "حجم ترافیک باید عددی مثبت باشد.\n\n"
                "💡 لطفاً عدد صحیحی وارد کنید:"
            )
            return
        
        if traffic_gb > 10000:  # More than 10TB seems unrealistic
            await message.answer(
                "⚠️ **حجم ترافیک خیلی زیاد است!**\n\n"
                f"آیا واقعاً می‌خواهید {traffic_gb} گیگابایت تخصیص دهید؟\n\n"
                "🤔 برای تایید همین مقدار را مجدد ارسال کنید، یا مقدار کمتری وارد کنید."
            )
            return
        
        # Convert GB to bytes
        traffic_bytes = gb_to_bytes(traffic_gb)
        
        # Save traffic to state data
        await state.update_data(traffic_gb=traffic_gb, traffic_bytes=traffic_bytes)
        
        logger.info(f"User {user_id} entered traffic volume: {traffic_gb} GB ({traffic_bytes} bytes)")
        
        # Move to next step
        await message.answer(
            f"✅ **حجم ترافیک دریافت شد:** {traffic_gb} گیگابایت\n\n"
            "📝 **مرحله ۶ از ۷: تعداد کاربر مجاز**\n\n"
            "لطفاً حداکثر تعداد کاربری که این ادمین می‌تواند ایجاد کند را وارد کنید:\n\n"
            "📋 **مثال‌ها:**\n"
            "• `10` برای ۱۰ کاربر\n"
            "• `50` برای ۵۰ کاربر\n"
            "• `100` برای ۱۰۰ کاربر\n\n"
            "💡 **نکته:** عدد صحیح وارد کنید"
        )
        
        # Change state to waiting for max users
        await state.set_state(AddAdminStates.waiting_for_max_users)
        
        # Log state change
        current_state = await state.get_state()
        logger.info(f"User {user_id} state changed to: {current_state}")
        
    except ValueError:
        logger.warning(f"User {user_id} entered invalid traffic volume: {message.text}")
        await message.answer(
            "❌ **فرمت حجم ترافیک اشتباه است!**\n\n"
            "🔢 لطفاً یک عدد صحیح یا اعشاری وارد کنید.\n"
            "📋 **مثال:** `100` یا `50.5`"
        )
    except Exception as e:
        logger.error(f"Error processing traffic volume from {user_id}: {e}")
        await message.answer(
            "❌ **خطا در پردازش حجم ترافیک**\n\n"
            "لطفاً مجدداً تلاش کنید یا /start را بزنید."
        )
        await state.clear()


@sudo_router.message(AddAdminStates.waiting_for_max_users, F.text)
async def process_max_users(message: Message, state: FSMContext):
    """Process max users input."""
    user_id = message.from_user.id
    current_state = await state.get_state()
    logger.info(f"FSM handler 'process_max_users' activated for user {user_id}, current state: {current_state}, message: {message.text}")
    
    # Verify user is sudo admin
    if user_id not in config.SUDO_ADMINS:
        logger.warning(f"Non-sudo user {user_id} attempted admin addition")
        await message.answer("⛔ شما مجاز به انجام این عمل نیستید.")
        await state.clear()
        return
    
    try:
        max_users = int(message.text.strip())
        
        # Validate max users
        if max_users <= 0:
            await message.answer(
                "❌ **تعداد کاربر نامعتبر!**\n\n"
                "تعداد کاربر باید عددی مثبت باشد.\n\n"
                "💡 لطفاً عدد صحیحی وارد کنید:"
            )
            return
        
        if max_users > 10000:  # More than 10k users seems unrealistic for one admin
            await message.answer(
                "⚠️ **تعداد کاربر خیلی زیاد است!**\n\n"
                f"آیا واقعاً می‌خواهید {max_users} کاربر تخصیص دهید؟\n\n"
                "🤔 برای تایید همین مقدار را مجدد ارسال کنید، یا عدد کمتری وارد کنید."
            )
            return
        
        # Save max users to state data
        await state.update_data(max_users=max_users)
        
        logger.info(f"User {user_id} entered max users: {max_users}")
        
        # Move to next step
        await message.answer(
            f"✅ **تعداد کاربر مجاز دریافت شد:** {max_users} کاربر\n\n"
            "📝 **مرحله ۷ از ۷: مدت اعتبار**\n\n"
            "لطفاً مدت اعتبار این ادمین را به روز وارد کنید:\n\n"
            "📋 **مثال‌ها:**\n"
            "• `30` برای ۳۰ روز (یک ماه)\n"
            "• `90` برای ۹۰ روز (سه ماه)\n"
            "• `365` برای ۳۶۵ روز (یک سال)\n\n"
            "💡 **نکته:** پس از انقضا، ادمین غیرفعال می‌شود"
        )
        
        # Change state to waiting for validity period
        await state.set_state(AddAdminStates.waiting_for_validity_period)
        
        # Log state change
        current_state = await state.get_state()
        logger.info(f"User {user_id} state changed to: {current_state}")
        
    except ValueError:
        logger.warning(f"User {user_id} entered invalid max users: {message.text}")
        await message.answer(
            "❌ **فرمت تعداد کاربر اشتباه است!**\n\n"
            "🔢 لطفاً یک عدد صحیح وارد کنید.\n"
            "📋 **مثال:** `10` یا `50`"
        )
    except Exception as e:
        logger.error(f"Error processing max users from {user_id}: {e}")
        await message.answer(
            "❌ **خطا در پردازش تعداد کاربر**\n\n"
            "لطفاً مجدداً تلاش کنید یا /start را بزنید."
        )
        await state.clear()


@sudo_router.message(AddAdminStates.waiting_for_validity_period, F.text)
async def process_validity_period(message: Message, state: FSMContext):
    """Process validity period input."""
    user_id = message.from_user.id
    current_state = await state.get_state()
    logger.info(f"FSM handler 'process_validity_period' activated for user {user_id}, current state: {current_state}, message: {message.text}")
    
    # Verify user is sudo admin
    if user_id not in config.SUDO_ADMINS:
        logger.warning(f"Non-sudo user {user_id} attempted admin addition")
        await message.answer("⛔ شما مجاز به انجام این عمل نیستید.")
        await state.clear()
        return
    
    try:
        validity_days = int(message.text.strip())
        
        # Validate validity period
        if validity_days <= 0:
            await message.answer(
                "❌ **مدت اعتبار نامعتبر!**\n\n"
                "مدت اعتبار باید عددی مثبت باشد.\n\n"
                "💡 لطفاً تعداد روز را وارد کنید:"
            )
            return
        
        if validity_days > 3650:  # More than 10 years seems unrealistic
            await message.answer(
                "⚠️ **مدت اعتبار خیلی طولانی است!**\n\n"
                f"آیا واقعاً می‌خواهید {validity_days} روز ({validity_days//365} سال) تخصیص دهید؟\n\n"
                "🤔 برای تایید همین مقدار را مجدد ارسال کنید، یا عدد کمتری وارد کنید."
            )
            return
        
        # Convert days to seconds
        validity_seconds = days_to_seconds(validity_days)
        
        # Save validity period to state data
        await state.update_data(validity_days=validity_days, validity_seconds=validity_seconds)
        
        logger.info(f"User {user_id} entered validity period: {validity_days} days ({validity_seconds} seconds)")
        
        # Get all collected data for confirmation
        data = await state.get_data()
        admin_user_id = data.get("user_id")
        admin_name = data.get("admin_name")
        marzban_username = data.get("marzban_username")
        traffic_gb = data.get("traffic_gb")
        max_users = data.get("max_users")
        
        # Show confirmation with summary
        confirmation_text = (
            "📋 **خلاصه اطلاعات ادمین جدید**\n\n"
            f"👤 **User ID:** `{admin_user_id}`\n"
            f"📝 **نام ادمین:** {admin_name}\n"
            f"🔐 **Username مرزبان:** {marzban_username}\n"
            f"📊 **حجم ترافیک:** {traffic_gb} گیگابایت\n"
            f"👥 **تعداد کاربر مجاز:** {max_users} کاربر\n"
            f"📅 **مدت اعتبار:** {validity_days} روز\n\n"
            "❓ **آیا اطلاعات صحیح است؟**\n\n"
            "✅ برای **تایید و ایجاد ادمین** دکمه تایید را بزنید\n"
            "❌ برای **لغو** دکمه لغو را بزنید"
        )
        
        # Create confirmation keyboard
        confirmation_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ تایید و ایجاد", callback_data="confirm_create_admin"),
                InlineKeyboardButton(text="❌ لغو", callback_data="back_to_main")
            ]
        ])
        
        await message.answer(confirmation_text, reply_markup=confirmation_keyboard)
        
        # Change state to waiting for confirmation
        await state.set_state(AddAdminStates.waiting_for_confirmation)
        
        # Log state change
        current_state = await state.get_state()
        logger.info(f"User {user_id} state changed to: {current_state}")
        
    except ValueError:
        logger.warning(f"User {user_id} entered invalid validity period: {message.text}")
        await message.answer(
            "❌ **فرمت مدت اعتبار اشتباه است!**\n\n"
            "🔢 لطفاً تعداد روز را به عدد صحیح وارد کنید.\n"
            "📋 **مثال:** `30` یا `90`"
        )
    except Exception as e:
        logger.error(f"Error processing validity period from {user_id}: {e}")
        await message.answer(
            "❌ **خطا در پردازش مدت اعتبار**\n\n"
            "لطفاً مجدداً تلاش کنید یا /start را بزنید."
        )
        await state.clear()


@sudo_router.callback_query(F.data == "confirm_create_admin")
async def confirm_create_admin(callback: CallbackQuery, state: FSMContext):
    """Confirm and create the admin."""
    user_id = callback.from_user.id
    
    # Verify user is sudo admin
    if user_id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    # Verify state
    current_state = await state.get_state()
    if current_state != AddAdminStates.waiting_for_confirmation:
        await callback.answer("جلسه منقضی شده", show_alert=True)
        await state.clear()
        return
    
    try:
        # Get all collected data
        data = await state.get_data()
        admin_user_id = data.get("user_id")
        admin_name = data.get("admin_name")
        marzban_username = data.get("marzban_username")
        marzban_password = data.get("marzban_password")
        traffic_bytes = data.get("traffic_bytes")
        max_users = data.get("max_users")
        validity_seconds = data.get("validity_seconds")
        validity_days = data.get("validity_days")
        
        # Validate required data
        if not all([admin_user_id, admin_name, marzban_username, marzban_password, traffic_bytes, max_users, validity_seconds]):
            logger.error(f"Missing required data in state for user {user_id}")
            await callback.message.edit_text(
                "❌ **خطا: اطلاعات ناقص**\n\n"
                "اطلاعات جلسه ناقص است. لطفاً مجدداً شروع کنید.",
                reply_markup=get_sudo_keyboard()
            )
            await state.clear()
            await callback.answer()
            return
        
        # Update message to show progress
        await callback.message.edit_text(
            "⏳ **در حال ایجاد ادمین...**\n\n"
            "لطفاً صبر کنید..."
        )
        
        logger.info(f"Creating admin: {admin_user_id} with username: {marzban_username}")
        
        # Step 1: Create admin in Marzban panel
        marzban_success = await marzban_api.create_admin(
            username=marzban_username,
            password=marzban_password,
            telegram_id=admin_user_id
        )
        
        if not marzban_success:
            logger.error(f"Failed to create admin in Marzban: {marzban_username}")
            await callback.message.edit_text(
                "❌ **خطا در ایجاد ادمین در پنل مرزبان**\n\n"
                "علت‌های احتمالی:\n"
                "• Username تکراری است\n"
                "• اتصال به مرزبان برقرار نیست\n"
                "• تنظیمات API نادرست است\n"
                "• مشکل در احراز هویت\n\n"
                "⚠️ **هیچ تغییری در سیستم انجام نشد**\n"
                "لطفاً مشکل را بررسی کرده و مجدداً تلاش کنید.",
                reply_markup=get_sudo_keyboard()
            )
            await state.clear()
            await callback.answer()
            return
        
        # Step 2: Create admin in local database
        admin = AdminModel(
            user_id=admin_user_id,
            admin_name=admin_name,
            marzban_username=marzban_username,
            marzban_password=marzban_password,  # Store for management purposes
            max_users=max_users,
            max_total_time=validity_seconds,
            max_total_traffic=traffic_bytes,
            validity_days=validity_days
        )
        
        admin_id = await db.add_admin(admin)
        
        if admin_id == 0:
            logger.error(f"Failed to add admin to database: {admin_user_id}")
            # Try to remove from Marzban if database failed
            try:
                await marzban_api.delete_admin(marzban_username)
                logger.info(f"Cleaned up admin {marzban_username} from Marzban after database failure")
            except Exception as cleanup_error:
                logger.error(f"Failed to cleanup admin {marzban_username} from Marzban: {cleanup_error}")
            
            await callback.message.edit_text(
                "❌ **خطا در ذخیره اطلاعات در پایگاه داده**\n\n"
                "ادمین در پنل مرزبان ایجاد شد اما در پایگاه داده ربات ذخیره نشد.\n\n"
                "🔄 **اقدام انجام شده:** ادمین از مرزبان نیز حذف شد تا تناقض پیش نیاید.\n\n"
                "⚠️ لطفاً مشکل پایگاه داده را بررسی و مجدداً تلاش کنید.",
                reply_markup=get_sudo_keyboard()
            )
            await state.clear()
            await callback.answer()
            return
        
        # Step 3: Send notifications
        admin_info = {
            "user_id": admin_user_id,
            "admin_name": admin_name,
            "marzban_username": marzban_username,
            "max_users": max_users,
            "max_total_time": validity_seconds,
            "max_total_traffic": traffic_bytes,
            "validity_days": validity_days
        }
        
        await notify_admin_added(callback.bot, admin_user_id, admin_info, user_id)
        
        # Step 4: Show success message
        success_text = (
            "✅ **ادمین با موفقیت ایجاد شد!**\n\n"
            f"👤 **User ID:** {admin_user_id}\n"
            f"📝 **نام ادمین:** {admin_name}\n"
            f"🔐 **Username مرزبان:** {marzban_username}\n"
            f"👥 **حداکثر کاربر:** {max_users}\n"
            f"📊 **حجم ترافیک:** {await format_traffic_size(traffic_bytes)}\n"
            f"📅 **مدت اعتبار:** {validity_days} روز\n\n"
            "🎉 **مراحل انجام شده:**\n"
            "✅ ایجاد در پنل مرزبان\n"
            "✅ ذخیره در پایگاه داده\n"
            "✅ ارسال اطلاع‌رسانی\n\n"
            "🔔 ادمین جدید می‌تواند از ربات استفاده کند."
        )
        
        await callback.message.edit_text(success_text, reply_markup=get_sudo_keyboard())
        
        logger.info(f"Admin {admin_user_id} successfully created by {user_id}")
        
        await state.clear()
        await callback.answer("ادمین با موفقیت ایجاد شد! ✅")
        
    except Exception as e:
        logger.error(f"Error creating admin for {user_id}: {e}")
        await callback.message.edit_text(
            f"❌ **خطا در ایجاد ادمین**\n\n"
            f"خطا: {str(e)}\n\n"
            "لطفاً مجدداً تلاش کنید.",
            reply_markup=get_sudo_keyboard()
        )
        await state.clear()
        await callback.answer()


@sudo_router.message(AddAdminStates.waiting_for_confirmation, F.text)
async def handle_text_in_confirmation_state(message: Message, state: FSMContext):
    """Handle text messages in confirmation state."""
    user_id = message.from_user.id
    logger.info(f"User {user_id} sent text in confirmation state: {message.text}")
    
    await message.answer(
        "⏸️ **در انتظار تایید**\n\n"
        "لطفاً از دکمه‌های زیر استفاده کنید:\n"
        "✅ **تایید و ایجاد** - برای ایجاد ادمین\n"
        "❌ **لغو** - برای لغو عملیات\n\n"
        "📝 **اطلاعات وارد شده قابل ویرایش نیست.** برای تغییر، عملیات را لغو کرده و مجدداً شروع کنید."
    )


# Add help handlers for when users send unrelated commands during FSM flow
@sudo_router.message(AddAdminStates.waiting_for_user_id, ~F.text)
@sudo_router.message(AddAdminStates.waiting_for_admin_name, ~F.text)  
@sudo_router.message(AddAdminStates.waiting_for_marzban_username, ~F.text)
@sudo_router.message(AddAdminStates.waiting_for_marzban_password, ~F.text)
@sudo_router.message(AddAdminStates.waiting_for_traffic_volume, ~F.text)
@sudo_router.message(AddAdminStates.waiting_for_max_users, ~F.text)
@sudo_router.message(AddAdminStates.waiting_for_validity_period, ~F.text)
async def handle_non_text_in_fsm(message: Message, state: FSMContext):
    """Handle non-text messages during FSM flow."""
    current_state = await state.get_state()
    logger.info(f"User {message.from_user.id} sent non-text message in state {current_state}")
    
    state_names = {
        "AddAdminStates:waiting_for_user_id": "User ID",
        "AddAdminStates:waiting_for_admin_name": "نام ادمین",
        "AddAdminStates:waiting_for_marzban_username": "Username مرزبان",
        "AddAdminStates:waiting_for_marzban_password": "Password مرزبان",
        "AddAdminStates:waiting_for_traffic_volume": "حجم ترافیک",
        "AddAdminStates:waiting_for_max_users": "تعداد کاربر مجاز",
        "AddAdminStates:waiting_for_validity_period": "مدت اعتبار"
    }
    
    current_step = state_names.get(current_state, "اطلاعات")
    
    await message.answer(
        f"📝 **در انتظار: {current_step}**\n\n"
        "لطفاً فقط متن ارسال کنید. فایل، عکس، صدا و سایر انواع پیام پذیرفته نمی‌شوند.\n\n"
        "❌ برای لغو عملیات /start را بزنید."
    )


# Add handler for commands during FSM (except /start which should cancel)
@sudo_router.message(F.text.startswith('/') & ~F.text.startswith('/start'))
async def handle_commands_in_fsm(message: Message, state: FSMContext):
    """Handle commands during FSM flow (except /start)."""
    current_state = await state.get_state()
    
    # Only handle if we're in an FSM state
    if not current_state or not current_state.startswith('AddAdminStates:'):
        return
        
    command = message.text
    logger.info(f"User {message.from_user.id} sent command {command} in state {current_state}")
    
    await message.answer(
        f"⚠️ **عملیات در حال انجام**\n\n"
        f"شما در حال افزودن ادمین جدید هستید.\n"
        f"دستور `{command}` در این مرحله قابل اجرا نیست.\n\n"
        "🔄 **گزینه‌های شما:**\n"
        "• ادامه فرآیند افزودن ادمین\n"
        "• ارسال /start برای لغو و بازگشت به منوی اصلی\n\n"
        "💡 پس از تکمیل یا لغو، می‌توانید از دستورات استفاده کنید."
    )


@sudo_router.callback_query(F.data == "remove_admin")
async def remove_admin_callback(callback: CallbackQuery):
    """Show panel list for complete deletion."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    # Get only active admins for deletion
    all_admins = await db.get_all_admins()
    active_admins = [admin for admin in all_admins if admin.is_active]
    
    if not active_admins:
        await callback.message.edit_text(
            "❌ هیچ پنل فعالی برای حذف یافت نشد.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_main")]
            ])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        "🗑️ انتخاب پنل برای حذف کامل (پنل و تمام کاربرانش):",
        reply_markup=get_panel_list_keyboard(active_admins, "select_for_deletion")
    )
    await callback.answer()


@sudo_router.callback_query(F.data.startswith("select_for_deletion_"))
async def select_panel_for_deletion(callback: CallbackQuery):
    """Show confirmation dialog before deletion."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    admin_id = int(callback.data.split("_")[-1])
    admin = await db.get_admin_by_id(admin_id)
    
    if not admin:
        await callback.answer("پنل یافت نشد", show_alert=True)
        return
    
    panel_name = admin.admin_name or admin.marzban_username or f"Panel-{admin.id}"
    
    # Show detailed confirmation
    confirmation_text = (
        "⚠️ **تأیید نهایی حذف پنل**\n\n"
        f"🏷️ **نام پنل:** {panel_name}\n"
        f"👤 **کاربر:** {admin.username or admin.user_id}\n"
        f"🔐 **نام کاربری مرزبان:** {admin.marzban_username}\n"
        f"📊 **حداکثر کاربران:** {admin.max_users}\n\n"
        "🚨 **هشدار مهم:**\n"
        "• این عمل تمام کاربران این پنل را از مرزبان حذف می‌کند\n"
        "• پنل از دیتابیس ربات حذف می‌شود\n"
        "• این عمل غیرقابل برگشت است\n\n"
        "آیا مطمئن هستید که می‌خواهید این پنل و **تمام کاربرانش** را حذف کنید؟"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚨 بله، حذف کن", callback_data=f"final_confirm_delete_{admin_id}"),
        ],
        [
            InlineKeyboardButton(text="❌ لغو", callback_data="remove_admin"),
        ]
    ])
    
    await callback.message.edit_text(confirmation_text, reply_markup=keyboard)
    await callback.answer()


@sudo_router.callback_query(F.data.startswith("final_confirm_delete_"))
async def final_confirm_delete_panel(callback: CallbackQuery):
    """Actually delete the panel after final confirmation."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    admin_id = int(callback.data.split("_")[-1])
    admin = await db.get_admin_by_id(admin_id)
    
    if not admin:
        await callback.answer("پنل یافت نشد", show_alert=True)
        return
    
    panel_name = admin.admin_name or admin.marzban_username or f"Panel-{admin.id}"
    
    # Show processing message
    await callback.message.edit_text(
        f"⏳ **در حال حذف پنل {panel_name}...**\n\n"
        "لطفاً منتظر بمانید..."
    )
    
    # Completely delete the panel and all users for manual deactivation
    success = await delete_admin_panel_completely(admin_id, "غیرفعالسازی دستی توسط سودو")
    
    if success:
        panel_name = admin.admin_name or admin.marzban_username or f"Panel-{admin.id}"
        await callback.message.edit_text(
            f"✅ پنل {panel_name} با موفقیت حذف شد.\n\n"
            f"👤 کاربر: {admin.username or admin.user_id}\n"
            f"🏷️ نام پنل: {panel_name}\n"
            f"🔐 نام کاربری مرزبان: {admin.marzban_username}\n\n"
            "🗑️ پنل و تمام کاربران آن به طور کامل حذف شدند.",
            reply_markup=get_sudo_keyboard()
        )
    else:
        await callback.message.edit_text(
            "❌ خطا در حذف پنل.",
            reply_markup=get_sudo_keyboard()
        )
    
    await callback.answer()


@sudo_router.callback_query(F.data == "edit_panel")
async def edit_panel_callback(callback: CallbackQuery):
    """Show panel list for editing."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    # Get all admins for editing
    admins = await db.get_all_admins()
    
    if not admins:
        await callback.message.edit_text(
            "❌ هیچ پنلی برای ویرایش یافت نشد.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_main")]
            ])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        config.MESSAGES["select_panel_to_edit"],
        reply_markup=get_panel_list_keyboard(admins, "start_edit")
    )
    await callback.answer()


@sudo_router.callback_query(F.data.startswith("start_edit_"))
async def start_edit_panel(callback: CallbackQuery, state: FSMContext):
    """Start editing a specific panel."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    admin_id = int(callback.data.split("_")[-1])
    admin = await db.get_admin_by_id(admin_id)
    
    if not admin:
        await callback.answer("پنل یافت نشد", show_alert=True)
        return
    
    # Store admin_id in state
    await state.update_data(admin_id=admin_id)
    
    # Show current limits and ask for new traffic
    from utils.notify import bytes_to_gb, seconds_to_days
    current_traffic = bytes_to_gb(admin.max_total_traffic)
    current_time = seconds_to_days(admin.max_total_time)
    
    panel_name = admin.admin_name or admin.marzban_username or f"Panel-{admin.id}"
    
    await callback.message.edit_text(
        f"✏️ **ویرایش پنل {panel_name}**\n\n"
        f"👤 کاربر: {admin.username or admin.user_id}\n"
        f"🔐 نام کاربری مرزبان: {admin.marzban_username}\n\n"
        f"📊 **محدودیت‌های فعلی:**\n"
        f"📡 ترافیک: {current_traffic} گیگابایت\n"
        f"⏰ مدت زمان: {current_time} روز\n\n"
        f"📝 **مرحله ۱ از ۳: ترافیک جدید**\n\n"
        "لطفاً مقدار ترافیک جدید را به گیگابایت وارد کنید:\n\n"
        "📋 **مثال:** `500` برای ۵۰۰ گیگابایت\n"
        "💡 **نکته:** عدد صحیح وارد کنید",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=config.BUTTONS["cancel"], callback_data="back_to_main")]
        ])
    )
    
    await state.set_state(EditPanelStates.waiting_for_traffic_volume)
    await callback.answer()


@sudo_router.message(EditPanelStates.waiting_for_traffic_volume, F.text)
async def process_edit_traffic(message: Message, state: FSMContext):
    """Process new traffic volume for editing."""
    user_id = message.from_user.id
    current_state = await state.get_state()
    logger.info(f"FSM handler 'process_edit_traffic' activated for user {user_id}, current state: {current_state}, message: {message.text}")
    
    # Verify user is sudo admin
    if user_id not in config.SUDO_ADMINS:
        logger.warning(f"Non-sudo user {user_id} attempted panel editing")
        await message.answer("⛔ شما مجاز به انجام این عمل نیستید.")
        await state.clear()
        return
    
    try:
        traffic_gb = int(message.text.strip())
        
        if traffic_gb <= 0:
            await message.answer(
                "❌ **مقدار ترافیک نامعتبر!**\n\n"
                "لطفاً عددی بزرگتر از صفر وارد کنید:"
            )
            return
        
        if traffic_gb > 10000:  # Reasonable upper limit
            await message.answer(
                "❌ **مقدار ترافیک خیلی زیاد!**\n\n"
                "لطفاً مقداری کمتر از ۱۰۰۰۰ گیگابایت وارد کنید:"
            )
            return
        
        # Save traffic to state
        await state.update_data(traffic_gb=traffic_gb)
        
        # Get admin info for display
        data = await state.get_data()
        admin_id = data.get('admin_id')
        admin = await db.get_admin_by_id(admin_id)
        
        from utils.notify import seconds_to_days
        current_time = seconds_to_days(admin.max_total_time)
        
        await message.answer(
            f"✅ **ترافیک جدید:** {traffic_gb} گیگابایت\n\n"
            f"📝 **مرحله ۲ از ۳: مدت زمان جدید**\n\n"
            f"⏰ **مدت زمان فعلی:** {current_time} روز\n\n"
            "لطفاً مدت زمان جدید را به روز وارد کنید:\n\n"
            "📋 **مثال:** `30` برای ۳۰ روز\n"
            "💡 **نکته:** عدد صحیح وارد کنید"
        )
        
        await state.set_state(EditPanelStates.waiting_for_validity_period)
        
    except ValueError:
        await message.answer(
            "❌ **فرمت ترافیک اشتباه است!**\n\n"
            "🔢 لطفاً یک عدد صحیح وارد کنید.\n"
            "📋 **مثال:** `500`"
        )
    except Exception as e:
        logger.error(f"Error processing traffic from {user_id}: {e}")
        await message.answer(
            "❌ **خطا در پردازش ترافیک**\n\n"
            "لطفاً مجدداً تلاش کنید یا /start را بزنید."
        )
        await state.clear()


@sudo_router.message(EditPanelStates.waiting_for_validity_period, F.text)
async def process_edit_time(message: Message, state: FSMContext):
    """Process new validity period for editing."""
    user_id = message.from_user.id
    current_state = await state.get_state()
    logger.info(f"FSM handler 'process_edit_time' activated for user {user_id}, current state: {current_state}, message: {message.text}")
    
    # Verify user is sudo admin
    if user_id not in config.SUDO_ADMINS:
        logger.warning(f"Non-sudo user {user_id} attempted panel editing")
        await message.answer("⛔ شما مجاز به انجام این عمل نیستید.")
        await state.clear()
        return
    
    try:
        validity_days = int(message.text.strip())
        
        if validity_days <= 0:
            await message.answer(
                "❌ **مدت زمان نامعتبر!**\n\n"
                "لطفاً عددی بزرگتر از صفر وارد کنید:"
            )
            return
        
        if validity_days > 3650:  # Max 10 years
            await message.answer(
                "❌ **مدت زمان خیلی زیاد!**\n\n"
                "لطفاً مقداری کمتر از ۳۶۵۰ روز وارد کنید:"
            )
            return
        
        # Save time to state
        await state.update_data(validity_days=validity_days)
        
        # Get all data for confirmation
        data = await state.get_data()
        admin_id = data.get('admin_id')
        traffic_gb = data.get('traffic_gb')
        admin = await db.get_admin_by_id(admin_id)
        
        from utils.notify import bytes_to_gb, seconds_to_days
        old_traffic = bytes_to_gb(admin.max_total_traffic)
        old_time = seconds_to_days(admin.max_total_time)
        
        panel_name = admin.admin_name or admin.marzban_username or f"Panel-{admin.id}"
        
        # Show confirmation
        confirmation_text = (
            f"📋 **تأیید نهایی ویرایش پنل**\n\n"
            f"🏷️ **پنل:** {panel_name}\n"
            f"👤 **کاربر:** {admin.username or admin.user_id}\n"
            f"🔐 **نام کاربری مرزبان:** {admin.marzban_username}\n\n"
            f"📊 **تغییرات:**\n"
            f"📡 ترافیک: {old_traffic} GB ← {traffic_gb} GB\n"
            f"⏰ مدت زمان: {old_time} روز ← {validity_days} روز\n\n"
            "❓ آیا از انجام این تغییرات اطمینان دارید؟"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ تأیید", callback_data="confirm_edit_panel"),
                InlineKeyboardButton(text="❌ لغو", callback_data="back_to_main")
            ]
        ])
        
        await message.answer(confirmation_text, reply_markup=keyboard)
        await state.set_state(EditPanelStates.waiting_for_confirmation)
        
    except ValueError:
        await message.answer(
            "❌ **فرمت مدت زمان اشتباه است!**\n\n"
            "🔢 لطفاً یک عدد صحیح وارد کنید.\n"
            "📋 **مثال:** `30`"
        )
    except Exception as e:
        logger.error(f"Error processing time from {user_id}: {e}")
        await message.answer(
            "❌ **خطا در پردازش مدت زمان**\n\n"
            "لطفاً مجدداً تلاش کنید یا /start را بزنید."
        )
        await state.clear()


@sudo_router.callback_query(F.data == "confirm_edit_panel")
async def confirm_edit_panel(callback: CallbackQuery, state: FSMContext):
    """Confirm panel editing."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        await state.clear()
        return
    
    try:
        # Get data from state
        data = await state.get_data()
        admin_id = data.get('admin_id')
        traffic_gb = data.get('traffic_gb')
        validity_days = data.get('validity_days')
        
        if not all([admin_id, traffic_gb, validity_days]):
            await callback.answer("داده‌های ناکافی", show_alert=True)
            await state.clear()
            return
        
        # Convert to database format
        from utils.notify import gb_to_bytes, days_to_seconds
        max_total_traffic = gb_to_bytes(traffic_gb)
        max_total_time = days_to_seconds(validity_days)
        
        # Update in database
        success = await db.update_admin(
            admin_id, 
            max_total_traffic=max_total_traffic,
            max_total_time=max_total_time
        )
        
        if success:
            admin = await db.get_admin_by_id(admin_id)
            panel_name = admin.admin_name or admin.marzban_username or f"Panel-{admin.id}"
            
            await callback.message.edit_text(
                f"✅ پنل {panel_name} با موفقیت ویرایش شد!\n\n"
                f"📊 **محدودیت‌های جدید:**\n"
                f"📡 ترافیک: {traffic_gb} گیگابایت\n"
                f"⏰ مدت زمان: {validity_days} روز\n\n"
                f"👤 کاربر: {admin.username or admin.user_id}\n"
                f"🔐 نام کاربری مرزبان: {admin.marzban_username}",
                reply_markup=get_sudo_keyboard()
            )
            
            # Log the change
            from models.schemas import LogModel
            log = LogModel(
                admin_user_id=admin.user_id,
                action="panel_limits_edited",
                details=f"Panel {admin_id} limits updated: Traffic={traffic_gb}GB, Time={validity_days}days"
            )
            await db.add_log(log)
            
        else:
            await callback.message.edit_text(
                "❌ خطا در ویرایش پنل.",
                reply_markup=get_sudo_keyboard()
            )
        
        await state.clear()
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error confirming panel edit: {e}")
        await callback.message.edit_text(
            "❌ خطا در ویرایش پنل.",
            reply_markup=get_sudo_keyboard()
        )
        await state.clear()
        await callback.answer()


async def get_admin_list_text() -> str:
    """Get admin list text. Shared logic for both callback and command handlers."""
    admins = await db.get_all_admins()
    
    if not admins:
        return "❌ هیچ ادمینی یافت نشد."
    
    text = "📋 لیست همه ادمین‌ها:\n\n"
    
    # Group admins by user_id to show multiple panels per user
    user_panels = {}
    for admin in admins:
        if admin.user_id not in user_panels:
            user_panels[admin.user_id] = []
        user_panels[admin.user_id].append(admin)
    
    counter = 1
    for user_id, user_admins in user_panels.items():
        text += f"{counter}. 👨‍💼 کاربر ID: {user_id}\n"
        
        for i, admin in enumerate(user_admins, 1):
            status = "✅ فعال" if admin.is_active else "❌ غیرفعال"
            panel_name = admin.admin_name or f"پنل {i}"
            
            text += f"   🔹 {panel_name} {status}\n"
            text += f"      🆔 پنل ID: {admin.id}\n"
            text += f"      👤 نام کاربری مرزبان: {admin.marzban_username or 'نامشخص'}\n"
            text += f"      🏷️ نام تلگرام: {admin.username or 'نامشخص'}\n"
            text += f"      👥 حداکثر کاربر: {admin.max_users}\n"
            text += f"      📅 تاریخ ایجاد: {admin.created_at.strftime('%Y-%m-%d %H:%M') if admin.created_at else 'نامشخص'}\n"
            
            if not admin.is_active and admin.deactivated_reason:
                text += f"      ❌ دلیل غیرفعالی: {admin.deactivated_reason}\n"
            
            text += "\n"
        
        counter += 1
        text += "\n"
    
    return text


async def get_admin_status_text() -> str:
    """Get admin status text. Shared logic for both callback and command handlers."""
    admins = await db.get_all_admins()
    
    if not admins:
        return "❌ هیچ ادمینی یافت نشد."
    
    text = "📊 وضعیت تفصیلی ادمین‌ها:\n\n"
    
    # Group admins by user_id to show multiple panels per user
    user_panels = {}
    for admin in admins:
        if admin.user_id not in user_panels:
            user_panels[admin.user_id] = []
        user_panels[admin.user_id].append(admin)
    
    for user_id, user_admins in user_panels.items():
        text += f"👨‍💼 کاربر ID: {user_id}\n"
        
        for i, admin in enumerate(user_admins, 1):
            status = "✅ فعال" if admin.is_active else "❌ غیرفعال"
            panel_name = admin.admin_name or f"پنل {i}"
            
            text += f"   🔹 {panel_name} ({admin.marzban_username}) {status}\n"
            
            # Get admin stats using their own credentials
            try:
                if admin.is_active and admin.marzban_username and admin.marzban_password:
                    admin_api = await marzban_api.create_admin_api(admin.marzban_username, admin.marzban_password)
                    admin_stats = await admin_api.get_admin_stats()
                    
                    # Calculate usage percentages
                    user_percentage = (admin_stats.total_users / admin.max_users * 100) if admin.max_users > 0 else 0
                    traffic_percentage = (admin_stats.total_traffic_used / admin.max_total_traffic * 100) if admin.max_total_traffic > 0 else 0
                    time_percentage = (admin_stats.total_time_used / admin.max_total_time * 100) if admin.max_total_time > 0 else 0
                    
                    text += f"      👥 کاربران: {admin_stats.total_users}/{admin.max_users} ({user_percentage:.1f}%)\n"
                    text += f"      📊 ترافیک: {await format_traffic_size(admin_stats.total_traffic_used)}/{await format_traffic_size(admin.max_total_traffic)} ({traffic_percentage:.1f}%)\n"
                    text += f"      ⏱️ زمان: {await format_time_duration(admin_stats.total_time_used)}/{await format_time_duration(admin.max_total_time)} ({time_percentage:.1f}%)\n"
                    
                    # Show warning if approaching limits
                    if any(p >= 80 for p in [user_percentage, traffic_percentage, time_percentage]):
                        text += f"      ⚠️ نزدیک به محدودیت!\n"
                        
                elif not admin.is_active:
                    text += f"      ❌ غیرفعال"
                    if admin.deactivated_reason:
                        text += f" - {admin.deactivated_reason}"
                    text += "\n"
                else:
                    text += f"      ❌ اطلاعات احراز هویت ناکامل\n"
                    
            except Exception as e:
                text += f"      ❌ خطا در دریافت آمار: {str(e)[:50]}...\n"
            
            text += "\n"
        
        text += "\n"
    
    return text


@sudo_router.callback_query(F.data == "list_admins")
async def list_admins_callback(callback: CallbackQuery):
    """Show list of all admins."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    text = await get_admin_list_text()
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_main")]
        ])
    )
    await callback.answer()


@sudo_router.callback_query(F.data == "admin_status")
async def admin_status_callback(callback: CallbackQuery):
    """Show detailed status of all admins."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    text = await get_admin_status_text()
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_main")]
        ])
    )
    await callback.answer()


@sudo_router.message(Command("add_admin"))
async def add_admin_command(message: Message, state: FSMContext):
    """Handle /add_admin text command."""
    if message.from_user.id not in config.SUDO_ADMINS:
        await message.answer(config.MESSAGES["unauthorized"])
        return
    
    # Clear any existing state first
    await state.clear()
    
    logger.info(f"Starting comprehensive add admin process via command for sudo user {message.from_user.id}")
    
    await message.answer(
        "🆕 **افزودن ادمین جدید**\n\n"
        "📝 **مرحله ۱ از ۷: User ID**\n\n"
        "لطفاً User ID (آیدی تلگرام) کاربری که می‌خواهید ادمین کنید را ارسال کنید:\n\n"
        "🔍 **نکته:** User ID باید یک عدد صحیح باشد\n"
        "📋 **مثال:** `123456789`\n\n"
        "💡 **راهنما:** برای یافتن User ID می‌توانید از ربات‌های مخصوص یا دستور /start در ربات‌ها استفاده کنید.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=config.BUTTONS["cancel"], callback_data="back_to_main")]
        ])
    )
    
    await state.set_state(AddAdminStates.waiting_for_user_id)
    
    # Log state change
    current_state = await state.get_state()
    logger.info(f"User {message.from_user.id} state set to: {current_state}")


@sudo_router.message(Command("show_admins", "list_admins"))
async def show_admins_command(message: Message):
    """Handle /show_admins or /list_admins text command."""
    if message.from_user.id not in config.SUDO_ADMINS:
        await message.answer(config.MESSAGES["unauthorized"])
        return
    
    text = await get_admin_list_text()
    await message.answer(text, reply_markup=get_sudo_keyboard())


@sudo_router.message(Command("remove_admin"))
async def remove_admin_command(message: Message):
    """Handle /remove_admin text command."""
    if message.from_user.id not in config.SUDO_ADMINS:
        await message.answer(config.MESSAGES["unauthorized"])
        return
    
    # Get only active admins for deactivation
    all_admins = await db.get_all_admins()
    active_admins = [admin for admin in all_admins if admin.is_active]
    
    if not active_admins:
        await message.answer(
            "❌ هیچ پنل فعالی برای غیرفعالسازی یافت نشد.",
            reply_markup=get_sudo_keyboard()
        )
        return
    
    await message.answer(
        config.MESSAGES["select_panel_to_deactivate"],
        reply_markup=get_panel_list_keyboard(active_admins, "confirm_deactivate")
    )


@sudo_router.message(Command("edit_panel"))
async def edit_panel_command(message: Message):
    """Handle /edit_panel text command."""
    if message.from_user.id not in config.SUDO_ADMINS:
        await message.answer(config.MESSAGES["unauthorized"])
        return
    
    # Get all admins for editing
    admins = await db.get_all_admins()
    
    if not admins:
        await message.answer(
            "❌ هیچ پنلی برای ویرایش یافت نشد.",
            reply_markup=get_sudo_keyboard()
        )
        return
    
    await message.answer(
        config.MESSAGES["select_panel_to_edit"],
        reply_markup=get_panel_list_keyboard(admins, "start_edit")
    )


@sudo_router.message(Command("admin_status"))
async def admin_status_command(message: Message):
    """Handle /admin_status text command."""
    if message.from_user.id not in config.SUDO_ADMINS:
        await message.answer(config.MESSAGES["unauthorized"])
        return
    
    text = await get_admin_status_text()
    await message.answer(text, reply_markup=get_sudo_keyboard())


@sudo_router.callback_query(F.data == "activate_admin")
async def activate_admin_callback(callback: CallbackQuery):
    """Show deactivated admin list for reactivation."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    deactivated_admins = await db.get_deactivated_admins()
    if not deactivated_admins:
        await callback.message.edit_text(
            config.MESSAGES["no_deactivated_admins"],
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_main")]
            ])
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        config.MESSAGES["select_admin_to_reactivate"],
        reply_markup=get_admin_list_keyboard(deactivated_admins, "confirm_activate")
    )
    await callback.answer()


@sudo_router.callback_query(F.data.startswith("confirm_activate_"))
async def confirm_activate_admin(callback: CallbackQuery):
    """Confirm admin reactivation with support for multiple panels per user."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[-1])
    
    # Get all deactivated admins for this user
    deactivated_admins = await db.get_deactivated_admins()
    user_deactivated_admins = [admin for admin in deactivated_admins if admin.user_id == user_id]
    
    if not user_deactivated_admins:
        await callback.answer("هیچ پنل غیرفعال برای این کاربر یافت نشد", show_alert=True)
        return
    
    successful_reactivations = 0
    failed_reactivations = 0
    reactivation_details = []
    
    # Process each deactivated admin panel for this user
    for admin in user_deactivated_admins:
        try:
            # Reactivate admin panel in database
            db_success = await db.reactivate_admin(admin.id)
            
            if db_success:
                # Restore original password in Marzban and update database
                password_restored = await restore_admin_password_and_update_db(admin.id, admin.original_password)
                
                # Reactivate users belonging to this admin panel
                users_reactivated = await reactivate_admin_panel_users(admin.id)
                
                successful_reactivations += 1
                panel_name = admin.admin_name or admin.marzban_username or f"Panel {admin.id}"
                reactivation_details.append(f"✅ {panel_name}: پنل فعال شد، {'پسورد بازیابی شد' if password_restored else 'خطا در بازیابی پسورد'}, {users_reactivated} کاربر فعال شد")
                
                # Log the action for this specific panel
                log = LogModel(
                    admin_user_id=user_id,
                    action="admin_panel_reactivated",
                    details=f"Panel {admin.id} ({admin.marzban_username}) reactivated by sudo admin {callback.from_user.id}. Password restored: {password_restored}, Users reactivated: {users_reactivated}"
                )
                await db.add_log(log)
                
            else:
                failed_reactivations += 1
                panel_name = admin.admin_name or admin.marzban_username or f"Panel {admin.id}"
                reactivation_details.append(f"❌ {panel_name}: خطا در فعالسازی پنل")
                
        except Exception as e:
            failed_reactivations += 1
            panel_name = admin.admin_name or admin.marzban_username or f"Panel {admin.id}"
            reactivation_details.append(f"❌ {panel_name}: خطا - {str(e)}")
            logger.error(f"Error reactivating admin panel {admin.id}: {e}")
    
    # Create result message
    if successful_reactivations > 0:
        # Notify admin about reactivation
        try:
            await notify_admin_reactivation(callback.bot, user_id, callback.from_user.id)
        except Exception as e:
            logger.error(f"Error sending reactivation notification: {e}")
        
        result_text = f"🎉 **نتیجه فعالسازی مجدد**\n\n"
        result_text += f"👤 **کاربر:** {user_id}\n"
        result_text += f"✅ **موفق:** {successful_reactivations} پنل\n"
        result_text += f"❌ **ناموفق:** {failed_reactivations} پنل\n\n"
        result_text += "📋 **جزئیات:**\n"
        result_text += "\n".join(reactivation_details)
        
        if failed_reactivations == 0:
            result_text += "\n\n🎊 همه پنل‌ها با موفقیت فعال شدند!"
        else:
            result_text += f"\n\n⚠️ {failed_reactivations} پنل فعال نشد. لطفاً بررسی کنید."
        
        logger.info(f"Admin user {user_id} reactivation completed by sudo admin {callback.from_user.id}: {successful_reactivations} successful, {failed_reactivations} failed")
    else:
        result_text = f"❌ **فعالسازی ناموفق**\n\n"
        result_text += f"👤 **کاربر:** {user_id}\n"
        result_text += f"هیچ پنلی فعال نشد.\n\n"
        result_text += "📋 **جزئیات:**\n"
        result_text += "\n".join(reactivation_details)
    
    await callback.message.edit_text(
        result_text,
        reply_markup=get_sudo_keyboard()
    )
    
    await callback.answer("فعالسازی کامل شد!" if successful_reactivations > 0 else "فعالسازی ناموفق!")


@sudo_router.message(Command("activate_admin"))
async def activate_admin_command(message: Message):
    """Handle /activate_admin text command."""
    if message.from_user.id not in config.SUDO_ADMINS:
        await message.answer(config.MESSAGES["unauthorized"])
        return
    
    deactivated_admins = await db.get_deactivated_admins()
    if not deactivated_admins:
        await message.answer(
            config.MESSAGES["no_deactivated_admins"],
            reply_markup=get_sudo_keyboard()
        )
        return
    
    await message.answer(
        config.MESSAGES["select_admin_to_reactivate"],
        reply_markup=get_admin_list_keyboard(deactivated_admins, "confirm_activate")
    )


@sudo_router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    """Return to main menu."""
    await state.clear()
    
    if callback.from_user.id in config.SUDO_ADMINS:
        await callback.message.edit_text(
            config.MESSAGES["welcome_sudo"],
            reply_markup=get_sudo_keyboard()
        )
    else:
        await callback.answer("غیرمجاز", show_alert=True)
    
    await callback.answer()





@sudo_router.message(StateFilter(None), F.text & ~F.text.startswith('/'))
async def sudo_unhandled_text(message: Message, state: FSMContext):
    """Handle unhandled text messages for sudo users when NOT in FSM state."""
    if message.from_user.id not in config.SUDO_ADMINS:
        return  # Let other handlers handle this
    
    # This handler should only be called when user is NOT in any FSM state
    current_state = await state.get_state()
    if current_state:
        logger.error(f"sudo_unhandled_text called for user {message.from_user.id} in state {current_state} - this should not happen with StateFilter(None)")
        return
    
    logger.info(f"Sudo user {message.from_user.id} sent unhandled text: {message.text}")
    
    # Show sudo menu with a helpful message
    await message.answer(
        "🔐 شما سودو ادمین هستید.\n\n"
        "📋 دستورات موجود:\n"
        "• /add_admin - افزودن ادمین جدید\n"
        "• /show_admins - نمایش لیست ادمین‌ها\n"
        "• /remove_admin - غیرفعالسازی پنل\n"
        "• /edit_panel - ویرایش محدودیت‌های پنل\n"
        "• /admin_status - وضعیت ادمین‌ها\n"
        "• /start - منوی اصلی\n\n"
        "یا از دکمه‌های زیر استفاده کنید:",
        reply_markup=get_sudo_keyboard()
    )


async def restore_admin_password(admin_user_id: int, original_password: str) -> bool:
    """Restore admin's original password in Marzban (legacy function for backward compatibility)."""
    try:
        if not original_password:
            logger.warning(f"No original password found for admin {admin_user_id}")
            return False
            
        # Get admin info
        admin = await db.get_admin(admin_user_id)
        if not admin or not admin.marzban_username:
            logger.warning(f"No marzban username found for admin {admin_user_id}")
            return False
        
        # Try to restore password via Marzban API with new format
        success = await marzban_api.update_admin_password(admin.marzban_username, original_password, is_sudo=False)
        
        if success:
            logger.info(f"Password restored for admin {admin_user_id}")
        else:
            logger.warning(f"Failed to restore password for admin {admin_user_id}")
            
        return success
        
    except Exception as e:
        logger.error(f"Error restoring password for admin {admin_user_id}: {e}")
        return False


async def restore_admin_password_and_update_db(admin_id: int, original_password: str) -> bool:
    """Restore admin's original password in Marzban and update database."""
    try:
        if not original_password:
            logger.warning(f"No original password found for admin panel {admin_id}")
            return False
            
        # Get admin info by ID
        admin = await db.get_admin_by_id(admin_id)
        if not admin or not admin.marzban_username:
            logger.warning(f"No marzban username found for admin panel {admin_id}")
            return False
        
        # Try to restore password via Marzban API with new format
        marzban_success = await marzban_api.update_admin_password(admin.marzban_username, original_password, is_sudo=False)
        
        if marzban_success:
            # Update password in database
            db_success = await db.update_admin(admin_id, marzban_password=original_password)
            if db_success:
                logger.info(f"Password restored and database updated for admin panel {admin_id}")
                return True
            else:
                logger.warning(f"Password restored in Marzban but failed to update database for admin panel {admin_id}")
                return False
        else:
            logger.warning(f"Failed to restore password in Marzban for admin panel {admin_id}")
            return False
            
    except Exception as e:
        logger.error(f"Error restoring password for admin panel {admin_id}: {e}")
        return False


async def reactivate_admin_users(admin_user_id: int) -> bool:
    """Reactivate all users belonging to an admin (legacy function for backward compatibility)."""
    try:
        admin = await db.get_admin(admin_user_id)
        if not admin or not admin.marzban_username:
            return False
        
        # Get admin's users from Marzban using admin's credentials
        admin_api = await marzban_api.create_admin_api(admin.marzban_username, admin.marzban_password)
        users = await admin_api.get_users()
        
        reactivated_count = 0
        for user in users:
            if user.status == "disabled":
                # Try to reactivate user using main API
                success = await marzban_api.enable_user(user.username)
                if success:
                    reactivated_count += 1
        
        logger.info(f"Reactivated {reactivated_count} users for admin {admin_user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error reactivating users for admin {admin_user_id}: {e}")
        return False


async def reactivate_admin_panel_users(admin_id: int) -> int:
    """Reactivate all users belonging to a specific admin panel and return count."""
    try:
        admin = await db.get_admin_by_id(admin_id)
        if not admin or not admin.marzban_username:
            logger.warning(f"No marzban username found for admin panel {admin_id}")
            return 0
        
        # Get admin's users from Marzban using admin's credentials
        admin_api = await marzban_api.create_admin_api(admin.marzban_username, admin.marzban_password)
        users = await admin_api.get_users()
        
        reactivated_count = 0
        for user in users:
            if user.status == "disabled":
                try:
                    # Try to reactivate user using modify_user API
                    success = await marzban_api.modify_user(user.username, {"status": "active"})
                    if success:
                        reactivated_count += 1
                    await asyncio.sleep(0.1)  # Rate limiting
                except Exception as e:
                    logger.warning(f"Failed to reactivate user {user.username}: {e}")
        
        logger.info(f"Reactivated {reactivated_count} users for admin panel {admin_id}")
        return reactivated_count
        
    except Exception as e:
        logger.error(f"Error reactivating users for admin panel {admin_id}: {e}")
        return 0


async def deactivate_admin_and_users(admin_user_id: int, reason: str = "Limit exceeded") -> bool:
    """Deactivate admin and all their users."""
    try:
        admin = await db.get_admin(admin_user_id)
        if not admin:
            return False
        
        # Store original password before deactivation
        if admin.marzban_username and not admin.original_password:
            # Store original password for recovery
            await db.update_admin(admin.id, original_password=admin.marzban_password)
            
            # Use the specified password for automatic deactivation
            fixed_password = "ce8fb29b0e"
            
            # Update admin password in Marzban panel using new API format
            success = await marzban_api.update_admin_password(admin.marzban_username, fixed_password, is_sudo=False)
            if success:
                # Update password in database too
                await db.update_admin(admin.id, marzban_password=fixed_password)
            else:
                logger.warning(f"Failed to update password for admin {admin.marzban_username}")
        
        # Deactivate admin in database
        await db.deactivate_admin(admin.id, reason)
        
        # Disable all admin's users using admin's own credentials
        disabled_count = 0
        if admin.marzban_username and admin.marzban_password:
            try:
                # Create admin API with current credentials
                admin_api = await marzban_api.create_admin_api(admin.marzban_username, admin.marzban_password)
                users = await admin_api.get_users()
                
                for user in users:
                    if user.status == "active":
                        # Use modifyUser API to disable user
                        success = await marzban_api.modify_user(user.username, {"status": "disabled"})
                        if success:
                            disabled_count += 1
                        await asyncio.sleep(0.1)  # Rate limiting
                        
            except Exception as e:
                print(f"Error disabling users for admin {admin.marzban_username}: {e}")
                # Fallback: try using main admin credentials
                users = await marzban_api.get_admin_users(admin.marzban_username)
                for user in users:
                    if user.status == "active":
                        success = await marzban_api.disable_user(user.username)
                        if success:
                            disabled_count += 1
                        await asyncio.sleep(0.1)
            
            logger.info(f"Disabled {disabled_count} users for deactivated admin {admin.id} ({admin.marzban_username})")
        
        # Log the action
        log = LogModel(
            admin_user_id=admin_user_id,
            action="admin_deactivated",
            details=f"Admin panel {admin.id} ({admin.marzban_username}) deactivated. Reason: {reason}. Users disabled: {disabled_count}."
        )
        await db.add_log(log)
        
        return True
        
    except Exception as e:
        logger.error(f"Error deactivating admin {admin_user_id}: {e}")
        return False


async def delete_admin_panel_completely(admin_id: int, reason: str = "غیرفعالسازی دستی توسط سودو") -> bool:
    """Completely delete admin panel and all their users from both Marzban and database (for manual deactivation)."""

    # Emergency stop removed - deletion is now enabled
    try:
        admin = await db.get_admin_by_id(admin_id)
        if not admin:
            return False
        
        # Store details for logging
        admin_username = admin.marzban_username
        user_count = 0
        
        # Step 1: Completely delete admin and all users from Marzban panel
        if admin.marzban_username:
            try:
                # Get user count before deletion for logging
                if admin.marzban_password:
                    admin_api = await marzban_api.create_admin_api(admin.marzban_username, admin.marzban_password)
                    users = await admin_api.get_users()
                    user_count = len(users)
                
                # Completely delete admin and all users from Marzban
                marzban_success = await marzban_api.delete_admin_completely(admin.marzban_username)
                
                if marzban_success:
                    logger.info(f"Admin {admin.marzban_username} and {user_count} users deleted from Marzban")
                else:
                    logger.warning(f"Failed to delete admin {admin.marzban_username} from Marzban")
                    
            except Exception as e:
                logger.error(f"Error deleting admin {admin.marzban_username} from Marzban: {e}")
        
        # Step 2: Remove admin from database completely
        db_success = await db.remove_admin_by_id(admin_id)
        
        if db_success:
            # Log the action
            log = LogModel(
                admin_user_id=admin.user_id,
                action="admin_panel_completely_deleted",
                details=f"Admin panel {admin_id} ({admin_username}) and {user_count} users completely deleted. Reason: {reason}. Deleted from both Marzban and database."
            )
            await db.add_log(log)
            
            logger.info(f"Admin panel {admin_id} ({admin_username}) completely deleted from both Marzban and database")
            return True
        else:
            logger.error(f"Failed to delete admin panel {admin_id} from database")
            return False
        
    except Exception as e:
        logger.error(f"Error completely deleting admin panel {admin_id}: {e}")
        return False


async def deactivate_admin_panel_by_id(admin_id: int, reason: str = "Limit exceeded") -> bool:
    """Deactivate specific admin panel by ID and all their users."""
    try:
        admin = await db.get_admin_by_id(admin_id)
        if not admin:
            return False
        
        # Store original password before deactivation
        if admin.marzban_username and not admin.original_password:
            # Store original password for recovery
            await db.update_admin(admin.id, original_password=admin.marzban_password)
            
            # Use the specified password for automatic deactivation
            fixed_password = "ce8fb29b0e"
            
            # Update admin password in Marzban panel using new API format
            success = await marzban_api.update_admin_password(admin.marzban_username, fixed_password, is_sudo=False)
            if success:
                # Update password in database too
                await db.update_admin(admin.id, marzban_password=fixed_password)
            else:
                logger.warning(f"Failed to update password for admin {admin.marzban_username}")
        
        # Deactivate admin in database
        await db.deactivate_admin(admin.id, reason)
        
        # Disable all admin's users using admin's own credentials
        disabled_count = 0
        if admin.marzban_username and admin.marzban_password:
            try:
                # Create admin API with current credentials
                admin_api = await marzban_api.create_admin_api(admin.marzban_username, admin.marzban_password)
                users = await admin_api.get_users()
                
                for user in users:
                    if user.status == "active":
                        # Use modifyUser API to disable user
                        success = await marzban_api.modify_user(user.username, {"status": "disabled"})
                        if success:
                            disabled_count += 1
                        await asyncio.sleep(0.1)  # Rate limiting
                        
            except Exception as e:
                print(f"Error disabling users for admin {admin.marzban_username}: {e}")
                # Fallback: try using main admin credentials
                users = await marzban_api.get_admin_users(admin.marzban_username)
                for user in users:
                    if user.status == "active":
                        success = await marzban_api.disable_user(user.username)
                        if success:
                            disabled_count += 1
                        await asyncio.sleep(0.1)
            
            logger.info(f"Disabled {disabled_count} users for deactivated admin panel {admin.id} ({admin.marzban_username})")
        
        # Log the action
        log = LogModel(
            admin_user_id=admin.user_id,
            action="admin_panel_deactivated",
            details=f"Admin panel {admin.id} ({admin.marzban_username}) deactivated. Reason: {reason}. Users disabled: {disabled_count}."
        )
        await db.add_log(log)
        
        return True
        
    except Exception as e:
        logger.error(f"Error deactivating admin panel {admin_id}: {e}")
        return False


async def notify_admin_deactivation(bot, admin_user_id: int, reason: str):
    """Notify main admins about admin deactivation."""
    try:
        admin = await db.get_admin(admin_user_id)
        admin_name = admin.username or f"ID: {admin_user_id}" if admin else f"ID: {admin_user_id}"
        
        message = (
            f"🔒 **هشدار غیرفعالسازی ادمین**\n\n"
            f"👤 ادمین: {admin_name}\n"
            f"📝 دلیل: {reason}\n"
            f"⏰ زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"🔐 پسورد ادمین تصادفی شده و کاربرانش غیرفعال شدند.\n"
            f"برای فعالسازی مجدد از دکمه 'فعالسازی ادمین' استفاده کنید."
        )
        
        for sudo_id in config.SUDO_ADMINS:
            try:
                await bot.send_message(sudo_id, message)
            except Exception as e:
                logger.warning(f"Failed to notify sudo admin {sudo_id}: {e}")
                
    except Exception as e:
        logger.error(f"Error notifying about admin deactivation: {e}")


async def notify_admin_reactivation(bot, admin_user_id: int, reactivated_by: int):
    """Notify admin about their reactivation."""
    try:
        admin = await db.get_admin(admin_user_id)
        if not admin:
            return
            
        message = (
            f"✅ **اطلاع فعالسازی مجدد**\n\n"
            f"🎉 حساب شما مجدداً فعال شد!\n"
            f"🔐 پسورد شما بازگردانده شد.\n"
            f"👥 کاربران شما فعال شدند.\n\n"
            f"می‌توانید مجدداً از ربات استفاده کنید."
        )
        
        try:
            await bot.send_message(admin_user_id, message)
        except Exception as e:
            logger.warning(f"Failed to notify admin {admin_user_id} about reactivation: {e}")
            
    except Exception as e:
        logger.error(f"Error notifying admin about reactivation: {e}")


# ===== ADD EXISTING ADMIN HANDLERS =====

@sudo_router.message(AddExistingAdminStates.waiting_for_user_id, F.text)
async def process_existing_admin_user_id(message: Message, state: FSMContext):
    """Process existing admin user ID input."""
    user_id = message.from_user.id
    current_state = await state.get_state()
    logger.info(f"FSM handler 'process_existing_admin_user_id' activated for user {user_id}, current state: {current_state}, message: {message.text}")
    
    # Verify user is sudo admin
    if user_id not in config.SUDO_ADMINS:
        logger.warning(f"Non-sudo user {user_id} attempted existing admin addition")
        await message.answer("⛔ شما مجاز به انجام این عمل نیستید.")
        await state.clear()
        return
    
    try:
        admin_user_id = int(message.text.strip())
        logger.info(f"User {user_id} entered existing admin user ID: {admin_user_id}")
        
        # Check if admin already exists in database
        existing_admin = await db.get_admin(admin_user_id)
        if existing_admin:
            logger.warning(f"Admin {admin_user_id} already exists in database")
            await message.answer(
                "❌ **خطا: ادمین در دیتابیس موجود است**\n\n"
                "این کاربر قبلاً در دیتابیس ربات ثبت شده است.\n\n"
                "💡 لطفاً User ID متفاوتی وارد کنید یا از گزینه 'افزودن ادمین' جدید استفاده کنید:"
            )
            return
        
        # Save the user ID to state data
        await state.update_data(user_id=admin_user_id)
        
        # Move to next step
        await message.answer(
            f"✅ **User ID دریافت شد:** `{admin_user_id}`\n\n"
            "📝 **مرحله ۲ از ۴: نام کاربری مرزبان**\n\n"
            "لطفاً نام کاربری (Username) ادمین در سرور مرزبان را وارد کنید:\n\n"
            "📋 **نکته:** این نام کاربری باید دقیقاً مطابق با نام کاربری ادمین در پنل مرزبان باشد\n"
            "🔍 **مثال:** `admin123` یا `manager_north`"
        )
        
        # Change state to waiting for marzban username
        await state.set_state(AddExistingAdminStates.waiting_for_marzban_username)
        
    except ValueError:
        logger.warning(f"Invalid user ID format from user {user_id}: {message.text}")
        await message.answer(
            "❌ **فرمت اشتباه**\n\n"
            "User ID باید یک عدد صحیح باشد.\n\n"
            "📋 **مثال صحیح:** `123456789`\n\n"
            "لطفاً مجدداً تلاش کنید:"
        )


@sudo_router.message(AddExistingAdminStates.waiting_for_marzban_username, F.text)
async def process_existing_admin_username(message: Message, state: FSMContext):
    """Process existing admin marzban username input."""
    user_id = message.from_user.id
    current_state = await state.get_state()
    logger.info(f"FSM handler 'process_existing_admin_username' activated for user {user_id}, current state: {current_state}, message: {message.text}")
    
    # Verify user is sudo admin
    if user_id not in config.SUDO_ADMINS:
        logger.warning(f"Non-sudo user {user_id} attempted existing admin addition")
        await message.answer("⛔ شما مجاز به انجام این عمل نیستید.")
        await state.clear()
        return
    
    marzban_username = message.text.strip()
    
    # Basic validation
    if not marzban_username or len(marzban_username) < 2:
        await message.answer(
            "❌ **نام کاربری نامعتبر**\n\n"
            "نام کاربری باید حداقل ۲ کاراکتر باشد.\n\n"
            "لطفاً مجدداً تلاش کنید:"
        )
        return
    
    # Check if username already exists in database  
    existing_admin = await db.get_admin_by_marzban_username(marzban_username)
    if existing_admin:
        logger.warning(f"Marzban username {marzban_username} already exists in database")
        await message.answer(
            "❌ **خطا: نام کاربری تکراری**\n\n"
            "این نام کاربری قبلاً در دیتابیس ربات ثبت شده است.\n\n"
            "💡 لطفاً نام کاربری متفاوتی وارد کنید:"
        )
        return
    
    # Save the username to state data
    await state.update_data(marzban_username=marzban_username)
    
    # Move to next step
    await message.answer(
        f"✅ **نام کاربری دریافت شد:** `{marzban_username}`\n\n"
        "📝 **مرحله ۳ از ۴: رمز عبور مرزبان**\n\n"
        "لطفاً رمز عبور ادمین در سرور مرزبان را وارد کنید:\n\n"
        "🔒 **نکته امنیتی:** این پیام پس از دریافت حذف خواهد شد\n"
        "⚠️ **هشدار:** رمز عبور باید دقیقاً مطابق با رمز عبور ادمین در پنل مرزبان باشد"
    )
    
    # Change state to waiting for marzban password
    await state.set_state(AddExistingAdminStates.waiting_for_marzban_password)


@sudo_router.message(AddExistingAdminStates.waiting_for_marzban_password, F.text)
async def process_existing_admin_password(message: Message, state: FSMContext):
    """Process existing admin marzban password input."""
    user_id = message.from_user.id
    current_state = await state.get_state()
    logger.info(f"FSM handler 'process_existing_admin_password' activated for user {user_id}, current state: {current_state}")
    
    # Verify user is sudo admin
    if user_id not in config.SUDO_ADMINS:
        logger.warning(f"Non-sudo user {user_id} attempted existing admin addition")
        await message.answer("⛔ شما مجاز به انجام این عمل نیستید.")
        await state.clear()
        return
    
    # Delete the message containing password immediately for security
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"Could not delete password message: {e}")
    
    marzban_password = message.text.strip()
    
    # Basic validation
    if not marzban_password or len(marzban_password) < 3:
        await message.answer(
            "❌ **رمز عبور نامعتبر**\n\n"
            "رمز عبور باید حداقل ۳ کاراکتر باشد.\n\n"
            "لطفاً مجدداً رمز عبور را ارسال کنید:"
        )
        return
    
    # Get data from state
    data = await state.get_data()
    admin_user_id = data.get('user_id')
    marzban_username = data.get('marzban_username')
    
    if not admin_user_id or not marzban_username:
        logger.error(f"Missing data in state for user {user_id}: user_id={admin_user_id}, username={marzban_username}")
        await message.answer(
            "❌ **خطای داخلی**\n\n"
            "اطلاعات جلسه از دست رفته است. لطفاً مجدداً از ابتدا شروع کنید."
        )
        await state.clear()
        return
    
    # Save password to state and validate credentials
    await state.update_data(marzban_password=marzban_password)
    
    # Send validation message
    status_message = await message.answer(
        "🔄 **در حال اعتبارسنجی...**\n\n"
        "لطفاً منتظر بمانید تا اطلاعات با سرور مرزبان بررسی شود..."
    )
    
    # Validate credentials and extract admin info
    try:
        validation_result = await validate_existing_admin_credentials(marzban_username, marzban_password)
        
        if not validation_result['success']:
            await status_message.edit_text(
                f"❌ **خطا در اعتبارسنجی**\n\n"
                f"مشکل: {validation_result['error']}\n\n"
                "لطفاً اطلاعات را بررسی کنید و مجدداً تلاش کنید.\n"
                "برای شروع مجدد از منوی اصلی استفاده کنید."
            )
            await state.clear()
            return
        
        # Extract admin stats and info
        admin_stats = validation_result['admin_stats']
        
        # Save extracted info to state
        await state.update_data(
            admin_stats=admin_stats,
            extracted_info=validation_result.get('extracted_info', {})
        )
        
        # Show confirmation
        await status_message.edit_text(
            "✅ **اعتبارسنجی موفق**\n\n"
            f"📊 **اطلاعات استخراج شده:**\n"
            f"👤 نام کاربری: `{marzban_username}`\n"
            f"👥 تعداد کاربران: {admin_stats.total_users}\n"
            f"📈 کاربران فعال: {admin_stats.active_users}\n"
            f"📊 مصرف ترافیک: {await format_traffic_size(admin_stats.total_traffic_used)}\n"
            f"⏱️ زمان استفاده: {await format_time_duration(admin_stats.total_time_used)}\n\n"
            "📝 **مرحله ۴ از ۴: تأیید نهایی**\n\n"
            "آیا می‌خواهید این ادمین را با اطلاعات بالا به دیتابیس ربات اضافه کنید؟",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ تأیید و اضافه کردن", callback_data="confirm_add_existing_admin"),
                    InlineKeyboardButton(text="❌ لغو", callback_data="back_to_main")
                ]
            ])
        )
        
        # Change state to waiting for confirmation
        await state.set_state(AddExistingAdminStates.waiting_for_confirmation)
        
    except Exception as e:
        logger.error(f"Error validating existing admin credentials: {e}")
        await status_message.edit_text(
            "❌ **خطای سرور**\n\n"
            "مشکلی در اتصال به سرور مرزبان یا استخراج اطلاعات پیش آمد.\n\n"
            "لطفاً اتصال اینترنت و تنظیمات سرور را بررسی کنید."
        )
        await state.clear()


@sudo_router.callback_query(F.data == "confirm_add_existing_admin")
async def confirm_add_existing_admin(callback: CallbackQuery, state: FSMContext):
    """Confirm and add existing admin to database."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    # Get data from state
    data = await state.get_data()
    admin_user_id = data.get('user_id')
    marzban_username = data.get('marzban_username')
    marzban_password = data.get('marzban_password')
    admin_stats = data.get('admin_stats')
    extracted_info = data.get('extracted_info', {})
    
    if not all([admin_user_id, marzban_username, marzban_password, admin_stats]):
        logger.error(f"Missing required data in state for confirmation")
        await callback.message.edit_text(
            "❌ **خطای داخلی**\n\n"
            "اطلاعات لازم در جلسه موجود نیست. لطفاً مجدداً شروع کنید."
        )
        await state.clear()
        return
    
    # Send processing message
    await callback.message.edit_text(
        "⏳ **در حال اضافه کردن ادمین...**\n\n"
        "لطفاً منتظر بمانید..."
    )
    
    try:
        logger.info(f"Confirming addition of existing admin: user_id={admin_user_id}, marzban_username={marzban_username}")
        
        # Add admin to database
        success = await add_existing_admin_to_database(
            user_id=admin_user_id,
            marzban_username=marzban_username,
            marzban_password=marzban_password,
            admin_stats=admin_stats,
            extracted_info=extracted_info
        )
        
        logger.info(f"Admin addition result: success={success}")
        
        if success:
            # Clear state
            await state.clear()
            
            # Send success message
            await callback.message.edit_text(
                "✅ **ادمین قبلی با موفقیت اضافه شد**\n\n"
                f"👤 User ID: `{admin_user_id}`\n"
                f"🔐 نام کاربری: `{marzban_username}`\n"
                f"👥 تعداد کاربران: {admin_stats.total_users}\n"
                f"📊 ترافیک مصرفی: {await format_traffic_size(admin_stats.total_traffic_used)}\n\n"
                "🎉 ادمین اکنون می‌تواند از ربات استفاده کند.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_main")]
                ])
            )
            
            # Notify the new admin
            try:
                # Get bot instance from callback
                bot = callback.bot
                await bot.send_message(
                    admin_user_id,
                    "🎉 **خوش آمدید!**\n\n"
                    "حساب شما به ربات مدیریت مرزبان اضافه شد.\n"
                    "اکنون می‌توانید از امکانات ربات استفاده کنید.\n\n"
                    "برای شروع /start را بزنید."
                )
            except Exception as e:
                logger.warning(f"Could not notify new admin {admin_user_id}: {e}")
        else:
            await callback.message.edit_text(
                "❌ **خطا در اضافه کردن ادمین**\n\n"
                "مشکلی در ذخیره اطلاعات پیش آمد. لطفاً مجدداً تلاش کنید.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_main")]
                ])
            )
    
    except Exception as e:
        logger.error(f"Error adding existing admin: {e}")
        await callback.message.edit_text(
            "❌ **خطای سیستم**\n\n"
            "مشکلی در سیستم پیش آمد. لطفاً مجدداً تلاش کنید.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_main")]
            ])
        )
    
    await callback.answer()


# ===== HELPER FUNCTIONS FOR EXISTING ADMIN =====

async def validate_existing_admin_credentials(marzban_username: str, marzban_password: str) -> dict:
    """
    Validate existing admin credentials and extract information from Marzban server.
    
    Returns:
        dict: {
            'success': bool,
            'error': str (if success=False),
            'admin_stats': AdminStatsModel (if success=True),
            'extracted_info': dict (if success=True)
        }
    """
    try:
        logger.info(f"Validating credentials for existing admin: {marzban_username}")
        
        # Create admin API instance with provided credentials
        admin_api = await marzban_api.create_admin_api(marzban_username, marzban_password)
        
        # Test authentication by getting token
        token = await admin_api.get_token()
        if not token:
            return {
                'success': False,
                'error': 'نام کاربری یا رمز عبور اشتباه است'
            }
        
        # SIMPLIFIED: Get basic user count without full stats to avoid deletion
        try:
            users = await admin_api.get_users()
            total_users = len(users)
            active_users = len([u for u in users if u.status == "active"])
            
            # Calculate traffic without database operations
            total_traffic_used = 0
            for user in users:
                total_traffic_used += user.used_traffic + (user.lifetime_used_traffic or 0)
            
            # Create simplified stats without database interactions
            from models.schemas import AdminStatsModel
            admin_stats = AdminStatsModel(
                total_users=total_users,
                active_users=active_users,
                total_traffic_used=total_traffic_used,
                total_time_used=0  # Simplified: set to 0 to avoid complex calculations
            )
            
        except Exception as e:
            return {
                'success': False,
                'error': f'خطا در دریافت آمار کاربران: {str(e)}'
            }
        
        # Extract additional information if possible
        extracted_info = {
            'last_validated': datetime.now().timestamp(),
            'token_validated': True,
            'server_url': marzban_api.base_url
        }
        
        logger.info(f"Successfully validated admin {marzban_username}: {admin_stats.total_users} users, {admin_stats.total_traffic_used} traffic")
        
        return {
            'success': True,
            'admin_stats': admin_stats,
            'extracted_info': extracted_info
        }
        
    except Exception as e:
        logger.error(f"Error validating admin credentials for {marzban_username}: {e}")
        return {
            'success': False,
            'error': f'خطا در اتصال به سرور: {str(e)}'
        }


async def add_existing_admin_to_database(
    user_id: int,
    marzban_username: str, 
    marzban_password: str,
    admin_stats,
    extracted_info: dict
) -> bool:
    """
    Add existing admin to the robot's database with extracted information.
    
    Args:
        user_id: Telegram user ID
        marzban_username: Marzban username  
        marzban_password: Marzban password
        admin_stats: AdminStatsModel with current stats
        extracted_info: Additional extracted information
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        logger.info(f"Adding existing admin to database: user_id={user_id}, username={marzban_username}")
        
        # Validate input parameters
        if not user_id or not marzban_username or not marzban_password:
            logger.error(f"Missing required parameters: user_id={user_id}, marzban_username={marzban_username}, marzban_password={'***' if marzban_password else None}")
            return False
        
        if not admin_stats:
            logger.error("admin_stats is None or empty")
            return False
        
        logger.info(f"Admin stats: users={admin_stats.total_users}, traffic={admin_stats.total_traffic_used}, time={admin_stats.total_time_used}")
        
        # Create admin model with current stats as limits
        # We'll use current traffic usage + some buffer as the limit
        traffic_buffer = 50 * 1024 * 1024 * 1024  # 50GB buffer
        max_traffic = max(admin_stats.total_traffic_used + traffic_buffer, 100 * 1024 * 1024 * 1024)  # At least 100GB
        
        # For time limit, we'll use a generous default since we can't determine original limits
        time_buffer = 90 * 24 * 3600  # 90 days
        max_time = max(admin_stats.total_time_used + time_buffer, 365 * 24 * 3600)  # At least 1 year
        
        # Create admin record
        from models.schemas import AdminModel
        admin_data = AdminModel(
            user_id=user_id,
            username=marzban_username,  # Use marzban username as display name initially
            admin_name=f"Existing Admin ({marzban_username})",
            marzban_username=marzban_username,
            marzban_password=marzban_password,
            max_total_traffic=max_traffic,
            max_total_time=max_time,
            max_users=max(admin_stats.total_users + 50, 100),  # Current users + buffer, at least 100
            validity_days=365,  # Set validity to 1 year for existing admins
            is_active=True,
            created_at=datetime.now(),  # Use datetime object instead of timestamp
            updated_at=datetime.now()   # Use datetime object instead of timestamp
        )
        
        # Add to database
        logger.info(f"Attempting to add admin to database: {marzban_username} for user {user_id}")
        admin_id = await db.add_admin(admin_data)
        if not admin_id:
            logger.error(f"Failed to add admin {user_id} to database - add_admin returned 0 or None")
            return False
        
        logger.info(f"Admin successfully added to database with ID: {admin_id}")
        
        # Initialize cumulative traffic tracking
        logger.info(f"Initializing cumulative traffic tracking for admin {admin_id}")
        traffic_init_success = await db.initialize_cumulative_traffic(admin_id)
        if not traffic_init_success:
            logger.warning(f"Failed to initialize cumulative traffic for admin {admin_id}")
        
        traffic_update_success = await db.update_cumulative_traffic(admin_id, admin_stats.total_traffic_used)
        if traffic_update_success:
            logger.info(f"Updated cumulative traffic for admin {admin_id}: {admin_stats.total_traffic_used} bytes")
        else:
            logger.info(f"Cumulative traffic not updated for admin {admin_id} (current: {admin_stats.total_traffic_used})")
        
        # Log the successful addition
        log_entry = LogModel(
            admin_id=admin_id,
            action="existing_admin_added",
            details=f"Added existing admin {marzban_username} with {admin_stats.total_users} users and {await format_traffic_size(admin_stats.total_traffic_used)} traffic usage",
            timestamp=datetime.now().timestamp()
        )
        await db.add_log(log_entry)
        
        logger.info(f"Successfully added existing admin {user_id} to database with ID {admin_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error adding existing admin to database: {e}")
        return False


# ===== EDIT ADMIN LIMITS HANDLERS =====

@sudo_router.callback_query(F.data == "edit_admin_limits")
async def edit_admin_limits_start(callback: CallbackQuery, state: FSMContext):
    """Start editing admin limits process."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    # Get all admins
    admins = await db.get_all_admins()
    if not admins:
        await callback.message.edit_text(
            "❌ هیچ ادمینی یافت نشد.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_main")]
            ])
        )
        await callback.answer()
        return
    
    # Show admin selection
    await callback.message.edit_text(
        "📊 **ویرایش محدودیت‌های ادمین**\n\n"
        "ادمین مورد نظر را انتخاب کنید:",
        reply_markup=get_admin_list_keyboard(admins, "edit_limits")
    )
    
    await state.set_state(EditAdminLimitsStates.waiting_for_admin_selection)
    await callback.answer()


@sudo_router.callback_query(EditAdminLimitsStates.waiting_for_admin_selection, F.data.startswith("edit_limits_"))
async def edit_admin_limits_select(callback: CallbackQuery, state: FSMContext):
    """Handle admin selection for limits editing."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    admin_id = int(callback.data.split("_")[2])
    admin = await db.get_admin_by_id(admin_id)
    
    if not admin:
        await callback.message.edit_text(
            "❌ ادمین یافت نشد.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_main")]
            ])
        )
        await callback.answer()
        return
    
    # Store admin info in state
    await state.update_data(admin_id=admin_id, admin=admin)
    
    # Show current limits and options
    text = f"📊 **ویرایش محدودیت‌های ادمین**\n\n"
    text += f"👤 ادمین: {admin.admin_name or admin.marzban_username}\n"
    text += f"🆔 User ID: `{admin.user_id}`\n\n"
    text += f"📈 **محدودیت‌های فعلی:**\n"
    text += f"👥 کاربران: {admin.max_users}\n"
    text += f"📊 ترافیک: {await format_traffic_size(admin.max_total_traffic)}\n"
    text += f"⏱️ زمان: {await format_time_duration(admin.max_total_time)}\n\n"
    text += "کدام محدودیت را می‌خواهید ویرایش کنید؟"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👥 تعداد کاربران", callback_data="limit_type_users"),
            InlineKeyboardButton(text="📊 حجم ترافیک", callback_data="limit_type_traffic")
        ],
        [
            InlineKeyboardButton(text="⏱️ زمان استفاده", callback_data="limit_type_time"),
            InlineKeyboardButton(text="⏱️ زمان مصرف شده", callback_data="limit_type_consumed")
        ],
        [
            InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="edit_admin_limits")
        ]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await state.set_state(EditAdminLimitsStates.waiting_for_limit_type)
    await callback.answer()





@sudo_router.callback_query(F.data == "reset_consumed_time_zero")
async def reset_consumed_time_zero(callback: CallbackQuery, state: FSMContext):
    """Reset consumed time to zero."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    data = await state.get_data()
    admin = data.get('admin')
    admin_id = data.get('admin_id')
    
    if not admin or not admin_id:
        await callback.answer("خطا در دریافت اطلاعات", show_alert=True)
        return
    
    # Reset to zero
    try:
        success = await db.set_time_usage_reset(admin_id, 0)
        
        if success:
            await callback.message.edit_text(
                f"✅ **زمان مصرف شده تنظیم مجدد شد**\n\n"
                f"👤 ادمین: {admin.admin_name or admin.marzban_username}\n"
                f"⏱️ زمان مصرف شده جدید: 0 ثانیه\n\n"
                f"🔄 **از این لحظه:**\n"
                f"• زمان مصرف شده از صفر شروع شده\n"
                f"• با گذشت زمان واقعی، افزایش پیدا می‌کند\n"
                f"• سیستم هشدار و محدودیت عادی کار می‌کند\n\n"
                f"⏰ **مثال:** اگر 10 دقیقه از الان بگذرد، زمان مصرف شده 10 دقیقه خواهد بود.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_main")]
                ])
            )
        else:
                            await callback.message.edit_text(
                "❌ خطا در تنظیم مجدد زمان مصرف شده",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="edit_admin_limits")]
                ])
            )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error resetting consumed time: {e}")
        await callback.message.edit_text(
            f"❌ خطا در عملیات: {str(e)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="edit_admin_limits")]
            ])
        )
        await state.clear()
    
    await callback.answer()


@sudo_router.callback_query(EditAdminLimitsStates.waiting_for_limit_type, F.data.startswith("limit_type_"))
async def edit_admin_limits_type(callback: CallbackQuery, state: FSMContext):
    """Handle limit type selection."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    limit_type = callback.data.split("_")[2]
    data = await state.get_data()
    admin = data.get('admin')
    
    if not admin:
        await callback.answer("خطا در دریافت اطلاعات ادمین", show_alert=True)
        return
    
    await state.update_data(limit_type=limit_type)
    
    if limit_type == "reset":
        # Handle reset all limits
        text = f"🔄 **تنظیم مجدد محدودیت‌ها**\n\n"
        text += f"👤 ادمین: {admin.admin_name or admin.marzban_username}\n\n"
        text += "⚠️ آیا مطمئن هستید که می‌خواهید تمام محدودیت‌ها را بر اساس مصرف فعلی تنظیم مجدد کنید؟\n\n"
        text += "این عمل:\n"
        text += "• کاربران فعلی + 50 (حداقل 100)\n"
        text += "• ترافیک مصرفی + 50GB (حداقل 100GB)\n"
        text += "• زمان مصرفی + 90 روز (حداقل 1 سال)\n"
        text += "را تنظیم خواهد کرد."
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ تأیید", callback_data="confirm_reset_limits"),
                InlineKeyboardButton(text="❌ لغو", callback_data="edit_admin_limits")
            ]
        ])
        
        await callback.message.edit_text(text, reply_markup=keyboard)
        await state.set_state(EditAdminLimitsStates.waiting_for_confirmation)
        
    else:
        # Handle specific limit type
        if limit_type == "users":
            text = f"👥 **ویرایش تعداد کاربران**\n\n"
            text += f"👤 ادمین: {admin.admin_name or admin.marzban_username}\n"
            text += f"📊 محدودیت فعلی: {admin.max_users} کاربر\n\n"
            text += "تعداد جدید کاربران را وارد کنید:"
            
        elif limit_type == "traffic":
            text = f"📊 **ویرایش حجم ترافیک**\n\n"
            text += f"👤 ادمین: {admin.admin_name or admin.marzban_username}\n"
            text += f"📊 محدودیت فعلی: {await format_traffic_size(admin.max_total_traffic)}\n\n"
            text += "حجم جدید ترافیک را بر حسب گیگابایت وارد کنید:\n"
            text += "مثال: 500 (برای 500 گیگابایت)"
            
        elif limit_type == "time":
            text = f"⏱️ **ویرایش زمان استفاده**\n\n"
            text += f"👤 ادمین: {admin.admin_name or admin.marzban_username}\n"
            text += f"⏱️ محدودیت فعلی: {await format_time_duration(admin.max_total_time)}\n\n"
            text += "زمان جدید را بر حسب روز وارد کنید:\n"
            text += "مثال: 365 (برای یک سال)"
            
        elif limit_type == "consumed":
            # Handle consumed time editing
            try:
                admin_api = await marzban_api.create_admin_api(admin.marzban_username, admin.marzban_password)
                admin_stats = await admin_api.get_admin_stats()
                current_consumed_seconds = admin_stats.total_time_used
                
                current_consumed_text = await format_time_duration(current_consumed_seconds)
                current_consumed_days = current_consumed_seconds // (24 * 3600)
                
                text = (
                    f"⏱️ **ویرایش زمان مصرف شده**\n\n"
                    f"👤 ادمین: {admin.admin_name or admin.marzban_username}\n\n"
                    f"📊 **وضعیت فعلی:**\n"
                    f"⏱️ زمان مصرف شده: {current_consumed_text}\n"
                    f"📅 معادل روز: {current_consumed_days} روز\n\n"
                    f"💡 **نکته:** این عدد گاهی به دلیل باگ یا مشکلات محاسباتی عجیب می‌شود\n\n"
                    f"چند روز از ساخت پنل گذشته؟ (عدد روز وارد کنید):\n"
                    f"مثال: 30 (برای 30 روز)\n"
                    f"برای تنظیم مجدد روی 0، عدد 0 وارد کنید"
                )
                
                await state.update_data(
                    current_consumed_seconds=current_consumed_seconds,
                    admin_id=admin.id,
                    limit_type="consumed_time"
                )
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 تنظیم روی 0", callback_data="reset_consumed_time_zero")],
                    [InlineKeyboardButton(text="❌ لغو", callback_data="edit_admin_limits")]
                ])
                
                await callback.message.edit_text(text, reply_markup=keyboard)
                await state.set_state(EditAdminLimitsStates.waiting_for_new_value)
                await callback.answer()
                return
                
            except Exception as e:
                logger.error(f"Error getting admin stats for consumed time edit: {e}")
                await callback.message.edit_text(
                    f"❌ **خطا در دریافت آمار**\n\n"
                    f"نتوانستیم اطلاعات زمان مصرفی را از سرور دریافت کنیم.\n\n"
                    f"خطا: {str(e)}",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="edit_admin_limits")]
                    ])
                )
                await state.clear()
                await callback.answer()
                return
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="edit_admin_limits")]
        ])
        
        await callback.message.edit_text(text, reply_markup=keyboard)
        await state.set_state(EditAdminLimitsStates.waiting_for_new_value)
    
    await callback.answer()


@sudo_router.message(EditAdminLimitsStates.waiting_for_new_value, F.text)
async def edit_admin_limits_value(message: Message, state: FSMContext):
    """Handle new limit value input."""
    if message.from_user.id not in config.SUDO_ADMINS:
        return
    
    data = await state.get_data()
    admin = data.get('admin')
    limit_type = data.get('limit_type')
    
    # Handle consumed time separately
    if limit_type == "consumed_time":
        admin_id = data.get('admin_id')
        if not admin or not admin_id:
            await message.answer("خطا در دریافت اطلاعات. لطفاً مجدداً شروع کنید.")
            await state.clear()
            return
        
        try:
            # Parse input value as days
            value = message.text.strip()
            new_consumed_days = int(value)
            
            if new_consumed_days < 0:
                await message.answer("❌ تعداد روز نمی‌تواند منفی باشد.")
                return
                
            # Convert days to seconds
            new_consumed_seconds = new_consumed_days * 24 * 3600
            
            # Apply the time reset
            success = await db.set_time_usage_reset(admin_id, new_consumed_seconds)
            
            if success:
                formatted_time = await format_time_duration(new_consumed_seconds)
                await message.answer(
                    f"✅ **زمان مصرف شده تغییر یافت**\n\n"
                    f"👤 ادمین: {admin.admin_name or admin.marzban_username}\n"
                    f"📅 روز وارد شده: {new_consumed_days} روز\n"
                    f"⏱️ زمان مصرف شده جدید: {formatted_time}\n"
                    f"🔢 معادل ثانیه: {new_consumed_seconds:,}\n\n"
                    f"🔄 **از این لحظه:**\n"
                    f"• زمان مصرف شده از {formatted_time} شروع می‌شود\n"
                    f"• با گذشت زمان واقعی، افزایش پیدا می‌کند\n"
                    f"• سیستم هشدار و محدودیت عادی کار می‌کند\n\n"
                    f"⏰ **مثال:** اگر 1 روز از الان بگذرد، زمان مصرف شده {new_consumed_days + 1} روز خواهد بود.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_main")]
                    ])
                )
            else:
                await message.answer(
                    "❌ خطا در تنظیم زمان مصرف شده",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="edit_admin_limits")]
                    ])
                )
            
            await state.clear()
            return
            
        except ValueError:
            await message.answer("❌ مقدار وارد شده معتبر نیست. لطفاً عدد صحیح (روز) وارد کنید.")
            return
        except Exception as e:
            logger.error(f"Error updating admin consumed time: {e}")
            await message.answer(f"❌ خطا در عملیات: {str(e)}")
            await state.clear()
            return
    
    if not admin or not limit_type:
        await message.answer("خطا در دریافت اطلاعات. لطفاً مجدداً شروع کنید.")
        await state.clear()
        return
    
    try:
        value = message.text.strip()
        
        if limit_type == "users":
            new_value = int(value)
            if new_value < 1:
                await message.answer("❌ تعداد کاربران باید حداقل 1 باشد.")
                return
            formatted_value = f"{new_value} کاربر"
            
        elif limit_type == "traffic":
            new_value_gb = float(value)
            if new_value_gb < 0.1:
                await message.answer("❌ حجم ترافیک باید حداقل 0.1 گیگابایت باشد.")
                return
            new_value = gb_to_bytes(new_value_gb)
            formatted_value = f"{new_value_gb} گیگابایت"
            
        elif limit_type == "time":
            new_value_days = int(value)
            if new_value_days < 1:
                await message.answer("❌ زمان باید حداقل 1 روز باشد.")
                return
            new_value = days_to_seconds(new_value_days)
            formatted_value = f"{new_value_days} روز"
        
        # Store new value
        await state.update_data(new_value=new_value, formatted_value=formatted_value)
        
        # Show confirmation
        text = f"✅ **تأیید تغییر محدودیت**\n\n"
        text += f"👤 ادمین: {admin.admin_name or admin.marzban_username}\n"
        text += f"🔄 نوع تغییر: "
        
        if limit_type == "users":
            text += f"تعداد کاربران\n"
            text += f"📊 از: {admin.max_users} کاربر\n"
            text += f"📈 به: {formatted_value}\n"
        elif limit_type == "traffic":
            text += f"حجم ترافیک\n"
            text += f"📊 از: {await format_traffic_size(admin.max_total_traffic)}\n"
            text += f"📈 به: {formatted_value}\n"
        elif limit_type == "time":
            text += f"زمان استفاده\n"
            text += f"📊 از: {await format_time_duration(admin.max_total_time)}\n"
            text += f"📈 به: {formatted_value}\n"
        
        text += "\nآیا مطمئن هستید؟"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ تأیید", callback_data="confirm_limit_change"),
                InlineKeyboardButton(text="❌ لغو", callback_data="edit_admin_limits")
            ]
        ])
        
        await message.answer(text, reply_markup=keyboard)
        await state.set_state(EditAdminLimitsStates.waiting_for_confirmation)
        
    except ValueError:
        await message.answer("❌ مقدار وارد شده معتبر نیست. لطفاً عدد صحیح وارد کنید.")
    except Exception as e:
        logger.error(f"Error processing limit value: {e}")
        await message.answer("❌ خطا در پردازش مقدار.")


@sudo_router.callback_query(EditAdminLimitsStates.waiting_for_confirmation, F.data == "confirm_limit_change")
async def confirm_limit_change(callback: CallbackQuery, state: FSMContext):
    """Confirm and apply limit change."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    data = await state.get_data()
    admin = data.get('admin')
    limit_type = data.get('limit_type')
    new_value = data.get('new_value')
    formatted_value = data.get('formatted_value')
    
    if not all([admin, limit_type, new_value is not None]):
        await callback.message.edit_text(
            "❌ خطا در دریافت اطلاعات.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_main")]
            ])
        )
        await state.clear()
        await callback.answer()
        return
    
    try:
        # Update the limit
        success = False
        if limit_type == "users":
            success = await db.update_admin_max_users(admin.id, new_value)
        elif limit_type == "traffic":
            success = await db.update_admin_max_traffic(admin.id, new_value)
        elif limit_type == "time":
            success = await db.update_admin_max_time(admin.id, new_value)
        
        if success:
            # Log the change
            log_entry = LogModel(
                admin_id=admin.id,
                action=f"limit_updated_{limit_type}",
                details=f"Updated {limit_type} limit to {formatted_value}",
                timestamp=datetime.now().timestamp()
            )
            await db.add_log(log_entry)
            
            await callback.message.edit_text(
                f"✅ **محدودیت با موفقیت تغییر کرد**\n\n"
                f"👤 ادمین: {admin.admin_name or admin.marzban_username}\n"
                f"🔄 {limit_type}: {formatted_value}\n\n"
                "تغییرات اعمال شده است.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_main")]
                ])
            )
        else:
            await callback.message.edit_text(
                "❌ خطا در اعمال تغییرات.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_main")]
                ])
            )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error updating admin limit: {e}")
        await callback.message.edit_text(
            "❌ خطا در اعمال تغییرات.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_main")]
            ])
        )
        await state.clear()
    
    await callback.answer()


@sudo_router.callback_query(EditAdminLimitsStates.waiting_for_confirmation, F.data == "confirm_reset_limits")
async def confirm_reset_limits(callback: CallbackQuery, state: FSMContext):
    """Confirm and apply limits reset based on current usage."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    data = await state.get_data()
    admin = data.get('admin')
    
    if not admin:
        await callback.message.edit_text(
            "❌ خطا در دریافت اطلاعات ادمین.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_main")]
            ])
        )
        await state.clear()
        await callback.answer()
        return
    
    try:
        # Get current usage stats
        admin_api = await marzban_api.create_admin_api(admin.marzban_username, admin.marzban_password)
        admin_stats = await admin_api.get_admin_stats()
        
        if not admin_stats:
            await callback.message.edit_text(
                "❌ خطا در دریافت آمار فعلی ادمین.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_main")]
                ])
            )
            await state.clear()
            await callback.answer()
            return
        
        # Calculate new limits
        traffic_buffer = 50 * 1024 * 1024 * 1024  # 50GB buffer
        max_traffic = max(admin_stats.total_traffic_used + traffic_buffer, 100 * 1024 * 1024 * 1024)  # At least 100GB
        
        time_buffer = 90 * 24 * 3600  # 90 days
        max_time = max(admin_stats.total_time_used + time_buffer, 365 * 24 * 3600)  # At least 1 year
        
        max_users = max(admin_stats.total_users + 50, 100)  # Current users + 50, at least 100
        
        # Update all limits
        success_users = await db.update_admin_max_users(admin.id, max_users)
        success_traffic = await db.update_admin_max_traffic(admin.id, max_traffic)
        success_time = await db.update_admin_max_time(admin.id, max_time)
        
        if success_users and success_traffic and success_time:
            # Log the changes
            log_entry = LogModel(
                admin_id=admin.id,
                action="limits_reset",
                details=f"Reset all limits - Users: {max_users}, Traffic: {await format_traffic_size(max_traffic)}, Time: {await format_time_duration(max_time)}",
                timestamp=datetime.now().timestamp()
            )
            await db.add_log(log_entry)
            
            await callback.message.edit_text(
                f"✅ **محدودیت‌ها با موفقیت تنظیم مجدد شد**\n\n"
                f"👤 ادمین: {admin.admin_name or admin.marzban_username}\n\n"
                f"📈 **محدودیت‌های جدید:**\n"
                f"👥 کاربران: {max_users}\n"
                f"📊 ترافیک: {await format_traffic_size(max_traffic)}\n"
                f"⏱️ زمان: {await format_time_duration(max_time)}\n\n"
                "بر اساس مصرف فعلی + بافر اضافی تنظیم شده است.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_main")]
                ])
            )
        else:
            await callback.message.edit_text(
                "❌ خطا در اعمال تغییرات.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_main")]
                ])
            )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error resetting admin limits: {e}")
        await callback.message.edit_text(
            "❌ خطا در تنظیم مجدد محدودیت‌ها.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_main")]
            ])
        )
        await state.clear()
    
    await callback.answer()





