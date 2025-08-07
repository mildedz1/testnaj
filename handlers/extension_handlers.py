#!/usr/bin/env python3
"""
Extension request handlers for admin limit extensions
"""
import json
import asyncio
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import config
from database import db
from models.schemas import AdminModel
import logging

logger = logging.getLogger(__name__)

# FSM States for extension requests
class ExtensionRequestStates(StatesGroup):
    waiting_for_panel_selection = State()
    waiting_for_extension_type = State()
    waiting_for_extension_amount = State()
    waiting_for_payment_screenshot = State()

extension_router = Router()

# ============= EXTENSION REQUEST SYSTEM =============

@extension_router.callback_query(F.data == "request_extension")
async def start_extension_request(callback: CallbackQuery, state: FSMContext):
    """Start extension request process for admin."""
    user_id = callback.from_user.id
    
    # Get user's admin panels
    admins = await db.get_admins_for_user(user_id)
    active_admins = [admin for admin in admins if admin.is_active]
    
    if not active_admins:
        await callback.message.edit_text(
            "❌ **هیچ پنل فعالی ندارید**\n\n"
            "برای درخواست تمدید، ابتدا باید پنل فعال داشته باشید.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="start")]
            ])
        )
        await callback.answer()
        return
    
    text = "📈 **درخواست تمدید/افزایش محدودیت**\n\n"
    text += "پنل مورد نظر را انتخاب کنید:\n\n"
    
    buttons = []
    for admin in active_admins:
        panel_name = admin.admin_name or admin.marzban_username
        text += f"🎛️ **{panel_name}**\n"
        text += f"   👥 کاربران: {'نامحدود' if admin.max_users == -1 else admin.max_users}\n"
        text += f"   📊 ترافیک: {'نامحدود' if admin.max_total_traffic == -1 else f'{admin.max_total_traffic // (1024**3)}GB'}\n"
        text += f"   ⏱️ زمان: {'نامحدود' if admin.max_total_time == -1 else f'{admin.max_total_time // (24*3600)} روز'}\n\n"
        
        buttons.append([
            InlineKeyboardButton(
                text=f"📈 تمدید {panel_name}",
                callback_data=f"select_panel_ext_{admin.id}"
            )
        ])
    
    buttons.append([InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="start")])
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

@extension_router.callback_query(F.data.startswith("select_panel_ext_"))
async def select_panel_for_extension(callback: CallbackQuery, state: FSMContext):
    """Handle panel selection for extension."""
    admin_id = int(callback.data.split("_")[3])
    
    # Get admin details
    admin = await db.get_admin_by_id(admin_id)
    if not admin or admin.user_id != callback.from_user.id:
        await callback.answer("پنل یافت نشد یا متعلق به شما نیست.", show_alert=True)
        return
    
    await state.update_data(selected_admin_id=admin_id, selected_admin=admin)
    
    panel_name = admin.admin_name or admin.marzban_username
    
    # Check current limits to determine pricing
    has_unlimited_users = admin.max_users == -1
    has_unlimited_time = admin.max_total_time == -1
    is_volume_panel = has_unlimited_users and has_unlimited_time
    
    text = f"📈 **درخواست تمدید پنل**\n\n"
    text += f"🎛️ **پنل:** {panel_name}\n\n"
    text += f"📊 **وضعیت فعلی:**\n"
    text += f"👥 کاربران: {'نامحدود' if admin.max_users == -1 else admin.max_users}\n"
    text += f"📊 ترافیک: {'نامحدود' if admin.max_total_traffic == -1 else f'{admin.max_total_traffic // (1024**3)}GB'}\n"
    text += f"⏱️ زمان: {'نامحدود' if admin.max_total_time == -1 else f'{admin.max_total_time // (24*3600)} روز'}\n\n"
    
    panel_type = "پنل های حجمی" if is_volume_panel else "پنل های عادی"
    text += f"🏷️ **نوع پنل:** {panel_type}\n\n"
    
    text += f"💰 **قیمت‌های تمدید:**\n"
    traffic_price = 1500 if is_volume_panel else 1000
    text += f"📊 ترافیک: {traffic_price:,} تومان/گیگابایت\n"
    text += f"⏱️ زمان: ۲۰۰,۰۰۰ تومان/۳۰ روز\n\n"
    text += f"چه نوع تمدیدی می‌خواهید؟"
    
    buttons = [
        [InlineKeyboardButton(text="📊 افزایش ترافیک", callback_data="ext_type_traffic")],
        [InlineKeyboardButton(text="⏱️ افزایش زمان", callback_data="ext_type_time")],
        [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="request_extension")]
    ]
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

