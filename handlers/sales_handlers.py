#!/usr/bin/env python3
"""
Sales handlers for panel purchase system
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
from models.schemas import AdminModel, SalesProductModel, PaymentMethodModel, SalesOrderModel
from utils.helpers import safe_callback_answer, truncate_error, convert_unlimited_for_display, format_traffic_display, format_time_display
import logging

logger = logging.getLogger(__name__)

# FSM States for sales management
class SalesManagementStates(StatesGroup):
    waiting_for_product_name = State()
    waiting_for_product_description = State()
    waiting_for_product_price = State()
    waiting_for_product_users = State()
    waiting_for_product_traffic = State()
    waiting_for_product_time = State()
    waiting_for_payment_method_name = State()
    waiting_for_card_number = State()
    waiting_for_card_holder = State()
    waiting_for_bank_name = State()
    waiting_for_product_edit_value = State()

# FSM States for customer purchase
class PurchaseStates(StatesGroup):
    waiting_for_payment_screenshot = State()

sales_router = Router()

# ============= NAVIGATION HANDLERS =============

@sales_router.callback_query(F.data == "start")
async def handle_start_callback(callback: CallbackQuery, state: FSMContext):
    """Handle start button from sales system."""
    await state.clear()  # Clear any FSM state
    
    user_id = callback.from_user.id
    
    if user_id in config.SUDO_ADMINS:
        from handlers.sudo_handlers import start_sudo_handler
        # Convert to message-like object for sudo handler
        message = callback.message
        message.from_user = callback.from_user
        await start_sudo_handler(message)
    else:
        # Check if user is admin
        admin = await db.get_admin(user_id)
        if admin and admin.is_active:
            from handlers.admin_handlers import start_admin_handler
            # Convert to message-like object for admin handler
            message = callback.message
            message.from_user = callback.from_user
            await start_admin_handler(message)
        else:
            # Non-admin user
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛒 خرید پنل", callback_data="buy_panel")]
            ])
            
            await callback.message.edit_text(
                f"👋 سلام {callback.from_user.first_name}!\n\n"
                f"🤖 به ربات مدیریت پنل خوش آمدید.\n\n"
                f"🛒 **برای خرید پنل جدید:**\n"
                f"بر روی دکمه زیر کلیک کنید تا محصولات موجود را مشاهده کنید.",
                reply_markup=keyboard
            )
    
    await callback.answer()

@sales_router.callback_query(F.data == "back_to_main")
async def handle_back_to_main(callback: CallbackQuery, state: FSMContext):
    """Handle back to main menu."""
    await handle_start_callback(callback, state)

# ============= ADMIN SALES MANAGEMENT =============

@sales_router.callback_query(F.data == "sales_management")
async def sales_management_start(callback: CallbackQuery):
    """Start sales management for sudo admins."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📦 مدیریت محصولات", callback_data="manage_products"),
            InlineKeyboardButton(text="💳 مدیریت کارت‌ها", callback_data="manage_payment_methods")
        ],
        [
            InlineKeyboardButton(text="📋 سفارشات در انتظار", callback_data="pending_orders"),
            InlineKeyboardButton(text="📊 آمار فروش", callback_data="sales_stats")
        ],
        [
            InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="back_to_main")
        ]
    ])
    
    await callback.message.edit_text(
        "🛒 **مدیریت سیستم فروش**\n\n"
        "لطفاً بخش مورد نظر را انتخاب کنید:",
        reply_markup=keyboard
    )
    await callback.answer()

@sales_router.callback_query(F.data == "manage_products")
async def manage_products_menu(callback: CallbackQuery):
    """Show products management menu."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    products = await db.get_sales_products(active_only=False)
    
    text = "📦 **مدیریت محصولات فروش**\n\n"
    
    if products:
        text += f"📊 تعداد محصولات: {len(products)}\n\n"
        for product in products:
            status = "✅" if product['is_active'] else "❌"
            text += f"{status} **{product['name']}**\n"
            text += f"   💰 قیمت: {product['price']:,} {product['currency']}\n"
            text += f"   👥 کاربران: {product['max_users']} | "
            text += f"📊 ترافیک: {product['max_traffic'] // (1024**3)}GB | "
            text += f"⏱️ زمان: {product['max_time'] // (24*3600)} روز\n\n"
    else:
        text += "هیچ محصولی تعریف نشده است.\n\n"
    
    buttons = []
    buttons.append([InlineKeyboardButton(text="➕ افزودن محصول", callback_data="add_product")])
    
    if products:
        buttons.append([InlineKeyboardButton(text="✏️ ویرایش محصول", callback_data="edit_product")])
        # Add individual edit buttons for each product
        for product in products[:5]:  # Limit to 5 products to avoid button overflow
            status_emoji = "✅" if product['is_active'] else "❌"
            buttons.append([
                InlineKeyboardButton(
                    text=f"{status_emoji} ویرایش: {product['name']}",
                    callback_data=f"edit_product_{product['id']}"
                )
            ])
    
    buttons.append([InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="sales_management")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@sales_router.callback_query(F.data == "add_product")
async def add_product_start(callback: CallbackQuery, state: FSMContext):
    """Start adding a new product."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    await callback.message.edit_text(
        "📦 **افزودن محصول جدید**\n\n"
        "**مرحله ۱ از ۶: نام محصول**\n\n"
        "لطفاً نام محصول را وارد کنید:\n"
        "مثال: پنل برنزی، پنل نقره‌ای، پنل طلایی",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="manage_products")]
        ])
    )
    
    await state.set_state(SalesManagementStates.waiting_for_product_name)
    await callback.answer()

@sales_router.message(SalesManagementStates.waiting_for_product_name, F.text)
async def add_product_name(message: Message, state: FSMContext):
    """Handle product name input."""
    if message.from_user.id not in config.SUDO_ADMINS:
        return
    
    product_name = message.text.strip()
    if len(product_name) < 2:
        await message.answer("❌ نام محصول باید حداقل ۲ کاراکتر باشد.")
        return
    
    await state.update_data(product_name=product_name)
    
    await message.answer(
        f"✅ **نام محصول:** {product_name}\n\n"
        "**مرحله ۲ از ۶: توضیحات محصول**\n\n"
        "لطفاً توضیحات محصول را وارد کنید:\n"
        "مثال: پنل اقتصادی مناسب برای استفاده شخصی",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭️ رد کردن", callback_data="skip_description")],
            [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="manage_products")]
        ])
    )
    
    await state.set_state(SalesManagementStates.waiting_for_product_description)

@sales_router.message(SalesManagementStates.waiting_for_product_description, F.text)
async def add_product_description(message: Message, state: FSMContext):
    """Handle product description input."""
    if message.from_user.id not in config.SUDO_ADMINS:
        return
    
    description = message.text.strip()
    await state.update_data(product_description=description)
    
    await message.answer(
        f"✅ **توضیحات:** {description}\n\n"
        "**مرحله ۳ از ۶: قیمت محصول**\n\n"
        "لطفاً قیمت محصول را به تومان وارد کنید:\n"
        "مثال: 50000 (برای ۵۰ هزار تومان)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="manage_products")]
        ])
    )
    
    await state.set_state(SalesManagementStates.waiting_for_product_price)

