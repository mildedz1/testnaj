#!/usr/bin/env python3
"""
Script to find and analyze Marzban backup files
"""

import os
import subprocess
import json
from datetime import datetime
import glob

def run_command(cmd):
    """Run a shell command and return output."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except Exception as e:
        return "", str(e), 1

def check_marzban_installation():
    """Check if Marzban is installed and get its directory."""
    print("🔍 بررسی نصب مرزبان...")
    
    # Common Marzban directories
    marzban_dirs = [
        "/opt/marzban",
        "/var/lib/marzban", 
        "/home/marzban",
        "/root/marzban"
    ]
    
    found_dirs = []
    for directory in marzban_dirs:
        if os.path.exists(directory):
            found_dirs.append(directory)
            print(f"✅ یافت شد: {directory}")
    
    # Check if docker is running Marzban
    stdout, stderr, code = run_command("docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}' | grep -i marzban")
    if code == 0 and stdout:
        print("✅ کانتینر مرزبان فعال:")
        print(stdout)
        
        # Get container details
        stdout, stderr, code = run_command("docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Mounts}}' | grep -i marzban")
        if code == 0:
            print("\n📂 مسیرهای mount شده:")
            print(stdout)
    
    return found_dirs

def find_backup_files():
    """Find backup files in common locations."""
    print("\n🔍 جستجو برای فایل‌های بکاپ...")
    
    # Common backup locations
    search_paths = [
        "/opt/*/backup*",
        "/var/*/backup*", 
        "/home/*/backup*",
        "/root/backup*",
        "/tmp/*backup*",
        "/opt/*marzban*backup*",
        "/var/*marzban*backup*",
        "*.sql",
        "*.zip",
        "*.tar.gz",
        "*.tar",
        "/var/lib/marzban/*.db",
        "/opt/marzban/*.db"
    ]
    
    found_files = []
    
    for pattern in search_paths:
        try:
            files = glob.glob(pattern, recursive=True)
            for file in files:
                if os.path.isfile(file):
                    stat = os.stat(file)
                    size = stat.st_size
                    mtime = datetime.fromtimestamp(stat.st_mtime)
                    found_files.append({
                        'path': file,
                        'size': size,
                        'modified': mtime,
                        'size_mb': round(size / (1024*1024), 2)
                    })
        except:
            continue
    
    # Sort by modification time (newest first)
    found_files.sort(key=lambda x: x['modified'], reverse=True)
    
    if found_files:
        print(f"✅ یافت شد {len(found_files)} فایل:")
        for i, file in enumerate(found_files[:20]):  # Show top 20
            print(f"{i+1:2d}. {file['path']}")
            print(f"    اندازه: {file['size_mb']} MB")
            print(f"    تاریخ: {file['modified'].strftime('%Y-%m-%d %H:%M:%S')}")
            print()
    else:
        print("❌ هیچ فایل بکاپی یافت نشد")
    
    return found_files

def check_telegram_backups():
    """Check for backup bot installations."""
    print("\n🤖 بررسی ربات‌های بکاپ...")
    
    # Check for common backup scripts
    backup_locations = [
        "/opt/sql_backup",
        "/opt/M03ED_Backup", 
        "/opt/backup-marz-x-ui",
        "/opt/Marzban-Backup",
        "/root/backup*",
        "/home/backup*"
    ]
    
    found_backup_tools = []
    for location in backup_locations:
        if os.path.exists(location):
            found_backup_tools.append(location)
            print(f"✅ ابزار بکاپ یافت شد: {location}")
            
            # Check config files
            config_files = [
                os.path.join(location, "config.json"),
                os.path.join(location, ".env"),
                os.path.join(location, "server_list.json")
            ]
            
            for config in config_files:
                if os.path.exists(config):
                    print(f"   📄 فایل تنظیمات: {config}")
    
    # Check cron jobs for backup
    stdout, stderr, code = run_command("crontab -l 2>/dev/null | grep -i backup")
    if code == 0 and stdout:
        print("✅ cron job بکاپ یافت شد:")
        print(stdout)
    
    return found_backup_tools

def check_database_backups():
    """Check for database backups."""
    print("\n💾 بررسی بکاپ‌های دیتابیس...")
    
    # Check for SQL dumps
    sql_patterns = [
        "*.sql",
        "*.sql.gz",
        "*marzban*.sql",
        "*backup*.sql",
        "/tmp/*.sql",
        "/var/tmp/*.sql"
    ]
    
    sql_files = []
    for pattern in sql_patterns:
        try:
            files = glob.glob(pattern, recursive=True)
            for file in files:
                if os.path.isfile(file):
                    stat = os.stat(file)
                    sql_files.append({
                        'path': file,
                        'size_mb': round(stat.st_size / (1024*1024), 2),
                        'modified': datetime.fromtimestamp(stat.st_mtime)
                    })
        except:
            continue
    
    sql_files.sort(key=lambda x: x['modified'], reverse=True)
    
    if sql_files:
        print(f"✅ یافت شد {len(sql_files)} فایل SQL:")
        for file in sql_files[:10]:
            print(f"  📄 {file['path']} ({file['size_mb']} MB) - {file['modified'].strftime('%Y-%m-%d %H:%M:%S')}")
    
    return sql_files

def show_restore_instructions(backup_files, sql_files):
    """Show instructions for restoring backups."""
    print("\n" + "="*60)
    print("📋 دستورالعمل بازگردانی بکاپ")
    print("="*60)
    
    if backup_files or sql_files:
        print("\n🔄 مراحل بازگردانی:")
        
        print("\n1️⃣ توقف مرزبان:")
        print("   cd /opt/marzban")
        print("   docker compose down")
        
        if sql_files:
            print("\n2️⃣ بازگردانی دیتابیس:")
            latest_sql = sql_files[0]
            print(f"   آخرین بکاپ SQL: {latest_sql['path']}")
            print("   # برای MySQL/MariaDB:")
            print("   docker compose up -d mysql  # یا mariadb")
            print(f"   docker exec -i marzban-mysql-1 mysql -u root -p marzban < {latest_sql['path']}")
            print("   # یا اگر فایل فشرده است:")
            print(f"   gunzip -c {latest_sql['path']} | docker exec -i marzban-mysql-1 mysql -u root -p marzban")
        
        if backup_files:
            print("\n3️⃣ بازگردانی فایل‌های مرزبان:")
            latest_backup = backup_files[0]
            print(f"   آخرین بکاپ: {latest_backup['path']}")
            
            if latest_backup['path'].endswith('.zip'):
                print(f"   unzip {latest_backup['path']} -d /tmp/restore/")
            elif latest_backup['path'].endswith('.tar.gz'):
                print(f"   tar -xzf {latest_backup['path']} -C /tmp/restore/")
            elif latest_backup['path'].endswith('.tar'):
                print(f"   tar -xf {latest_backup['path']} -C /tmp/restore/")
            
            print("   # کپی فایل‌ها به مکان‌های درست")
            print("   cp -r /tmp/restore/var/lib/marzban/* /var/lib/marzban/")
            print("   cp -r /tmp/restore/opt/marzban/* /opt/marzban/")
        
        print("\n4️⃣ راه‌اندازی مجدد:")
        print("   cd /opt/marzban")
        print("   docker compose up -d")
        
        print("\n5️⃣ بررسی:")
        print("   docker compose logs -f")
        
    else:
        print("❌ هیچ فایل بکاپی یافت نشد!")
        print("\n💡 راه‌حل‌های احتمالی:")
        print("1. بررسی تلگرام برای بکاپ‌های ارسالی توسط ربات")
        print("2. بررسی سرور‌های دیگر")
        print("3. بررسی هارد دیسک‌های خارجی")
        print("4. بازیابی از snapshot های VPS (اگر دارید)")

def main():
    """Main function."""
    print("🚨 ابزار جستجو و بازگردانی بکاپ مرزبان")
    print("="*50)
    
    # Check Marzban installation
    marzban_dirs = check_marzban_installation()
    
    # Find backup files
    backup_files = find_backup_files()
    
    # Check backup tools
    backup_tools = check_telegram_backups()
    
    # Check database backups
    sql_files = check_database_backups()
    
    # Show restore instructions
    show_restore_instructions(backup_files, sql_files)
    
    # Summary
    print(f"\n📊 خلاصه:")
    print(f"   📂 مسیرهای مرزبان یافت شده: {len(marzban_dirs)}")
    print(f"   📄 فایل‌های بکاپ: {len(backup_files)}")
    print(f"   💾 فایل‌های SQL: {len(sql_files)}")
    print(f"   🤖 ابزار بکاپ: {len(backup_tools)}")
    
    if backup_files or sql_files:
        print("\n✅ امکان بازگردانی وجود دارد!")
    else:
        print("\n❌ هیچ بکاپی یافت نشد!")

if __name__ == "__main__":
    main()