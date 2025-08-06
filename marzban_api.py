import httpx
import asyncio
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
import config
from models.schemas import MarzbanUserModel, AdminStatsModel


def safe_extract_username(value: Union[str, Dict[str, Any], None]) -> Optional[str]:
    """
    Safely extract username from a value that could be a string, dict, or None.
    
    Args:
        value: The value to extract username from
        
    Returns:
        str: The username if found, None if value is None or username not found
        
    This function prevents Pydantic validation errors when Marzban API returns
    dict objects instead of strings for fields like admin, username, owner, etc.
    """
    if value is None:
        return None
    elif isinstance(value, str):
        return value
    elif isinstance(value, dict):
        return value.get("username")
    else:
        # For any other type, try to convert to string
        return str(value) if value else None


class MarzbanAdminAPI:
    """API class for individual admin authentication."""
    
    def __init__(self, marzban_url: str, admin_username: str, admin_password: str):
        self.base_url = marzban_url.rstrip('/')
        self.username = admin_username
        self.password = admin_password
        self.token = None
        self.token_expires = None

    async def get_token(self) -> Optional[str]:
        """Get authentication token from Marzban using admin credentials."""
        try:
            async with httpx.AsyncClient(timeout=config.API_TIMEOUT) as client:
                response = await client.post(
                    f"{self.base_url}/api/admin/token",
                    data={
                        "username": self.username,
                        "password": self.password
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    self.token = data.get("access_token")
                    return self.token
                else:
                    print(f"Failed to get token for {self.username}: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            print(f"Error getting token for {self.username}: {e}")
            return None

    async def ensure_authenticated(self) -> bool:
        """Ensure we have a valid token."""
        if not self.token:
            token = await self.get_token()
            return token is not None
        return True

    async def get_headers(self) -> Dict[str, str]:
        """Get headers with authentication token."""
        if not await self.ensure_authenticated():
            raise Exception(f"Failed to authenticate admin {self.username} with Marzban API")
        
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    async def get_users(self) -> List[MarzbanUserModel]:
        """Get all users belonging to this admin."""
        try:
            headers = await self.get_headers()
            
            async with httpx.AsyncClient(timeout=config.API_TIMEOUT) as client:
                # Get users with admin filter to get only this admin's users
                response = await client.get(
                    f"{self.base_url}/api/users",
                    headers=headers,
                    params={"admin": self.username}
                )
                
                if response.status_code == 200:
                    users_data = response.json()
                    users = []
                    
                    for user_data in users_data.get("users", []):
                        try:
                            user = MarzbanUserModel(
                                username=safe_extract_username(user_data.get("username")) or "",
                                status=user_data.get("status", ""),
                                used_traffic=user_data.get("used_traffic", 0),
                                lifetime_used_traffic=user_data.get("lifetime_used_traffic", 0),
                                data_limit=user_data.get("data_limit"),
                                expire=user_data.get("expire"),
                                admin=safe_extract_username(user_data.get("admin"))
                            )
                            users.append(user)
                        except Exception as e:
                            print(f"Error parsing user data: {e}")
                            continue
                    
                    return users
                else:
                    print(f"Failed to get users for {self.username}: {response.status_code} - {response.text}")
                    return []
                    
        except Exception as e:
            print(f"Error getting users for {self.username}: {e}")
            return []

    async def get_admin_stats(self) -> AdminStatsModel:
        """Get statistics for this admin - only count users owned by this admin."""
        try:
            # Get all users belonging to this admin
            admin_users = await self.get_users()
            
            # Filter out deleted/expired users and count only active/valid users
            valid_users = []
            for user in admin_users:
                # Check if user is not expired
                if user.expire is None or user.expire > datetime.now().timestamp():
                    # Check if user status is not disabled/deleted
                    if user.status in ["active", "limited"]:
                        valid_users.append(user)
            
            total_users = len(valid_users)
            active_users = len([u for u in valid_users if u.status == "active"])
            
            # Calculate current traffic from existing users
            current_traffic_used = 0
            for user in valid_users:
                # Get user's current usage data (upload + download)
                user_total_usage = user.used_traffic + (user.lifetime_used_traffic or 0)
                current_traffic_used += user_total_usage
            
            # Get cumulative traffic (includes deleted users' consumption)
            from database import db
            # For MarzbanAdminAPI, we need to find the admin_id based on username
            # This is a workaround since we don't have direct access to admin_id here
            admin_from_db = await db.get_admin_by_marzban_username(self.username)
            if admin_from_db:
                await db.initialize_cumulative_traffic(admin_from_db.id)
                cumulative_traffic = await db.get_cumulative_traffic(admin_from_db.id)
                # Update cumulative traffic if current is higher
                await db.update_cumulative_traffic(admin_from_db.id, current_traffic_used)
                # Use the maximum of cumulative and current traffic
                total_traffic_used = max(cumulative_traffic, current_traffic_used)
            else:
                # Fallback to current traffic if admin not found in DB
                total_traffic_used = current_traffic_used
            
            # Calculate total time used based on user creation/activation times
            # Note: This would need actual time tracking from Marzban API
            # For now, we estimate based on user activity
            marzban_time_used = 0
            for user in valid_users:
                if user.expire and user.status == "active":
                    # Estimate time used (this is approximate)
                    creation_time = datetime.now().timestamp() - (30 * 24 * 3600)  # Assume 30 days ago
                    time_used = datetime.now().timestamp() - creation_time
                    marzban_time_used += int(time_used)
            
            # Apply time reset if exists
            if admin_from_db:
                total_time_used = await db.get_time_usage_with_reset(admin_from_db.id, marzban_time_used)
            else:
                total_time_used = marzban_time_used
            
            return AdminStatsModel(
                total_users=total_users,
                active_users=active_users,
                total_traffic_used=total_traffic_used,
                total_time_used=total_time_used
            )
            
        except Exception as e:
            print(f"Error getting admin stats for {self.username}: {e}")
            return AdminStatsModel()

    async def test_connection(self) -> bool:
        """Test connection to Marzban API."""
        try:
            return await self.ensure_authenticated()
        except Exception as e:
            print(f"Connection test failed for {self.username}: {e}")
            return False


class MarzbanAPI:
    def __init__(self):
        self.base_url = config.MARZBAN_URL.rstrip('/')
        self.username = config.MARZBAN_USERNAME
        self.password = config.MARZBAN_PASSWORD
        self.token = None
        self.token_expires = None

    async def get_token(self) -> Optional[str]:
        """Get authentication token from Marzban."""
        try:
            async with httpx.AsyncClient(timeout=config.API_TIMEOUT) as client:
                response = await client.post(
                    f"{self.base_url}/api/admin/token",
                    data={
                        "username": self.username,
                        "password": self.password
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    self.token = data.get("access_token")
                    return self.token
                else:
                    print(f"Failed to get token: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            print(f"Error getting token: {e}")
            return None

    async def ensure_authenticated(self) -> bool:
        """Ensure we have a valid token."""
        if not self.token:
            token = await self.get_token()
            return token is not None
        return True

    async def get_headers(self) -> Dict[str, str]:
        """Get headers with authentication token."""
        if not await self.ensure_authenticated():
            raise Exception("Failed to authenticate with Marzban API")
        
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    async def create_admin_api(self, marzban_username: str, marzban_password: str) -> MarzbanAdminAPI:
        """Create a MarzbanAdminAPI instance for specific admin credentials."""
        return MarzbanAdminAPI(self.base_url, marzban_username, marzban_password)

    async def get_admin_stats_with_credentials(self, marzban_username: str, marzban_password: str) -> AdminStatsModel:
        """Get admin stats using specific admin credentials for real-time data."""
        try:
            admin_api = await self.create_admin_api(marzban_username, marzban_password)
            return await admin_api.get_admin_stats()
        except Exception as e:
            print(f"Error getting stats with credentials for {marzban_username}: {e}")
            return AdminStatsModel()

    async def get_token(self) -> Optional[str]:
        """Get authentication token from Marzban."""
        try:
            async with httpx.AsyncClient(timeout=config.API_TIMEOUT) as client:
                response = await client.post(
                    f"{self.base_url}/api/admin/token",
                    data={
                        "username": self.username,
                        "password": self.password
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    self.token = data.get("access_token")
                    return self.token
                else:
                    print(f"Failed to get token: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            print(f"Error getting token: {e}")
            return None

    async def ensure_authenticated(self) -> bool:
        """Ensure we have a valid token."""
        if not self.token:
            token = await self.get_token()
            return token is not None
        return True

    async def get_headers(self) -> Dict[str, str]:
        """Get headers with authentication token."""
        if not await self.ensure_authenticated():
            raise Exception("Failed to authenticate with Marzban API")
        
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    async def get_users(self, admin_username: Optional[str] = None) -> List[MarzbanUserModel]:
        """Get all users or users for specific admin."""
        try:
            headers = await self.get_headers()
            
            async with httpx.AsyncClient(timeout=config.API_TIMEOUT) as client:
                params = {}
                if admin_username:
                    params["admin"] = admin_username
                    
                response = await client.get(
                    f"{self.base_url}/api/users",
                    headers=headers,
                    params=params
                )
                
                if response.status_code == 200:
                    users_data = response.json()
                    users = []
                    
                    for user_data in users_data.get("users", []):
                        try:
                            user = MarzbanUserModel(
                                username=safe_extract_username(user_data.get("username")) or "",
                                status=user_data.get("status", ""),
                                used_traffic=user_data.get("used_traffic", 0),
                                lifetime_used_traffic=user_data.get("lifetime_used_traffic", 0),
                                data_limit=user_data.get("data_limit"),
                                expire=user_data.get("expire"),
                                admin=safe_extract_username(user_data.get("admin"))
                            )
                            users.append(user)
                        except Exception as e:
                            print(f"Error parsing user data: {e}")
                            continue
                    
                    return users
                else:
                    print(f"Failed to get users: {response.status_code} - {response.text}")
                    return []
                    
        except Exception as e:
            print(f"Error getting users: {e}")
            return []

    async def get_user(self, username: str) -> Optional[MarzbanUserModel]:
        """Get specific user information."""
        try:
            headers = await self.get_headers()
            
            async with httpx.AsyncClient(timeout=config.API_TIMEOUT) as client:
                response = await client.get(
                    f"{self.base_url}/api/user/{username}",
                    headers=headers
                )
                
                if response.status_code == 200:
                    user_data = response.json()
                    return MarzbanUserModel(
                        username=safe_extract_username(user_data.get("username")) or "",
                        status=user_data.get("status", ""),
                        used_traffic=user_data.get("used_traffic", 0),
                        lifetime_used_traffic=user_data.get("lifetime_used_traffic", 0),
                        data_limit=user_data.get("data_limit"),
                        expire=user_data.get("expire"),
                        admin=safe_extract_username(user_data.get("admin"))
                    )
                else:
                    print(f"Failed to get user {username}: {response.status_code}")
                    return None
                    
        except Exception as e:
            print(f"Error getting user {username}: {e}")
            return None

    async def disable_user(self, username: str) -> bool:
        """Disable a user."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            headers = await self.get_headers()
            
            logger.debug(f"Disabling user {username} in Marzban...")
            
            async with httpx.AsyncClient(timeout=config.API_TIMEOUT) as client:
                response = await client.put(
                    f"{self.base_url}/api/user/{username}",
                    headers=headers,
                    json={"status": "disabled"}
                )
                
                if response.status_code == 200:
                    logger.debug(f"User {username} disabled successfully")
                    return True
                else:
                    # Log detailed error information
                    error_details = f"HTTP {response.status_code}"
                    try:
                        response_text = response.text
                        if response_text:
                            error_details += f" - Response: {response_text}"
                    except Exception:
                        error_details += " - Could not read response text"
                    
                    logger.warning(f"Failed to disable user {username}: {error_details}")
                    return False
                    
        except Exception as e:
            logger.error(f"Exception while disabling user {username}: {type(e).__name__}: {e}")
            return False

    async def enable_user(self, username: str) -> bool:
        """Enable a user."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            headers = await self.get_headers()
            
            logger.debug(f"Enabling user {username} in Marzban...")
            
            async with httpx.AsyncClient(timeout=config.API_TIMEOUT) as client:
                response = await client.put(
                    f"{self.base_url}/api/user/{username}",
                    headers=headers,
                    json={"status": "active"}
                )
                
                if response.status_code == 200:
                    logger.debug(f"User {username} enabled successfully")
                    return True
                else:
                    # Log detailed error information
                    error_details = f"HTTP {response.status_code}"
                    try:
                        response_text = response.text
                        if response_text:
                            error_details += f" - Response: {response_text}"
                    except Exception:
                        error_details += " - Could not read response text"
                    
                    logger.warning(f"Failed to enable user {username}: {error_details}")
                    return False
                    
        except Exception as e:
            logger.error(f"Exception while enabling user {username}: {type(e).__name__}: {e}")
            return False

    async def disable_users_batch(self, usernames: List[str]) -> Dict[str, bool]:
        """Disable multiple users."""
        results = {}
        for username in usernames:
            results[username] = await self.disable_user(username)
            await asyncio.sleep(0.1)  # Small delay to avoid overwhelming the API
        return results

    async def enable_users_batch(self, usernames: List[str]) -> Dict[str, bool]:
        """Enable multiple users."""
        results = {}
        for username in usernames:
            results[username] = await self.enable_user(username)
            await asyncio.sleep(0.1)  # Small delay to avoid overwhelming the API
        return results

    async def get_admin_stats(self, admin_username: str) -> AdminStatsModel:
        """Get statistics for a specific admin - only count users owned by this admin."""
        try:
            # Get all users and filter by admin ownership
            all_users = await self.get_users()
            admin_users = []
            
            for user in all_users:
                # Get detailed user info to check ownership and calculate accurate usage
                detailed_user = await self.get_user(user.username)
                if detailed_user:
                    # Check if user belongs to this admin
                    if detailed_user.admin == admin_username:
                        admin_users.append(detailed_user)
                    elif not detailed_user.admin and user.admin == admin_username:
                        # If owner not set but user came from admin filter, set ownership
                        await self.set_user_owner(user.username, admin_username)
                        admin_users.append(detailed_user)
            
            # Filter out deleted/expired users and count only active/valid users
            valid_users = []
            for user in admin_users:
                # Check if user is not expired
                if user.expire is None or user.expire > datetime.now().timestamp():
                    # Check if user status is not disabled/deleted
                    if user.status in ["active", "limited"]:
                        valid_users.append(user)
            
            total_users = len(valid_users)
            active_users = len([u for u in valid_users if u.status == "active"])
            
            # Calculate current traffic from existing users
            current_traffic_used = 0
            for user in valid_users:
                # Get user's current usage data (upload + download)
                user_total_usage = user.used_traffic + (user.lifetime_used_traffic or 0)
                current_traffic_used += user_total_usage
            
            # Get cumulative traffic (includes deleted users' consumption)
            from database import db
            # For MarzbanAPI get_stats, we need to find the admin_id based on username
            admin_from_db = await db.get_admin_by_marzban_username(admin_username)
            if admin_from_db:
                await db.initialize_cumulative_traffic(admin_from_db.id)
                cumulative_traffic = await db.get_cumulative_traffic(admin_from_db.id)
                # Update cumulative traffic if current is higher
                await db.update_cumulative_traffic(admin_from_db.id, current_traffic_used)
                # Use the maximum of cumulative and current traffic
                total_traffic_used = max(cumulative_traffic, current_traffic_used)
            else:
                # Fallback to current traffic if admin not found in DB
                total_traffic_used = current_traffic_used
            
            # Calculate total time used based on user creation/activation times
            # Note: This would need actual time tracking from Marzban API
            # For now, we estimate based on user activity
            total_time_used = 0
            for user in valid_users:
                if user.expire and user.status == "active":
                    # Estimate time used (this is approximate)
                    creation_time = datetime.now().timestamp() - (30 * 24 * 3600)  # Assume 30 days ago
                    time_used = datetime.now().timestamp() - creation_time
                    total_time_used += int(time_used)
            
            return AdminStatsModel(
                total_users=total_users,
                active_users=active_users,
                total_traffic_used=total_traffic_used,
                total_time_used=total_time_used
            )
            
        except Exception as e:
            print(f"Error getting admin stats for {admin_username}: {e}")
            return AdminStatsModel()

    async def get_system_stats(self) -> Dict[str, Any]:
        """Get system statistics."""
        try:
            headers = await self.get_headers()
            
            async with httpx.AsyncClient(timeout=config.API_TIMEOUT) as client:
                response = await client.get(
                    f"{self.base_url}/api/system",
                    headers=headers
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    return {}
                    
        except Exception as e:
            print(f"Error getting system stats: {e}")
            return {}

    async def update_admin_password(self, admin_username: str, new_password: str, is_sudo: bool = False) -> bool:
        """Update admin password in Marzban using the new API format."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            headers = await self.get_headers()
            
            # Use the new API format as specified in requirements
            admin_data = {
                "password": new_password,
                "is_sudo": is_sudo
            }
            
            logger.info(f"Updating password for admin {admin_username} in Marzban panel...")
            
            async with httpx.AsyncClient(timeout=config.API_TIMEOUT) as client:
                response = await client.put(
                    f"{self.base_url}/api/admin/{admin_username}",
                    headers=headers,
                    json=admin_data
                )
                
                # Check for successful update - 200 is typical for PUT operations
                if response.status_code == 200:
                    logger.info(f"Password updated successfully for admin {admin_username} (status: {response.status_code})")
                    return True
                else:
                    # Log detailed error information
                    error_details = f"HTTP {response.status_code}"
                    try:
                        response_text = response.text
                        if response_text:
                            error_details += f" - Response: {response_text}"
                    except Exception:
                        error_details += " - Could not read response text"
                    
                    logger.error(f"Failed to update password for admin {admin_username}: {error_details}")
                    return False
                    
        except Exception as e:
            logger.error(f"Exception while updating password for admin {admin_username}: {type(e).__name__}: {e}")
            return False

    async def get_admin_users(self, admin_username: str) -> List[MarzbanUserModel]:
        """Get all users belonging to a specific admin."""
        return await self.get_users(admin_username)

    async def create_admin(self, username: str, password: str, telegram_id: int, is_sudo: bool = False) -> bool:
        """Create a new admin in Marzban panel."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            headers = await self.get_headers()
            
            admin_data = {
                "username": username,
                "password": password,
                "telegram_id": telegram_id,
                "is_sudo": is_sudo
            }
            
            logger.info(f"Creating admin {username} in Marzban panel...")
            
            async with httpx.AsyncClient(timeout=config.API_TIMEOUT) as client:
                response = await client.post(
                    f"{self.base_url}/api/admin",
                    headers=headers,
                    json=admin_data
                )
                
                # Check for successful creation - both 200 and 201 are valid success codes
                if response.status_code in [200, 201]:
                    logger.info(f"Admin {username} created successfully in Marzban (status: {response.status_code})")
                    return True
                else:
                    # Log detailed error information
                    error_details = f"HTTP {response.status_code}"
                    try:
                        response_text = response.text
                        if response_text:
                            error_details += f" - Response: {response_text}"
                    except Exception:
                        error_details += " - Could not read response text"
                    
                    logger.error(f"Failed to create admin {username} in Marzban: {error_details}")
                    return False
                    
        except Exception as e:
            logger.error(f"Exception while creating admin {username}: {type(e).__name__}: {e}")
            return False

    async def admin_exists(self, username: str) -> bool:
        """Check if admin username already exists in Marzban."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            headers = await self.get_headers()
            
            logger.debug(f"Checking if admin {username} exists in Marzban...")
            
            async with httpx.AsyncClient(timeout=config.API_TIMEOUT) as client:
                response = await client.get(
                    f"{self.base_url}/api/admin/{username}",
                    headers=headers
                )
                
                if response.status_code == 200:
                    logger.debug(f"Admin {username} exists in Marzban")
                    return True
                elif response.status_code == 404:
                    logger.debug(f"Admin {username} does not exist in Marzban")
                    return False
                else:
                    # Log unexpected status codes
                    error_details = f"HTTP {response.status_code}"
                    try:
                        response_text = response.text
                        if response_text:
                            error_details += f" - Response: {response_text}"
                    except Exception:
                        error_details += " - Could not read response text"
                    
                    logger.warning(f"Unexpected response when checking admin {username} existence: {error_details}")
                    return False
                    
        except Exception as e:
            logger.error(f"Exception while checking admin {username} existence: {type(e).__name__}: {e}")
            return False

    async def set_user_owner(self, username: str, admin_username: str) -> bool:
        """Set the owner (admin) for a user."""
        try:
            headers = await self.get_headers()
            
            async with httpx.AsyncClient(timeout=config.API_TIMEOUT) as client:
                response = await client.put(
                    f"{self.base_url}/api/user/{username}",
                    headers=headers,
                    json={"admin": admin_username}
                )
                
                return response.status_code == 200
                
        except Exception as e:
            print(f"Error setting user owner for {username}: {e}")
            return False

    async def modify_user(self, username: str, user_data: Dict[str, Any]) -> bool:
        """Modify user with given data."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            headers = await self.get_headers()
            
            logger.debug(f"Modifying user {username} in Marzban...")
            
            async with httpx.AsyncClient(timeout=config.API_TIMEOUT) as client:
                response = await client.put(
                    f"{self.base_url}/api/user/{username}",
                    headers=headers,
                    json=user_data
                )
                
                if response.status_code == 200:
                    logger.debug(f"User {username} modified successfully")
                    return True
                else:
                    # Log detailed error information
                    error_details = f"HTTP {response.status_code}"
                    try:
                        response_text = response.text
                        if response_text:
                            error_details += f" - Response: {response_text}"
                    except Exception:
                        error_details += " - Could not read response text"
                    
                    logger.warning(f"Failed to modify user {username}: {error_details}")
                    return False
                    
        except Exception as e:
            logger.error(f"Exception while modifying user {username}: {type(e).__name__}: {e}")
            return False

    async def enable_user(self, username: str) -> bool:
        """Enable (activate) a user."""
        return await self.modify_user(username, {"status": "active"})

    async def disable_user(self, username: str) -> bool:
        """Disable (deactivate) a user."""
        return await self.modify_user(username, {"status": "disabled"})

    async def remove_user(self, username: str, preserve_traffic: bool = True) -> bool:
        """Remove (delete) a user with optional traffic preservation."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Preserve traffic before deletion if requested
            if preserve_traffic:
                await self._preserve_user_traffic_before_deletion(username)
            
            headers = await self.get_headers()
            
            logger.debug(f"Removing user {username} from Marzban...")
            
            async with httpx.AsyncClient(timeout=config.API_TIMEOUT) as client:
                response = await client.delete(
                    f"{self.base_url}/api/user/{username}",
                    headers=headers
                )
                
                # Check for successful deletion - 200, 204 are common success codes for DELETE
                if response.status_code in [200, 204]:
                    logger.debug(f"User {username} removed successfully")
                    return True
                else:
                    # Log detailed error information
                    error_details = f"HTTP {response.status_code}"
                    try:
                        response_text = response.text
                        if response_text:
                            error_details += f" - Response: {response_text}"
                    except Exception:
                        error_details += " - Could not read response text"
                    
                    logger.warning(f"Failed to remove user {username}: {error_details}")
                    return False
                    
        except Exception as e:
            logger.error(f"Exception while removing user {username}: {type(e).__name__}: {e}")
            return False

    async def _preserve_user_traffic_before_deletion(self, username: str):
        """Preserve user's traffic consumption in cumulative tracking before deletion."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Get user details to find their admin and traffic usage
            user = await self.get_user(username)
            if not user or not user.admin:
                logger.debug(f"User {username} not found or has no admin assigned")
                return
            
            # Calculate user's total traffic consumption
            user_traffic = user.used_traffic + (user.lifetime_used_traffic or 0)
            if user_traffic <= 0:
                return
            
            # Find admin in database and preserve traffic
            from database import db
            admin_from_db = await db.get_admin_by_marzban_username(user.admin)
            if admin_from_db:
                await db.initialize_cumulative_traffic(admin_from_db.id)
                # Add user's traffic to cumulative total
                await db.add_to_cumulative_traffic(admin_from_db.id, user_traffic)
                logger.debug(f"Preserved {user_traffic} bytes of traffic for user {username} (admin: {user.admin})")
            else:
                logger.warning(f"Could not find admin {user.admin} in database to preserve traffic for user {username}")
                
        except Exception as e:
            logger.error(f"Error preserving traffic for user {username}: {e}")
            # Don't fail deletion if traffic preservation fails
            pass

    async def get_expired_users(self, admin_username: Optional[str] = None) -> List[MarzbanUserModel]:
        """Get list of expired users."""
        try:
            headers = await self.get_headers()
            
            async with httpx.AsyncClient(timeout=config.API_TIMEOUT) as client:
                params = {"expired": "true"}
                if admin_username:
                    params["admin"] = admin_username
                    
                response = await client.get(
                    f"{self.base_url}/api/users",
                    headers=headers,
                    params=params
                )
                
                if response.status_code == 200:
                    users_data = response.json()
                    users = []
                    
                    for user_data in users_data.get("users", []):
                        try:
                            user = MarzbanUserModel(
                                username=safe_extract_username(user_data.get("username")) or "",
                                status=user_data.get("status", ""),
                                used_traffic=user_data.get("used_traffic", 0),
                                lifetime_used_traffic=user_data.get("lifetime_used_traffic", 0),
                                data_limit=user_data.get("data_limit"),
                                expire=user_data.get("expire"),
                                admin=safe_extract_username(user_data.get("admin"))
                            )
                            users.append(user)
                        except Exception as e:
                            print(f"Error parsing expired user data: {e}")
                            continue
                    
                    return users
                else:
                    print(f"Failed to get expired users: {response.status_code}")
                    return []
                    
        except Exception as e:
            print(f"Error getting expired users: {e}")
            return []

    async def delete_expired_users(self, admin_username: Optional[str] = None) -> bool:
        """Delete all expired users."""
        try:
            expired_users = await self.get_expired_users(admin_username)
            
            results = []
            for user in expired_users:
                result = await self.remove_user(user.username)
                results.append(result)
                await asyncio.sleep(0.1)  # Small delay to avoid overwhelming the API
            
            return all(results)
                
        except Exception as e:
            print(f"Error deleting expired users: {e}")
            return False

    async def reset_user_data_usage(self, username: str) -> bool:
        """Reset data usage for a specific user."""
        try:
            headers = await self.get_headers()
            
            async with httpx.AsyncClient(timeout=config.API_TIMEOUT) as client:
                response = await client.post(
                    f"{self.base_url}/api/user/{username}/reset",
                    headers=headers
                )
                
                return response.status_code == 200
                
        except Exception as e:
            print(f"Error resetting data usage for user {username}: {e}")
            return False

    async def reset_users_data_usage(self, admin_username: Optional[str] = None) -> Dict[str, bool]:
        """Reset data usage for all users or users of specific admin."""
        try:
            users = await self.get_users(admin_username)
            
            results = {}
            for user in users:
                results[user.username] = await self.reset_user_data_usage(user.username)
                await asyncio.sleep(0.1)  # Small delay to avoid overwhelming the API
            
            return results
                
        except Exception as e:
            print(f"Error resetting users data usage: {e}")
            return {}

    async def get_current_admin(self) -> Optional[Dict[str, Any]]:
        """Get current admin information."""
        try:
            headers = await self.get_headers()
            
            async with httpx.AsyncClient(timeout=config.API_TIMEOUT) as client:
                response = await client.get(
                    f"{self.base_url}/api/admin",
                    headers=headers
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    print(f"Failed to get current admin: {response.status_code}")
                    return None
                    
        except Exception as e:
            print(f"Error getting current admin: {e}")
            return None

    async def list_admins(self) -> List[Dict[str, Any]]:
        """Get list of all admins."""
        try:
            headers = await self.get_headers()
            
            async with httpx.AsyncClient(timeout=config.API_TIMEOUT) as client:
                response = await client.get(
                    f"{self.base_url}/api/admins",
                    headers=headers
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    print(f"Failed to get admins list: {response.status_code}")
                    return []
                    
        except Exception as e:
            print(f"Error getting admins list: {e}")
            return []

    async def delete_admin(self, admin_username: str) -> bool:
        """Delete an admin."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            headers = await self.get_headers()
            
            logger.info(f"Deleting admin {admin_username} from Marzban panel...")
            
            async with httpx.AsyncClient(timeout=config.API_TIMEOUT) as client:
                response = await client.delete(
                    f"{self.base_url}/api/admin/{admin_username}",
                    headers=headers
                )
                
                # Check for successful deletion - 200, 204 are common success codes for DELETE
                if response.status_code in [200, 204]:
                    logger.info(f"Admin {admin_username} deleted successfully from Marzban (status: {response.status_code})")
                    return True
                else:
                    # Log detailed error information
                    error_details = f"HTTP {response.status_code}"
                    try:
                        response_text = response.text
                        if response_text:
                            error_details += f" - Response: {response_text}"
                    except Exception:
                        error_details += " - Could not read response text"
                    
                    logger.error(f"Failed to delete admin {admin_username} from Marzban: {error_details}")
                    return False
                    
        except Exception as e:
            logger.error(f"Exception while deleting admin {admin_username}: {type(e).__name__}: {e}")
            return False

    async def delete_admin_completely(self, admin_username: str) -> bool:
        """Completely delete admin and all their users from Marzban panel."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.info(f"Starting complete deletion of admin {admin_username} and all their users...")
            
            # First, get all users belonging to this admin and calculate their total traffic
            admin_users = await self.get_users(admin_username)
            user_count = len(admin_users)
            
            logger.info(f"Found {user_count} users belonging to admin {admin_username}")
            
            # Calculate total traffic consumed by users before deletion
            total_traffic_to_preserve = 0
            for user in admin_users:
                user_traffic = user.used_traffic + (user.lifetime_used_traffic or 0)
                total_traffic_to_preserve += user_traffic
                logger.debug(f"User {user.username} consumed {user_traffic} bytes")
            
            logger.info(f"Total traffic to preserve for admin {admin_username}: {total_traffic_to_preserve} bytes")
            
            # Update cumulative traffic before deleting users
            from database import db
            admin_from_db = await db.get_admin_by_marzban_username(admin_username)
            if admin_from_db and total_traffic_to_preserve > 0:
                await db.initialize_cumulative_traffic(admin_from_db.id)
                # Get current cumulative traffic
                current_cumulative = await db.get_cumulative_traffic(admin_from_db.id)
                # Ensure we preserve at least the current traffic consumption
                if total_traffic_to_preserve > current_cumulative:
                    await db.update_cumulative_traffic(admin_from_db.id, total_traffic_to_preserve)
                    logger.info(f"Updated cumulative traffic for admin {admin_username} to {total_traffic_to_preserve} bytes")
            
            # Delete all users belonging to this admin
            deleted_users_count = 0
            failed_users = []
            
            for user in admin_users:
                try:
                    success = await self.remove_user(user.username)
                    if success:
                        deleted_users_count += 1
                        logger.debug(f"User {user.username} deleted successfully")
                    else:
                        failed_users.append(user.username)
                        logger.warning(f"Failed to delete user {user.username}")
                    await asyncio.sleep(0.1)  # Rate limiting
                except Exception as e:
                    failed_users.append(user.username)
                    logger.error(f"Exception while deleting user {user.username}: {type(e).__name__}: {e}")
                    continue
            
            logger.info(f"User deletion summary for admin {admin_username}: {deleted_users_count} deleted, {len(failed_users)} failed")
            
            # Now delete the admin itself
            admin_deleted = await self.delete_admin(admin_username)
            
            if admin_deleted:
                logger.info(f"Admin {admin_username} completely deleted from Marzban (users: {deleted_users_count}/{user_count})")
                return True
            else:
                logger.error(f"Failed to delete admin {admin_username} from Marzban after deleting {deleted_users_count} users")
                return False
                
        except Exception as e:
            logger.error(f"Exception during complete deletion of admin {admin_username}: {type(e).__name__}: {e}")
            return False

    async def update_admin(self, admin_username: str, admin_data: Dict[str, Any]) -> bool:
        """Update admin information."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            headers = await self.get_headers()
            
            logger.info(f"Updating admin {admin_username} in Marzban panel...")
            
            async with httpx.AsyncClient(timeout=config.API_TIMEOUT) as client:
                response = await client.put(
                    f"{self.base_url}/api/admin/{admin_username}",
                    headers=headers,
                    json=admin_data
                )
                
                # Check for successful update
                if response.status_code == 200:
                    logger.info(f"Admin {admin_username} updated successfully (status: {response.status_code})")
                    return True
                else:
                    # Log detailed error information
                    error_details = f"HTTP {response.status_code}"
                    try:
                        response_text = response.text
                        if response_text:
                            error_details += f" - Response: {response_text}"
                    except Exception:
                        error_details += " - Could not read response text"
                    
                    logger.error(f"Failed to update admin {admin_username}: {error_details}")
                    return False
                    
        except Exception as e:
            logger.error(f"Exception while updating admin {admin_username}: {type(e).__name__}: {e}")
            return False

    async def test_connection(self) -> bool:
        """Test connection to Marzban API."""
        try:
            return await self.ensure_authenticated()
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False


# Global API instance
marzban_api = MarzbanAPI()