@sales_router.callback_query(F.data == "skip_description")
async def skip_product_description(callback: CallbackQuery, state: FSMContext):
    """Skip product description."""
    await state.update_data(product_description="")
    
    await callback.message.edit_text(
        "**مرحله ۳ از ۶: قیمت محصول**\n\n"
        "لطفاً قیمت محصول را به تومان وارد کنید:\n"
        "مثال: 50000 (برای ۵۰ هزار تومان)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="manage_products")]
        ])
    )
    
    await state.set_state(SalesManagementStates.waiting_for_product_price)
    await callback.answer()

@sales_router.message(SalesManagementStates.waiting_for_product_price, F.text)
async def add_product_price(message: Message, state: FSMContext):
    """Handle product price input."""
    if message.from_user.id not in config.SUDO_ADMINS:
        return
    
    try:
        price = int(message.text.strip())
        if price < 1000:
            await message.answer("❌ قیمت باید حداقل ۱۰۰۰ تومان باشد.")
            return
    except ValueError:
        await message.answer("❌ لطفاً عدد صحیح وارد کنید.")
        return
    
    await state.update_data(product_price=price)
    
    await message.answer(
        f"✅ **قیمت:** {price:,} تومان\n\n"
        "**مرحله ۴ از ۶: تعداد کاربران**\n\n"
        "لطفاً حداکثر تعداد کاربران مجاز را وارد کنید:\n"
        "مثال: 50",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="manage_products")]
        ])
    )
    
    await state.set_state(SalesManagementStates.waiting_for_product_users)

@sales_router.message(SalesManagementStates.waiting_for_product_users, F.text)
async def add_product_users(message: Message, state: FSMContext):
    """Handle product max users input."""
    if message.from_user.id not in config.SUDO_ADMINS:
        return
    
    user_input = message.text.strip().lower()
    
    if user_input in ['نامحدود', 'unlimited', '-1', '0']:
        max_users = -1  # -1 indicates unlimited
    else:
        try:
            max_users = int(user_input)
            if max_users < 1:
                await message.answer("❌ تعداد کاربران باید حداقل ۱ باشد یا 'نامحدود' بنویسید.")
                return
        except ValueError:
            await message.answer("❌ لطفاً عدد صحیح وارد کنید یا 'نامحدود' بنویسید.")
            return
    
    await state.update_data(max_users=max_users)
    
    await message.answer(
        f"✅ **تعداد کاربران:** {max_users}\n\n"
        "**مرحله ۵ از ۶: حجم ترافیک**\n\n"
        "لطفاً حداکثر حجم ترافیک را بر حسب گیگابایت وارد کنید:\n"
        "مثال: 100 (برای ۱۰۰ گیگابایت)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="manage_products")]
        ])
    )
    
    await state.set_state(SalesManagementStates.waiting_for_product_traffic)

@sales_router.message(SalesManagementStates.waiting_for_product_traffic, F.text)
async def add_product_traffic(message: Message, state: FSMContext):
    """Handle product max traffic input."""
    if message.from_user.id not in config.SUDO_ADMINS:
        return
    
    traffic_input = message.text.strip().lower()
    
    if traffic_input in ['نامحدود', 'unlimited', '-1', '0']:
        traffic_bytes = -1  # -1 indicates unlimited
    else:
        try:
            traffic_gb = float(traffic_input)
            if traffic_gb < 0.1:
                await message.answer("❌ حجم ترافیک باید حداقل ۰.۱ گیگابایت باشد یا 'نامحدود' بنویسید.")
                return
            
            traffic_bytes = int(traffic_gb * 1024 * 1024 * 1024)
        except ValueError:
            await message.answer("❌ لطفاً عدد معتبر وارد کنید یا 'نامحدود' بنویسید.")
            return
    
    await state.update_data(max_traffic=traffic_bytes)
    
    await message.answer(
        f"✅ **حجم ترافیک:** {traffic_gb} گیگابایت\n\n"
        "**مرحله ۶ از ۶: مدت زمان**\n\n"
        "لطفاً مدت زمان اعتبار را بر حسب روز وارد کنید:\n"
        "مثال: 30 (برای ۳۰ روز)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="manage_products")]
        ])
    )
    
    await state.set_state(SalesManagementStates.waiting_for_product_time)

@sales_router.message(SalesManagementStates.waiting_for_product_time, F.text)
async def add_product_time(message: Message, state: FSMContext):
    """Handle product max time input and create the product."""
    if message.from_user.id not in config.SUDO_ADMINS:
        return
    
    time_input = message.text.strip().lower()
    
    if time_input in ['نامحدود', 'unlimited', '-1', '0']:
        time_seconds = -1  # -1 indicates unlimited
        time_days = -1
    else:
        try:
            time_days = int(time_input)
            if time_days < 1:
                await message.answer("❌ مدت زمان باید حداقل ۱ روز باشد یا 'نامحدود' بنویسید.")
                return
            
            time_seconds = time_days * 24 * 3600
        except ValueError:
            await message.answer("❌ لطفاً عدد صحیح وارد کنید یا 'نامحدود' بنویسید.")
            return
    
    # Get all data from state
    data = await state.get_data()
    
    # Create the product
    success = await db.add_sales_product(
        name=data['product_name'],
        description=data.get('product_description', ''),
        price=data['product_price'],
        max_users=data['max_users'],
        max_traffic=data['max_traffic'],
        max_time=time_seconds,
        validity_days=time_days
    )
    
    if success:
        await message.answer(
            "✅ **محصول با موفقیت اضافه شد!**\n\n"
            f"📦 **نام:** {data['product_name']}\n"
            f"💰 **قیمت:** {data['product_price']:,} تومان\n"
            f"👥 **کاربران:** {data['max_users']}\n"
            f"📊 **ترافیک:** {data['max_traffic'] // (1024**3)} گیگابایت\n"
            f"⏱️ **مدت:** {time_days} روز\n"
            f"📝 **توضیحات:** {data.get('product_description', 'ندارد')}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📦 مدیریت محصولات", callback_data="manage_products")],
                [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="sales_management")]
            ])
        )
        logger.info(f"New product added: {data['product_name']} by admin {message.from_user.id}")
    else:
        await message.answer(
            "❌ **خطا در ایجاد محصول**\n\n"
            "لطفاً دوباره تلاش کنید.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 تلاش مجدد", callback_data="add_product")],
                [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="manage_products")]
            ])
        )
    
    await state.clear()

# ============= PAYMENT METHODS MANAGEMENT =============

