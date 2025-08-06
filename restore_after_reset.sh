#!/bin/bash
# Script to restore backed up files after git reset

echo "🔄 بازگردانی فایل‌های بکاپ شده"
echo "=============================="

# Find the latest backup directory
LATEST_BACKUP=$(ls -td backup_* 2>/dev/null | head -1)

if [ -z "$LATEST_BACKUP" ]; then
    echo "❌ هیچ پوشه بکاپی یافت نشد!"
    echo "دنبال پوشه‌هایی با نام backup_YYYYMMDD_HHMMSS می‌گردیم..."
    ls -la | grep backup
    exit 1
fi

echo "📁 آخرین بکاپ یافت شده: $LATEST_BACKUP"
echo ""

# Files to restore
FILES_TO_RESTORE=(
    "bot_database.db"
    "config.py"
    ".env"
    "logs/"
)

echo "📋 بازگردانی فایل‌ها:"

for file in "${FILES_TO_RESTORE[@]}"; do
    if [ -e "$LATEST_BACKUP/$file" ]; then
        echo "  🔄 $file"
        cp -r "$LATEST_BACKUP/$file" .
        echo "     ✅ بازگردانی شد"
    else
        echo "  ❌ $file - در بکاپ یافت نشد"
    fi
done

echo ""
echo "🔧 بررسی فایل‌های مهم:"

# Check important files
if [ -f "config.py" ]; then
    echo "  ✅ config.py - موجود"
else
    echo "  ❌ config.py - وجود ندارد!"
fi

if [ -f "bot_database.db" ]; then
    echo "  ✅ bot_database.db - موجود"
else
    echo "  ❌ bot_database.db - وجود ندارد!"
fi

echo ""
echo "🎯 مراحل نهایی:"
echo "1. بررسی کنید که config.py تنظیمات درست دارد"
echo "2. مجوزهای اجرا را تنظیم کنید:"
echo "   chmod +x *.py"
echo "3. ربات را راه‌اندازی کنید:"
echo "   python3 main.py"

echo ""
echo "💡 اگر مشکلی پیش آمد:"
echo "• تمام فایل‌های بکاپ در $LATEST_BACKUP موجودند"
echo "• می‌توانید manual کپی کنید: cp -r $LATEST_BACKUP/* ."

echo ""
echo "✅ بازگردانی کامل شد!"