import asyncio
import json
import logging
from datetime import datetime
from typing import List, Dict
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

import config
from database import db
from marzban_api import marzban_api
from models.schemas import UsageReportModel, LogModel, LimitCheckResult
from utils.notify import notify_limit_warning, notify_limit_exceeded

logger = logging.getLogger(__name__)


class MonitoringScheduler:
    def __init__(self, bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        self.is_running = False

    async def check_admin_limits(self, admin_user_id: int) -> LimitCheckResult:
        """Check if admin has exceeded or is approaching limits using their own credentials (backward compatibility)."""
        admin = await db.get_admin(admin_user_id)
        if not admin:
            return LimitCheckResult(admin_user_id=admin_user_id)
        return await self.check_admin_limits_by_id(admin.id)

    async def check_admin_limits_by_id(self, admin_id: int) -> LimitCheckResult:
        """Check if admin has exceeded or is approaching limits using their own credentials."""
        try:
            admin = await db.get_admin_by_id(admin_id)
            if not admin or not admin.is_active:
                return LimitCheckResult(admin_user_id=admin.user_id if admin else 0)
            
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

            # Initialize cumulative traffic tracking for this admin
            await db.initialize_cumulative_traffic(admin_id)

            # Use admin's own credentials for authentication
            admin_api = await marzban_api.create_admin_api(admin.marzban_username, admin.marzban_password)
            
            # Get current usage from Marzban using admin's own credentials
            admin_stats = await admin_api.get_admin_stats()
            
            # Get users that belong to this admin using their own credentials
            admin_users = await admin_api.get_users()

            # Calculate usage percentages
            user_percentage = admin_stats.total_users / admin.max_users if admin.max_users > 0 else 0
            traffic_percentage = admin_stats.total_traffic_used / admin.max_total_traffic if admin.max_total_traffic > 0 else 0
            time_percentage = admin_stats.total_time_used / admin.max_total_time if admin.max_total_time > 0 else 0

            # Check for limits exceeded
            limits_exceeded = any([
                user_percentage >= 1.0,
                traffic_percentage >= 1.0,
                time_percentage >= 1.0
            ])

            # Check for warning threshold (80%)
            warning_needed = any([
                user_percentage >= config.WARNING_THRESHOLD,
                traffic_percentage >= config.WARNING_THRESHOLD,
                time_percentage >= config.WARNING_THRESHOLD
            ])

            # Get active users for potential disabling (only include this admin's users)
            active_users = [
                user.username for user in admin_users 
                if user.status == "active"
            ]

            # Create usage report with detailed user data
            users_data = []
            for user in admin_users:
                # Get accurate data consumption (upload + download)
                total_usage = user.used_traffic + (user.lifetime_used_traffic or 0)
                users_data.append({
                    "username": user.username,
                    "status": user.status,
                    "used_traffic": user.used_traffic,
                    "lifetime_used_traffic": user.lifetime_used_traffic,
                    "total_usage": total_usage,
                    "data_limit": user.data_limit,
                    "expire": user.expire,
                    "admin": user.admin
                })

            # Save report to database with admin_id reference
            report = UsageReportModel(
                admin_user_id=admin.user_id,
                check_time=datetime.now(),
                current_users=len(admin_users),
                current_total_time=admin_stats.total_time_used,
                current_total_traffic=admin_stats.total_traffic_used,
                users_data=json.dumps(users_data, ensure_ascii=False)
            )

            await db.add_usage_report(report)

            return LimitCheckResult(
                admin_user_id=admin.user_id,
                admin_id=admin.id,
                exceeded=limits_exceeded,
                warning=warning_needed,
                limits_data={
                    "user_percentage": user_percentage,
                    "traffic_percentage": traffic_percentage,
                    "time_percentage": time_percentage,
                    "current_users": admin_stats.total_users,
                    "max_users": admin.max_users,
                    "current_traffic": admin_stats.total_traffic_used,
                    "max_traffic": admin.max_total_traffic,
                    "current_time": admin_stats.total_time_used,
                    "max_time": admin.max_total_time
                },
                affected_users=active_users
            )

        except Exception as e:
            print(f"Error checking limits for admin panel {admin_id}: {e}")
            return LimitCheckResult(admin_user_id=admin.user_id if admin else 0, admin_id=admin_id)

    async def handle_limit_exceeded(self, result: LimitCheckResult):
        """Handle when admin exceeds limits - use proper API calls."""
        try:
            if not result.exceeded or not result.affected_users:
                return

            # Import deactivation function
            from handlers.sudo_handlers import deactivate_admin_panel_by_id, notify_admin_deactivation
            
            # Get the admin info
            admin = await db.get_admin_by_id(result.admin_id)
            if not admin:
                return
                
            admin_username = admin.marzban_username or f"Panel ID: {admin.id}"
                
            # Check which limits were exceeded
            limits_data = result.limits_data
            exceeded_limits = []
            
            if limits_data.get("user_percentage", 0) >= 1.0:
                exceeded_limits.append(f"کاربران ({limits_data['current_users']}/{limits_data['max_users']})")
                
            if limits_data.get("traffic_percentage", 0) >= 1.0:
                from utils.notify import format_traffic_size
                current_traffic = await format_traffic_size(limits_data['current_traffic'])
                max_traffic = await format_traffic_size(limits_data['max_traffic'])
                exceeded_limits.append(f"ترافیک ({current_traffic}/{max_traffic})")
                
            if limits_data.get("time_percentage", 0) >= 1.0:
                from utils.notify import format_time_duration
                current_time = await format_time_duration(limits_data['current_time'])
                max_time = await format_time_duration(limits_data['max_time'])
                exceeded_limits.append(f"زمان ({current_time}/{max_time})")
            
            reason = "تجاوز از محدودیت: " + ", ".join(exceeded_limits)

            # Try to deactivate admin panel and all their users first
            try:
                success = await deactivate_admin_panel_by_id(result.admin_id, reason)
                
                if success:
                    # Notify sudo admins about deactivation
                    await notify_admin_deactivation(self.bot, result.admin_user_id, reason)
                    
                    # Log the action
                    log = LogModel(
                        admin_user_id=result.admin_user_id,
                        action="admin_panel_auto_deactivated",
                        details=f"Admin panel {result.admin_id} and users deactivated due to limit exceeded. {reason}",
                        timestamp=datetime.now()
                    )
                    await db.add_log(log)
                    
                    print(f"Admin panel {result.admin_id} (user {result.admin_user_id}) and their users deactivated due to limit exceeded: {reason}")
                    return
            except Exception as e:
                print(f"Failed to deactivate admin panel {result.admin_id}: {e}")
            
            # Fallback: Use modifyUser API to disable users individually
            disable_results = {}
            for username in result.affected_users:
                try:
                    # Use modifyUser to set status to disabled
                    success = await marzban_api.modify_user(username, {"status": "disabled"})
                    disable_results[username] = success
                    await asyncio.sleep(0.1)  # Rate limiting
                except Exception as e:
                    print(f"Error disabling user {username}: {e}")
                    disable_results[username] = False
            
            # Count successful disables
            disabled_users = [username for username, success in disable_results.items() if success]
            
            if disabled_users:
                # Send notifications
                await notify_limit_exceeded(self.bot, result.admin_user_id, disabled_users)
                
                # Log the action
                log = LogModel(
                    admin_user_id=result.admin_user_id,
                    action="users_disabled_by_system",
                    details=f"Limits exceeded. Disabled {len(disabled_users)} users: {', '.join(disabled_users)}. {reason}",
                    timestamp=datetime.now()
                )
                await db.add_log(log)
                
                print(f"Disabled {len(disabled_users)} users for admin {result.admin_user_id} due to limit exceeded")

        except Exception as e:
            print(f"Error handling limit exceeded for admin {result.admin_user_id}: {e}")

    async def handle_limit_warning(self, result: LimitCheckResult):
        """Handle when admin approaches limits."""
        try:
            if not result.warning:
                return

            limits_data = result.limits_data
            
            # Check which limits are approaching threshold
            warning_types = []
            
            if limits_data.get("user_percentage", 0) >= config.WARNING_THRESHOLD:
                warning_types.append(f"کاربران ({limits_data['user_percentage']:.1%})")
                
            if limits_data.get("traffic_percentage", 0) >= config.WARNING_THRESHOLD:
                warning_types.append(f"ترافیک ({limits_data['traffic_percentage']:.1%})")
                
            if limits_data.get("time_percentage", 0) >= config.WARNING_THRESHOLD:
                warning_types.append(f"زمان ({limits_data['time_percentage']:.1%})")

            # Send warning for each type approaching limit
            for warning_type in warning_types:
                percentage = max(
                    limits_data.get("user_percentage", 0),
                    limits_data.get("traffic_percentage", 0),
                    limits_data.get("time_percentage", 0)
                )
                
                await notify_limit_warning(
                    self.bot, 
                    result.admin_user_id, 
                    warning_type, 
                    percentage
                )

        except Exception as e:
            print(f"Error handling limit warning for admin {result.admin_user_id}: {e}")

    async def cleanup_expired_users(self):
        """Clean up expired users for all admins."""
        try:
            print(f"Starting expired users cleanup at {datetime.now()}")
            
            # Get all active admins
            admins = await db.get_all_admins()
            active_admins = [admin for admin in admins if admin.is_active]
            
            total_cleaned = 0
            
            for admin in active_admins:
                try:
                    admin_username = admin.username or str(admin.user_id)
                    
                    # Get expired users for this admin
                    expired_users = await marzban_api.get_expired_users(admin_username)
                    
                    if expired_users:
                        # Remove expired users using proper API
                        for user in expired_users:
                            try:
                                success = await marzban_api.remove_user(user.username)
                                if success:
                                    total_cleaned += 1
                                    print(f"Removed expired user: {user.username} (admin: {admin_username})")
                                await asyncio.sleep(0.1)  # Rate limiting
                            except Exception as e:
                                print(f"Error removing expired user {user.username}: {e}")
                                continue
                    
                    await asyncio.sleep(0.5)  # Delay between admin processing
                    
                except Exception as e:
                    print(f"Error cleaning expired users for admin {admin.user_id}: {e}")
                    continue
            
            if total_cleaned > 0:
                # Log the cleanup action
                log = LogModel(
                    admin_user_id=None,
                    action="expired_users_cleanup",
                    details=f"Automatically cleaned up {total_cleaned} expired users",
                    timestamp=datetime.now()
                )
                await db.add_log(log)
            
            print(f"Expired users cleanup completed. Removed {total_cleaned} users at {datetime.now()}")
            
        except Exception as e:
            print(f"Error in cleanup_expired_users: {e}")

    async def monitor_all_admins(self):
        """Monitor all active admins for limit violations."""
        try:
            print(f"Starting monitoring check at {datetime.now()}")
            
            # DISABLED: cleanup expired users (was causing user deletion)
            # await self.cleanup_expired_users()
            
            # Get all active admins
            admins = await db.get_all_admins()
            active_admins = [admin for admin in admins if admin.is_active]
            
            if not active_admins:
                print("No active admins to monitor")
                return
            
            print(f"Monitoring {len(active_admins)} active admins")
            
            # Check each admin panel individually
            for admin in active_admins:
                try:
                    # Use admin.id instead of user_id to identify unique admin panels
                    result = await self.check_admin_limits_by_id(admin.id)
                    
                    # Handle exceeded limits (disable users)
                    if result.exceeded:
                        await self.handle_limit_exceeded(result)
                    
                    # Handle warning notifications
                    elif result.warning:
                        await self.handle_limit_warning(result)
                    
                    # Small delay between admin checks
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    print(f"Error monitoring admin panel {admin.id} (user {admin.user_id}): {e}")
                    continue
            
            print(f"Monitoring check completed at {datetime.now()}")
            
        except Exception as e:
            print(f"Error in monitor_all_admins: {e}")

    async def start(self):
        """Start the monitoring scheduler."""
        if self.is_running:
            print("Scheduler is already running")
            return
        
        print("Starting monitoring scheduler...")
        
        # Add monitoring job
        self.scheduler.add_job(
            self.monitor_all_admins,
            trigger=IntervalTrigger(seconds=config.MONITORING_INTERVAL),
            id="admin_monitor",
            name="Admin Limit Monitor",
            replace_existing=True,
            max_instances=1
        )
        
        # Start scheduler
        self.scheduler.start()
        self.is_running = True
        
        print(f"Monitoring scheduler started. Will check every {config.MONITORING_INTERVAL} seconds.")
        
        # DISABLED: initial check (was triggering cleanup)
        # await self.monitor_all_admins()

    async def stop(self):
        """Stop the monitoring scheduler."""
        if not self.is_running:
            return
        
        print("Stopping monitoring scheduler...")
        self.scheduler.shutdown(wait=False)
        self.is_running = False
        print("Monitoring scheduler stopped.")

    def get_status(self) -> Dict:
        """Get scheduler status."""
        return {
            "running": self.is_running,
            "jobs": len(self.scheduler.get_jobs()) if self.is_running else 0,
            "next_run": str(self.scheduler.get_job("admin_monitor").next_run_time) if self.is_running else None
        }


# Global scheduler instance (will be initialized with bot)
scheduler = None


def init_scheduler(bot):
    """Initialize the global scheduler with bot instance."""
    global scheduler
    scheduler = MonitoringScheduler(bot)
    return scheduler