@sales_router.callback_query(F.data == "manage_payment_methods")
async def manage_payment_methods_menu(callback: CallbackQuery):
    """Show payment methods management menu."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    methods = await db.get_payment_methods(active_only=False)
    
    text = "💳 **مدیریت روش‌های پرداخت**\n\n"
    
    if methods:
        text += f"📊 تعداد کارت‌ها: {len(methods)}\n\n"
        for method in methods:
            status = "✅" if method['is_active'] else "❌"
            text += f"{status} **{method['method_name']}**\n"
            text += f"   💳 کارت: {method['card_number']}\n"
            text += f"   👤 صاحب کارت: {method['card_holder_name']}\n"
            text += f"   🏦 بانک: {method['bank_name']}\n\n"
    else:
        text += "هیچ روش پرداختی تعریف نشده است.\n\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ افزودن کارت", callback_data="add_payment_method")],
        [InlineKeyboardButton(text="✏️ ویرایش کارت", callback_data="edit_payment_method")] if methods else [],
        [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="sales_management")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@sales_router.callback_query(F.data == "add_payment_method")
async def add_payment_method_start(callback: CallbackQuery, state: FSMContext):
    """Start adding a new payment method."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    await callback.message.edit_text(
        "💳 **افزودن روش پرداخت جدید**\n\n"
        "**مرحله ۱ از ۴: نام روش پرداخت**\n\n"
        "لطفاً نام روش پرداخت را وارد کنید:\n"
        "مثال: کارت ملی، کارت پاسارگاد، کارت تجارت",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="manage_payment_methods")]
        ])
    )
    
    await state.set_state(SalesManagementStates.waiting_for_payment_method_name)
    await callback.answer()

@sales_router.message(SalesManagementStates.waiting_for_payment_method_name, F.text)
async def add_payment_method_name(message: Message, state: FSMContext):
    """Handle payment method name input."""
    if message.from_user.id not in config.SUDO_ADMINS:
        return
    
    method_name = message.text.strip()
    if len(method_name) < 2:
        await message.answer("❌ نام روش پرداخت باید حداقل ۲ کاراکتر باشد.")
        return
    
    await state.update_data(method_name=method_name)
    
    await message.answer(
        f"✅ **نام روش:** {method_name}\n\n"
        "**مرحله ۲ از ۴: شماره کارت**\n\n"
        "لطفاً شماره کارت را وارد کنید:\n"
        "مثال: 6037-9977-1234-5678",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="manage_payment_methods")]
        ])
    )
    
    await state.set_state(SalesManagementStates.waiting_for_card_number)

@sales_router.message(SalesManagementStates.waiting_for_card_number, F.text)
async def add_payment_card_number(message: Message, state: FSMContext):
    """Handle card number input."""
    if message.from_user.id not in config.SUDO_ADMINS:
        return
    
    card_number = message.text.strip()
    if len(card_number) < 16:
        await message.answer("❌ شماره کارت باید حداقل ۱۶ رقم باشد.")
        return
    
    await state.update_data(card_number=card_number)
    
    await message.answer(
        f"✅ **شماره کارت:** {card_number}\n\n"
        "**مرحله ۳ از ۴: نام صاحب کارت**\n\n"
        "لطفاً نام صاحب کارت را وارد کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="manage_payment_methods")]
        ])
    )
    
    await state.set_state(SalesManagementStates.waiting_for_card_holder)

@sales_router.message(SalesManagementStates.waiting_for_card_holder, F.text)
async def add_payment_card_holder(message: Message, state: FSMContext):
    """Handle card holder name input."""
    if message.from_user.id not in config.SUDO_ADMINS:
        return
    
    card_holder_name = message.text.strip()
    if len(card_holder_name) < 2:
        await message.answer("❌ نام صاحب کارت باید حداقل ۲ کاراکتر باشد.")
        return
    
    await state.update_data(card_holder_name=card_holder_name)
    
    await message.answer(
        f"✅ **صاحب کارت:** {card_holder_name}\n\n"
        "**مرحله ۴ از ۴: نام بانک**\n\n"
        "لطفاً نام بانک را وارد کنید:\n"
        "مثال: بانک ملی، بانک پاسارگاد، بانک تجارت",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="manage_payment_methods")]
        ])
    )
    
    await state.set_state(SalesManagementStates.waiting_for_bank_name)

@sales_router.message(SalesManagementStates.waiting_for_bank_name, F.text)
async def add_payment_bank_name(message: Message, state: FSMContext):
    """Handle bank name input and create payment method."""
    if message.from_user.id not in config.SUDO_ADMINS:
        return
    
    bank_name = message.text.strip()
    if len(bank_name) < 2:
        await message.answer("❌ نام بانک باید حداقل ۲ کاراکتر باشد.")
        return
    
    # Get all data from state
    data = await state.get_data()
    
    # Create the payment method
    success = await db.add_payment_method(
        method_name=data['method_name'],
        card_number=data['card_number'],
        card_holder_name=data['card_holder_name'],
        bank_name=bank_name
    )
    
    if success:
        await message.answer(
            "✅ **روش پرداخت با موفقیت اضافه شد!**\n\n"
            f"💳 **نام:** {data['method_name']}\n"
            f"🔢 **شماره کارت:** {data['card_number']}\n"
            f"👤 **صاحب کارت:** {data['card_holder_name']}\n"
            f"🏦 **بانک:** {bank_name}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 مدیریت کارت‌ها", callback_data="manage_payment_methods")],
                [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="sales_management")]
            ])
        )
        logger.info(f"New payment method added: {data['method_name']} by admin {message.from_user.id}")
    else:
        await message.answer(
            "❌ **خطا در ایجاد روش پرداخت**\n\n"
            "لطفاً دوباره تلاش کنید.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 تلاش مجدد", callback_data="add_payment_method")],
                [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="manage_payment_methods")]
            ])
        )
    
    await state.clear()

# ============= PRODUCT EDITING =============

