#!/usr/bin/env python3
"""Test script to reproduce and verify admin reactivation bug fix."""

import asyncio
from database import db
from models.schemas import AdminModel
from handlers.sudo_handlers import deactivate_admin_panel_by_id
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_reactivation_bug():
    """Test admin reactivation bug and fix."""
    print("🧪 Testing Admin Reactivation Bug\n")
    
    # Initialize database
    await db.init_db()
    print("✅ Database initialized")
    
    # Test user ID
    test_user_id = 123456789
    
    # Create admin panel
    admin = AdminModel(
        user_id=test_user_id,
        admin_name="Test Panel",
        marzban_username="test_admin",
        marzban_password="original_password123",
        username="testuser",
        first_name="Test",
        last_name="User",
        max_users=10,
        max_total_time=2592000,  # 30 days
        max_total_traffic=107374182400,  # 100GB
        validity_days=30,
        is_active=True
    )
    
    # Add admin
    result = await db.add_admin(admin)
    print(f"✅ Admin added: {result}")
    
    if not result:
        print("❌ Failed to add admin")
        return
    
    # Get the created admin to get the ID
    admins = await db.get_admins_for_user(test_user_id)
    if not admins:
        print("❌ No admin found after creation")
        return
    
    created_admin = admins[0]
    print(f"✅ Created admin ID: {created_admin.id}")
    print(f"✅ Original password: {created_admin.marzban_password}")
    print(f"✅ Original password stored: {created_admin.original_password}")
    print(f"✅ Is active: {created_admin.is_active}")
    
    # Test deactivation (simulating limit exceeded)
    print("\n📉 Testing Admin Deactivation...")
    deactivation_result = await deactivate_admin_panel_by_id(created_admin.id, "Limit exceeded - test")
    print(f"✅ Deactivation result: {deactivation_result}")
    
    # Check admin status after deactivation
    admin_after_deactivation = await db.get_admin_by_id(created_admin.id)
    if admin_after_deactivation:
        print(f"✅ After deactivation - Is active: {admin_after_deactivation.is_active}")
        print(f"✅ After deactivation - Current password: {admin_after_deactivation.marzban_password}")
        print(f"✅ After deactivation - Original password stored: {admin_after_deactivation.original_password}")
        print(f"✅ After deactivation - Deactivation reason: {admin_after_deactivation.deactivated_reason}")
    else:
        print("❌ Admin not found after deactivation")
        return
    
    # Test reactivation
    print("\n📈 Testing Admin Reactivation...")
    reactivation_result = await db.reactivate_admin(created_admin.id)
    print(f"✅ Reactivation result: {reactivation_result}")
    
    # Check admin status after reactivation
    admin_after_reactivation = await db.get_admin_by_id(created_admin.id)
    if admin_after_reactivation:
        print(f"✅ After reactivation - Is active: {admin_after_reactivation.is_active}")
        print(f"✅ After reactivation - Current password: {admin_after_reactivation.marzban_password}")
        print(f"✅ After reactivation - Original password stored: {admin_after_reactivation.original_password}")
        print(f"✅ After reactivation - Deactivation reason: {admin_after_reactivation.deactivated_reason}")
        
        # Check if the bug exists
        if admin_after_reactivation.is_active:
            print("✅ Admin is properly reactivated")
        else:
            print("❌ BUG: Admin is not reactivated")
            
        if admin_after_reactivation.deactivated_reason is None:
            print("✅ Deactivation reason is properly cleared")
        else:
            print(f"❌ BUG: Deactivation reason not cleared: {admin_after_reactivation.deactivated_reason}")
            
        # The key issue: password should be restored to original
        if admin_after_reactivation.marzban_password == admin_after_reactivation.original_password:
            print("✅ Password properly restored to original")
        else:
            print(f"❌ BUG: Password not restored. Current: {admin_after_reactivation.marzban_password}, Original: {admin_after_reactivation.original_password}")
    
    # Cleanup
    await db.remove_admin_by_id(created_admin.id)
    print("\n✅ Cleanup completed")
    
    print("\n🎉 Admin reactivation test completed!")

if __name__ == "__main__":
    asyncio.run(test_reactivation_bug())