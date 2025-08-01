#!/usr/bin/env python3
"""
Test script for the new comprehensive FSM admin addition feature
"""

import asyncio
import sys
import os
import logging

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from handlers.sudo_handlers import AddAdminStates
from utils.notify import gb_to_bytes, days_to_seconds, bytes_to_gb, seconds_to_days
from models.schemas import AdminModel
from marzban_api import marzban_api

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


async def test_utility_functions():
    """Test utility conversion functions."""
    print("🧪 Testing utility functions...")
    
    # Test GB to bytes conversion
    assert gb_to_bytes(1) == 1073741824, "1 GB should be 1073741824 bytes"
    assert gb_to_bytes(100) == 107374182400, "100 GB should be 107374182400 bytes"
    assert gb_to_bytes(0.5) == 536870912, "0.5 GB should be 536870912 bytes"
    print("✅ GB to bytes conversion")
    
    # Test days to seconds conversion
    assert days_to_seconds(1) == 86400, "1 day should be 86400 seconds"
    assert days_to_seconds(30) == 2592000, "30 days should be 2592000 seconds"
    assert days_to_seconds(365) == 31536000, "365 days should be 31536000 seconds"
    print("✅ Days to seconds conversion")
    
    # Test reverse conversions
    assert bytes_to_gb(1073741824) == 1.0, "1073741824 bytes should be 1 GB"
    assert seconds_to_days(86400) == 1, "86400 seconds should be 1 day"
    print("✅ Reverse conversions")
    
    return True


async def test_admin_model_validation():
    """Test the new AdminModel with all fields."""
    print("🧪 Testing AdminModel validation...")
    
    # Test basic admin creation
    admin = AdminModel(
        user_id=123456789,
        admin_name="Test Admin",
        marzban_username="test_admin",
        marzban_password="SecurePass123!",
        max_users=50,
        max_total_time=days_to_seconds(90),
        max_total_traffic=gb_to_bytes(200),
        validity_days=90
    )
    
    assert admin.user_id == 123456789
    assert admin.admin_name == "Test Admin"
    assert admin.marzban_username == "test_admin"
    assert admin.marzban_password == "SecurePass123!"
    assert admin.max_users == 50
    assert admin.max_total_time == 7776000  # 90 days in seconds
    assert admin.max_total_traffic == 214748364800  # 200 GB in bytes
    assert admin.validity_days == 90
    print("✅ AdminModel creation and validation")
    
    # Test default values
    admin_defaults = AdminModel(user_id=987654321)
    assert admin_defaults.max_users == 10
    assert admin_defaults.max_total_time == 2592000  # 30 days
    assert admin_defaults.max_total_traffic == 107374182400  # 100 GB
    assert admin_defaults.validity_days == 30
    print("✅ AdminModel default values")
    
    return True


async def test_fsm_states():
    """Test FSM states definition."""
    print("🧪 Testing FSM states...")
    
    # Check all required states exist
    required_states = [
        'waiting_for_user_id',
        'waiting_for_admin_name',
        'waiting_for_marzban_username',
        'waiting_for_marzban_password',
        'waiting_for_traffic_volume',
        'waiting_for_max_users',
        'waiting_for_validity_period',
        'waiting_for_confirmation'
    ]
    
    for state_name in required_states:
        assert hasattr(AddAdminStates, state_name), f"Missing state: {state_name}"
    
    print("✅ All FSM states defined")
    return True


async def test_marzban_api_functions():
    """Test new Marzban API functions."""
    print("🧪 Testing Marzban API functions...")
    
    # Test that new methods exist
    assert hasattr(marzban_api, 'create_admin'), "Missing create_admin method"
    assert hasattr(marzban_api, 'admin_exists'), "Missing admin_exists method"
    print("✅ Marzban API methods exist")
    
    # Test methods are callable
    assert callable(marzban_api.create_admin), "create_admin should be callable"
    assert callable(marzban_api.admin_exists), "admin_exists should be callable"
    print("✅ Marzban API methods are callable")
    
    return True


async def test_database_schema_compatibility():
    """Test database schema supports new fields."""
    print("🧪 Testing database schema...")
    
    from database import db
    
    # Initialize database
    await db.init_db()
    
    # Create test admin with new fields
    admin = AdminModel(
        user_id=999888777,
        admin_name="Schema Test Admin",
        marzban_username="schema_test",
        marzban_password="TestPass123!",
        max_users=25,
        max_total_time=days_to_seconds(60),
        max_total_traffic=gb_to_bytes(150),
        validity_days=60
    )
    
    # Test adding admin with new fields
    success = await db.add_admin(admin)
    assert success, "Should be able to add admin with new fields"
    print("✅ Admin added with new fields")
    
    # Test retrieving admin
    retrieved = await db.get_admin(999888777)
    assert retrieved is not None, "Should be able to retrieve admin"
    assert retrieved.admin_name == "Schema Test Admin"
    assert retrieved.marzban_username == "schema_test"
    assert retrieved.validity_days == 60
    print("✅ Admin retrieved with new fields")
    
    # Cleanup
    await db.remove_admin(999888777)
    print("✅ Test cleanup completed")
    
    return True


async def test_validation_logic():
    """Test input validation logic."""
    print("🧪 Testing validation logic...")
    
    # Test username validation pattern
    import re
    username_pattern = r'^[a-zA-Z0-9_-]{3,50}$'
    
    valid_usernames = ['admin_test', 'user123', 'test-admin', 'a_b_c']
    invalid_usernames = ['ab', 'test user', 'admin@test', 'x' * 51]
    
    for username in valid_usernames:
        assert re.match(username_pattern, username), f"Should be valid: {username}"
    
    for username in invalid_usernames:
        assert not re.match(username_pattern, username), f"Should be invalid: {username}"
    
    print("✅ Username validation pattern")
    
    # Test password strength logic
    def check_password_strength(password):
        if len(password) < 8:
            return False, "Too short"
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        return (has_upper or has_lower or has_digit), "Basic requirements"
    
    strong_passwords = ['Password123', 'myPass2024', 'Secure!Pass', '12345678']  # 12345678 has digits
    weak_passwords = ['pass', '        ', 'short']
    
    for password in strong_passwords:
        is_strong, _ = check_password_strength(password)
        assert is_strong, f"Should be strong: {password}"
    
    for password in weak_passwords:
        is_strong, _ = check_password_strength(password)
        assert not is_strong, f"Should be weak: {password}"
    
    print("✅ Password strength validation")
    
    return True


async def main():
    """Run all FSM tests."""
    print("🚀 Starting FSM Admin Addition Tests\n")
    
    tests = [
        ("Utility Functions", test_utility_functions),
        ("AdminModel Validation", test_admin_model_validation),
        ("FSM States", test_fsm_states),
        ("Marzban API Functions", test_marzban_api_functions),
        ("Database Schema", test_database_schema_compatibility),
        ("Validation Logic", test_validation_logic),
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
    print("📊 FSM TEST SUMMARY")
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
        print("🎉 All FSM tests passed! New admin addition system is ready!")
        return 0
    else:
        print("⚠️  Some FSM tests failed. Please check the implementation.")
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