@sales_router.callback_query(F.data.startswith("edit_product_"))
async def edit_specific_product(callback: CallbackQuery, state: FSMContext):
    """Handle editing a specific product."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    product_id = int(callback.data.split("_")[2])
    products = await db.get_sales_products(active_only=False)
    product = next((p for p in products if p['id'] == product_id), None)
    
    if not product:
        await callback.answer("محصول یافت نشد.", show_alert=True)
        return
    
    status_text = "فعال" if product['is_active'] else "غیرفعال"
    status_emoji = "✅" if product['is_active'] else "❌"
    
    text = f"✏️ **ویرایش محصول**\n\n"
    text += f"📦 **نام:** {product['name']}\n"
    text += f"💰 **قیمت:** {product['price']:,} {product['currency']}\n"
    text += f"👥 **کاربران:** {product['max_users']}\n"
    text += f"📊 **ترافیک:** {product['max_traffic'] // (1024**3)}GB\n"
    text += f"⏱️ **زمان:** {product['max_time'] // (24*3600)} روز\n"
    text += f"📅 **اعتبار:** {product['validity_days']} روز\n"
    text += f"📝 **توضیحات:** {product['description'] or 'ندارد'}\n"
    text += f"📊 **وضعیت:** {status_emoji} {status_text}\n\n"
    text += "چه قسمتی را می‌خواهید ویرایش کنید؟"
    
    buttons = [
        [
            InlineKeyboardButton(text="✏️ نام", callback_data=f"edit_field_name_{product_id}"),
            InlineKeyboardButton(text="💰 قیمت", callback_data=f"edit_field_price_{product_id}")
        ],
        [
            InlineKeyboardButton(text="👥 کاربران", callback_data=f"edit_field_users_{product_id}"),
            InlineKeyboardButton(text="📊 ترافیک", callback_data=f"edit_field_traffic_{product_id}")
        ],
        [
            InlineKeyboardButton(text="⏱️ زمان", callback_data=f"edit_field_time_{product_id}"),
            InlineKeyboardButton(text="📝 توضیحات", callback_data=f"edit_field_description_{product_id}")
        ],
        [
            InlineKeyboardButton(
                text=f"{'❌ غیرفعال کردن' if product['is_active'] else '✅ فعال کردن'}",
                callback_data=f"toggle_product_{product_id}"
            )
        ],
        [
            InlineKeyboardButton(text="🗑️ حذف محصول", callback_data=f"delete_product_{product_id}"),
            InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="manage_products")
        ]
    ]
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

@sales_router.callback_query(F.data.startswith("toggle_product_"))
async def toggle_product_status(callback: CallbackQuery):
    """Toggle product active status."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    product_id = int(callback.data.split("_")[2])
    products = await db.get_sales_products(active_only=False)
    product = next((p for p in products if p['id'] == product_id), None)
    
    if not product:
        await callback.answer("محصول یافت نشد.", show_alert=True)
        return
    
    new_status = not product['is_active']
    success = await db.update_sales_product(product_id, is_active=new_status)
    
    if success:
        status_text = "فعال" if new_status else "غیرفعال"
        await callback.answer(f"وضعیت محصول به {status_text} تغییر یافت.", show_alert=True)
        # Refresh the edit page
        await edit_specific_product(callback, None)
    else:
        await callback.answer("خطا در تغییر وضعیت محصول.", show_alert=True)