@extension_router.callback_query(F.data.startswith("ext_type_"))
async def select_extension_type(callback: CallbackQuery, state: FSMContext):
    """Handle extension type selection."""
    extension_type = callback.data.split("_")[2]  # traffic or time
    
    data = await state.get_data()
    admin = data.get('selected_admin')
    
    if not admin:
        await callback.answer("خطا در دریافت اطلاعات پنل.", show_alert=True)
        return
    
    await state.update_data(extension_type=extension_type)
    
    # Check if panel has unlimited users and time for pricing
    has_unlimited_users = admin.max_users == -1
    has_unlimited_time = admin.max_total_time == -1
    is_volume_panel = has_unlimited_users and has_unlimited_time
    
    panel_type = "پنل حجمی" if is_volume_panel else "پنل عادی"
    
    if extension_type == "traffic":
        price_per_gb = 1500 if is_volume_panel else 1000
        text = f"📊 **افزایش ترافیک**\n\n"
        text += f"🏷️ **نوع پنل:** {panel_type}\n"
        text += f"💰 **قیمت:** {price_per_gb:,} تومان هر گیگابایت\n\n"
        text += f"چند گیگابایت ترافیک می‌خواهید اضافه کنید؟\n"
        text += f"مثال: 10 (برای ۱۰ گیگابایت)"
        
    else:  # time
        text = f"⏱️ **افزایش زمان**\n\n"
        text += f"🏷️ **نوع پنل:** {panel_type}\n"
        text += f"💰 **قیمت:** ۲۰۰,۰۰۰ تومان هر ۳۰ روز\n\n"
        text += f"چند روز زمان می‌خواهید اضافه کنید؟\n"
        text += f"مثال: 30 (برای ۳۰ روز)\n"
        text += f"مثال: 60 (برای ۶۰ روز)"
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data=f"select_panel_ext_{admin.id}")]
        ])
    )
    
    await state.set_state(ExtensionRequestStates.waiting_for_extension_amount)
    await callback.answer()

@extension_router.message(ExtensionRequestStates.waiting_for_extension_amount, F.text)
async def handle_extension_amount(message: Message, state: FSMContext):
    """Handle extension amount input."""
    data = await state.get_data()
    admin = data.get('selected_admin')
    extension_type = data.get('extension_type')
    
    if not admin or not extension_type:
        await message.answer("خطا در دریافت اطلاعات.")
        await state.clear()
        return
    
    try:
        amount = int(message.text.strip())
        if amount < 1:
            await message.answer("❌ مقدار باید حداقل ۱ باشد.")
            return
    except ValueError:
        await message.answer("❌ لطفاً عدد صحیح وارد کنید.")
        return
    
    # Calculate price
    has_unlimited_users = admin.max_users == -1
    has_unlimited_time = admin.max_total_time == -1
    is_volume_panel = has_unlimited_users and has_unlimited_time
    
    if extension_type == "traffic":
        price_per_unit = 1500 if is_volume_panel else 1000
        total_price = amount * price_per_unit
        unit_name = "گیگابایت"
    else:  # time
        price_per_30_days = 200000
        total_price = (amount / 30) * price_per_30_days
        total_price = int(total_price)
        unit_name = "روز"
    
    await state.update_data(
        extension_amount=amount,
        total_price=total_price
    )
    
    # Show confirmation and payment methods
    panel_name = admin.admin_name or admin.marzban_username
    
    text = f"✅ **تأیید درخواست تمدید**\n\n"
    text += f"🎛️ **پنل:** {panel_name}\n"
    text += f"📈 **نوع تمدید:** {'افزایش ترافیک' if extension_type == 'traffic' else 'افزایش زمان'}\n"
    text += f"📊 **مقدار:** {amount} {unit_name}\n"
    text += f"💰 **قیمت کل:** {total_price:,} تومان\n\n"
    
    # Get payment methods
    payment_methods = await db.get_payment_methods(active_only=True)
    
    if not payment_methods:
        await message.answer(
            "❌ **روش پرداختی موجود نیست**\n\n"
            "در حال حاضر هیچ روش پرداختی فعال نیست.\n"
            "لطفاً با پشتیبانی تماس بگیرید.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="request_extension")]
            ])
        )
        return
    
    # Group payment methods by type
    card_methods = []
    crypto_methods = []
    
    for method in payment_methods:
        method_name_lower = method['method_name'].lower()
        if any(crypto in method_name_lower for crypto in ['usdt', 'btc', 'eth', 'ترون', 'تتر', 'بیت', 'اتریوم', 'crypto', 'کریپتو']):
            crypto_methods.append(method)
        else:
            card_methods.append(method)
    
    text += "💳 **انتخاب روش پرداخت:**\n"
    text += "روش پرداخت مورد نظر خود را انتخاب کنید:\n\n"
    
    buttons = []
    
    # Show payment type options only (without details)
    if card_methods:
        buttons.append([
            InlineKeyboardButton(
                text="💳 پرداخت کارت به کارت",
                callback_data="ext_payment_card"
            )
        ])
    
    if crypto_methods:
        buttons.append([
            InlineKeyboardButton(
                text="🪙 پرداخت با ارز دیجیتال",
                callback_data="ext_payment_crypto"
            )
        ])
    
    buttons.append([InlineKeyboardButton(text="❌ لغو", callback_data="request_extension")])
    
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

