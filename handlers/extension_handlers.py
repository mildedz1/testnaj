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
    is_premium = has_unlimited_users and has_unlimited_time
    
    text = f"📈 **درخواست تمدید پنل**\n\n"
    text += f"🎛️ **پنل:** {panel_name}\n\n"
    text += f"📊 **وضعیت فعلی:**\n"
    text += f"👥 کاربران: {'نامحدود' if admin.max_users == -1 else admin.max_users}\n"
    text += f"📊 ترافیک: {'نامحدود' if admin.max_total_traffic == -1 else f'{admin.max_total_traffic // (1024**3)}GB'}\n"
    text += f"⏱️ زمان: {'نامحدود' if admin.max_total_time == -1 else f'{admin.max_total_time // (24*3600)} روز'}\n\n"
    
    text += f"💰 **قیمت‌های تمدید:**\n"
    traffic_price = 1500 if is_premium else 1000
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
    is_premium = has_unlimited_users and has_unlimited_time
    
    if extension_type == "traffic":
        price_per_gb = 1500 if is_premium else 1000
        text = f"📊 **افزایش ترافیک**\n\n"
        text += f"💰 **قیمت:** {price_per_gb:,} تومان هر گیگابایت\n\n"
        text += f"چند گیگابایت ترافیک می‌خواهید اضافه کنید؟\n"
        text += f"مثال: 10 (برای ۱۰ گیگابایت)"
        
    else:  # time
        text = f"⏱️ **افزایش زمان**\n\n"
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
    is_premium = has_unlimited_users and has_unlimited_time
    
    if extension_type == "traffic":
        price_per_unit = 1500 if is_premium else 1000
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
    text += "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    buttons = []
    
    # Show card-to-card option
    if card_methods:
        text += "💳 **کارت به کارت:**\n"
        for method in card_methods:
            text += f"┃ 🏦 {method['bank_name']}\n"
            text += f"┃ 💳 {method['card_number']}\n"
            text += f"┃ 👤 {method['card_holder_name']}\n"
        text += "\n"
        
        buttons.append([
            InlineKeyboardButton(
                text="💳 پرداخت کارت به کارت",
                callback_data="ext_payment_card"
            )
        ])
    
    # Show crypto option
    if crypto_methods:
        text += "🪙 **ارزهای دیجیتال:**\n"
        for method in crypto_methods:
            text += f"┃ 🪙 {method['method_name']}\n"
            if method['card_number']:
                text += f"┃ 📍 {method['card_number']}\n"
        text += "\n"
        
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
    
    # Show payment instructions
    panel_name = admin.admin_name or admin.marzban_username
    unit_name = "گیگابایت" if extension_type == "traffic" else "روز"
    
    if payment_type == "card":
        instructions = (
            f"💳 **اطلاعات پرداخت کارت به کارت:**\n\n"
            f"🏦 **بانک:** {selected_method['bank_name']}\n"
            f"💳 **شماره کارت:** `{selected_method['card_number']}`\n"
            f"👤 **صاحب حساب:** {selected_method['card_holder_name']}\n\n"
            f"💰 **مبلغ قابل پرداخت:** {total_price:,} تومان"
        )
    else:  # crypto
        instructions = (
            f"🪙 **اطلاعات پرداخت ارز دیجیتال:**\n\n"
            f"💎 **ارز:** {selected_method['method_name']}\n"
            f"📍 **آدرس کیف پول:** `{selected_method['card_number']}`\n\n"
            f"💰 **مبلغ:** {total_price:,} تومان معادل ارز"
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