@sales_router.callback_query(F.data.startswith("edit_field_"))
async def edit_product_field(callback: CallbackQuery, state: FSMContext):
    """Handle editing a specific field of a product."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    parts = callback.data.split("_")
    field = parts[2]
    product_id = int(parts[3])
    
    await state.update_data(edit_product_id=product_id, edit_field=field)
    
    field_names = {
        "name": "نام محصول",
        "price": "قیمت (به تومان)",
        "users": "تعداد کاربران",
        "traffic": "حجم ترافیک (به گیگابایت)",
        "time": "مدت زمان (به روز)",
        "description": "توضیحات محصول"
    }
    
    field_name = field_names.get(field, field)
    
    await callback.message.edit_text(
        f"✏️ **ویرایش {field_name}**\n\n"
        f"مقدار جدید را وارد کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data=f"edit_product_{product_id}")]
        ])
    )
    
    await state.set_state(SalesManagementStates.waiting_for_product_edit_value)
    await callback.answer()

@sales_router.message(SalesManagementStates.waiting_for_product_edit_value, F.text)
async def product_edit_value_received(message: Message, state: FSMContext):
    """Handle new value for product field."""
    if message.from_user.id not in config.SUDO_ADMINS:
        return
    
    data = await state.get_data()
    product_id = data.get('edit_product_id')
    field = data.get('edit_field')
    new_value = message.text.strip()
    
    if not product_id or not field:
        await message.answer("خطا در دریافت اطلاعات ویرایش.")
        await state.clear()
        return
    
    try:
        # Validate and convert values
        update_data = {}
        
        if field == "name":
            if len(new_value) < 2:
                await message.answer("❌ نام محصول باید حداقل ۲ کاراکتر باشد.")
                return
            update_data['name'] = new_value
            
        elif field == "price":
            price = int(new_value)
            if price < 1000:
                await message.answer("❌ قیمت باید حداقل ۱۰۰۰ تومان باشد.")
                return
            update_data['price'] = price
            
        elif field == "users":
            # Check for unlimited input
            if new_value.lower() in ['نامحدود', 'unlimited', '-1', '0']:
                update_data['max_users'] = -1
            else:
                users = int(new_value)
                if users < 1:
                    await message.answer("❌ تعداد کاربران باید حداقل ۱ باشد یا 'نامحدود' بنویسید.")
                    return
                update_data['max_users'] = users
            
        elif field == "traffic":
            # Check for unlimited input
            if new_value.lower() in ['نامحدود', 'unlimited', '-1', '0']:
                update_data['max_traffic'] = -1
            else:
                traffic_gb = float(new_value)
                if traffic_gb < 0.1:
                    await message.answer("❌ حجم ترافیک باید حداقل ۰.۱ گیگابایت باشد یا 'نامحدود' بنویسید.")
                    return
                update_data['max_traffic'] = int(traffic_gb * 1024 * 1024 * 1024)
            
        elif field == "time":
            # Check for unlimited input
            if new_value.lower() in ['نامحدود', 'unlimited', '-1', '0']:
                update_data['max_time'] = -1
                update_data['validity_days'] = -1
            else:
                days = int(new_value)
                if days < 1:
                    await message.answer("❌ مدت زمان باید حداقل ۱ روز باشد یا 'نامحدود' بنویسید.")
                    return
                update_data['max_time'] = days * 24 * 3600
                update_data['validity_days'] = days
            
        elif field == "description":
            update_data['description'] = new_value
        
        # Update the product
        success = await db.update_sales_product(product_id, **update_data)
        
        if success:
            await message.answer(
                "✅ محصول با موفقیت بروزرسانی شد!",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📦 مدیریت محصولات", callback_data="manage_products")],
                    [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="sales_management")]
                ])
            )
            logger.info(f"Product {product_id} field {field} updated to {new_value} by admin {message.from_user.id}")
        else:
            await message.answer("❌ خطا در بروزرسانی محصول.")
            
    except ValueError:
        await message.answer("❌ مقدار وارد شده نامعتبر است. لطفاً عدد صحیح وارد کنید.")
        return
    except Exception as e:
        logger.error(f"Error updating product field: {e}")
        await message.answer("❌ خطا در بروزرسانی محصول.")
    
    await state.clear()

# ============= CUSTOMER PURCHASE INTERFACE =============

@sales_router.callback_query(F.data == "buy_panel")
async def show_products_for_purchase(callback: CallbackQuery):
    """Show available products for purchase."""
    products = await db.get_sales_products(active_only=True)
    
    if not products:
        await callback.message.edit_text(
            "❌ **محصولی برای فروش موجود نیست**\n\n"
            "در حال حاضر هیچ پنلی برای فروش تعریف نشده است.\n"
            "لطفاً بعداً مراجعه کنید.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="start")]
            ])
        )
        await callback.answer()
        return
    
    text = "🛒 **فروشگاه پنل مرزبان**\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    text += "💎 **محصولات موجود برای خرید:**\n\n"
    
    buttons = []
    for i, product in enumerate(products, 1):
        # Create attractive product display
        text += f"🔥 **پکیج {i}: {product['name']}**\n"
        text += f"┏━━━━━━━━━━━━━━━━━━━━━━━\n"
        text += f"┃ 💰 **قیمت:** {product['price']:,} {product['currency']}\n"
        
        # Handle unlimited values with utility functions
        users_display = convert_unlimited_for_display(product['max_users'])
        if users_display != "نامحدود":
            users_display += " نفر"
            
        traffic_display = format_traffic_display(product['max_traffic'])
        time_display = format_time_display(product['max_time'])
        validity_display = convert_unlimited_for_display(product['validity_days'])
        if validity_display != "نامحدود":
            validity_display += " روز"
        
        text += f"┃ 👥 **کاربران:** {users_display}\n"
        text += f"┃ 📊 **ترافیک:** {traffic_display}\n"
        text += f"┃ ⏱️ **مدت زمان:** {time_display}\n"
        text += f"┃ 📅 **اعتبار:** {validity_display}\n"
        if product['description']:
            text += f"┃ 📝 **توضیحات:** {product['description']}\n"
        text += f"┗━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # Make button more attractive
        button_text = f"🛒 انتخاب {product['name']} | {product['price']:,} تومان"
        buttons.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"select_product_{product['id']}"
            )
        ])
    
    buttons.append([InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="start")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@sales_router.callback_query(F.data.startswith("select_product_"))
async def select_product_for_purchase(callback: CallbackQuery, state: FSMContext):
    """Handle product selection for purchase."""
    product_id = int(callback.data.split("_")[2])
    
    # Get product details
    products = await db.get_sales_products(active_only=True)
    product = next((p for p in products if p['id'] == product_id), None)
    
    if not product:
        await callback.answer("محصول یافت نشد.", show_alert=True)
        return
    
    # Get payment methods
    payment_methods = await db.get_payment_methods(active_only=True)
    
    if not payment_methods:
        await callback.message.edit_text(
            "❌ **روش پرداختی موجود نیست**\n\n"
            "در حال حاضر هیچ روش پرداختی فعال نیست.\n"
            "لطفاً با پشتیبانی تماس بگیرید.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="buy_panel")]
            ])
        )
        await callback.answer()
        return
    
    # Store product info in state
    await state.update_data(
        selected_product_id=product_id,
        selected_product=product
    )
    
    text = f"🛒 **خرید {product['name']}**\n\n"
    text += f"💰 **قیمت:** {product['price']:,} {product['currency']}\n"
    text += f"📦 **مشخصات:**\n"
    
    # Use utility functions for proper display
    users_display = convert_unlimited_for_display(product['max_users'])
    if users_display != "نامحدود":
        users_display += " نفر"
    
    text += f"   👥 کاربران: {users_display}\n"
    text += f"   📊 ترافیک: {format_traffic_display(product['max_traffic'])}\n"
    text += f"   ⏱️ زمان: {format_time_display(product['max_time'])}\n\n"
    
    if product['description']:
        text += f"📝 **توضیحات:** {product['description']}\n\n"
    
    text += "💳 **انتخاب روش پرداخت:**\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # Group payment methods by type
    card_methods = []
    crypto_methods = []
    
    for method in payment_methods:
        method_name_lower = method['method_name'].lower()
        if any(crypto in method_name_lower for crypto in ['usdt', 'btc', 'eth', 'ترون', 'تتر', 'بیت', 'اتریوم', 'crypto', 'کریپتو']):
            crypto_methods.append(method)
        else:
            card_methods.append(method)
    
    buttons = []
    
    # Show payment type options without details
    if card_methods:
        buttons.append([
            InlineKeyboardButton(
                text="💳 پرداخت کارت به کارت",
                callback_data="payment_type_card"
            )
        ])
    
    if crypto_methods:
        buttons.append([
            InlineKeyboardButton(
                text="🪙 پرداخت با ارز دیجیتال",
                callback_data="payment_type_crypto"
            )
        ])
    
    buttons.append([InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="buy_panel")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@sales_router.callback_query(F.data.startswith("payment_type_"))
async def select_payment_type(callback: CallbackQuery, state: FSMContext):
    """Handle payment type selection (card vs crypto)."""
    payment_type = callback.data.split("_")[2]  # card or crypto
    
    # Get product from state
    data = await state.get_data()
    product = data.get('selected_product')
    
    if not product:
        await callback.answer("خطا در دریافت اطلاعات محصول.", show_alert=True)
        return
    
    # Get appropriate payment methods
    payment_methods = await db.get_payment_methods(active_only=True)
    
    if payment_type == "card":
        methods = [m for m in payment_methods if not any(crypto in m['method_name'].lower() 
                  for crypto in ['usdt', 'btc', 'eth', 'ترون', 'تتر', 'بیت', 'اتریوم', 'crypto', 'کریپتو'])]
        type_name = "کارت به کارت"
        type_emoji = "💳"
    else:  # crypto
        methods = [m for m in payment_methods if any(crypto in m['method_name'].lower() 
                  for crypto in ['usdt', 'btc', 'eth', 'ترون', 'تتر', 'بیت', 'اتریوم', 'crypto', 'کریپتو'])]
        type_name = "ارز دیجیتال"
        type_emoji = "🪙"
    
    if not methods:
        await callback.answer("روش پرداخت یافت نشد.", show_alert=True)
        return
    
    # For now, use the first method of selected type
    selected_method = methods[0]
    
    # Create order
    product_snapshot = json.dumps(product)
    order_id = await db.create_sales_order(
        customer_user_id=callback.from_user.id,
        customer_username=callback.from_user.username,
        customer_first_name=callback.from_user.first_name,
        customer_last_name=callback.from_user.last_name,
        product_id=product['id'],
        total_price=product['price'],
        product_snapshot=product_snapshot
    )
    
    if order_id == 0:
        await callback.answer("خطا در ثبت سفارش.", show_alert=True)
        return
    
    # Store order info in state
    await state.update_data(
        order_id=order_id,
        payment_method_id=selected_method['id'],
        payment_method=selected_method,
        payment_type=payment_type
    )
    
    # Show payment instructions
    if payment_type == "card":
        instructions = (
            f"💳 **اطلاعات پرداخت کارت به کارت:**\n\n"
            f"🏦 **بانک:** {selected_method['bank_name']}\n"
            f"💳 **شماره کارت:** `{selected_method['card_number']}`\n"
            f"👤 **صاحب حساب:** {selected_method['card_holder_name']}\n\n"
            f"💰 **مبلغ قابل پرداخت:** {product['price']:,} تومان\n\n"
            f"📝 **مراحل پرداخت:**\n"
            f"1️⃣ مبلغ را به شماره کارت بالا واریز کنید\n"
            f"2️⃣ اسکرین‌شات رسید واریز را در همین چت ارسال کنید\n"
            f"3️⃣ منتظر تأیید ادمین باشید (حداکثر ۲۴ ساعت)"
        )
    else:  # crypto
        instructions = (
            f"🪙 **اطلاعات پرداخت ارز دیجیتال:**\n\n"
            f"💎 **ارز:** {selected_method['method_name']}\n"
            f"📍 **آدرس کیف پول:** `{selected_method['card_number']}`\n\n"
            f"💰 **مبلغ:** {product['price']:,} تومان معادل ارز\n\n"
            f"📝 **مراحل پرداخت:**\n"
            f"1️⃣ معادل مبلغ را به آدرس بالا ارسال کنید\n"
            f"2️⃣ اسکرین‌شات تراکنش را در همین چت ارسال کنید\n"
            f"3️⃣ منتظر تأیید ادمین باشید (حداکثر ۲۴ ساعت)\n\n"
            f"⚠️ **توجه:** نرخ ارز در زمان پرداخت محاسبه می‌شود"
        )
    
    text = f"✅ **سفارش ثبت شد**\n\n"
    text += f"🆔 **شماره سفارش:** {order_id}\n"
    text += f"📦 **محصول:** {product['name']}\n\n"
    text += instructions
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ لغو سفارش", callback_data=f"cancel_order_{order_id}")],
            [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="buy_panel")]
        ])
    )
    
    await state.set_state(PurchaseStates.waiting_for_payment_screenshot)
    await callback.answer()

@sales_router.callback_query(F.data.startswith("select_payment_"))
async def select_payment_method(callback: CallbackQuery, state: FSMContext):
    """Handle payment method selection."""
    payment_method_id = int(callback.data.split("_")[2])
    
    # Get payment method details
    payment_methods = await db.get_payment_methods(active_only=True)
    payment_method = next((pm for pm in payment_methods if pm['id'] == payment_method_id), None)
    
    if not payment_method:
        await callback.answer("روش پرداخت یافت نشد.", show_alert=True)
        return
    
    # Get product from state
    data = await state.get_data()
    product = data.get('selected_product')
    
    if not product:
        await callback.answer("خطا در دریافت اطلاعات محصول.", show_alert=True)
        return
    
    # Create order
    product_snapshot = json.dumps(product)
    order_id = await db.create_sales_order(
        customer_user_id=callback.from_user.id,
        customer_username=callback.from_user.username,
        customer_first_name=callback.from_user.first_name,
        customer_last_name=callback.from_user.last_name,
        product_id=product['id'],
        total_price=product['price'],
        product_snapshot=product_snapshot
    )
    
    if order_id == 0:
        await callback.answer("خطا در ثبت سفارش.", show_alert=True)
        return
    
    # Store order info in state
    await state.update_data(
        order_id=order_id,
        payment_method_id=payment_method_id,
        payment_method=payment_method
    )
    
    text = f"✅ **سفارش ثبت شد**\n\n"
    text += f"🆔 **شماره سفارش:** {order_id}\n"
    text += f"📦 **محصول:** {product['name']}\n"
    text += f"💰 **مبلغ:** {product['price']:,} {product['currency']}\n\n"
    text += f"💳 **اطلاعات پرداخت:**\n"
    text += f"🏦 {payment_method['bank_name']}\n"
    text += f"💳 {payment_method['card_number']}\n"
    text += f"👤 {payment_method['card_holder_name']}\n\n"
    text += "📷 **لطفاً اسکرین شات واریز را ارسال کنید:**\n"
    text += "پس از واریز مبلغ، تصویر رسید را در همین چت ارسال کنید.\n"
    text += "سفارش شما پس از تأیید ادمین پردازش خواهد شد."
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ لغو سفارش", callback_data=f"cancel_order_{order_id}")],
            [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="buy_panel")]
        ])
    )
    
    await state.set_state(PurchaseStates.waiting_for_payment_screenshot)
    await callback.answer()

@sales_router.message(PurchaseStates.waiting_for_payment_screenshot, F.photo)
async def handle_payment_screenshot(message: Message, state: FSMContext):
    """Handle payment screenshot upload."""
    data = await state.get_data()
    order_id = data.get('order_id')
    payment_method_id = data.get('payment_method_id')
    
    if not order_id or not payment_method_id:
        await message.answer("خطا در دریافت اطلاعات سفارش.")
        await state.clear()
        return
    
    # Get the largest photo
    photo = message.photo[-1]
    
    # Update order with payment screenshot
    success = await db.update_order_payment(order_id, payment_method_id, photo.file_id)
    
    if not success:
        await message.answer("خطا در ثبت اطلاعات پرداخت.")
        return
    
    # Notify customer
    await message.answer(
        f"✅ **رسید پرداخت دریافت شد**\n\n"
        f"🆔 شماره سفارش: {order_id}\n"
        f"📷 تصویر رسید ثبت شد\n\n"
        f"⏳ سفارش شما در انتظار تأیید ادمین است.\n"
        f"پس از تأیید، اطلاعات پنل برای شما ارسال خواهد شد.\n\n"
        f"🕐 زمان پردازش: معمولاً کمتر از ۲۴ ساعت",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 بازگشت به منو", callback_data="start")]
        ])
    )
    
    # Notify admin about new order
    for admin_id in config.SUDO_ADMINS:
        try:
            await message.bot.send_photo(
                chat_id=admin_id,
                photo=photo.file_id,
                caption=f"🔔 **سفارش جدید**\n\n"
                       f"🆔 شماره: {order_id}\n"
                       f"👤 مشتری: {message.from_user.first_name or 'ناشناس'} (@{message.from_user.username or 'ندارد'})\n"
                       f"📦 محصول: {data.get('selected_product', {}).get('name', 'نامشخص')}\n"
                       f"💰 مبلغ: {data.get('selected_product', {}).get('price', 0):,} تومان\n\n"
                       f"📷 رسید پرداخت:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ تأیید", callback_data=f"approve_order_{order_id}"),
                        InlineKeyboardButton(text="❌ رد", callback_data=f"reject_order_{order_id}")
                    ],
                    [InlineKeyboardButton(text="📋 مدیریت سفارشات", callback_data="pending_orders")]
                ])
            )
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")
    
    logger.info(f"New order {order_id} submitted by user {message.from_user.id}")
    await state.clear()

# Continue with order management handlers...

# ============= ORDER MANAGEMENT AND APPROVAL =============

@sales_router.callback_query(F.data == "pending_orders")
async def show_pending_orders(callback: CallbackQuery):
    """Show pending orders for admin review."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    orders = await db.get_pending_orders()
    
    if not orders:
        await callback.message.edit_text(
            "📋 **سفارشات در انتظار**\n\n"
            "هیچ سفارشی در انتظار تأیید نیست.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="sales_management")]
            ])
        )
        await callback.answer()
        return
    
    text = f"📋 **سفارشات در انتظار ({len(orders)})**\n\n"
    
    buttons = []
    for order in orders:
        text += f"🆔 **سفارش #{order['id']}**\n"
        text += f"👤 {order['customer_first_name'] or 'ناشناس'} (@{order['customer_username'] or 'ندارد'})\n"
        text += f"📦 {order['product_name']}\n"
        text += f"💰 {order['total_price']:,} تومان\n"
        text += f"📅 {order['created_at']}\n\n"
        
        buttons.append([
            InlineKeyboardButton(
                text=f"📋 بررسی سفارش #{order['id']}",
                callback_data=f"review_order_{order['id']}"
            )
        ])
    
    buttons.append([InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="sales_management")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@sales_router.callback_query(F.data.startswith("review_order_"))
async def review_order_details(callback: CallbackQuery):
    """Show order details for review."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    order_id = int(callback.data.split("_")[2])
    order = await db.get_order_by_id(order_id)
    
    if not order:
        await callback.answer("سفارش یافت نشد.", show_alert=True)
        return
    
    text = f"📋 **جزئیات سفارش #{order_id}**\n\n"
    text += f"👤 **مشتری:**\n"
    text += f"   نام: {order['customer_first_name'] or 'ناشناس'} {order['customer_last_name'] or ''}\n"
    text += f"   نام کاربری: @{order['customer_username'] or 'ندارد'}\n"
    text += f"   ID: `{order['customer_user_id']}`\n\n"
    text += f"📦 **محصول:** {order['product_name']}\n"
    text += f"💰 **مبلغ:** {order['total_price']:,} تومان\n\n"
    text += f"📋 **مشخصات پنل:**\n"
    
    # Use utility functions for proper display
    users_display = convert_unlimited_for_display(order['max_users'])
    if users_display != "نامحدود":
        users_display += " نفر"
    
    validity_display = convert_unlimited_for_display(order['validity_days'])
    if validity_display != "نامحدود":
        validity_display += " روز"
    
    text += f"   👥 کاربران: {users_display}\n"
    text += f"   📊 ترافیک: {format_traffic_display(order['max_traffic'])}\n"
    text += f"   ⏱️ زمان: {format_time_display(order['max_time'])}\n"
    text += f"   📅 اعتبار: {validity_display}\n\n"
    text += f"📅 **تاریخ سفارش:** {order['created_at']}\n"
    text += f"📷 **رسید پرداخت:** ارسال شده"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ تأیید و ساخت پنل", callback_data=f"approve_order_{order_id}"),
            InlineKeyboardButton(text="❌ رد سفارش", callback_data=f"reject_order_{order_id}")
        ],
        [InlineKeyboardButton(text="📷 نمایش رسید", callback_data=f"show_receipt_{order_id}")],
        [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="pending_orders")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@sales_router.callback_query(F.data.startswith("show_receipt_"))
async def show_payment_receipt(callback: CallbackQuery):
    """Show payment receipt for order."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    order_id = int(callback.data.split("_")[2])
    order = await db.get_order_by_id(order_id)
    
    if not order or not order.get('payment_screenshot_file_id'):
        await callback.answer("رسید پرداخت یافت نشد.", show_alert=True)
        return
    
    try:
        await callback.message.bot.send_photo(
            chat_id=callback.message.chat.id,
            photo=order['payment_screenshot_file_id'],
            caption=f"📷 **رسید پرداخت سفارش #{order_id}**\n\n"
                   f"👤 مشتری: {order['customer_first_name']} (@{order['customer_username']})\n"
                   f"📦 محصول: {order['product_name']}\n"
                   f"💰 مبلغ: {order['total_price']:,} تومان",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ تأیید", callback_data=f"approve_order_{order_id}"),
                    InlineKeyboardButton(text="❌ رد", callback_data=f"reject_order_{order_id}")
                ]
            ])
        )
        await callback.answer()
    except Exception as e:
        error_msg = truncate_error(e)
        await safe_callback_answer(callback, f"خطا در نمایش رسید: {error_msg}", show_alert=True)