@extension_router.callback_query(F.data.startswith("ext_payment_"))
async def select_extension_payment_type(callback: CallbackQuery, state: FSMContext):
    """Handle payment type selection for extension."""
    payment_type = callback.data.split("_")[2]  # card or crypto
    
    data = await state.get_data()
    admin = data.get('selected_admin')
    extension_type = data.get('extension_type')
    extension_amount = data.get('extension_amount')
    total_price = data.get('total_price')
    
    if not all([admin, extension_type, extension_amount, total_price]):
        await callback.answer("خطا در دریافت اطلاعات.", show_alert=True)
        return
    
    # Get appropriate payment methods
    payment_methods = await db.get_payment_methods(active_only=True)
    
    if payment_type == "card":
        methods = [m for m in payment_methods if not any(crypto in m['method_name'].lower() 
                  for crypto in ['usdt', 'btc', 'eth', 'ترون', 'تتر', 'بیت', 'اتریوم', 'crypto', 'کریپتو'])]
    else:  # crypto
        methods = [m for m in payment_methods if any(crypto in m['method_name'].lower() 
                  for crypto in ['usdt', 'btc', 'eth', 'ترون', 'تتر', 'بیت', 'اتریوم', 'crypto', 'کریپتو'])]
    
    if not methods:
        await callback.answer("روش پرداخت یافت نشد.", show_alert=True)
        return
    
    selected_method = methods[0]
    
    # Create extension request
    request_id = await db.create_extension_request(
        admin_id=admin.id,
        admin_user_id=callback.from_user.id,
        request_type=extension_type,
        requested_amount=extension_amount,
        total_price=total_price
    )
    
    if request_id == 0:
        await callback.answer("خطا در ثبت درخواست.", show_alert=True)
        return
    
    await state.update_data(
        request_id=request_id,
        payment_method_id=selected_method['id'],
        payment_method=selected_method
    )
    
    # Show payment instructions with detailed information
    panel_name = admin.admin_name or admin.marzban_username
    unit_name = "گیگابایت" if extension_type == "traffic" else "روز"
    
    if payment_type == "card":
        instructions = (
            f"💳 **اطلاعات پرداخت کارت به کارت:**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏦 **بانک:** {selected_method['bank_name']}\n"
            f"💳 **شماره کارت:** `{selected_method['card_number']}`\n"
            f"👤 **صاحب حساب:** {selected_method['card_holder_name']}\n"
            f"💰 **مبلغ قابل پرداخت:** {total_price:,} تومان\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━"
        )
    else:  # crypto
        instructions = (
            f"🪙 **اطلاعات پرداخت ارز دیجیتال:**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💎 **ارز:** {selected_method['method_name']}\n"
            f"📍 **آدرس کیف پول:** `{selected_method['card_number']}`\n"
            f"💰 **مبلغ:** {total_price:,} تومان معادل ارز\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━"
        )
    
    text = f"✅ **درخواست تمدید ثبت شد**\n\n"
    text += f"🆔 **شماره درخواست:** {request_id}\n"
    text += f"🎛️ **پنل:** {panel_name}\n"
    text += f"📈 **نوع:** {'افزایش ترافیک' if extension_type == 'traffic' else 'افزایش زمان'}\n"
    text += f"📊 **مقدار:** {extension_amount} {unit_name}\n\n"
    text += instructions
    text += f"\n\n📝 **مراحل پرداخت:**\n"
    text += f"1️⃣ مبلغ را پرداخت کنید\n"
    text += f"2️⃣ اسکرین‌شات رسید را در همین چت ارسال کنید\n"
    text += f"3️⃣ منتظر تأیید ادمین باشید"
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ لغو درخواست", callback_data=f"cancel_ext_req_{request_id}")],
            [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="request_extension")]
        ])
    )
    
    await state.set_state(ExtensionRequestStates.waiting_for_payment_screenshot)
    await callback.answer()

