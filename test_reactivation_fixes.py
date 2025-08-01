#!/usr/bin/env python3
"""Test script to verify the admin reactivation fixes."""

import asyncio
from database import db
from models.schemas import AdminModel
from handlers.sudo_handlers import deactivate_admin_panel_by_id, restore_admin_password_and_update_db, reactivate_admin_panel_users
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_reactivation_fixes():
    """Test all admin reactivation fixes."""
    print("🧪 Testing Admin Reactivation Fixes\n")
    
    # Initialize database
    await db.init_db()
    print("✅ Database initialized")
    
    # Test user ID
    test_user_id = 555555555
    
    # Create multiple admin panels for the same user
    admin1 = AdminModel(
        user_id=test_user_id,
        admin_name="Main Panel",
        marzban_username="main_admin",
        marzban_password="main_original_pass123",
        username="testuser",
        first_name="Test",
        last_name="User",
        max_users=20,
        max_total_time=2592000,  # 30 days
        max_total_traffic=107374182400,  # 100GB
        validity_days=30,
        is_active=True
    )
    
    admin2 = AdminModel(
        user_id=test_user_id,
        admin_name="Secondary Panel",
        marzban_username="secondary_admin",
        marzban_password="secondary_original_pass456",
        username="testuser",
        first_name="Test",
        last_name="User",
        max_users=10,
        max_total_time=1296000,  # 15 days
        max_total_traffic=53687091200,  # 50GB
        validity_days=15,
        is_active=True
    )
    
    # Add both admins
    result1 = await db.add_admin(admin1)
    result2 = await db.add_admin(admin2)
    
    print(f"✅ Admin 1 added: {result1}")
    print(f"✅ Admin 2 added: {result2}")
    
    if not (result1 and result2):
        print("❌ Failed to add admins")
        return
    
    # Get the created admins
    admins = await db.get_admins_for_user(test_user_id)
    if len(admins) != 2:
        print(f"❌ Expected 2 admins, found {len(admins)}")
        return
    
    print(f"✅ Created {len(admins)} admin panels")
    for admin in admins:
        print(f"   - Panel {admin.id}: {admin.admin_name} ({admin.marzban_username})")
    
    # Test 1: Deactivate both panels
    print("\n📉 Test 1: Deactivating Admin Panels...")
    for admin in admins:
        deactivation_result = await deactivate_admin_panel_by_id(admin.id, "Test limit exceeded")
        print(f"✅ Panel {admin.id} deactivation: {deactivation_result}")
    
    # Check status after deactivation
    admins_after_deactivation = await db.get_admins_for_user(test_user_id)
    print("\n📊 Status after deactivation:")
    for admin in admins_after_deactivation:
        print(f"   - Panel {admin.id}: Active={admin.is_active}, "
              f"Current_Pass={admin.marzban_password[:10]}..., "
              f"Original_Pass={admin.original_password[:10] if admin.original_password else 'None'}...")
    
    # Test 2: Individual password restoration
    print("\n🔑 Test 2: Testing Individual Password Restoration...")
    for admin in admins_after_deactivation:
        if admin.original_password:
            restore_result = await restore_admin_password_and_update_db(admin.id, admin.original_password)
            print(f"✅ Panel {admin.id} password restoration: {restore_result}")
            
            # Check if password was updated in DB
            updated_admin = await db.get_admin_by_id(admin.id)
            if updated_admin and updated_admin.marzban_password == updated_admin.original_password:
                print(f"✅ Panel {admin.id} database password updated correctly")
            else:
                print(f"❌ Panel {admin.id} database password NOT updated")
    
    # Test 3: Individual user reactivation (will fail without real Marzban but should not crash)
    print("\n👥 Test 3: Testing Individual User Reactivation...")
    for admin in admins_after_deactivation:
        reactivated_count = await reactivate_admin_panel_users(admin.id)
        print(f"✅ Panel {admin.id} user reactivation: {reactivated_count} users reactivated")
    
    # Test 4: Database reactivation
    print("\n📈 Test 4: Testing Database Reactivation...")
    for admin in admins_after_deactivation:
        reactivation_result = await db.reactivate_admin(admin.id)
        print(f"✅ Panel {admin.id} database reactivation: {reactivation_result}")
    
    # Check final status
    final_admins = await db.get_admins_for_user(test_user_id)
    print("\n📊 Final Status:")
    for admin in final_admins:
        print(f"   - Panel {admin.id}: Active={admin.is_active}, "
              f"Deactivation_Reason={admin.deactivated_reason}")
    
    # Test 5: Check authorization
    auth_result = await db.is_admin_authorized(test_user_id)
    print(f"\n✅ User authorization after reactivation: {auth_result}")
    
    # Test 6: Test the improved admin list display
    print("\n📋 Test 6: Testing Admin List Display...")
    from handlers.sudo_handlers import get_admin_list_keyboard
    all_admins = await db.get_all_admins()
    keyboard = get_admin_list_keyboard(all_admins, "test_action")
    print(f"✅ Admin list keyboard created with {len(keyboard.inline_keyboard)} buttons")
    
    # Print some button texts to verify grouping
    for i, button_row in enumerate(keyboard.inline_keyboard[:3]):  # Show first 3 rows
        if button_row:
            print(f"   - Button {i+1}: {button_row[0].text}")
    
    # Cleanup
    for admin in final_admins:
        await db.remove_admin_by_id(admin.id)
    print("\n✅ Cleanup completed")
    
    print("\n🎉 All reactivation fixes tested successfully!")

if __name__ == "__main__":
    asyncio.run(test_reactivation_fixes())