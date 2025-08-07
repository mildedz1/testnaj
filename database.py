import aiosqlite
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from models.schemas import AdminModel, UsageReportModel, LogModel
import config


class Database:
    def __init__(self, db_path: str = config.DATABASE_PATH):
        self.db_path = db_path

    async def init_db(self):
        """Initialize database and create tables if they don't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            # Check if we need to migrate the old schema
            try:
                # Check if the old UNIQUE constraint exists
                async with db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='admins'") as cursor:
                    row = await cursor.fetchone()
                    if row and "user_id INTEGER UNIQUE NOT NULL" in row[0]:
                        print("Migrating database schema to support multiple admin panels per user...")
                        await self._migrate_admin_table(db)
                        await db.commit()
                        print("Database migration completed successfully!")
            except Exception as e:
                print(f"Error checking schema: {e}")
            
            # Create admins table - removed UNIQUE constraint on user_id to allow multiple panels per user
            await db.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    admin_name TEXT,
                    marzban_username TEXT UNIQUE,
                    marzban_password TEXT,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    max_users INTEGER DEFAULT 10,
                    max_total_time INTEGER DEFAULT 2592000,
                    max_total_traffic INTEGER DEFAULT 107374182400,
                    validity_days INTEGER DEFAULT 30,
                    is_active BOOLEAN DEFAULT 1,
                    original_password TEXT,
                    deactivated_at TIMESTAMP,
                    deactivated_reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Add new columns if they don't exist (for migration)
            try:
                await db.execute("ALTER TABLE admins ADD COLUMN admin_name TEXT")
            except aiosqlite.OperationalError:
                pass  # Column already exists
                
            try:
                await db.execute("ALTER TABLE admins ADD COLUMN marzban_username TEXT")
            except aiosqlite.OperationalError:
                pass  # Column already exists
                
            try:
                await db.execute("ALTER TABLE admins ADD COLUMN marzban_password TEXT")
            except aiosqlite.OperationalError:
                pass  # Column already exists
                
            try:
                await db.execute("ALTER TABLE admins ADD COLUMN validity_days INTEGER DEFAULT 30")
            except aiosqlite.OperationalError:
                pass  # Column already exists
            
            try:
                await db.execute("ALTER TABLE admins ADD COLUMN original_password TEXT")
            except aiosqlite.OperationalError:
                pass  # Column already exists
            
            try:
                await db.execute("ALTER TABLE admins ADD COLUMN deactivated_at TIMESTAMP")
            except aiosqlite.OperationalError:
                pass  # Column already exists
                
            try:
                await db.execute("ALTER TABLE admins ADD COLUMN deactivated_reason TEXT")
            except aiosqlite.OperationalError:
                pass  # Column already exists

            # Create usage_reports table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS usage_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_user_id INTEGER NOT NULL,
                    check_time TIMESTAMP NOT NULL,
                    current_users INTEGER DEFAULT 0,
                    current_total_time INTEGER DEFAULT 0,
                    current_total_traffic INTEGER DEFAULT 0,
                    users_data TEXT,
                    FOREIGN KEY (admin_user_id) REFERENCES admins(user_id)
                )
            """)

            # Create logs table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_user_id INTEGER,
                    action TEXT NOT NULL,
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (admin_user_id) REFERENCES admins(user_id)
                )
            """)

            # Create cumulative_traffic table for persistent traffic tracking
            await db.execute("""
                CREATE TABLE IF NOT EXISTS cumulative_traffic (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER NOT NULL,
                    total_traffic_consumed INTEGER DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (admin_id) REFERENCES admins(id)
                )
            """)

            # Create unique index on admin_id for cumulative_traffic
            await db.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_cumulative_traffic_admin_id 
                ON cumulative_traffic(admin_id)
            """)

            # Create time_usage_override table for manual time adjustments
            await db.execute("""
                CREATE TABLE IF NOT EXISTS time_usage_override (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER NOT NULL,
                    override_time_used INTEGER DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (admin_id) REFERENCES admins(id)
                )
            """)

            # Create unique index on admin_id for time_usage_override
            await db.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_time_usage_override_admin_id 
                ON time_usage_override(admin_id)
            """)

            # Create panel sales products table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sales_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    price INTEGER NOT NULL,
                    currency TEXT DEFAULT 'تومان',
                    max_users INTEGER NOT NULL,
                    max_traffic INTEGER NOT NULL,
                    max_time INTEGER NOT NULL,
                    validity_days INTEGER DEFAULT 30,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create payment methods table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS payment_methods (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    method_name TEXT NOT NULL,
                    card_number TEXT,
                    card_holder_name TEXT,
                    bank_name TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create sales orders table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sales_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_user_id INTEGER NOT NULL,
                    customer_username TEXT,
                    customer_first_name TEXT,
                    customer_last_name TEXT,
                    product_id INTEGER NOT NULL,
                    product_snapshot TEXT,
                    total_price INTEGER NOT NULL,
                    payment_method_id INTEGER,
                    payment_screenshot_file_id TEXT,
                    status TEXT DEFAULT 'pending',
                    admin_notes TEXT,
                    created_panel_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP,
                    FOREIGN KEY (product_id) REFERENCES sales_products(id),
                    FOREIGN KEY (payment_method_id) REFERENCES payment_methods(id),
                    FOREIGN KEY (created_panel_id) REFERENCES admins(id)
                )
            """)

            # Create extension requests table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS extension_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER NOT NULL,
                    admin_user_id INTEGER NOT NULL,
                    request_type TEXT NOT NULL,
                    requested_amount INTEGER NOT NULL,
                    total_price INTEGER NOT NULL,
                    payment_method_id INTEGER,
                    payment_screenshot_file_id TEXT,
                    status TEXT DEFAULT 'pending',
                    admin_notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP,
                    FOREIGN KEY (admin_id) REFERENCES admins(id),
                    FOREIGN KEY (payment_method_id) REFERENCES payment_methods(id)
                )
            """)

            # Initialize cumulative traffic tracking for existing admins
            await self._initialize_cumulative_tracking_for_existing_admins(db)

            await db.commit()

    async def _migrate_admin_table(self, db):
        """Migrate the admins table to remove UNIQUE constraint on user_id."""
        # Create new table without UNIQUE constraint
        await db.execute("""
            CREATE TABLE admins_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                admin_name TEXT,
                marzban_username TEXT UNIQUE,
                marzban_password TEXT,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                max_users INTEGER DEFAULT 10,
                max_total_time INTEGER DEFAULT 2592000,
                max_total_traffic INTEGER DEFAULT 107374182400,
                validity_days INTEGER DEFAULT 30,
                is_active BOOLEAN DEFAULT 1,
                original_password TEXT,
                deactivated_at TIMESTAMP,
                deactivated_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Copy data from old table to new table
        await db.execute("""
            INSERT INTO admins_new (id, user_id, admin_name, marzban_username, marzban_password, 
                                  username, first_name, last_name, max_users, max_total_time, 
                                  max_total_traffic, validity_days, is_active, original_password, 
                                  deactivated_at, deactivated_reason, created_at, updated_at)
            SELECT id, user_id, admin_name, marzban_username, marzban_password, 
                   username, first_name, last_name, max_users, max_total_time, 
                   max_total_traffic, validity_days, is_active, original_password, 
                   deactivated_at, deactivated_reason, created_at, updated_at
            FROM admins
        """)
        
        # Drop old table and rename new table
        await db.execute("DROP TABLE admins")
        await db.execute("ALTER TABLE admins_new RENAME TO admins")

    async def _initialize_cumulative_tracking_for_existing_admins(self, db):
        """Initialize cumulative traffic tracking for all existing admins in the database."""
        try:
            print("Initializing cumulative traffic tracking for existing admins...")
            async with db.execute("SELECT id FROM admins") as cursor:
                admin_ids = [row[0] for row in await cursor.fetchall()]

            for admin_id in admin_ids:
                try:
                    await db.execute("""
                        INSERT OR IGNORE INTO cumulative_traffic (admin_id, total_traffic_consumed, last_updated)
                        VALUES (?, 0, CURRENT_TIMESTAMP)
                    """, (admin_id,))
                except Exception as e:
                    print(f"Error initializing cumulative traffic for admin {admin_id}: {e}")
            print(f"Cumulative traffic tracking initialized for {len(admin_ids)} existing admins.")
        except Exception as e:
            print(f"Error initializing cumulative traffic for existing admins: {e}")

    async def add_admin(self, admin: AdminModel) -> int:
        """Add a new admin to the database. Returns admin_id on success, 0 on failure."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    INSERT INTO admins (user_id, admin_name, marzban_username, marzban_password,
                                      username, first_name, last_name, 
                                      max_users, max_total_time, max_total_traffic, validity_days,
                                      is_active, original_password, deactivated_at, deactivated_reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (admin.user_id, admin.admin_name, admin.marzban_username, admin.marzban_password,
                      admin.username, admin.first_name, admin.last_name,
                      admin.max_users, admin.max_total_time, admin.max_total_traffic, admin.validity_days,
                      admin.is_active, admin.original_password, admin.deactivated_at, admin.deactivated_reason))
                
                # Get the new admin ID and initialize cumulative tracking
                new_admin_id = cursor.lastrowid
                await db.execute("""
                    INSERT OR IGNORE INTO cumulative_traffic (admin_id, total_traffic_consumed, last_updated)
                    VALUES (?, 0, CURRENT_TIMESTAMP)
                """, (new_admin_id,))
                
                await db.commit()
                return new_admin_id
        except aiosqlite.IntegrityError as e:
            print(f"Admin already exists (marzban_username must be unique): {e}")
            print(f"Failed to add admin with marzban_username: {admin.marzban_username}")
            return 0
        except Exception as e:
            print(f"Error adding admin: {e}")
            print(f"Admin data: user_id={admin.user_id}, marzban_username={admin.marzban_username}")
            import traceback
            traceback.print_exc()
            return 0

    async def add_admin_legacy(self, admin: AdminModel) -> bool:
        """Legacy wrapper for add_admin that returns bool for backward compatibility."""
        result = await self.add_admin(admin)
        return result > 0

    async def get_admin(self, user_id: int) -> Optional[AdminModel]:
        """Get first admin by user_id for backward compatibility."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT * FROM admins WHERE user_id = ? ORDER BY created_at ASC LIMIT 1", (user_id,)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return AdminModel(**dict(row))
                    return None
        except Exception as e:
            print(f"Error getting admin: {e}")
            return None

    async def get_admins_for_user(self, user_id: int) -> List[AdminModel]:
        """Get all admins for a specific user_id."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT * FROM admins WHERE user_id = ? ORDER BY created_at DESC", (user_id,)) as cursor:
                    rows = await cursor.fetchall()
                    return [AdminModel(**dict(row)) for row in rows]
        except Exception as e:
            print(f"Error getting admins for user: {e}")
            return []

    async def get_admin_by_marzban_username(self, marzban_username: str) -> Optional[AdminModel]:
        """Get admin by marzban username."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT * FROM admins WHERE marzban_username = ?", (marzban_username,)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return AdminModel(**dict(row))
                    return None
        except Exception as e:
            print(f"Error getting admin by marzban username: {e}")
            return None

    async def get_admin_by_id(self, admin_id: int) -> Optional[AdminModel]:
        """Get admin by admin ID."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT * FROM admins WHERE id = ?", (admin_id,)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return AdminModel(**dict(row))
                    return None
        except Exception as e:
            print(f"Error getting admin by ID: {e}")
            return None

    async def get_all_admins(self) -> List[AdminModel]:
        """Get all admins."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT * FROM admins ORDER BY created_at DESC") as cursor:
                    rows = await cursor.fetchall()
                    return [AdminModel(**dict(row)) for row in rows]
        except Exception as e:
            print(f"Error getting all admins: {e}")
            return []

    async def update_admin(self, admin_id: int, **kwargs) -> bool:
        """Update admin data by admin ID."""
        try:
            if not kwargs:
                return False
            
            set_clause = ", ".join([f"{key} = ?" for key in kwargs.keys()])
            values = list(kwargs.values()) + [admin_id]
            
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(f"""
                    UPDATE admins SET {set_clause}, updated_at = CURRENT_TIMESTAMP 
                    WHERE id = ?
                """, values)
                await db.commit()
                return True
        except Exception as e:
            print(f"Error updating admin: {e}")
            return False

    async def update_admin_by_user_id(self, user_id: int, **kwargs) -> bool:
        """Update admin data by user_id (for backward compatibility)."""
        try:
            if not kwargs:
                return False
            
            set_clause = ", ".join([f"{key} = ?" for key in kwargs.keys()])
            values = list(kwargs.values()) + [user_id]
            
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(f"""
                    UPDATE admins SET {set_clause}, updated_at = CURRENT_TIMESTAMP 
                    WHERE user_id = ? 
                    ORDER BY created_at ASC LIMIT 1
                """, values)
                await db.commit()
                return True
        except Exception as e:
            print(f"Error updating admin by user_id: {e}")
            return False

    async def remove_admin(self, user_id: int) -> bool:
        """Remove first admin from database by user_id (for backward compatibility)."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM admins WHERE user_id = ? ORDER BY created_at ASC LIMIT 1", (user_id,))
                await db.commit()
                return True
        except Exception as e:
            print(f"Error removing admin: {e}")
            return False

    async def remove_admin_by_id(self, admin_id: int) -> bool:
        """Remove admin from database by admin ID."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM admins WHERE id = ?", (admin_id,))
                await db.commit()
                return True
        except Exception as e:
            print(f"Error removing admin by ID: {e}")
            return False

    async def add_usage_report(self, report: UsageReportModel) -> bool:
        """Add usage report."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO usage_reports (admin_user_id, check_time, current_users, 
                                             current_total_time, current_total_traffic, users_data)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (report.admin_user_id, report.check_time, report.current_users,
                      report.current_total_time, report.current_total_traffic, report.users_data))
                await db.commit()
                return True
        except Exception as e:
            print(f"Error adding usage report: {e}")
            return False

    async def get_latest_usage_report(self, admin_user_id: int) -> Optional[UsageReportModel]:
        """Get latest usage report for admin."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("""
                    SELECT * FROM usage_reports WHERE admin_user_id = ? 
                    ORDER BY check_time DESC LIMIT 1
                """, (admin_user_id,)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return UsageReportModel(**dict(row))
                    return None
        except Exception as e:
            print(f"Error getting latest usage report: {e}")
            return None

    async def add_log(self, log: LogModel) -> bool:
        """Add log entry."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO logs (admin_user_id, action, details, timestamp)
                    VALUES (?, ?, ?, ?)
                """, (log.admin_user_id, log.action, log.details, log.timestamp))
                await db.commit()
                return True
        except Exception as e:
            print(f"Error adding log: {e}")
            return False

    async def get_logs(self, admin_user_id: Optional[int] = None, limit: int = 100) -> List[LogModel]:
        """Get logs, optionally filtered by admin."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                if admin_user_id:
                    query = "SELECT * FROM logs WHERE admin_user_id = ? ORDER BY timestamp DESC LIMIT ?"
                    params = (admin_user_id, limit)
                else:
                    query = "SELECT * FROM logs ORDER BY timestamp DESC LIMIT ?"
                    params = (limit,)
                
                async with db.execute(query, params) as cursor:
                    rows = await cursor.fetchall()
                    return [LogModel(**dict(row)) for row in rows]
        except Exception as e:
            print(f"Error getting logs: {e}")
            return []

    async def is_admin_authorized(self, user_id: int) -> bool:
        """Check if user is authorized admin (has at least one active admin panel)."""
        if user_id in config.SUDO_ADMINS:
            return True
        
        admins = await self.get_admins_for_user(user_id)
        return any(admin.is_active for admin in admins)

    async def deactivate_admin(self, admin_id: int, reason: str = "Limit exceeded") -> bool:
        """Deactivate admin by admin ID and store original password."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE admins SET 
                        is_active = 0, 
                        deactivated_at = CURRENT_TIMESTAMP,
                        deactivated_reason = ?,
                        updated_at = CURRENT_TIMESTAMP 
                    WHERE id = ?
                """, (reason, admin_id))
                await db.commit()
                return True
        except Exception as e:
            print(f"Error deactivating admin: {e}")
            return False

    async def deactivate_admin_by_user_id(self, user_id: int, reason: str = "Limit exceeded") -> bool:
        """Deactivate admin by user_id (for backward compatibility)."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE admins SET 
                        is_active = 0, 
                        deactivated_at = CURRENT_TIMESTAMP,
                        deactivated_reason = ?,
                        updated_at = CURRENT_TIMESTAMP 
                    WHERE user_id = ?
                """, (reason, user_id))
                await db.commit()
                return True
        except Exception as e:
            print(f"Error deactivating admin: {e}")
            return False

    async def reactivate_admin(self, admin_id: int) -> bool:
        """Reactivate admin by admin ID and restore original password."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE admins SET 
                        is_active = 1, 
                        deactivated_at = NULL,
                        deactivated_reason = NULL,
                        updated_at = CURRENT_TIMESTAMP 
                    WHERE id = ?
                """, (admin_id,))
                await db.commit()
                return True
        except Exception as e:
            print(f"Error reactivating admin: {e}")
            return False

    async def reactivate_admin_by_user_id(self, user_id: int) -> bool:
        """Reactivate admin by user_id (for backward compatibility)."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE admins SET 
                        is_active = 1, 
                        deactivated_at = NULL,
                        deactivated_reason = NULL,
                        updated_at = CURRENT_TIMESTAMP 
                    WHERE user_id = ?
                """, (user_id,))
                await db.commit()
                return True
        except Exception as e:
            print(f"Error reactivating admin: {e}")
            return False

    async def get_deactivated_admins(self) -> List[AdminModel]:
        """Get all deactivated admins."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT * FROM admins WHERE is_active = 0 ORDER BY deactivated_at DESC") as cursor:
                    rows = await cursor.fetchall()
                    return [AdminModel(**dict(row)) for row in rows]
        except Exception as e:
            print(f"Error getting deactivated admins: {e}")
            return []

    async def get_cumulative_traffic(self, admin_id: int) -> int:
        """Get cumulative traffic consumed for an admin."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT total_traffic_consumed FROM cumulative_traffic WHERE admin_id = ?", 
                    (admin_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row else 0
        except Exception as e:
            print(f"Error getting cumulative traffic for admin {admin_id}: {e}")
            return 0

    async def update_cumulative_traffic(self, admin_id: int, current_traffic: int) -> bool:
        """Update cumulative traffic for an admin (only increases, never decreases)."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Get current cumulative traffic
                current_cumulative = await self.get_cumulative_traffic(admin_id)
                
                # Only update if current traffic is higher than stored cumulative
                if current_traffic > current_cumulative:
                    await db.execute("""
                        INSERT OR REPLACE INTO cumulative_traffic (admin_id, total_traffic_consumed, last_updated)
                        VALUES (?, ?, CURRENT_TIMESTAMP)
                    """, (admin_id, current_traffic))
                    await db.commit()
                    return True
                return False
        except Exception as e:
            print(f"Error updating cumulative traffic for admin {admin_id}: {e}")
            return False

    async def add_to_cumulative_traffic(self, admin_id: int, traffic_to_add: int) -> bool:
        """Add traffic to cumulative total (used when users are deleted)."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Get current cumulative traffic
                current_cumulative = await self.get_cumulative_traffic(admin_id)
                new_total = current_cumulative + traffic_to_add
                
                await db.execute("""
                    INSERT OR REPLACE INTO cumulative_traffic (admin_id, total_traffic_consumed, last_updated)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """, (admin_id, new_total))
                await db.commit()
                return True
        except Exception as e:
            print(f"Error adding to cumulative traffic for admin {admin_id}: {e}")
            return False

    async def initialize_cumulative_traffic(self, admin_id: int) -> bool:
        """Initialize cumulative traffic tracking for an admin if not exists."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT OR IGNORE INTO cumulative_traffic (admin_id, total_traffic_consumed, last_updated)
                    VALUES (?, 0, CURRENT_TIMESTAMP)
                """, (admin_id,))
                await db.commit()
                return True
        except Exception as e:
            print(f"Error initializing cumulative traffic for admin {admin_id}: {e}")
            return False

    async def is_admin_expired(self, admin_id: int) -> bool:
        """Check if admin has expired based on created_at and validity_days."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT created_at, validity_days FROM admins WHERE id = ?", 
                    (admin_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        return True  # Admin not found, consider expired
                    
                    created_at_str, validity_days = row
                    if not created_at_str or not validity_days:
                        return False  # No expiration info, don't expire
                    
                    # Parse creation time
                    created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                    
                    # Calculate expiration time
                    expiration_time = created_at.timestamp() + (validity_days * 24 * 3600)
                    current_time = datetime.now().timestamp()
                    
                    return current_time > expiration_time
        except Exception as e:
            print(f"Error checking admin expiration for admin {admin_id}: {e}")
            return False  # Don't expire on error
    
    async def get_admin_remaining_days(self, admin_id: int) -> int:
        """Get remaining days for admin before expiration."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT created_at, validity_days FROM admins WHERE id = ?", 
                    (admin_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        return 0  # Admin not found
                    
                    created_at_str, validity_days = row
                    if not created_at_str or not validity_days:
                        return validity_days or 0  # Return original validity if no creation time
                    
                    # Parse creation time
                    created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                    
                    # Calculate remaining time
                    expiration_time = created_at.timestamp() + (validity_days * 24 * 3600)
                    current_time = datetime.now().timestamp()
                    remaining_seconds = expiration_time - current_time
                    
                    # Convert to days (round up)
                    remaining_days = max(0, int(remaining_seconds / (24 * 3600)) + (1 if remaining_seconds % (24 * 3600) > 0 else 0))
                    return remaining_days
        except Exception as e:
            print(f"Error getting remaining days for admin {admin_id}: {e}")
            return 0

    async def execute_query(self, query: str, params: tuple):
        """Execute a custom query with parameters."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(query, params)
                await db.commit()
                return True
        except Exception as e:
            print(f"Error executing query: {e}")
            return False

    async def update_admin_max_users(self, admin_id: int, max_users: int) -> bool:
        """Update admin's max users limit."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE admins SET max_users = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (max_users, admin_id))
                await db.commit()
                return True
        except Exception as e:
            print(f"Error updating admin max users: {e}")
            return False

    async def update_admin_max_traffic(self, admin_id: int, max_traffic: int) -> bool:
        """Update admin's max traffic limit."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE admins SET max_total_traffic = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (max_traffic, admin_id))
                await db.commit()
                return True
        except Exception as e:
            print(f"Error updating admin max traffic: {e}")
            return False

    async def update_admin_max_time(self, admin_id: int, max_time: int) -> bool:
        """Update admin's max time limit."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE admins SET max_total_time = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (max_time, admin_id))
                await db.commit()
                return True
        except Exception as e:
            print(f"Error updating admin max time: {e}")
            return False

    async def set_time_usage_reset(self, admin_id: int, reset_time_seconds: int) -> bool:
        """Set a time usage reset point for an admin."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Store reset point with current timestamp
                await db.execute("""
                    INSERT OR REPLACE INTO time_usage_override 
                    (admin_id, override_time_used, last_updated) 
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """, (admin_id, reset_time_seconds))
                await db.commit()
                
                # Get admin info for logging
                admin = await self.get_admin_by_id(admin_id)
                admin_user_id = admin.user_id if admin else 0
                
                # Log this action
                await db.execute("""
                    INSERT INTO logs (admin_user_id, action, details, timestamp) 
                    VALUES (?, ?, ?, ?)
                """, (admin_user_id, "time_usage_reset", f"Reset time usage to {reset_time_seconds} seconds", datetime.now().timestamp()))
                await db.commit()
                return True
        except Exception as e:
            print(f"Error setting time usage reset: {e}")
            return False

    async def get_time_usage_with_reset(self, admin_id: int, current_marzban_time: int) -> int:
        """Get time usage considering any reset points."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("""
                    SELECT override_time_used, last_updated FROM time_usage_override 
                    WHERE admin_id = ?
                """, (admin_id,)) as cursor:
                    row = await cursor.fetchone()
                    
                    if not row:
                        # No reset point, return Marzban time
                        return current_marzban_time
                    
                    reset_time, reset_timestamp = row
                    
                    # Handle different timestamp formats
                    if isinstance(reset_timestamp, str):
                        try:
                            reset_datetime = datetime.fromisoformat(reset_timestamp.replace('Z', '+00:00'))
                        except:
                            reset_datetime = datetime.strptime(reset_timestamp, '%Y-%m-%d %H:%M:%S')
                    else:
                        reset_datetime = reset_timestamp
                    
                    # Calculate elapsed time since reset
                    elapsed_since_reset = (datetime.now() - reset_datetime).total_seconds()
                    
                    # Return reset point + elapsed time
                    return int(reset_time + elapsed_since_reset)
                    
        except Exception as e:
            print(f"Error calculating time usage with reset: {e}")
            return current_marzban_time

    async def clear_time_usage_reset(self, admin_id: int) -> bool:
        """Clear time usage reset for an admin."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    DELETE FROM time_usage_override WHERE admin_id = ?
                """, (admin_id,))
                await db.commit()
                return True
        except Exception as e:
            print(f"Error clearing time usage reset: {e}")
            return False

    # Sales System Functions
    
    async def add_sales_product(self, name: str, description: str, price: int, max_users: int, 
                               max_traffic: int, max_time: int, validity_days: int = 30) -> bool:
        """Add a new sales product."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO sales_products (name, description, price, max_users, max_traffic, max_time, validity_days)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (name, description, price, max_users, max_traffic, max_time, validity_days))
                await db.commit()
                return True
        except Exception as e:
            print(f"Error adding sales product: {e}")
            return False

    async def get_sales_products(self, active_only: bool = True):
        """Get all sales products."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                query = "SELECT * FROM sales_products"
                if active_only:
                    query += " WHERE is_active = 1"
                query += " ORDER BY price ASC"
                
                async with db.execute(query) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
        except Exception as e:
            print(f"Error getting sales products: {e}")
            return []

    async def update_sales_product(self, product_id: int, **kwargs) -> bool:
        """Update a sales product."""
        try:
            if not kwargs:
                return False
            
            set_clause = ", ".join([f"{key} = ?" for key in kwargs.keys()])
            values = list(kwargs.values()) + [product_id]
            
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(f"""
                    UPDATE sales_products SET {set_clause}, updated_at = CURRENT_TIMESTAMP 
                    WHERE id = ?
                """, values)
                await db.commit()
                return True
        except Exception as e:
            print(f"Error updating sales product: {e}")
            return False

    async def add_payment_method(self, method_name: str, card_number: str, 
                                card_holder_name: str, bank_name: str) -> bool:
        """Add a new payment method."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO payment_methods (method_name, card_number, card_holder_name, bank_name)
                    VALUES (?, ?, ?, ?)
                """, (method_name, card_number, card_holder_name, bank_name))
                await db.commit()
                return True
        except Exception as e:
            print(f"Error adding payment method: {e}")
            return False

    async def get_payment_methods(self, active_only: bool = True):
        """Get all payment methods."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                query = "SELECT * FROM payment_methods"
                if active_only:
                    query += " WHERE is_active = 1"
                query += " ORDER BY id ASC"
                
                async with db.execute(query) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
        except Exception as e:
            print(f"Error getting payment methods: {e}")
            return []

    async def get_payment_method_by_id(self, payment_id: int):
        """Get a payment method by ID."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT * FROM payment_methods WHERE id = ?", (payment_id,)) as cursor:
                    row = await cursor.fetchone()
                    return dict(row) if row else None
        except Exception as e:
            print(f"Error getting payment method by ID {payment_id}: {e}")
            return None

    async def create_sales_order(self, customer_user_id: int, customer_username: str,
                                customer_first_name: str, customer_last_name: str,
                                product_id: int, total_price: int, product_snapshot: str) -> int:
        """Create a new sales order."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    INSERT INTO sales_orders (customer_user_id, customer_username, customer_first_name, 
                                            customer_last_name, product_id, total_price, product_snapshot)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (customer_user_id, customer_username, customer_first_name, 
                      customer_last_name, product_id, total_price, product_snapshot))
                order_id = cursor.lastrowid
                await db.commit()
                return order_id
        except Exception as e:
            print(f"Error creating sales order: {e}")
            return 0

    async def update_order_payment(self, order_id: int, payment_method_id: int, screenshot_file_id: str) -> bool:
        """Update order with payment information."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE sales_orders SET payment_method_id = ?, payment_screenshot_file_id = ?
                    WHERE id = ?
                """, (payment_method_id, screenshot_file_id, order_id))
                await db.commit()
                return True
        except Exception as e:
            print(f"Error updating order payment: {e}")
            return False

    async def get_pending_orders(self):
        """Get all pending orders for admin review."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("""
                    SELECT o.*, p.name as product_name, p.description as product_description,
                           pm.method_name, pm.card_number
                    FROM sales_orders o
                    LEFT JOIN sales_products p ON o.product_id = p.id
                    LEFT JOIN payment_methods pm ON o.payment_method_id = pm.id
                    WHERE o.status = 'pending'
                    ORDER BY o.created_at ASC
                """) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
        except Exception as e:
            print(f"Error getting pending orders: {e}")
            return []

    async def approve_order(self, order_id: int, created_panel_id: int) -> bool:
        """Approve an order and mark panel as created."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE sales_orders SET status = 'approved', created_panel_id = ?, processed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (created_panel_id, order_id))
                await db.commit()
                return True
        except Exception as e:
            print(f"Error approving order: {e}")
            return False

    async def reject_order(self, order_id: int, admin_notes: str) -> bool:
        """Reject an order with notes."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE sales_orders SET status = 'rejected', admin_notes = ?, processed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (admin_notes, order_id))
                await db.commit()
                return True
        except Exception as e:
            print(f"Error rejecting order: {e}")
            return False

    async def get_order_by_id(self, order_id: int):
        """Get order details by ID."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("""
                    SELECT o.*, p.name as product_name, p.max_users, p.max_traffic, p.max_time, p.validity_days
                    FROM sales_orders o
                    LEFT JOIN sales_products p ON o.product_id = p.id
                    WHERE o.id = ?
                """, (order_id,)) as cursor:
                    row = await cursor.fetchone()
                    return dict(row) if row else None
        except Exception as e:
            print(f"Error getting order by ID: {e}")
            return None

    async def get_admin_by_marzban_username(self, marzban_username: str):
        """Get admin by marzban username."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("""
                    SELECT * FROM admins WHERE marzban_username = ?
                """, (marzban_username,)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return AdminModel(**dict(row))
                    return None
        except Exception as e:
            print(f"Error getting admin by marzban username: {e}")
            return None

    # Extension Requests Functions
    
    async def create_extension_request(self, admin_id: int, admin_user_id: int, 
                                     request_type: str, requested_amount: int, total_price: int) -> int:
        """Create a new extension request."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    INSERT INTO extension_requests (admin_id, admin_user_id, request_type, requested_amount, total_price)
                    VALUES (?, ?, ?, ?, ?)
                """, (admin_id, admin_user_id, request_type, requested_amount, total_price))
                request_id = cursor.lastrowid
                await db.commit()
                return request_id
        except Exception as e:
            print(f"Error creating extension request: {e}")
            return 0

    async def update_extension_request_payment(self, request_id: int, payment_method_id: int, screenshot_file_id: str) -> bool:
        """Update extension request with payment information."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE extension_requests SET payment_method_id = ?, payment_screenshot_file_id = ?
                    WHERE id = ?
                """, (payment_method_id, screenshot_file_id, request_id))
                await db.commit()
                return True
        except Exception as e:
            print(f"Error updating extension request payment: {e}")
            return False

    async def get_pending_extension_requests(self):
        """Get all pending extension requests for admin review."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("""
                    SELECT er.*, a.admin_name, a.marzban_username, pm.method_name, pm.card_number
                    FROM extension_requests er
                    LEFT JOIN admins a ON er.admin_id = a.id
                    LEFT JOIN payment_methods pm ON er.payment_method_id = pm.id
                    WHERE er.status = 'pending'
                    ORDER BY er.created_at ASC
                """) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
        except Exception as e:
            print(f"Error getting pending extension requests: {e}")
            return []

    async def approve_extension_request(self, request_id: int) -> bool:
        """Approve an extension request."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE extension_requests SET status = 'approved', processed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (request_id,))
                await db.commit()
                return True
        except Exception as e:
            print(f"Error approving extension request: {e}")
            return False

    async def reject_extension_request(self, request_id: int, admin_notes: str) -> bool:
        """Reject an extension request with notes."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE extension_requests SET status = 'rejected', admin_notes = ?, processed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (admin_notes, request_id))
                await db.commit()
                return True
        except Exception as e:
            print(f"Error rejecting extension request: {e}")
            return False

    async def get_extension_request_by_id(self, request_id: int):
        """Get extension request details by ID."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("""
                    SELECT er.*, a.admin_name, a.marzban_username, a.max_users, a.max_total_traffic, a.max_total_time
                    FROM extension_requests er
                    LEFT JOIN admins a ON er.admin_id = a.id
                    WHERE er.id = ?
                """, (request_id,)) as cursor:
                    row = await cursor.fetchone()
                    return dict(row) if row else None
        except Exception as e:
            print(f"Error getting extension request by ID: {e}")
            return None

    async def close(self):
        """Close database connection (placeholder for future connection pooling)."""
        pass


# Global database instance
db = Database()