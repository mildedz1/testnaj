#!/usr/bin/env python3
"""
Test script for the new panel management functionality:
1. Panel deactivation instead of deletion
2. Panel limits editing
"""

import asyncio
from database import db
from models.schemas import AdminModel
from handlers.sudo_handlers import get_panel_list_keyboard
from utils.notify import gb_to_bytes, days_to_seconds, bytes_to_gb, seconds_to_days

async def test_panel_management():
    """Test the new panel management features."""
    print("🧪 Testing Panel Management Features\n")
    
    # Initialize database
    await db.init_db()
    print("✅ Database initialized")
    
    # Test user IDs
    test_user_id_1 = 111111111
    test_user_id_2 = 222222222
    
    # Clean up any existing test data for these users
    existing_admins_1 = await db.get_admins_for_user(test_user_id_1)
    existing_admins_2 = await db.get_admins_for_user(test_user_id_2)
    
    for admin in existing_admins_1 + existing_admins_2:
        await db.remove_admin_by_id(admin.id)
    
    # Create test admin panels
    print("\n📝 Creating test admin panels...")
    
    admin1 = AdminModel(
        user_id=test_user_id_1,
        admin_name="Test Admin 1",
        marzban_username="test_admin_1",
        marzban_password="test_pass_1",
        username="testuser1",
        max_users=10,
        max_total_traffic=gb_to_bytes(500),  # 500 GB
        max_total_time=days_to_seconds(30),  # 30 days
        validity_days=30,
        is_active=True
    )
    
    admin2 = AdminModel(
        user_id=test_user_id_2,
        admin_name="Test Admin 2",
        marzban_username="test_admin_2", 
        marzban_password="test_pass_2",
        username="testuser2",
        max_users=20,
        max_total_traffic=gb_to_bytes(1000),  # 1000 GB
        max_total_time=days_to_seconds(60),   # 60 days
        validity_days=60,
        is_active=True
    )
    
    success1 = await db.add_admin(admin1)
    success2 = await db.add_admin(admin2)
    
    print(f"✅ Admin 1 created: {success1}")
    print(f"✅ Admin 2 created: {success2}")
    
    # Get the created admins with their auto-generated IDs
    created_admins_1 = await db.get_admins_for_user(test_user_id_1)
    created_admins_2 = await db.get_admins_for_user(test_user_id_2)
    test_admins = created_admins_1 + created_admins_2
    
    if len(test_admins) < 2:
        print("❌ Test panels not created properly")
        return False
    
    admin_1_id = created_admins_1[0].id if created_admins_1 else None
    admin_2_id = created_admins_2[0].id if created_admins_2 else None
    
    print(f"✅ Created panels with IDs: {admin_1_id}, {admin_2_id}")
    
    # Test 1: Panel List Display
    print("\n🔍 Test 1: Panel List Display")
    
    if len(test_admins) >= 2:
        print(f"✅ Found {len(test_admins)} test panels")
        
        # Test panel list keyboard generation
        keyboard = get_panel_list_keyboard(test_admins, "test_action")
        print(f"✅ Panel list keyboard generated with {len(keyboard.inline_keyboard)} buttons")
        
        # Check if panel info shows correctly
        for admin in test_admins:
            traffic_gb = bytes_to_gb(admin.max_total_traffic)
            time_days = seconds_to_days(admin.max_total_time)
            print(f"   - Panel {admin.id}: {admin.admin_name} - {traffic_gb}GB/{time_days}د")
    else:
        print("❌ Test panels not found")
        return False
    
    # Test 2: Panel Deactivation
    print("\n⏸️ Test 2: Panel Deactivation")
    if admin_1_id:
        admin_to_deactivate = await db.get_admin_by_id(admin_1_id)
        if admin_to_deactivate and admin_to_deactivate.is_active:
            success = await db.deactivate_admin(admin_1_id, "Test deactivation")
            print(f"✅ Panel deactivation: {success}")
            
            # Verify deactivation
            deactivated_admin = await db.get_admin_by_id(admin_1_id)
            if deactivated_admin and not deactivated_admin.is_active:
                print(f"✅ Panel {admin_1_id} successfully deactivated")
                print(f"   - Reason: {deactivated_admin.deactivated_reason}")
                print(f"   - Deactivated at: {deactivated_admin.deactivated_at}")
            else:
                print(f"❌ Panel {admin_1_id} deactivation failed")
        else:
            print("❌ Test panel not found or already inactive")
    else:
        print("❌ No admin ID to test deactivation")
    
    # Test 3: Panel Limits Editing
    print("\n✏️ Test 3: Panel Limits Editing")
    if admin_2_id:
        admin_to_edit = await db.get_admin_by_id(admin_2_id)
        if admin_to_edit:
            # Original limits
            orig_traffic = bytes_to_gb(admin_to_edit.max_total_traffic)
            orig_time = seconds_to_days(admin_to_edit.max_total_time)
            print(f"   Original limits: {orig_traffic}GB / {orig_time} days")
            
            # New limits
            new_traffic_gb = 750
            new_time_days = 45
            new_traffic_bytes = gb_to_bytes(new_traffic_gb)
            new_time_seconds = days_to_seconds(new_time_days)
            
            # Update limits
            success = await db.update_admin(
                admin_2_id,
                max_total_traffic=new_traffic_bytes,
                max_total_time=new_time_seconds
            )
            print(f"✅ Panel limits update: {success}")
            
            # Verify update
            updated_admin = await db.get_admin_by_id(admin_2_id)
            if updated_admin:
                updated_traffic = bytes_to_gb(updated_admin.max_total_traffic)
                updated_time = seconds_to_days(updated_admin.max_total_time)
                print(f"   Updated limits: {updated_traffic}GB / {updated_time} days")
                
                if updated_traffic == new_traffic_gb and updated_time == new_time_days:
                    print("✅ Panel limits successfully updated")
                else:
                    print("❌ Panel limits update verification failed")
            else:
                print("❌ Updated panel not found")
        else:
            print("❌ Test panel for editing not found")
    else:
        print("❌ No admin ID to test editing")
    
    # Test 4: Active/Inactive Panel Filtering
    print("\n🔍 Test 4: Active/Inactive Panel Filtering")
    all_test_admins = []
    if admin_1_id:
        admin_1 = await db.get_admin_by_id(admin_1_id)
        if admin_1:
            all_test_admins.append(admin_1)
    if admin_2_id:
        admin_2 = await db.get_admin_by_id(admin_2_id)
        if admin_2:
            all_test_admins.append(admin_2)
    
    active_admins = [admin for admin in all_test_admins if admin.is_active]
    inactive_admins = [admin for admin in all_test_admins if not admin.is_active]
    
    print(f"✅ Active panels: {len(active_admins)}")
    print(f"✅ Inactive panels: {len(inactive_admins)}")
    
    for admin in active_admins:
        print(f"   - Active: Panel {admin.id} ({admin.admin_name})")
    
    for admin in inactive_admins:
        print(f"   - Inactive: Panel {admin.id} ({admin.admin_name}) - {admin.deactivated_reason}")
    
    # Test 5: Panel Reactivation
    print("\n🔄 Test 5: Panel Reactivation")
    if inactive_admins:
        panel_to_reactivate = inactive_admins[0]
        success = await db.reactivate_admin(panel_to_reactivate.id)
        print(f"✅ Panel reactivation: {success}")
        
        # Verify reactivation
        reactivated_admin = await db.get_admin_by_id(panel_to_reactivate.id)
        if reactivated_admin and reactivated_admin.is_active:
            print(f"✅ Panel {panel_to_reactivate.id} successfully reactivated")
        else:
            print(f"❌ Panel {panel_to_reactivate.id} reactivation failed")
    else:
        print("⏭️ No inactive panels to test reactivation")
    
    # Cleanup
    print("\n🧹 Cleanup...")
    if admin_1_id:
        await db.remove_admin_by_id(admin_1_id)
    if admin_2_id:
        await db.remove_admin_by_id(admin_2_id)
    print("✅ Test data cleaned up")
    
    print("\n✨ Panel Management Tests Completed!")
    return True


if __name__ == "__main__":
    asyncio.run(test_panel_management())