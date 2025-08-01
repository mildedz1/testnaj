#!/usr/bin/env python3
"""
Test script for Marzban Admin Bot
Tests basic functionality without requiring actual API connections
"""

import asyncio
import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def test_imports():
    """Test that all modules can be imported correctly."""
    print("🧪 Testing imports...")
    
    try:
        import config
        print("✅ config imported")
        
        from database import db
        print("✅ database imported")
        
        from models.schemas import AdminModel, UsageReportModel, LogModel
        print("✅ models imported")
        
        from marzban_api import marzban_api
        print("✅ marzban_api imported")
        
        from utils.notify import format_traffic_size, format_time_duration
        print("✅ utils imported")
        
        from handlers.sudo_handlers import sudo_router
        from handlers.admin_handlers import admin_router
        print("✅ handlers imported")
        
        from scheduler import init_scheduler
        print("✅ scheduler imported")
        
        return True
        
    except Exception as e:
        print(f"❌ Import error: {e}")
        return False


async def test_database():
    """Test database initialization."""
    print("\n🧪 Testing database...")
    
    try:
        from database import db
        await db.init_db()
        print("✅ Database initialized")
        
        # Test basic operations
        from models.schemas import AdminModel
        admin = AdminModel(
            user_id=123456789,
            username="test_admin",
            max_users=5,
            max_total_time=86400,
            max_total_traffic=1073741824
        )
        
        # Test add admin
        result = await db.add_admin(admin)
        print(f"✅ Add admin test: {result}")
        
        # Test get admin
        retrieved = await db.get_admin(123456789)
        print(f"✅ Get admin test: {retrieved is not None}")
        
        # Test authorization
        authorized = await db.is_admin_authorized(123456789)
        print(f"✅ Authorization test: {authorized}")
        
        # Cleanup
        await db.remove_admin(123456789)
        print("✅ Cleanup completed")
        
        return True
        
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False


async def test_models():
    """Test data models."""
    print("\n🧪 Testing models...")
    
    try:
        from models.schemas import AdminModel, UsageReportModel, LogModel
        from datetime import datetime
        
        # Test AdminModel
        admin = AdminModel(
            user_id=123456789,
            username="test_admin",
            max_users=10,
            max_total_time=2592000,
            max_total_traffic=107374182400
        )
        print(f"✅ AdminModel: {admin.user_id}")
        
        # Test UsageReportModel
        report = UsageReportModel(
            admin_user_id=123456789,
            check_time=datetime.now(),
            current_users=5,
            current_total_traffic=1073741824
        )
        print(f"✅ UsageReportModel: {report.admin_user_id}")
        
        # Test LogModel
        log = LogModel(
            admin_user_id=123456789,
            action="test_action",
            details="Test log entry"
        )
        print(f"✅ LogModel: {log.action}")
        
        return True
        
    except Exception as e:
        print(f"❌ Models error: {e}")
        return False


async def test_utilities():
    """Test utility functions."""
    print("\n🧪 Testing utilities...")
    
    try:
        from utils.notify import format_traffic_size, format_time_duration
        
        # Test traffic formatting
        traffic_1gb = await format_traffic_size(1073741824)
        print(f"✅ Traffic format (1GB): {traffic_1gb}")
        
        traffic_500mb = await format_traffic_size(524288000)
        print(f"✅ Traffic format (500MB): {traffic_500mb}")
        
        # Test time formatting
        time_1day = await format_time_duration(86400)
        print(f"✅ Time format (1 day): {time_1day}")
        
        time_2hours = await format_time_duration(7200)
        print(f"✅ Time format (2 hours): {time_2hours}")
        
        return True
        
    except Exception as e:
        print(f"❌ Utilities error: {e}")
        return False


async def test_config():
    """Test configuration."""
    print("\n🧪 Testing configuration...")
    
    try:
        import config
        
        print(f"✅ BOT_TOKEN set: {config.BOT_TOKEN != 'YOUR_BOT_TOKEN'}")
        print(f"✅ MARZBAN_URL: {config.MARZBAN_URL}")
        print(f"✅ SUDO_ADMINS count: {len(config.SUDO_ADMINS)}")
        print(f"✅ MONITORING_INTERVAL: {config.MONITORING_INTERVAL}s")
        print(f"✅ WARNING_THRESHOLD: {config.WARNING_THRESHOLD}")
        
        # Test messages
        print(f"✅ Messages loaded: {len(config.MESSAGES)} items")
        print(f"✅ Buttons loaded: {len(config.BUTTONS)} items")
        
        return True
        
    except Exception as e:
        print(f"❌ Config error: {e}")
        return False


async def main():
    """Run all tests."""
    print("🚀 Starting Marzban Admin Bot Tests\n")
    
    tests = [
        ("Imports", test_imports),
        ("Configuration", test_config),
        ("Models", test_models),
        ("Utilities", test_utilities),
        ("Database", test_database),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n" + "="*50)
        print(f"Running {test_name} tests...")
        print("="*50)
        
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} test failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*50)
    print("📊 TEST SUMMARY")
    print("="*50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Bot is ready to run.")
        return 0
    else:
        print("⚠️  Some tests failed. Please check the configuration.")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n🛑 Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Critical error during testing: {e}")
        sys.exit(1)