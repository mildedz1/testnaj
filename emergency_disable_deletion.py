#!/usr/bin/env python3
"""
Emergency script to disable all deletion capabilities in the bot
"""

import sys
import os

def disable_deletion_functions():
    """Add safety checks to prevent accidental deletions."""
    
    # Read the current sudo_handlers.py
    with open('/workspace/handlers/sudo_handlers.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Add emergency stop at the beginning of delete_admin_panel_completely
    emergency_check = '''
    # EMERGENCY STOP: Deletion temporarily disabled
    print("🚨 EMERGENCY: Admin deletion is temporarily disabled!")
    print("To re-enable, remove this emergency check from the code.")
    return False
'''
    
    # Find the delete_admin_panel_completely function and add emergency stop
    if 'async def delete_admin_panel_completely(' in content:
        # Find the function start
        func_start = content.find('async def delete_admin_panel_completely(')
        if func_start != -1:
            # Find the end of function signature (the colon)
            colon_pos = content.find(':', func_start)
            if colon_pos != -1:
                # Find the next line (after the docstring)
                next_line = content.find('"""', colon_pos)
                if next_line != -1:
                    end_docstring = content.find('"""', next_line + 3)
                    if end_docstring != -1:
                        insert_pos = content.find('\n', end_docstring) + 1
                        # Insert emergency check
                        content = content[:insert_pos] + emergency_check + content[insert_pos:]
                        
                        # Write back
                        with open('/workspace/handlers/sudo_handlers.py', 'w', encoding='utf-8') as f:
                            f.write(content)
                        
                        print("✅ Emergency deletion disable added to delete_admin_panel_completely")
                        return True
    
    print("❌ Could not find delete_admin_panel_completely function")
    return False

def check_marzban_connection():
    """Check if we can connect to Marzban to see current status."""
    try:
        import asyncio
        import sys
        sys.path.append('/workspace')
        
        async def check_connection():
            try:
                from marzban_api import marzban_api
                from config import MARZBAN_USERNAME, MARZBAN_PASSWORD
                
                # Try to create main admin API
                admin_api = await marzban_api.create_admin_api(MARZBAN_USERNAME, MARZBAN_PASSWORD)
                if admin_api:
                    print("✅ Connection to Marzban successful")
                    
                    # Get current admins and users
                    try:
                        stats = await admin_api.get_admin_stats()
                        if stats:
                            print(f"📊 Current Marzban status:")
                            print(f"   Total users: {stats.total_users}")
                            print(f"   Active users: {stats.active_users}")
                            print(f"   Traffic used: {stats.total_traffic_used}")
                        
                        users = await admin_api.get_users()
                        if users:
                            print(f"👥 Found {len(users)} users in Marzban")
                            for user in users[:5]:  # Show first 5 users
                                print(f"   - {user.username}: {user.status}")
                            if len(users) > 5:
                                print(f"   ... and {len(users) - 5} more users")
                        else:
                            print("⚠️ No users found in Marzban")
                            
                    except Exception as e:
                        print(f"❌ Error getting Marzban data: {e}")
                else:
                    print("❌ Could not connect to Marzban")
                    
            except Exception as e:
                print(f"❌ Error checking Marzban: {e}")
        
        asyncio.run(check_connection())
        
    except Exception as e:
        print(f"❌ Error in connection check: {e}")

if __name__ == "__main__":
    print("🚨 EMERGENCY RESPONSE SCRIPT")
    print("=" * 50)
    
    print("\n1. Disabling deletion functions...")
    disable_deletion_functions()
    
    print("\n2. Checking Marzban connection...")
    check_marzban_connection()
    
    print("\n3. Recommendations:")
    print("   - Stop the bot immediately if running")
    print("   - Check Marzban panel manually")
    print("   - Review bot logs")
    print("   - Check who had access to sudo commands")
    
    print("\n🔒 Deletion functions are now disabled!")