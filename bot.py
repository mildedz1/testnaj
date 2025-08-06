import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

import config
from database import db
from marzban_api import marzban_api
from handlers.sudo_handlers import sudo_router
from handlers.admin_handlers import admin_router
from scheduler import init_scheduler


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


class MarzbanAdminBot:
    def __init__(self):
        self.bot = Bot(
            token=config.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        self.dp = Dispatcher()
        self.scheduler = None

    async def setup(self):
        """Setup bot components."""
        logger.info("Setting up Marzban Admin Bot...")
        
        # Initialize database
        try:
            await db.init_db()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
        
        # Test Marzban API connection
        try:
            if await marzban_api.test_connection():
                logger.info("Marzban API connection successful")
            else:
                logger.warning("Marzban API connection failed - bot will continue but some features may not work")
        except Exception as e:
            logger.warning(f"Error testing Marzban API: {e}")
        
        # Setup routers - IMPORTANT: Register state-specific routers FIRST
        # This ensures FSM state handlers are processed before general handlers
        logger.info("=== ROUTER REGISTRATION ORDER (CRITICAL FOR FSM) ===")
        logger.info("Registering sudo_router (FSM-aware)...")
        self.dp.include_router(sudo_router)
        logger.info("✅ sudo_router registered successfully")
        
        logger.info("Registering admin_router (FSM-aware)...")
        self.dp.include_router(admin_router)
        logger.info("✅ admin_router registered successfully")
        
        logger.info("=== GENERAL HANDLERS (AFTER FSM ROUTERS) ===")
        # Add global handlers AFTER state-specific routers
        logger.info("Registering start command handler...")
        self.dp.message.register(self.unauthorized_handler, Command("start"))
        logger.info("✅ Start command handler registered")
        
        # Register help handler with proper filters to avoid FSM interference
        logger.info("Registering help handler with StateFilter(None)...")
        self.dp.message.register(
            self.help_handler,
            StateFilter(None),  # Only handle messages when user is NOT in any FSM state
            ~Command("start")   # And exclude /start command (handled by unauthorized_handler)
        )
        logger.info("✅ Help handler registered with StateFilter(None)")
        
        # Add global fallback for unhandled messages LAST - with StateFilter to prevent FSM interference
        logger.info("Registering general message handler with StateFilter(None)...")
        self.dp.message.register(
            self.general_message_handler,
            StateFilter(None)  # Only handle messages when user is NOT in any FSM state
        )
        logger.info("✅ General message handler registered with StateFilter(None)")
        logger.info("=== ROUTER REGISTRATION COMPLETE ===")
        logger.info("📋 Handler order: FSM routers → Command handlers → StateFilter(None) handlers")
        
        # Initialize scheduler
        self.scheduler = init_scheduler(self.bot)
        
        logger.info("Bot setup completed")

    async def help_handler(self, message: Message, state: FSMContext = None):
        """Handler for unrecognized commands and help."""
        user_id = message.from_user.id
        
        # Log handler activation with detailed state information
        current_state = await state.get_state() if state else None
        logger.info(f"Help handler activated for user {user_id}, current state: {current_state}, message: {message.text}")
        
        # This should not happen anymore due to StateFilter(None), but keep as safety check
        if current_state:
            logger.error(f"CRITICAL: Help handler called for user {user_id} in state {current_state} - StateFilter(None) not working properly!")
            return  # Don't interfere with FSM flow
        
        # Check if user is authorized
        if user_id not in config.SUDO_ADMINS and not await db.is_admin_authorized(user_id):
            await message.answer(config.MESSAGES["unauthorized"])
            logger.warning(f"Unauthorized help request from user {user_id}")
            return
        
        # Different help messages for sudo and regular admins
        if user_id in config.SUDO_ADMINS:
            logger.info(f"Providing sudo admin help to user {user_id}")
            help_text = (
                "🤖 دستورات سودو ادمین:\n\n"
                "📝 مدیریت ادمین‌ها:\n"
                "• /add_admin - افزودن ادمین جدید\n"
                "• افزودن ادمین قبلی - اضافه کردن ادمین‌های موجود در سرور مرزبان\n"
                "• /show_admins یا /list_admins - نمایش لیست ادمین‌ها\n"
                "• /remove_admin - غیرفعالسازی پنل\n"
                "• /edit_panel - ویرایش محدودیت‌های پنل\n"
                "• /admin_status - وضعیت تفصیلی ادمین‌ها\n"
                "• /activate_admin - فعالسازی ادمین غیرفعال\n\n"
                "📋 یا از دکمه‌های شیشه‌ای استفاده کنید:"
            )
            from handlers.sudo_handlers import get_sudo_keyboard
            await message.answer(help_text, reply_markup=get_sudo_keyboard())
        else:
            logger.info(f"Providing regular admin help to user {user_id}")
            help_text = (
                "🤖 دستورات ادمین معمولی:\n\n"
                "📊 گزارش‌گیری:\n"
                "• /گزارش_من - گزارش لحظه‌ای شما\n"
                "• /کاربران_من - لیست کاربران شما\n\n"
                "📋 یا از دکمه‌های شیشه‌ای استفاده کنید:"
            )
            from handlers.admin_handlers import get_admin_keyboard
            await message.answer(help_text, reply_markup=get_admin_keyboard())
        
        logger.info(f"Help message sent to user {user_id}")

    async def unauthorized_handler(self, message: Message, state: FSMContext = None):
        """Handler for unauthorized users."""
        user_id = message.from_user.id
        
        # Log handler activation with state information
        current_state = await state.get_state() if state else None
        logger.info(f"Unauthorized handler activated for user {user_id}, current state: {current_state}, message: {message.text}")
        
        # This should not happen with proper StateFilter, but keep as safety check
        if current_state:
            logger.warning(f"Unauthorized handler called for user {user_id} in state {current_state} with message: {message.text} - this should not happen")
            return  # Don't interfere with FSM flow
        
        # This will only be reached if user is not sudo and not authorized admin
        if user_id not in config.SUDO_ADMINS and not await db.is_admin_authorized(user_id):
            await message.answer(config.MESSAGES["unauthorized"])
            logger.warning(f"Unauthorized access attempt from user {user_id}, message: {message.text}")

    async def general_message_handler(self, message: Message, state: FSMContext = None):
        """General handler for unhandled messages."""
        user_id = message.from_user.id
        
        # Log handler activation with detailed state information
        current_state = await state.get_state() if state else None
        logger.info(f"General message handler activated for user {user_id}, current state: {current_state}, message: {message.text}")
        
        # This should not happen with StateFilter(None), but keep as safety check
        if current_state:
            logger.error(f"CRITICAL: General handler called for user {user_id} in state {current_state} with message: {message.text} - StateFilter(None) not working properly!")
            return  # Don't interfere with FSM flow
        
        # Check if user is sudo admin
        if user_id in config.SUDO_ADMINS:
            logger.info(f"Providing sudo admin help to user {user_id}")
            await message.answer(
                "🔐 شما سودو ادمین هستید.\n\n"
                "📋 دستورات موجود:\n"
                "• /start - منوی اصلی\n"
                "• /add_admin - افزودن ادمین جدید\n"
                "• افزودن ادمین قبلی - اضافه کردن ادمین‌های موجود در سرور\n"
                "• /show_admins - نمایش لیست ادمین‌ها\n"
                "• /remove_admin - غیرفعالسازی پنل\n"
                "• /edit_panel - ویرایش محدودیت‌های پنل\n"
                "• /admin_status - وضعیت ادمین‌ها\n"
                "• /activate_admin - فعالسازی ادمین غیرفعال\n\n"
                "برای دسترسی به منوی اصلی /start را بزنید."
            )
            logger.info(f"Sudo admin help message sent to user {user_id}")
            return
        
        # Check if user is authorized admin
        if await db.is_admin_authorized(user_id):
            logger.info(f"Providing regular admin help to user {user_id}")
            await message.answer(
                "👋 شما ادمین معمولی هستید.\n\n"
                "📋 دستورات موجود:\n"
                "• /start - منوی اصلی\n"
                "• /گزارش_من - گزارش استفاده\n"
                "• /کاربران_من - لیست کاربران\n"
                "• /اطلاعات_من - اطلاعات حساب\n\n"
                "برای دسترسی به منوی اصلی /start را بزنید."
            )
            logger.info(f"Regular admin help message sent to user {user_id}")
            return
        
        # Unauthorized user
        await message.answer(config.MESSAGES["unauthorized"])
        logger.warning(f"Unauthorized access attempt from user {user_id}, message: {message.text}")

    async def start_polling(self):
        """Start bot polling."""
        logger.info("Starting bot polling...")
        
        try:
            # Start monitoring scheduler
            await self.scheduler.start()
            
            # Start polling
            await self.dp.start_polling(self.bot)
            
        except Exception as e:
            logger.error(f"Error during polling: {e}")
            raise
        finally:
            await self.cleanup()

    async def cleanup(self):
        """Cleanup resources."""
        logger.info("Cleaning up bot resources...")
        
        try:
            if self.scheduler:
                await self.scheduler.stop()
            
            await db.close()
            await self.bot.session.close()
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    async def send_startup_message(self):
        """Send startup notification to sudo admins."""
        startup_message = (
            "🚀 ربات مدیریت ادمین‌های مرزبان راه‌اندازی شد!\n\n"
            f"⏰ دوره مانیتورینگ: {config.MONITORING_INTERVAL} ثانیه\n"
            f"📊 آستانه هشدار: {int(config.WARNING_THRESHOLD * 100)}%\n"
            f"🔗 آدرس مرزبان: {config.MARZBAN_URL}"
        )
        
        for sudo_id in config.SUDO_ADMINS:
            try:
                await self.bot.send_message(sudo_id, startup_message)
            except Exception as e:
                logger.warning(f"Failed to send startup message to sudo {sudo_id}: {e}")


async def main():
    """Main function."""
    try:
        # Validate config
        if not config.BOT_TOKEN or config.BOT_TOKEN == "YOUR_BOT_TOKEN":
            logger.error("BOT_TOKEN is not set in config!")
            return
        
        if not config.SUDO_ADMINS:
            logger.error("No SUDO_ADMINS configured!")
            return
        
        # Create and setup bot
        bot = MarzbanAdminBot()
        await bot.setup()
        
        # Send startup message
        await bot.send_startup_message()
        
        # Start polling
        await bot.start_polling()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Critical error: {e}")
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application terminated by user")
    except Exception as e:
        logger.error(f"Application failed: {e}")
        sys.exit(1)