@extension_router.message(ExtensionRequestStates.waiting_for_payment_screenshot, F.photo)
async def handle_extension_payment_screenshot(message: Message, state: FSMContext):
    """Handle payment screenshot upload for extension request."""
    data = await state.get_data()
    request_id = data.get('request_id')
    payment_method_id = data.get('payment_method_id')
    admin = data.get('selected_admin')
    extension_type = data.get('extension_type')
    extension_amount = data.get('extension_amount')
    total_price = data.get('total_price')
    
    if not all([request_id, payment_method_id]):
        await message.answer("خطا در دریافت اطلاعات درخواست.")
        await state.clear()
        return
    
    # Get the largest photo
    photo = message.photo[-1]
    
    # Update request with payment screenshot
    success = await db.update_extension_request_payment(request_id, payment_method_id, photo.file_id)
    
    if not success:
        await message.answer("خطا در ثبت اطلاعات پرداخت.")
        return
    
    # Notify customer
    panel_name = admin.admin_name if admin else "پنل شما"
    unit_name = "گیگابایت" if extension_type == "traffic" else "روز"
    
    await message.answer(
        f"✅ **رسید پرداخت دریافت شد**\n\n"
        f"🆔 شماره درخواست: {request_id}\n"
        f"🎛️ پنل: {panel_name}\n"
        f"📈 نوع: {'افزایش ترافیک' if extension_type == 'traffic' else 'افزایش زمان'}\n"
        f"📊 مقدار: {extension_amount} {unit_name}\n"
        f"💰 مبلغ: {total_price:,} تومان\n\n"
        f"⏳ درخواست شما در انتظار تأیید ادمین است.\n"
        f"پس از تأیید، محدودیت‌های پنل افزایش خواهد یافت.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 بازگشت به منو", callback_data="start")]
        ])
    )
    
    # Notify admin about new extension request
    for admin_id in config.SUDO_ADMINS:
        try:
            await message.bot.send_photo(
                chat_id=admin_id,
                photo=photo.file_id,
                caption=f"📈 **درخواست تمدید جدید**\n\n"
                       f"🆔 شماره: {request_id}\n"
                       f"👤 کاربر: {message.from_user.first_name or 'ناشناس'} (@{message.from_user.username or 'ندارد'})\n"
                       f"🎛️ پنل: {panel_name}\n"
                       f"📈 نوع: {'افزایش ترافیک' if extension_type == 'traffic' else 'افزایش زمان'}\n"
                       f"📊 مقدار: {extension_amount} {unit_name}\n"
                       f"💰 مبلغ: {total_price:,} تومان\n\n"
                       f"📷 رسید پرداخت:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ تأیید", callback_data=f"approve_ext_req_{request_id}"),
                        InlineKeyboardButton(text="❌ رد", callback_data=f"reject_ext_req_{request_id}")
                    ],
                    [InlineKeyboardButton(text="📋 مدیریت درخواست‌ها", callback_data="manage_extension_requests")]
                ])
            )
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")
    
    logger.info(f"Extension request {request_id} submitted by user {message.from_user.id}")
    await state.clear()

# ============= ADMIN EXTENSION REQUEST MANAGEMENT =============

