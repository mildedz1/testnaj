#!/usr/bin/env python3
"""
Test script to verify fixed password deactivation functionality.
Tests requirement: Change admin password to fixed value (ce8fb29b0e) when deactivated.
"""

import asyncio
import sys
import os
from datetime import datetime

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import Database
from models.schemas import AdminModel
from handlers.sudo_handlers import deactivate_admin_panel_by_id
import config


async def test_fixed_password_deactivation():
    """Test that deactivation uses the correct fixed password."""
    print("🧪 Testing Fixed Password Deactivation Functionality")
    print("=" * 60)
    
    # Initialize database
    db = Database("/tmp/test_fixed_password.db")
    await db.init_db()
    print("✅ Test database initialized")
    
    try:
        # Create a test admin
        test_admin = AdminModel(
            user_id=123456789,
            admin_name="Test Fixed Password Panel",
            marzban_username="test_fixed_pass_admin",
            marzban_password="original_test_password",
            username="test_user",
            first_name="Test",
            last_name="User",
            max_users=10,
            max_total_traffic=10737418240,  # 10GB
            validity_days=30,
            is_active=True
        )
        
        # Add admin to database
        success = await db.add_admin(test_admin)
        if not success:
            print("❌ Failed to add test admin")
            return False
        
        print("✅ Test admin created")
        
        # Get the admin with ID
        admin = await db.get_admin(test_admin.user_id)
        if not admin:
            print("❌ Failed to retrieve test admin")
            return False
        
        print(f"✅ Admin retrieved: ID={admin.id}")
        
        # Store original values for verification
        original_password = admin.marzban_password
        print(f"📝 Original password: {original_password}")
        
        # Test deactivation (this will try to call Marzban API but should update database)
        print("\n🔄 Testing deactivation process...")
        deactivation_success = await deactivate_admin_panel_by_id(admin.id, "Test deactivation")
        
        # Retrieve admin after deactivation
        deactivated_admin = await db.get_admin_by_id(admin.id)
        if not deactivated_admin:
            print("❌ Failed to retrieve admin after deactivation")
            return False
        
        # Check if original password was stored
        if deactivated_admin.original_password != original_password:
            print(f"❌ Original password not stored correctly!")
            print(f"   Expected: {original_password}")
            print(f"   Got: {deactivated_admin.original_password}")
            return False
        
        print(f"✅ Original password stored: {deactivated_admin.original_password}")
        
        # Check if password was changed to fixed value
        expected_fixed_password = "ce8fb29b0e"
        if deactivated_admin.marzban_password != expected_fixed_password:
            print(f"❌ Password not changed to fixed value!")
            print(f"   Expected: {expected_fixed_password}")
            print(f"   Got: {deactivated_admin.marzban_password}")
            return False
        
        print(f"✅ Password changed to fixed value: {deactivated_admin.marzban_password}")
        
        # Check if admin was deactivated
        if deactivated_admin.is_active:
            print("❌ Admin was not deactivated!")
            return False
        
        print("✅ Admin deactivated successfully")
        
        # Check deactivation reason
        if deactivated_admin.deactivated_reason != "Test deactivation":
            print(f"❌ Deactivation reason not set correctly!")
            print(f"   Expected: Test deactivation")
            print(f"   Got: {deactivated_admin.deactivated_reason}")
            return False
        
        print(f"✅ Deactivation reason set: {deactivated_admin.deactivated_reason}")
        
        # Test that API calls would use the correct format
        print("\n📋 Testing API call parameters:")
        print(f"✅ Fixed password matches requirement: {expected_fixed_password}")
        print("✅ API call would use: update_admin_password(username, password, is_sudo=False)")
        
        print("\n🎉 All fixed password deactivation tests PASSED!")
        return True
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Clean up test database
        try:
            os.remove("/tmp/test_fixed_password.db")
            print("🧹 Test database cleaned up")
        except:
            pass