@sales_router.callback_query(F.data.startswith("approve_order_"))
async def approve_order_and_create_panel(callback: CallbackQuery):
    """Approve order and automatically create panel."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    order_id = int(callback.data.split("_")[2])
    order = await db.get_order_by_id(order_id)
    
    if not order:
        await callback.answer("سفارش یافت نشد.", show_alert=True)
        return
    
    if order['status'] != 'pending':
        await callback.answer("این سفارش قبلاً پردازش شده است.", show_alert=True)
        return
    
    try:
        # Generate unique marzban username
        base_username = f"panel_{order['customer_user_id']}"
        marzban_username = base_username
        counter = 1
        
        # Check if username exists and make it unique
        while await db.get_admin_by_marzban_username(marzban_username):
            marzban_username = f"{base_username}_{counter}"
            counter += 1
        
        # Generate random password
        import secrets
        import string
        password_chars = string.ascii_letters + string.digits
        marzban_password = ''.join(secrets.choice(password_chars) for _ in range(12))
        
        # Create admin model
        admin = AdminModel(
            user_id=order['customer_user_id'],
            admin_name=f"{order['customer_first_name'] or 'مشتری'} - {order['product_name']}",
            marzban_username=marzban_username,
            marzban_password=marzban_password,
            username=order['customer_username'],
            first_name=order['customer_first_name'],
            last_name=order['customer_last_name'],
            max_users=order['max_users'],
            max_total_traffic=order['max_traffic'],
            max_total_time=order['max_time'],
            validity_days=order['validity_days'],
            is_active=True,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        # First create admin in Marzban panel
        from marzban_api import marzban_api
        marzban_success = await marzban_api.create_admin(
            username=marzban_username,
            password=marzban_password,
            telegram_id=order['customer_user_id'],
            is_sudo=False
        )
        
        if not marzban_success:
            logger.error(f"Failed to create admin {marzban_username} in Marzban panel")
            await callback.answer("خطا در ایجاد پنل در سرور مرزبان.", show_alert=True)
            return
        
        logger.info(f"Admin {marzban_username} created successfully in Marzban panel")
        
        # Add admin to bot database
        admin_id = await db.add_admin(admin)
        
        if admin_id > 0:
            # Approve order
            await db.approve_order(order_id, admin_id)
            
            # Notify customer about successful order
            try:
                await callback.message.bot.send_message(
                    chat_id=order['customer_user_id'],
                    text=f"🎉 **سفارش شما تأیید شد!**\n\n"
                         f"🆔 **شماره سفارش:** {order_id}\n"
                         f"📦 **محصول:** {order['product_name']}\n\n"
                         f"🔐 **اطلاعات ورود به پنل مرزبان:**\n"
                         f"🌐 **آدرس پنل:** `{config.MARZBAN_URL}/dashboard`\n"
                         f"👤 **نام کاربری:** `{marzban_username}`\n"
                         f"🔑 **رمز عبور:** `{marzban_password}`\n\n"
                         f"📋 **مشخصات پنل:**\n"
                         f"👥 حداکثر کاربران: {convert_unlimited_for_display(order['max_users'])}\n"
                         f"📊 حداکثر ترافیک: {format_traffic_display(order['max_traffic'])}\n"
                         f"⏱️ حداکثر زمان: {format_time_display(order['max_time'])}\n"
                         f"📅 اعتبار: {convert_unlimited_for_display(order['validity_days'])} {'روز' if order['validity_days'] != -1 else ''}\n\n"
                         f"✨ پنل شما در سرور مرزبان ایجاد شد و فعال است.\n"
                         f"🎯 برای مدیریت پنل از ربات، دستور /start را ارسال کنید.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🏠 شروع استفاده", callback_data="start")]
                    ])
                )
            except Exception as e:
                logger.error(f"Failed to notify customer {order['customer_user_id']}: {e}")
            
            # Notify admin about successful approval
            try:
                await callback.message.edit_text(
                    f"✅ **سفارش تأیید شد**\n\n"
                    f"🆔 سفارش #{order_id} با موفقیت تأیید شد.\n"
                    f"👤 مشتری: {order['customer_first_name']} (@{order['customer_username']})\n"
                    f"📦 محصول: {order['product_name']}\n"
                    f"💰 مبلغ: {order['total_price']:,} تومان\n\n"
                    f"🔐 **پنل ایجاد شده:**\n"
                    f"👤 نام کاربری: {marzban_username}\n"
                    f"🔑 رمز عبور: {marzban_password}\n"
                    f"🆔 ID پنل: {admin_id}\n\n"
                    f"📩 اطلاعات برای مشتری ارسال شد.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="📋 سفارشات در انتظار", callback_data="pending_orders")],
                        [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="sales_management")]
                    ])
                )
            except Exception as edit_error:
                # If edit fails, send new message
                logger.warning(f"Failed to edit message, sending new one: {edit_error}")
                await callback.message.bot.send_message(
                    chat_id=callback.message.chat.id,
                    text=f"✅ **سفارش تأیید شد**\n\n"
                         f"🆔 سفارش #{order_id} با موفقیت تأیید شد.\n"
                         f"👤 مشتری: {order['customer_first_name']} (@{order['customer_username']})\n"
                         f"📦 محصول: {order['product_name']}\n"
                         f"💰 مبلغ: {order['total_price']:,} تومان\n\n"
                         f"🔐 **پنل ایجاد شده:**\n"
                         f"👤 نام کاربری: {marzban_username}\n"
                         f"🔑 رمز عبور: {marzban_password}\n"
                         f"🆔 ID پنل: {admin_id}\n\n"
                         f"📩 اطلاعات برای مشتری ارسال شد.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="📋 سفارشات در انتظار", callback_data="pending_orders")],
                        [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="sales_management")]
                    ])
                )
            
            logger.info(f"Order {order_id} approved and panel {admin_id} created for user {order['customer_user_id']}")
            
        else:
            await callback.answer("خطا در ایجاد پنل.", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error approving order {order_id}: {e}")
        error_msg = truncate_error(e)
        await safe_callback_answer(callback, f"خطا در تأیید سفارش: {error_msg}", show_alert=True)
    
    await callback.answer()

@sales_router.callback_query(F.data.startswith("reject_order_"))
async def reject_order_with_reason(callback: CallbackQuery):
    """Reject order with notification to customer."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    order_id = int(callback.data.split("_")[2])
    order = await db.get_order_by_id(order_id)
    
    if not order:
        await callback.answer("سفارش یافت نشد.", show_alert=True)
        return
    
    if order['status'] != 'pending':
        await callback.answer("این سفارش قبلاً پردازش شده است.", show_alert=True)
        return
    
    try:
        # Reject order
        await db.reject_order(order_id, "سفارش توسط ادمین رد شد")
        
        # Notify customer about rejection
        try:
            await callback.message.bot.send_message(
                chat_id=order['customer_user_id'],
                text=f"❌ **سفارش رد شد**\n\n"
                     f"🆔 **شماره سفارش:** {order_id}\n"
                     f"📦 **محصول:** {order['product_name']}\n"
                     f"💰 **مبلغ:** {order['total_price']:,} تومان\n\n"
                     f"📝 **دلیل:** رسید پرداخت معتبر نیست یا مبلغ کامل نیست.\n\n"
                     f"🔄 **راه حل:**\n"
                     f"• مبلغ صحیح را واریز کنید\n"
                     f"• رسید واضح و کامل ارسال کنید\n"
                     f"• دوباره سفارش ثبت کنید\n\n"
                     f"💬 برای راهنمایی با پشتیبانی تماس بگیرید.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🛒 سفارش مجدد", callback_data="buy_panel")],
                    [InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="start")]
                ])
            )
        except Exception as e:
            logger.error(f"Failed to notify customer {order['customer_user_id']}: {e}")
        
        # Notify admin about successful rejection
        await callback.message.edit_text(
            f"❌ **سفارش رد شد**\n\n"
            f"🆔 سفارش #{order_id} رد شد.\n"
            f"👤 مشتری: {order['customer_first_name']} (@{order['customer_username']})\n"
            f"📦 محصول: {order['product_name']}\n"
            f"💰 مبلغ: {order['total_price']:,} تومان\n\n"
            f"📩 اطلاعات رد برای مشتری ارسال شد.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 سفارشات در انتظار", callback_data="pending_orders")],
                [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="sales_management")]
            ])
        )
        
        logger.info(f"Order {order_id} rejected by admin {callback.from_user.id}")
          
    except Exception as e:
        logger.error(f"Error rejecting order {order_id}: {e}")
        error_msg = truncate_error(e)
        await safe_callback_answer(callback, f"خطا در رد سفارش: {error_msg}", show_alert=True)
    
    await callback.answer()