@extension_router.callback_query(F.data.startswith("approve_ext_req_"))
async def approve_extension_request(callback: CallbackQuery):
    """Approve an extension request and update admin limits."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("شما مجاز به این عمل نیستید.", show_alert=True)
        return
    
    request_id = int(callback.data.split("_")[3])
    
    # Get request details
    request_details = await db.get_extension_request_by_id(request_id)
    if not request_details:
        await callback.answer("درخواست یافت نشد.", show_alert=True)
        return
    
    if request_details['status'] != 'pending':
        await callback.answer("این درخواست قبلاً پردازش شده است.", show_alert=True)
        return
    
    # Approve the request
    success = await db.approve_extension_request(request_id)
    if not success:
        await callback.answer("خطا در تأیید درخواست.", show_alert=True)
        return
    
    # Update admin limits based on request type
    admin_id = request_details['admin_id']
    request_type = request_details['request_type']
    requested_amount = request_details['requested_amount']
    
    if request_type == 'traffic':
        # Convert GB to bytes
        additional_bytes = requested_amount * 1024 * 1024 * 1024
        current_limit = request_details['max_total_traffic']
        
        if current_limit == -1:  # Already unlimited
            new_limit = -1
        else:
            new_limit = current_limit + additional_bytes
        
        await db.update_admin_max_traffic(admin_id, new_limit)
        
    elif request_type == 'time':
        # Convert days to seconds
        additional_seconds = requested_amount * 24 * 3600
        current_limit = request_details['max_total_time']
        
        if current_limit == -1:  # Already unlimited
            new_limit = -1
        else:
            new_limit = current_limit + additional_seconds
        
        await db.update_admin_max_time(admin_id, new_limit)
    
    # Notify admin (sudoer) about approval
    try:
        await callback.message.edit_text(
            f"✅ **درخواست تأیید شد**\n\n"
            f"🆔 شماره درخواست: {request_id}\n"
            f"👤 کاربر: {request_details.get('admin_name', 'ناشناس')}\n"
            f"📈 نوع: {'افزایش ترافیک' if request_type == 'traffic' else 'افزایش زمان'}\n"
            f"📊 مقدار: {requested_amount} {'گیگابایت' if request_type == 'traffic' else 'روز'}\n"
            f"💰 مبلغ: {request_details['total_price']:,} تومان\n\n"
            f"محدودیت‌های کاربر به‌روزرسانی شد.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 مدیریت درخواست‌ها", callback_data="manage_extension_requests")]
            ])
        )
    except Exception as e:
        logger.error(f"Failed to edit approval message: {e}")
        await callback.message.answer(
            f"✅ درخواست {request_id} تأیید شد و محدودیت‌ها به‌روزرسانی شد."
        )
    
    # Notify customer about approval
    customer_user_id = request_details['admin_user_id']
    panel_name = request_details.get('admin_name') or request_details.get('marzban_username', 'پنل شما')
    unit_name = "گیگابایت" if request_type == "traffic" else "روز"
    
    try:
        await callback.bot.send_message(
            chat_id=customer_user_id,
            text=f"✅ **درخواست تمدید تأیید شد!**\n\n"
                 f"🆔 شماره درخواست: {request_id}\n"
                 f"🎛️ پنل: {panel_name}\n"
                 f"📈 نوع: {'افزایش ترافیک' if request_type == 'traffic' else 'افزایش زمان'}\n"
                 f"📊 مقدار: {requested_amount} {unit_name}\n"
                 f"💰 مبلغ: {request_details['total_price']:,} تومان\n\n"
                 f"🎉 محدودیت‌های پنل شما افزایش یافت.\n"
                 f"از خرید شما متشکریم!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 بازگشت به منو", callback_data="start")]
            ])
        )
    except Exception as e:
        logger.error(f"Failed to notify customer {customer_user_id}: {e}")
    
    logger.info(f"Extension request {request_id} approved by admin {callback.from_user.id}")
    await callback.answer("درخواست تأیید شد و کاربر مطلع گردید.")

@extension_router.callback_query(F.data.startswith("reject_ext_req_"))
async def reject_extension_request(callback: CallbackQuery):
    """Reject an extension request."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("شما مجاز به این عمل نیستید.", show_alert=True)
        return
    
    request_id = int(callback.data.split("_")[3])
    
    # Get request details
    request_details = await db.get_extension_request_by_id(request_id)
    if not request_details:
        await callback.answer("درخواست یافت نشد.", show_alert=True)
        return
    
    if request_details['status'] != 'pending':
        await callback.answer("این درخواست قبلاً پردازش شده است.", show_alert=True)
        return
    
    # Reject the request
    rejection_reason = "درخواست توسط ادمین رد شد."
    success = await db.reject_extension_request(request_id, rejection_reason)
    
    if not success:
        await callback.answer("خطا در رد درخواست.", show_alert=True)
        return
    
    # Notify admin (sudoer) about rejection
    try:
        await callback.message.edit_text(
            f"❌ **درخواست رد شد**\n\n"
            f"🆔 شماره درخواست: {request_id}\n"
            f"👤 کاربر: {request_details.get('admin_name', 'ناشناس')}\n"
            f"📈 نوع: {'افزایش ترافیک' if request_details['request_type'] == 'traffic' else 'افزایش زمان'}\n"
            f"📊 مقدار: {request_details['requested_amount']} {'گیگابایت' if request_details['request_type'] == 'traffic' else 'روز'}\n"
            f"💰 مبلغ: {request_details['total_price']:,} تومان\n\n"
            f"دلیل رد: {rejection_reason}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 مدیریت درخواست‌ها", callback_data="manage_extension_requests")]
            ])
        )
    except Exception as e:
        logger.error(f"Failed to edit rejection message: {e}")
        await callback.message.answer(
            f"❌ درخواست {request_id} رد شد."
        )
    
    # Notify customer about rejection
    customer_user_id = request_details['admin_user_id']
    panel_name = request_details.get('admin_name') or request_details.get('marzban_username', 'پنل شما')
    unit_name = "گیگابایت" if request_details['request_type'] == "traffic" else "روز"
    
    try:
        await callback.bot.send_message(
            chat_id=customer_user_id,
            text=f"❌ **درخواست تمدید رد شد**\n\n"
                 f"🆔 شماره درخواست: {request_id}\n"
                 f"🎛️ پنل: {panel_name}\n"
                 f"📈 نوع: {'افزایش ترافیک' if request_details['request_type'] == 'traffic' else 'افزایش زمان'}\n"
                 f"📊 مقدار: {request_details['requested_amount']} {unit_name}\n"
                 f"💰 مبلغ: {request_details['total_price']:,} تومان\n\n"
                 f"📝 دلیل: {rejection_reason}\n\n"
                 f"💡 می‌توانید مجدداً درخواست تمدید ارسال کنید.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 بازگشت به منو", callback_data="start")],
                [InlineKeyboardButton(text="📈 درخواست مجدد", callback_data="request_extension")]
            ])
        )
    except Exception as e:
        logger.error(f"Failed to notify customer {customer_user_id}: {e}")
    
    logger.info(f"Extension request {request_id} rejected by admin {callback.from_user.id}")
    await callback.answer("درخواست رد شد و کاربر مطلع گردید.")

