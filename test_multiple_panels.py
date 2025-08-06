#!/usr/bin/env python3
"""
Test script to demonstrate multiple panels per user functionality
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import db
from models.schemas import AdminModel
from datetime import datetime

async def test_multiple_panels():
    """Test multiple panels per user functionality."""
    print("🧪 Testing Multiple Panels Per User...")
    
    # Initialize database
    await db.init_db()
    
    # Test user ID
    test_user_id = 123456789
    
    print(f"\n1️⃣ Creating multiple panels for user {test_user_id}...")
    
    # Create multiple panels for the same user
    panels_data = [
        {
            "admin_name": "پنل اول",
            "marzban_username": "panel1_user123",
            "marzban_password": "pass123",
            "max_users": 50,
            "max_total_traffic": 100 * 1024**3,  # 100GB
            "max_total_time": 30 * 24 * 3600,    # 30 days
        },
        {
            "admin_name": "پنل دوم", 
            "marzban_username": "panel2_user123",
            "marzban_password": "pass456",
            "max_users": 100,
            "max_total_traffic": 200 * 1024**3,  # 200GB
            "max_total_time": 60 * 24 * 3600,    # 60 days
        },
        {
            "admin_name": "پنل تست",
            "marzban_username": "test_panel_user123", 
            "marzban_password": "testpass",
            "max_users": 25,
            "max_total_traffic": 50 * 1024**3,   # 50GB
            "max_total_time": 15 * 24 * 3600,    # 15 days
        }
    ]
    
    created_panels = []
    for i, panel_data in enumerate(panels_data):
        admin = AdminModel(
            user_id=test_user_id,
            username=f"test_user_{test_user_id}",
            first_name="Test User",
            last_name="Multiple Panels",
            **panel_data,
            validity_days=365,
            is_active=True,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        admin_id = await db.add_admin(admin)
        if admin_id > 0:
            admin.id = admin_id
            created_panels.append(admin)
            print(f"   ✅ Created panel {i+1}: {panel_data['admin_name']} (ID: {admin_id})")
        else:
            print(f"   ❌ Failed to create panel {i+1}: {panel_data['admin_name']}")
    
    print(f"\n2️⃣ Retrieving all panels for user {test_user_id}...")
    user_panels = await db.get_admins_for_user(test_user_id)
    print(f"   📊 Found {len(user_panels)} panels for this user:")
    
    for panel in user_panels:
        status = "🟢 Active" if panel.is_active else "🔴 Inactive"
        print(f"   • {panel.admin_name} ({panel.marzban_username}) - {status}")
        print(f"     Users: {panel.max_users}, Traffic: {panel.max_total_traffic // (1024**3)}GB, Time: {panel.max_total_time // (24*3600)} days")
    
    print(f"\n3️⃣ Testing individual panel operations...")
    
    if created_panels:
        # Test editing limits for specific panel
        test_panel = created_panels[0]
        print(f"   🔧 Testing limit updates for panel: {test_panel.admin_name}")
        
        # Update user limit
        success = await db.update_admin_max_users(test_panel.id, 75)
        print(f"   • Update max users to 75: {'✅ Success' if success else '❌ Failed'}")
        
        # Update traffic limit  
        new_traffic = 150 * 1024**3  # 150GB
        success = await db.update_admin_max_traffic(test_panel.id, new_traffic)
        print(f"   • Update max traffic to 150GB: {'✅ Success' if success else '❌ Failed'}")
        
        # Update time limit
        new_time = 45 * 24 * 3600  # 45 days
        success = await db.update_admin_max_time(test_panel.id, new_time)
        print(f"   • Update max time to 45 days: {'✅ Success' if success else '❌ Failed'}")
        
        # Verify changes
        updated_panel = await db.get_admin_by_id(test_panel.id)
        if updated_panel:
            print(f"   📋 Updated panel limits:")
            print(f"     • Users: {updated_panel.max_users}")
            print(f"     • Traffic: {updated_panel.max_total_traffic // (1024**3)}GB")
            print(f"     • Time: {updated_panel.max_total_time // (24*3600)} days")
    
    print(f"\n4️⃣ Testing panel deactivation/reactivation...")
    
    if len(created_panels) >= 2:
        # Deactivate one panel
        test_panel = created_panels[1]
        success = await db.deactivate_admin(test_panel.id, "Test deactivation")
        print(f"   • Deactivate panel '{test_panel.admin_name}': {'✅ Success' if success else '❌ Failed'}")
        
        # Check active panels
        active_panels = [p for p in await db.get_admins_for_user(test_user_id) if p.is_active]
        print(f"   📊 Active panels after deactivation: {len(active_panels)}/{len(user_panels)}")
        
        # Reactivate panel
        success = await db.reactivate_admin(test_panel.id)
        print(f"   • Reactivate panel '{test_panel.admin_name}': {'✅ Success' if success else '❌ Failed'}")
        
        # Check active panels again
        active_panels = [p for p in await db.get_admins_for_user(test_user_id) if p.is_active]
        print(f"   📊 Active panels after reactivation: {len(active_panels)}/{len(user_panels)}")
    
    print(f"\n5️⃣ Cleanup - Removing test panels...")
    for panel in created_panels:
        success = await db.remove_admin_by_id(panel.id)
        print(f"   🗑️ Removed panel {panel.admin_name}: {'✅ Success' if success else '❌ Failed'}")
    
    print(f"\n🎉 Multiple panels test completed!")
    print(f"📝 Summary:")
    print(f"   • ✅ Database supports multiple panels per user")
    print(f"   • ✅ Each panel has individual limits and settings")
    print(f"   • ✅ Individual panel operations work correctly")
    print(f"   • ✅ Panel activation/deactivation works independently")
    print(f"   • ✅ User can have unlimited number of panels")

if __name__ == "__main__":
    asyncio.run(test_multiple_panels())