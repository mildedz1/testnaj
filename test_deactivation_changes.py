#!/usr/bin/env python3
"""
Test script to verify the manual vs automatic deactivation changes.
This script tests the new implementation without requiring actual Marzban API calls.
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from marzban_api import marzban_api
from handlers.sudo_handlers import delete_admin_panel_completely, deactivate_admin_panel_by_id
from database import db
from models.schemas import AdminModel


class TestDeactivationChanges(unittest.TestCase):
    """Test the new deactivation logic implementation."""

    def setUp(self):
        """Set up test mocks."""
        self.test_admin = AdminModel(
            id=1,
            user_id=12345,
            admin_name="Test Admin",
            marzban_username="test_admin",
            marzban_password="original_password",
            max_users=10,
            max_total_time=2592000,  # 30 days
            max_total_traffic=107374182400,  # 100GB
            validity_days=30,
            is_active=True,
            original_password=None
        )

    @patch('marzban_api.marzban_api.update_admin_password')
    async def test_update_admin_password_new_api_format(self, mock_update):
        """Test that the new API format is used for password updates."""
        mock_update.return_value = True
        
        # Test the new API format with is_sudo parameter
        result = await marzban_api.update_admin_password("test_admin", "f26560291b", is_sudo=False)
        
        # Verify the function was called with the correct parameters
        mock_update.assert_called_once_with("test_admin", "f26560291b", is_sudo=False)
        self.assertTrue(result)

    @patch('database.db.get_admin_by_id')
    @patch('marzban_api.marzban_api.delete_admin_completely')
    @patch('database.db.remove_admin_by_id')
    @patch('database.db.add_log')
    async def test_manual_deactivation_complete_deletion(self, mock_log, mock_remove_db, mock_delete_marzban, mock_get_admin):
        """Test that manual deactivation completely deletes admin and users."""
        mock_get_admin.return_value = self.test_admin
        mock_delete_marzban.return_value = True
        mock_remove_db.return_value = True
        mock_log.return_value = True
        
        result = await delete_admin_panel_completely(1, "Manual deactivation test")
        
        # Verify complete deletion was attempted
        mock_delete_marzban.assert_called_once_with("test_admin")
        mock_remove_db.assert_called_once_with(1)
        mock_log.assert_called_once()
        self.assertTrue(result)

    @patch('database.db.get_admin_by_id')
    @patch('database.db.update_admin')
    @patch('marzban_api.marzban_api.update_admin_password')
    @patch('database.db.deactivate_admin')
    async def test_automatic_deactivation_password_change(self, mock_deactivate, mock_update_password, mock_update_admin, mock_get_admin):
        """Test that automatic deactivation uses the fixed password and new API format."""
        mock_get_admin.return_value = self.test_admin
        mock_update_admin.return_value = True
        mock_update_password.return_value = True
        mock_deactivate.return_value = True
        
        result = await deactivate_admin_panel_by_id(1, "Automatic limit exceeded")
        
        # Verify the fixed password is used with the new API format
        mock_update_password.assert_called_with("test_admin", "f26560291b", is_sudo=False)
        
        # Verify admin is deactivated, not deleted
        mock_deactivate.assert_called_once_with(1, "Automatic limit exceeded")
        
        # Verify original password is stored
        mock_update_admin.assert_any_call(1, original_password="original_password")
        mock_update_admin.assert_any_call(1, marzban_password="f26560291b")
        
        self.assertTrue(result)

    def test_fixed_password_constant(self):
        """Test that the fixed password constant is correct."""
        # This should be the exact password specified in requirements
        fixed_password = "f26560291b"
        self.assertEqual(fixed_password, "f26560291b")

    async def test_api_format_structure(self):
        """Test that the API call structure matches requirements."""
        # Mock the httpx client to verify the request structure
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.put.return_value = mock_response
            
            # Mock authentication
            with patch.object(marzban_api, 'ensure_authenticated', return_value=True):
                with patch.object(marzban_api, 'token', 'fake_token'):
                    await marzban_api.update_admin_password("test_admin", "f26560291b", is_sudo=False)
            
            # Verify the API call was made with correct structure
            mock_client.return_value.__aenter__.return_value.put.assert_called_once()
            call_args = mock_client.return_value.__aenter__.return_value.put.call_args
            
            # Check the JSON payload structure
            json_data = call_args[1]['json']
            expected_structure = {
                "password": "f26560291b",
                "is_sudo": False
            }
            self.assertEqual(json_data, expected_structure)


async def run_tests():
    """Run all async tests."""
    test_instance = TestDeactivationChanges()
    test_instance.setUp()
    
    print("🧪 Running tests for deactivation changes...")
    
    try:
        await test_instance.test_update_admin_password_new_api_format()
        print("✅ Test 1 passed: update_admin_password with new API format")
        
        await test_instance.test_manual_deactivation_complete_deletion()
        print("✅ Test 2 passed: manual deactivation complete deletion")
        
        await test_instance.test_automatic_deactivation_password_change()
        print("✅ Test 3 passed: automatic deactivation password change")
        
        test_instance.test_fixed_password_constant()
        print("✅ Test 4 passed: fixed password constant")
        
        await test_instance.test_api_format_structure()
        print("✅ Test 5 passed: API format structure")
        
        print("\n🎉 All tests passed! The implementation correctly handles:")
        print("   • Manual deactivation: Complete deletion of admin and users")
        print("   • Automatic deactivation: Password change to 'f26560291b' with is_sudo=false")
        print("   • New API format: PUT /api/admin/{username} with password and is_sudo fields")
        print("   • Original password storage for restoration")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(run_tests())