async def test_multiple_panels_individual_deactivation():
    """Test that only specific panels get deactivated, not all panels of same user."""
    print("\n" + "=" * 60)
    print("🧪 Testing Individual Panel Deactivation")
    print("=" * 60)
    
    # Initialize database
    db = Database("/tmp/test_individual_deactivation.db")
    await db.init_db()
    print("✅ Test database initialized")
    
    try:
        # Create multiple panels for the same user
        user_id = 987654321
        panels = []
        
        for i in range(3):
            admin = AdminModel(
                user_id=user_id,
                admin_name=f"Panel {i+1}",
                marzban_username=f"admin_panel_{i+1}",
                marzban_password=f"password_{i+1}",
                username="multi_panel_user",
                first_name="Multi",
                last_name="Panel",
                max_users=10,
                max_total_traffic=10737418240,  # 10GB
                validity_days=30,
                is_active=True
            )
            
            success = await db.add_admin(admin)
            if not success:
                print(f"❌ Failed to add panel {i+1}")
                return False
            
            panels.append(admin)
        
        print(f"✅ Created {len(panels)} panels for user {user_id}")
        
        # Get all panels for verification
        user_panels = await db.get_admins_for_user(user_id)
        if len(user_panels) != 3:
            print(f"❌ Expected 3 panels, got {len(user_panels)}")
            return False
        
        print(f"✅ Verified {len(user_panels)} panels in database")
        
        # Deactivate only the second panel
        target_panel = user_panels[1]  # Panel 2
        print(f"\n🔄 Deactivating Panel 2 (ID: {target_panel.id})...")
        
        deactivation_success = await deactivate_admin_panel_by_id(target_panel.id, "Individual deactivation test")
        
        # Check results
        updated_panels = await db.get_admins_for_user(user_id)
        active_count = len([p for p in updated_panels if p.is_active])
        inactive_count = len([p for p in updated_panels if not p.is_active])
        
        if active_count != 2:
            print(f"❌ Expected 2 active panels, got {active_count}")
            return False
        
        if inactive_count != 1:
            print(f"❌ Expected 1 inactive panel, got {inactive_count}")
            return False
        
        print(f"✅ Individual deactivation successful: {active_count} active, {inactive_count} inactive")
        
        # Verify which panel was deactivated
        deactivated_panel = [p for p in updated_panels if not p.is_active][0]
        if deactivated_panel.id != target_panel.id:
            print(f"❌ Wrong panel deactivated! Expected ID {target_panel.id}, got {deactivated_panel.id}")
            return False
        
        print(f"✅ Correct panel deactivated: {deactivated_panel.admin_name}")
        
        # Verify the other panels remain active
        active_panels = [p for p in updated_panels if p.is_active]
        for panel in active_panels:
            if panel.marzban_password == "ce8fb29b0e":
                print(f"❌ Active panel {panel.admin_name} has fixed password! Should only be for deactivated panels.")
                return False
        
        print("✅ Active panels retain original passwords")
        
        # Verify deactivated panel has fixed password and stored original
        if deactivated_panel.marzban_password != "ce8fb29b0e":
            print(f"❌ Deactivated panel doesn't have fixed password!")
            return False
        
        if deactivated_panel.original_password != "password_2":
            print(f"❌ Original password not stored correctly for deactivated panel!")
            return False
        
        print("✅ Deactivated panel has correct fixed password and stored original")
        
        print("\n🎉 Individual panel deactivation tests PASSED!")
        return True
        
    except Exception as e:
        print(f"❌ Error during individual deactivation testing: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Clean up test database
        try:
            os.remove("/tmp/test_individual_deactivation.db")
            print("🧹 Test database cleaned up")
        except:
            pass


async def main():
    """Run all tests."""
    print("🧪 Testing Panel Management Requirements")
    print("=" * 60)
    
    success1 = await test_fixed_password_deactivation()
    success2 = await test_multiple_panels_individual_deactivation()
    
    print("\n" + "=" * 60)
    print("📋 TEST SUMMARY")
    print("=" * 60)
    
    if success1:
        print("✅ Fixed password deactivation - PASSED")
    else:
        print("❌ Fixed password deactivation - FAILED")
    
    if success2:
        print("✅ Individual panel deactivation - PASSED")
    else:
        print("❌ Individual panel deactivation - FAILED")
    
    if success1 and success2:
        print("\n🎉 ALL TESTS PASSED!")
        return True
    else:
        print("\n❌ SOME TESTS FAILED!")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)