@extension_router.callback_query(F.data == "manage_extension_requests")
async def show_extension_requests_management(callback: CallbackQuery):
    """Show pending extension requests for admin management."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("شما مجاز به این عمل نیستید.", show_alert=True)
        return
    
    pending_requests = await db.get_pending_extension_requests()
    
    if not pending_requests:
        await callback.message.edit_text(
            "📋 **مدیریت درخواست‌های تمدید**\n\n"
            "❌ هیچ درخواست در انتظاری وجود ندارد.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 بازگشت", callback_data="start")]
            ])
        )
        await callback.answer()
        return
    
    text = "📋 **درخواست‌های تمدید در انتظار**\n\n"
    buttons = []
    
    for req in pending_requests:
        unit_name = "گیگابایت" if req['request_type'] == 'traffic' else "روز"
        panel_name = req.get('admin_name') or req.get('marzban_username', 'ناشناس')
        
        text += f"🆔 **درخواست {req['id']}**\n"
        text += f"👤 کاربر: {panel_name}\n"
        text += f"📈 نوع: {'افزایش ترافیک' if req['request_type'] == 'traffic' else 'افزایش زمان'}\n"
        text += f"📊 مقدار: {req['requested_amount']} {unit_name}\n"
        text += f"💰 مبلغ: {req['total_price']:,} تومان\n"
        text += f"📅 تاریخ: {req['created_at']}\n\n"
        
        buttons.append([
            InlineKeyboardButton(
                text=f"📋 مشاهده درخواست {req['id']}",
                callback_data=f"view_ext_req_{req['id']}"
            )
        ])
    
    buttons.append([InlineKeyboardButton(text="🏠 بازگشت", callback_data="start")])
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

@extension_router.callback_query(F.data.startswith("view_ext_req_"))
async def view_extension_request_details(callback: CallbackQuery):
    """View detailed information about an extension request."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("شما مجاز به این عمل نیستید.", show_alert=True)
        return
    
    request_id = int(callback.data.split("_")[3])
    request_details = await db.get_extension_request_by_id(request_id)
    
    if not request_details:
        await callback.answer("درخواست یافت نشد.", show_alert=True)
        return
    
    panel_name = request_details.get('admin_name') or request_details.get('marzban_username', 'ناشناس')
    unit_name = "گیگابایت" if request_details['request_type'] == 'traffic' else "روز"
    
    text = f"📋 **جزئیات درخواست {request_id}**\n\n"
    text += f"👤 **کاربر:** {panel_name}\n"
    text += f"🎛️ **پنل:** {request_details.get('marzban_username', 'ناشناس')}\n"
    text += f"📈 **نوع:** {'افزایش ترافیک' if request_details['request_type'] == 'traffic' else 'افزایش زمان'}\n"
    text += f"📊 **مقدار:** {request_details['requested_amount']} {unit_name}\n"
    text += f"💰 **مبلغ:** {request_details['total_price']:,} تومان\n"
    text += f"📅 **تاریخ درخواست:** {request_details['created_at']}\n"
    text += f"🏷️ **وضعیت:** {request_details['status']}\n\n"
    
    # Show current limits
    text += f"📊 **محدودیت‌های فعلی:**\n"
    text += f"👥 کاربران: {'نامحدود' if request_details['max_users'] == -1 else request_details['max_users']}\n"
    text += f"📊 ترافیک: {'نامحدود' if request_details['max_total_traffic'] == -1 else f"{request_details['max_total_traffic'] // (1024**3)}GB"}\n"
    text += f"⏱️ زمان: {'نامحدود' if request_details['max_total_time'] == -1 else f"{request_details['max_total_time'] // (24*3600)} روز"}\n"
    
    buttons = []
    if request_details['status'] == 'pending':
        buttons.extend([
            [
                InlineKeyboardButton(text="✅ تأیید", callback_data=f"approve_ext_req_{request_id}"),
                InlineKeyboardButton(text="❌ رد", callback_data=f"reject_ext_req_{request_id}")
            ],
            [InlineKeyboardButton(text="📷 مشاهده رسید", callback_data=f"view_ext_receipt_{request_id}")]
        ])
    
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="manage_extension_requests")])
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

