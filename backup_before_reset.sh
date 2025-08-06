#!/bin/bash
# Script to backup important files before git reset

echo "🔒 بکاپ فایل‌های مهم قبل از Git Reset"
echo "====================================="

# Create backup directory with timestamp
BACKUP_DIR="backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "📁 ایجاد پوشه بکاپ: $BACKUP_DIR"

# Files to backup
FILES_TO_BACKUP=(
    "bot_database.db"
    "config.py"
    ".env"
    "logs/"
)

echo "📋 فایل‌های مورد نیاز برای بکاپ:"

for file in "${FILES_TO_BACKUP[@]}"; do
    if [ -e "$file" ]; then
        echo "  ✅ $file - یافت شد"
        cp -r "$file" "$BACKUP_DIR/"
        echo "     → کپی شد به $BACKUP_DIR/"
    else
        echo "  ❌ $file - یافت نشد"
    fi
done

echo ""
echo "🎯 مراحل Git Reset با حفظ فایل‌ها:"
echo "1. بکاپ گرفته شد در: $BACKUP_DIR"
echo "2. اجرای git reset:"
echo "   git fetch origin"
echo "   git reset --hard origin/main"
echo "3. بازگردانی فایل‌ها:"
echo "   cp -r $BACKUP_DIR/* ."
echo "4. راه‌اندازی مجدد ربات"

echo ""
echo "💡 نکات مهم:"
echo "• فایل config.py شامل تنظیمات مرزبان و تلگرام است"
echo "• فایل bot_database.db شامل تمام اطلاعات ادمین‌ها و logs است"
echo "• فایل .env شامل متغیرهای محیطی است (اگر دارید)"
echo "• پوشه logs/ شامل گزارش‌های ربات است"

echo ""
echo "✅ بکاپ کامل شد! حالا می‌توانید git reset انجام دهید."