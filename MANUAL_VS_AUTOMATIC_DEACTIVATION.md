# Manual vs Automatic Panel Deactivation Implementation

This document outlines the implementation of the dual deactivation logic as requested in the requirements.

## Overview

The system now differentiates between two types of panel deactivation:

### 1. Manual Deactivation (غیرفعالسازی دستی پنل/ادمین)
**Behavior**: Complete deletion of both panel and all its users
**Trigger**: When sudo admin manually deactivates a panel via the bot interface
**Implementation**: `delete_admin_panel_completely()` function

### 2. Automatic Deactivation (غیرفعالسازی خودکار)
**Behavior**: Preserves panel but changes password and deactivates users
**Trigger**: When panel reaches usage limits (traffic, time, user count)
**Implementation**: `deactivate_admin_panel_by_id()` function with fixed password

## Key Changes Made

### API Updates (marzban_api.py)

1. **Updated password change API format**:
   ```python
   PUT /api/admin/{username}
   Content-Type: application/json
   {
     "password": "f26560291b",
     "is_sudo": true_or_false
   }
   ```

2. **Added complete deletion function**:
   - `delete_admin_completely()`: Deletes admin and all their users from Marzban
   - Used for manual deactivation only

### Manual Deactivation Logic (sudo_handlers.py)

1. **New function**: `delete_admin_panel_completely()`
   - Deletes all users belonging to the admin from Marzban
   - Deletes the admin from Marzban
   - Removes admin record from local database
   - Logs the complete deletion action

2. **Updated UI**:
   - Button text changed to "حذف پنل" (Delete Panel)
   - Messages updated to reflect deletion instead of deactivation

### Automatic Deactivation Logic

1. **Fixed password**: Uses "f26560291b" instead of random password
2. **API format**: Includes `is_sudo: false` parameter
3. **Preservation**: Admin remains in database as deactivated (not deleted)
4. **Original password storage**: Stored for restoration when reactivated

### Password Restoration

1. **Enhanced restoration**: Uses new API format with `is_sudo` parameter
2. **Database sync**: Updates both Marzban and local database
3. **Reactivation support**: Allows full restoration of admin functionality

## Function Signatures

### Core Functions

```python
# Complete deletion (manual deactivation)
async def delete_admin_panel_completely(admin_id: int, reason: str = "غیرفعالسازی دستی توسط سودو") -> bool

# Password change deactivation (automatic)
async def deactivate_admin_panel_by_id(admin_id: int, reason: str = "Limit exceeded") -> bool

# Updated API method
async def update_admin_password(admin_username: str, new_password: str, is_sudo: bool = False) -> bool
```

## Usage Flow

### Manual Deactivation Flow
1. Sudo admin clicks "حذف پنل" button
2. System shows list of active panels
3. Sudo admin selects panel to delete
4. System calls `delete_admin_panel_completely()`
5. All users deleted from Marzban
6. Admin deleted from Marzban
7. Admin record removed from database
8. Action logged

### Automatic Deactivation Flow
1. Monitoring system detects limit exceeded
2. System calls `deactivate_admin_panel_by_id()`
3. Original password stored in database
4. Admin password changed to "f26560291b" using new API
5. Admin marked as deactivated in database (not deleted)
6. Users disabled
7. Action logged

### Reactivation Flow
1. Sudo admin selects deactivated admin for reactivation
2. System restores original password using new API format
3. Admin marked as active in database
4. Users reactivated
5. Action logged

## Testing

The implementation includes comprehensive tests in `test_deactivation_changes.py` that verify:
- API format compliance
- Manual vs automatic deactivation behavior
- Password management
- Database operations

## Compatibility

- Backward compatible with existing admin management
- Maintains all existing functionality
- Supports multi-panel per user architecture
- Preserves logging and notification systems

## Security Notes

- Original passwords are securely stored and restored
- Fixed password "f26560291b" used only for automatic deactivation
- All API calls include proper authentication
- Complete deletion ensures no data remnants for manual deactivation