@extension_router.callback_query(F.data.startswith("view_ext_receipt_"))
async def view_extension_payment_receipt(callback: CallbackQuery):
    """View payment receipt for extension request."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("شما مجاز به این عمل نیستید.", show_alert=True)
        return
    
    request_id = int(callback.data.split("_")[3])
    request_details = await db.get_extension_request_by_id(request_id)
    
    if not request_details or not request_details.get('payment_screenshot_file_id'):
        await callback.answer("رسید پرداخت یافت نشد.", show_alert=True)
        return
    
    panel_name = request_details.get('admin_name') or request_details.get('marzban_username', 'ناشناس')
    unit_name = "گیگابایت" if request_details['request_type'] == 'traffic' else "روز"
    
    try:
        await callback.bot.send_photo(
            chat_id=callback.message.chat.id,
            photo=request_details['payment_screenshot_file_id'],
            caption=f"📷 **رسید پرداخت درخواست {request_id}**\n\n"
                   f"👤 کاربر: {panel_name}\n"
                   f"📈 نوع: {'افزایش ترافیک' if request_details['request_type'] == 'traffic' else 'افزایش زمان'}\n"
                   f"📊 مقدار: {request_details['requested_amount']} {unit_name}\n"
                   f"💰 مبلغ: {request_details['total_price']:,} تومان",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ تأیید", callback_data=f"approve_ext_req_{request_id}"),
                    InlineKeyboardButton(text="❌ رد", callback_data=f"reject_ext_req_{request_id}")
                ],
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"view_ext_req_{request_id}")]
            ])
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Failed to send receipt photo: {e}")
        await callback.answer("خطا در نمایش رسید.", show_alert=True)