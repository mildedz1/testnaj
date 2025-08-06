#!/bin/bash
# Emergency backup search commands

echo "🚨 دستورات اضطراری برای پیدا کردن بکاپ"
echo "=" * 50

echo "1️⃣ جستجوی کامل فایل‌های مرزبان:"
echo "find / -type f \( -name '*marzban*' -o -name '*.sql' -o -name '*backup*' \) -ls 2>/dev/null | head -50"

echo -e "\n2️⃣ بررسی docker containers و volumes:"
echo "docker ps -a"
echo "docker volume ls"
echo "docker inspect \$(docker volume ls -q) 2>/dev/null | grep -A 10 -B 10 marzban"

echo -e "\n3️⃣ بررسی cron jobs و services:"
echo "cat /etc/crontab"
echo "ls /etc/cron.d/*"
echo "systemctl list-units '*backup*'"
echo "systemctl list-units '*marzban*'"

echo -e "\n4️⃣ بررسی فایل‌های اخیر (آخرین 24 ساعت):"
echo "find / -type f -mtime -1 -size +1M 2>/dev/null | grep -E '\.(sql|zip|tar|gz)$'"

echo -e "\n5️⃣ بررسی logs برای یافتن backup processes:"
echo "journalctl --since '1 hour ago' | grep -i backup"
echo "grep -r 'backup' /var/log/ 2>/dev/null | tail -10"

echo -e "\n6️⃣ بررسی mounted drives:"
echo "lsblk"
echo "df -h"
echo "mount | grep -v proc"

echo -e "\n7️⃣ اگر تلگرام بکاپ دارید:"
echo "# در تلگرام دنبال فایل‌هایی مثل:"
echo "# - marzban-backup-YYYY-MM-DD.zip"
echo "# - database-backup.sql"
echo "# - backup_TIMESTAMP.tar.gz"

echo -e "\n8️⃣ بررسی مسیرهای غیرعادی:"
echo "ls -la /tmp/"
echo "ls -la /var/tmp/"
echo "ls -la /home/*/Downloads/"

echo -e "\n🔧 دستورات برای اجرا:"
echo "bash emergency_commands.sh | bash"

echo -e "\n🚨 اگر هیچ بکاپی نیست:"
echo "1. بررسی snapshot VPS (اگر دارید)"
echo "2. تماس با provider VPS برای backup"
echo "3. بررسی cloud storage (اگر متصل بوده)"
echo "4. بررسی local backups روی کامپیوتر شخصی"