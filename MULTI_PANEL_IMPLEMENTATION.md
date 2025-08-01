# Multi-Panel Admin System Implementation

## Summary

This implementation successfully addresses all three requirements from the problem statement:

## Requirement 1: Multiple Marzban panels per Telegram user

✅ **IMPLEMENTED**: The database schema has been designed to support multiple admin panels per Telegram user.

### Key Changes:
- Database uses unique constraint on `marzban_username` instead of `user_id`
- Each admin panel has a unique `id` for individual identification
- Added `admin_name` field to distinguish between panels
- Added `marzban_username` and `marzban_password` for individual authentication

### Database Schema:
```sql
CREATE TABLE admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,                -- Telegram user ID (can repeat)
    admin_name TEXT,                         -- Panel name (e.g., "Main Panel")
    marzban_username TEXT UNIQUE,            -- Unique Marzban username
    marzban_password TEXT,                   -- Panel-specific password
    username TEXT,                           -- Telegram username
    first_name TEXT,
    last_name TEXT,
    max_users INTEGER DEFAULT 10,
    max_total_time INTEGER DEFAULT 2592000,
    max_total_traffic INTEGER DEFAULT 107374182400,
    validity_days INTEGER DEFAULT 30,
    is_active BOOLEAN DEFAULT 1,
    original_password TEXT,                  -- For recovery after deactivation
    deactivated_at TIMESTAMP,
    deactivated_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

## Requirement 2: Individual authentication for each admin panel

✅ **IMPLEMENTED**: Each admin panel authenticates separately with its own credentials.

### Key Changes:
- **Scheduler Enhancement**: Uses individual admin credentials for each panel
- **MarzbanAdminAPI Class**: Separate API instance per admin panel
- **Sudo Handler Updates**: Displays information grouped by user but separated by panel

### Authentication Flow:
1. For each admin panel, create `MarzbanAdminAPI(marzban_url, admin_username, admin_password)`
2. Each panel gets its own token and makes separate API calls
3. Stats and user management happen per individual panel

### Updated Display Format:
```
👨‍💼 کاربر ID: 123456789
   🔹 Main Panel (admin_main) ✅ فعال
      👥 کاربران: 15/20 (75.0%)
      📊 ترافیک: 80GB/100GB (80.0%)
      ⏱️ زمان: 25 days/30 days (83.3%)
      
   🔹 Secondary Panel (admin_secondary) ✅ فعال
      👥 کاربران: 8/10 (80.0%)
      📊 ترافیک: 40GB/50GB (80.0%)
      ⏱️ زمان: 12 days/15 days (80.0%)
```

## Requirement 3: Complete admin deactivation procedure

✅ **IMPLEMENTED**: Full deactivation workflow including password randomization and user deactivation.

### Deactivation Process:
1. **Password Randomization**: Generate random password and update in Marzban
2. **Store Original Password**: Save for potential recovery
3. **User Deactivation**: Disable all users belonging to that admin panel
4. **Database Update**: Mark admin as inactive with reason and timestamp
5. **Sudo Notification**: Notify all sudo admins about the deactivation
6. **Logging**: Record all actions in the logs table

### Enhanced Functions:
- `deactivate_admin_panel_by_id(admin_id, reason)`: Deactivate specific panel
- `deactivate_admin_and_users(admin_user_id, reason)`: Backward compatibility
- Individual user deactivation using `modify_user` API

### Automatic Triggers:
- Scheduler monitors each panel individually
- When limits exceeded: automatic deactivation triggered
- Separate handling for each admin panel

## Implementation Details

### Files Modified:

1. **`database.py`**:
   - Already supported multi-panel schema
   - Added methods for admin panel management by ID
   - Enhanced with individual panel operations

2. **`scheduler.py`**:
   - Updated to work with individual admin panel IDs
   - Uses separate authentication per panel
   - Enhanced deactivation logic

3. **`handlers/sudo_handlers.py`**:
   - Enhanced admin display functions
   - Added new deactivation functions
   - Improved admin listing with panel grouping

4. **`marzban_api.py`**:
   - Fixed duplicate code
   - Enhanced individual admin API support
   - Added admin credential management

### Test Coverage:

- **`test_multi_panel.py`**: Basic multi-panel functionality
- **`test_requirements.py`**: Comprehensive requirement verification
- **`test_fsm_admin_addition.py`**: FSM and database schema tests

## Usage Examples

### Adding Multiple Panels:
```python
# First panel for user
admin1 = AdminModel(
    user_id=123456789,
    admin_name="Main Panel",
    marzban_username="admin_main",
    marzban_password="secure_pass_1",
    max_users=20
)

# Second panel for same user
admin2 = AdminModel(
    user_id=123456789,
    admin_name="Backup Panel", 
    marzban_username="admin_backup",
    marzban_password="secure_pass_2",
    max_users=10
)
```

### Individual Panel Authentication:
```python
# Get all panels for user
panels = await db.get_admins_for_user(123456789)

for panel in panels:
    # Create separate API instance
    admin_api = await marzban_api.create_admin_api(
        panel.marzban_username, 
        panel.marzban_password
    )
    
    # Get panel-specific stats
    stats = await admin_api.get_admin_stats()
    users = await admin_api.get_users()
```

### Panel Deactivation:
```python
# Deactivate specific panel
success = await deactivate_admin_panel_by_id(
    admin_id=panel.id, 
    reason="Limit exceeded - 95% traffic usage"
)
```

## Backward Compatibility

All existing functionality remains compatible:
- Old methods still work for single-panel users
- Database migration handles existing data
- API maintains existing interfaces

## Security Enhancements

- Individual password management per panel
- Secure password generation for deactivation
- Original password storage for recovery
- Comprehensive logging of all actions

## Performance Considerations

- Efficient database queries with proper indexing
- Rate-limited API calls to prevent overload
- Asynchronous operations for better performance
- Minimal overhead for multi-panel operations

## Error Handling

- Graceful handling of API failures
- Fallback mechanisms for critical operations
- Comprehensive error logging
- User-friendly error messages

This implementation fully satisfies all requirements while maintaining system stability and performance.