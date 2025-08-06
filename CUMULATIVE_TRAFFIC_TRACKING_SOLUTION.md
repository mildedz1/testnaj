# Cumulative Traffic Tracking Solution

## Problem Statement

Previously, when admins deleted users, the total traffic consumption for the admin would decrease because the system only counted traffic from currently existing users. This caused issues where:

1. Admin's traffic statistics would decrease after user deletion
2. Admins could bypass traffic limits by deleting and recreating users
3. Historical traffic consumption data was lost

## Solution Overview

Implemented a cumulative traffic tracking system that maintains persistent traffic consumption records even after users are deleted.

## Implementation Details

### 1. Database Schema Changes

Added a new table `cumulative_traffic` to store persistent traffic consumption:

```sql
CREATE TABLE cumulative_traffic (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER NOT NULL,
    total_traffic_consumed INTEGER DEFAULT 0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (admin_id) REFERENCES admins(id)
);
```

### 2. Traffic Calculation Logic

Modified the traffic calculation in `marzban_api.py` to use cumulative tracking:

- **Before**: Only counted traffic from currently existing users
- **After**: Uses the maximum of current user traffic and stored cumulative traffic

Key changes in `get_admin_stats()` methods:
- Calculate current traffic from existing users
- Retrieve cumulative traffic from database
- Use `max(cumulative_traffic, current_traffic)` to ensure traffic never decreases
- Update cumulative traffic if current is higher

### 3. User Deletion Protection

Enhanced user deletion processes to preserve traffic before deletion:

#### In `delete_admin_completely()`:
- Calculate total traffic from all users before deletion
- Update cumulative traffic with this total
- Then proceed with user deletion

#### In `remove_user()`:
- Added `preserve_traffic` parameter (default: True)
- New `_preserve_user_traffic_before_deletion()` method
- Retrieves user's traffic consumption before deletion
- Adds it to admin's cumulative traffic total

### 4. Database Methods Added

New methods in `database.py`:

- `get_cumulative_traffic(admin_id)`: Get current cumulative traffic
- `update_cumulative_traffic(admin_id, traffic)`: Update if higher than current
- `add_to_cumulative_traffic(admin_id, traffic)`: Add traffic to cumulative total
- `initialize_cumulative_traffic(admin_id)`: Initialize tracking for an admin

### 5. Migration and Initialization

- Automatic migration initializes cumulative tracking for existing admins
- New admins automatically get cumulative tracking initialized
- Scheduler ensures cumulative tracking is initialized during monitoring

## How It Works

### Normal Operation:
1. System calculates current traffic from existing users
2. Compares with stored cumulative traffic
3. Uses the higher value (traffic can only increase or stay same)
4. Updates cumulative traffic if current is higher

### When Users Are Deleted:
1. Before deletion, user's traffic is preserved in cumulative tracking
2. User is deleted from Marzban
3. Current user traffic decreases, but cumulative traffic remains
4. Admin's total traffic shows cumulative value (no decrease)

### When Users Are Created:
1. New users start with 0 traffic
2. As they consume traffic, current traffic increases
3. When current exceeds cumulative, it becomes the new total
4. System seamlessly transitions between cumulative and current tracking

## Benefits

1. **Traffic Never Decreases**: Admin traffic consumption can only increase or stay the same
2. **Historical Accuracy**: All traffic consumption is preserved even after user deletion
3. **Limit Enforcement**: Prevents bypass of traffic limits through user manipulation
4. **Automatic Migration**: Existing systems are automatically upgraded
5. **Transparent Operation**: No changes needed to existing workflows

## Files Modified

- `database.py`: Added cumulative traffic table and methods
- `marzban_api.py`: Modified traffic calculation and user deletion
- `scheduler.py`: Added cumulative tracking initialization
- Migration logic for existing installations

## Usage

The system works automatically without any manual intervention required. Traffic tracking is now cumulative and persistent across user deletions and recreations.