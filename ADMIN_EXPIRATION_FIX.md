# رفع مشکل محدودیت زمان ادمین‌ها

## شرح مشکل
قبلاً سیستم محدودیت زمان ادمین‌ها مشکلی داشت که به جای کاهش زمان باقی‌مانده، هر بار 30 روز به validity_days اضافه می‌کرد. این باعث می‌شد ادمین‌ها هرگز منقضی نشوند.

## راه‌حل پیاده‌سازی شده

### 1. توابع جدید در Database
- `is_admin_expired(admin_id)`: بررسی می‌کند که آیا ادمین منقضی شده یا نه
- `get_admin_remaining_days(admin_id)`: روزهای باقی‌مانده تا انقضا را برمی‌گرداند
- `execute_query(query, params)`: اجرای query های سفارشی

### 2. بروزرسانی Scheduler
در `scheduler.py` بررسی انقضای ادمین اضافه شد:
```python
# Check if admin has expired based on creation time and validity_days
if await db.is_admin_expired(admin_id):
    logger.warning(f"Admin {admin_id} ({admin.admin_name}) has expired")
    return LimitCheckResult(
        admin_user_id=admin.user_id,
        admin_id=admin_id,
        limits_exceeded=True,
        time_exceeded=True,
        message="ادمین شما منقضی شده است"
    )
```

### 3. نمایش زمان باقی‌مانده
در `admin_handlers.py` نمایش روزهای باقی‌مانده اضافه شد:
```python
# Get remaining days
remaining_days = await db.get_admin_remaining_days(admin.id)

text += f"⏰ روزهای باقی‌مانده: {remaining_days} روز\n"
```

### 4. بروزرسانی LimitCheckResult
فیلدهای جدید اضافه شد:
- `limits_exceeded`: برای backward compatibility
- `time_exceeded`: مشخص کننده انقضای زمان
- `message`: پیام توضیحی

## منطق محاسبه انقضا

```python
async def is_admin_expired(self, admin_id: int) -> bool:
    """Check if admin has expired based on created_at and validity_days."""
    created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
    expiration_time = created_at.timestamp() + (validity_days * 24 * 3600)
    current_time = datetime.now().timestamp()
    return current_time > expiration_time
```

## تست‌های انجام شده

تست‌های جامع در `test_admin_expiration.py` شامل:

1. **تست ایجاد ادمین با 30 روز اعتبار**
   - وضعیت اولیه: منقضی نشده، 30 روز باقی‌مانده
   - بعد از 15 روز: منقضی نشده، 15 روز باقی‌مانده  
   - بعد از 35 روز: منقضی شده، 0 روز باقی‌مانده

2. **تست ادمین با 7 روز اعتبار**
   - بعد از 5 روز: منقضی نشده، 2 روز باقی‌مانده
   - بعد از 10 روز: منقضی شده، 0 روز باقی‌مانده

3. **تست یکپارچگی با Scheduler**
   - شناسایی صحیح ادمین‌های منقضی شده
   - ایجاد LimitCheckResult مناسب

## نتایج تست

```
🧪 Testing Admin Expiration System
==================================================
📋 Test 1: Creating admin with 30 days validity
✅ Admin created with ID: 3
📊 Initial status: Expired=False, Remaining days=30

📋 Test 2: Simulating 15 days passage
📊 After 15 days: Expired=False, Remaining days=15

📋 Test 3: Simulating 35 days passage (should expire)
📊 After 35 days: Expired=True, Remaining days=0

📋 Test 4: Creating admin with 7 days validity
✅ Short validity admin: Expired=False, Remaining days=2
📊 After 10 days (7-day limit): Expired=True, Remaining days=0

✅ All expiration tests completed!
```

## تأثیرات سیستم

✅ **رفع شده:**
- محدودیت زمان حالا به درستی کاهش می‌یابد
- ادمین‌ها بعد از انقضای validity_days غیرفعال می‌شوند  
- نمایش صحیح روزهای باقی‌مانده

✅ **بهبودهای اضافی:**
- نمایش بهتر وضعیت ادمین
- پیام‌های واضح‌تر برای کاربران
- سیستم لاگ بهتر برای ادمین‌های منقضی شده

## مشکلات برطرف شده

1. **مشکل اصلی**: زمان محدودیت هر بار 30 روز اضافه می‌شد ❌
   **راه‌حل**: محاسبه بر اساس created_at و validity_days ✅

2. **عدم نمایش زمان باقی‌مانده** ❌
   **راه‌حل**: اضافه شدن فیلد "روزهای باقی‌مانده" ✅

3. **عدم بررسی انقضا در scheduler** ❌
   **راه‌حل**: اضافه شدن چک انقضا در ابتدای check_admin_limits ✅

## نکات مهم

- کد backward compatible است
- ادمین‌های موجود تحت تأثیر قرار نمی‌گیرند
- سیستم مقاوم در برابر خطا طراحی شده
- محاسبات زمان بر اساس UTC انجام می‌شود