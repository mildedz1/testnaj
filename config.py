import os
from typing import List

# Bot Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")

# Marzban Configuration
MARZBAN_URL = os.getenv("MARZBAN_URL", "https://your-marzban-panel.com")
MARZBAN_USERNAME = os.getenv("MARZBAN_USERNAME", "admin")
MARZBAN_PASSWORD = os.getenv("MARZBAN_PASSWORD", "admin_password")

# Sudo Admins (User IDs)
SUDO_ADMINS: List[int] = [
    int(x) for x in os.getenv("SUDO_ADMINS", "123456789").split(",") if x.strip()
]

# Database Configuration
DATABASE_PATH = os.getenv("DATABASE_PATH", "bot_database.db")

# Monitoring Configuration
MONITORING_INTERVAL = int(os.getenv("MONITORING_INTERVAL", "600"))  # 10 minutes in seconds
WARNING_THRESHOLD = float(os.getenv("WARNING_THRESHOLD", "0.8"))  # 80% threshold

# API Configuration
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "30"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))

# Messages in Persian
MESSAGES = {
    "welcome_sudo": "🔐 سلام! شما به عنوان سودو ادمین وارد شده‌اید.\n\nکلیدهای دستور:",
    "welcome_admin": "👋 سلام! شما به عنوان ادمین معمولی وارد شده‌اید.\n\nکلیدهای دستور:",
    "unauthorized": "⛔ شما مجاز به استفاده از این ربات نیستید.",
    "admin_added": "✅ ادمین جدید با موفقیت اضافه شد:",
    "admin_removed": "❌ پنل با موفقیت غیرفعال شد.",
    "admin_activated": "✅ ادمین فعال شد.",
    "admin_deactivated": "❌ ادمین غیرفعال شد.",
    "admin_not_found": "❌ ادمین مورد نظر یافت نشد.",
    "panel_not_found": "❌ پنل مورد نظر یافت نشد.",
    "invalid_format": "❌ فرمت ورودی اشتباه است.",
    "api_error": "⚠️ خطا در اتصال به API مرزبان.",
    "database_error": "⚠️ خطا در پایگاه داده.",
    "limit_warning": "⚠️ هشدار: شما به {percent}% از محدودیت خود رسیده‌اید!",
    "limit_exceeded": "🚫 محدودیت شما اشباع شده و کاربران غیرفعال شدند.",
    "users_reactivated": "✅ کاربران مجدداً فعال شدند.",
    "admin_deactivated": "🔒 ادمین {admin_id} به دلیل {reason} غیرفعال شد.",
    "admin_reactivated": "✅ ادمین {admin_id} مجدداً فعال شد.",
    "admin_users_deactivated": "👥 تمام کاربران ادمین {admin_id} غیرفعال شدند.",
    "admin_password_randomized": "🔐 پسورد ادمین {admin_id} تصادفی شد.",
    "no_deactivated_admins": "✅ همه ادمین‌ها فعال هستند.",
    "select_admin_to_reactivate": "🔄 انتخاب ادمین برای فعالسازی مجدد:",
    "select_panel_to_deactivate": "❌ انتخاب پنل برای غیرفعالسازی:",
    "select_panel_to_edit": "✏️ انتخاب پنل برای ویرایش:",
    "panel_limits_updated": "✅ محدودیت‌های پنل با موفقیت به‌روزرسانی شد."
}

# Button Labels
BUTTONS = {
    "add_admin": "➕ افزودن ادمین",
    "remove_admin": "🗑️ حذف پنل", 
    "edit_panel": "✏️ ویرایش پنل",
    "list_admins": "📋 لیست ادمین‌ها",
    "admin_status": "📊 وضعیت ادمین‌ها",
    "activate_admin": "🔄 فعالسازی ادمین",
    "my_info": "👤 اطلاعات من",
    "my_users": "👥 کاربران من",
    "my_report": "📈 گزارش من",
    "reactivate_users": "🔄 فعالسازی کاربران",
    "back": "🔙 بازگشت",
    "cancel": "❌ لغو"
}