@sales_router.callback_query(F.data.startswith("cancel_order_"))
async def cancel_order_by_customer(callback: CallbackQuery, state: FSMContext):
    """Handle order cancellation by customer."""
    order_id = int(callback.data.split("_")[2])
    
    await callback.message.edit_text(
        f"❌ **سفارش لغو شد**\n\n"
        f"🆔 سفارش #{order_id} لغو شد.\n"
        f"می‌توانید مجدداً سفارش ثبت کنید.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 سفارش مجدد", callback_data="buy_panel")],
            [InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="start")]
        ])
    )
    
    await state.clear()
    await callback.answer()

# ============= SALES STATISTICS =============

@sales_router.callback_query(F.data == "sales_stats")
async def show_sales_statistics(callback: CallbackQuery):
    """Show sales statistics for admin."""
    if callback.from_user.id not in config.SUDO_ADMINS:
        await callback.answer("غیرمجاز", show_alert=True)
        return
    
    # This would require additional database queries for statistics
    # For now, show basic info
    products = await db.get_sales_products(active_only=False)
    active_products = [p for p in products if p['is_active']]
    payment_methods = await db.get_payment_methods(active_only=False)
    active_payment_methods = [pm for pm in payment_methods if pm['is_active']]
    
    text = "📊 **آمار سیستم فروش**\n\n"
    text += f"📦 **محصولات:**\n"
    text += f"   کل: {len(products)}\n"
    text += f"   فعال: {len(active_products)}\n\n"
    text += f"💳 **روش‌های پرداخت:**\n"
    text += f"   کل: {len(payment_methods)}\n"
    text += f"   فعال: {len(active_payment_methods)}\n\n"
    text += f"📋 **سفارشات:**\n"
    text += f"   در انتظار: {len(await db.get_pending_orders())}\n\n"
    text += "⚠️ آمار تفصیلی در نسخه‌های بعدی اضافه خواهد شد."
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=config.BUTTONS["back"], callback_data="sales_management")]
        ])
    )
    await callback.answer()