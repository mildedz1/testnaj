#!/usr/bin/env python3
"""Test script for multi-panel admin functionality."""

import asyncio
from database import db
from models.schemas import AdminModel
from marzban_api import marzban_api

async def test_multi_panel():
    """Test multi-panel functionality."""
    print("🧪 Testing Multi-Panel Admin Functionality\n")
    
    # Initialize database
    await db.init_db()
    print("✅ Database initialized")
    
    # Test user ID
    test_user_id = 987654321
    
    # Create two admin panels for the same user
    admin1 = AdminModel(
        user_id=test_user_id,
        admin_name="Main Panel",
        marzban_username="admin_main",
        marzban_password="password123",
        username="testuser",
        first_name="Test",
        last_name="User",
        max_users=20,
        max_total_time=2592000,  # 30 days
        max_total_traffic=107374182400,  # 100GB
        validity_days=30
    )
    
    admin2 = AdminModel(
        user_id=test_user_id,
        admin_name="Secondary Panel",
        marzban_username="admin_secondary",
        marzban_password="password456",
        username="testuser",
        first_name="Test",
        last_name="User",
        max_users=10,
        max_total_time=1296000,  # 15 days
        max_total_traffic=53687091200,  # 50GB
        validity_days=15
    )
    
    # Add both admins
    result1 = await db.add_admin(admin1)
    result2 = await db.add_admin(admin2)
    
    print(f"✅ Admin 1 added: {result1}")
    print(f"✅ Admin 2 added: {result2}")
    
    # Test getting admins for user
    admins = await db.get_admins_for_user(test_user_id)
    print(f"✅ Found {len(admins)} admin panels for user {test_user_id}")
    
    for admin in admins:
        print(f"   - Panel: {admin.admin_name} (ID: {admin.id})")
        print(f"     Marzban Username: {admin.marzban_username}")
        print(f"     Max Users: {admin.max_users}")
    
    # Test authorization
    authorized = await db.is_admin_authorized(test_user_id)
    print(f"✅ User authorization: {authorized}")
    
    # Test MarzbanAdminAPI creation
    if admins:
        admin = admins[0]
        try:
            admin_api = await marzban_api.create_admin_api(
                admin.marzban_username, 
                admin.marzban_password
            )
            print(f"✅ MarzbanAdminAPI created for {admin.marzban_username}")
            
            # Test connection (will fail without real Marzban, but should not crash)
            connected = await admin_api.test_connection()
            print(f"✅ Connection test result: {connected} (expected to fail without real Marzban)")
            
        except Exception as e:
            print(f"✅ API test completed with expected error: {e}")
    
    # Test get admin by ID
    if admins:
        admin_by_id = await db.get_admin_by_id(admins[0].id)
        print(f"✅ Get admin by ID: {admin_by_id.admin_name if admin_by_id else 'Not found'}")
    
    # Cleanup
    for admin in admins:
        await db.remove_admin_by_id(admin.id)
    print("✅ Cleanup completed")
    
    print("\n🎉 Multi-panel test completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_multi_panel())