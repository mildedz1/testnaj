# Admin Deactivation & Enhanced FSM Implementation

## Overview
This implementation addresses the FSM state handling issue and adds comprehensive admin deactivation functionality to the Marzban Admin Bot.

## 🔧 Changes Made

### 1. Database Schema Enhancements
- **AdminModel** extended with new fields:
  - `original_password`: Stores admin's original password for reactivation
  - `deactivated_at`: Timestamp when admin was deactivated
  - `deactivated_reason`: Reason for deactivation (e.g., limit exceeded)

- **Database Methods** added:
  - `deactivate_admin()`: Deactivate admin with reason
  - `reactivate_admin()`: Reactivate admin and clear deactivation data
  - `get_deactivated_admins()`: Get list of all deactivated admins

### 2. FSM State Management Fixes
- ✅ **Handler Registration Order**: State-specific handlers registered BEFORE general handlers
- ✅ **State-Aware General Handlers**: Check for active FSM states before processing messages
- ✅ **Enhanced Logging**: Comprehensive state transition logging
- ✅ **Error Handling**: Proper state preservation and clearing

### 3. Admin Deactivation System

#### Automatic Deactivation Triggers
When an admin exceeds any limit:
- **User Limit**: More users than allowed
- **Traffic Limit**: More traffic consumed than allowed  
- **Time Limit**: More time used than allowed

#### Deactivation Process
1. **Password Randomization**: Admin's password is changed to a random value
2. **User Deactivation**: All admin's active users are disabled
3. **Database Update**: Admin marked as deactivated with reason and timestamp
4. **Notification**: Sudo admins notified about the deactivation
5. **Logging**: Action logged for audit trail

#### Reactivation Process (Sudo Admin Only)
1. **Select Admin**: Choose from list of deactivated admins
2. **Password Restoration**: Original password restored (if available)
3. **User Reactivation**: Admin's users are reactivated
4. **Database Update**: Admin marked as active, deactivation data cleared
5. **Notification**: Admin notified about reactivation

### 4. Enhanced UI Components

#### New Sudo Admin Features
- **🔄 Activate Admin Button**: Added to main sudo keyboard
- **📋 Deactivated Admin List**: Shows admins awaiting reactivation
- **📊 Enhanced Status Display**: Shows activation status in admin lists

#### Commands Added
- `/activate_admin`: CLI command for activating deactivated admins
- Enhanced help text includes new functionality

### 5. Marzban API Extensions
- `update_admin_password()`: Update admin password in Marzban
- `get_admin_users()`: Get all users belonging to a specific admin

### 6. Scheduler Enhancements
- **Auto-Deactivation**: When limits exceeded, automatically deactivate admin and users
- **Enhanced Notifications**: Detailed limit exceeded notifications
- **Comprehensive Logging**: All actions logged with context

### 7. Persian Language Support
New messages added for all deactivation/reactivation scenarios:
- Admin deactivation notifications
- Reactivation confirmations
- Error messages
- Help text updates

## 🚀 How It Works

### Normal Operation Flow
1. **Monitoring**: Scheduler checks admin limits every 10 minutes (configurable)
2. **Warning**: At 80% of any limit, warning sent to admin
3. **Enforcement**: At 100% of any limit, auto-deactivation triggered

### Deactivation Flow
```
Limit Exceeded → Password Randomized → Users Disabled → Admin Deactivated → Sudo Notified
```

### Reactivation Flow  
```
Sudo Selection → Password Restored → Users Enabled → Admin Activated → Admin Notified
```

## 🔍 Testing & Validation

### FSM State Tests
- ✅ Handler registration order verified
- ✅ State transitions work correctly
- ✅ No interference from general handlers
- ✅ Proper error handling and recovery

### Deactivation Tests
- ✅ Database schema migration works
- ✅ Admin deactivation/reactivation cycle
- ✅ User deactivation/reactivation
- ✅ Notification system
- ✅ Logging and audit trail

### Integration Tests
- ✅ All handlers properly registered
- ✅ UI components work correctly
- ✅ API extensions functional
- ✅ Scheduler enhancements active

## 📋 Usage Instructions

### For Sudo Admins

#### Via UI (Recommended)
1. Start bot with `/start`
2. Click **🔄 Activate Admin** button
3. Select deactivated admin from list
4. Confirm reactivation

#### Via Commands
```
/activate_admin - Show deactivated admins for reactivation
/admin_status - View detailed status including deactivated admins
```

### For Regular Admins
- **Automatic**: Deactivation happens automatically when limits exceeded
- **Notification**: Will receive notification when reactivated
- **No Action Required**: Cannot self-reactivate (security measure)

## 🛡️ Security Features

1. **Permission Control**: Only sudo admins can reactivate
2. **Password Security**: Passwords randomized during deactivation
3. **User Protection**: Users automatically disabled when admin deactivated
4. **Audit Trail**: All actions logged with timestamps and reasons
5. **State Protection**: FSM states protected from interference

## 🔧 Configuration

### Environment Variables
- `MONITORING_INTERVAL`: How often to check limits (seconds, default: 600)
- `WARNING_THRESHOLD`: When to send warnings (percentage, default: 0.8)

### Admin Limits
- `max_users`: Maximum number of users
- `max_total_time`: Maximum time in seconds
- `max_total_traffic`: Maximum traffic in bytes

## 📊 Monitoring & Logs

### Log Types
- `admin_deactivated`: When admin automatically deactivated
- `admin_reactivated`: When admin reactivated by sudo
- `users_disabled_by_system`: When users disabled due to limits
- `admin_auto_deactivated`: Enhanced deactivation with context

### Monitoring Points
- Active admin count
- Deactivated admin count
- Limit violation frequency
- Reactivation requests

## 🎯 Benefits

1. **Automatic Enforcement**: No manual intervention needed for limit violations
2. **Complete Isolation**: Deactivated admins cannot access or affect system
3. **Easy Recovery**: Simple reactivation process for sudo admins
4. **Audit Compliance**: Complete trail of all actions
5. **User Protection**: Users automatically managed with admin status
6. **Robust FSM**: No more stuck states or lost sessions

## 🔄 Migration Notes

- **Backward Compatible**: Existing admins continue to work normally
- **Database Migration**: New columns added automatically
- **No Downtime**: Changes can be deployed without service interruption
- **Existing Data**: All existing admin data preserved