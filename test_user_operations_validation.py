#!/usr/bin/env python3
"""
Test for user operations validation to ensure no false success messages.
This test validates that user operations (enable/disable/delete) only show success when operation truly succeeds.
"""

import asyncio
import sys
import os
import logging
from unittest.mock import AsyncMock, MagicMock, patch

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from marzban_api import MarzbanAPI
import config

# Setup logging for testing
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


class MockResponse:
    """Mock HTTP response for testing."""
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self._text = text
    
    @property
    def text(self):
        return self._text


async def test_disable_user_validation():
    """Test that disable_user correctly validates responses."""
    print("🧪 Testing User Disable Validation")
    print("=" * 50)
    
    api = MarzbanAPI()
    
    # Test case 1: Successful disable (HTTP 200)
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MockResponse(200, '{"message": "User disabled"}')
        mock_client.return_value.__aenter__.return_value.put.return_value = mock_response
        
        with patch.object(api, 'get_headers', return_value={"Authorization": "Bearer test"}):
            result = await api.disable_user("test_user")
            
        assert result == True, "Should return True for HTTP 200"
        print("✅ HTTP 200 user disable handled correctly")
    
    # Test case 2: User not found (HTTP 404)
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MockResponse(404, '{"error": "User not found"}')
        mock_client.return_value.__aenter__.return_value.put.return_value = mock_response
        
        with patch.object(api, 'get_headers', return_value={"Authorization": "Bearer test"}):
            result = await api.disable_user("nonexistent_user")
            
        assert result == False, "Should return False for HTTP 404"
        print("✅ HTTP 404 user disable handled correctly")
    
    # Test case 3: Server error (HTTP 500)
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MockResponse(500, '{"error": "Internal server error"}')
        mock_client.return_value.__aenter__.return_value.put.return_value = mock_response
        
        with patch.object(api, 'get_headers', return_value={"Authorization": "Bearer test"}):
            result = await api.disable_user("test_user")
            
        assert result == False, "Should return False for HTTP 500"
        print("✅ HTTP 500 user disable handled correctly")
    
    print("\n🎉 All user disable validation tests passed!")
    return True


async def test_enable_user_validation():
    """Test that enable_user correctly validates responses."""
    print("\n🧪 Testing User Enable Validation")
    print("=" * 50)
    
    api = MarzbanAPI()
    
    # Test case 1: Successful enable (HTTP 200)
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MockResponse(200, '{"message": "User enabled"}')
        mock_client.return_value.__aenter__.return_value.put.return_value = mock_response
        
        with patch.object(api, 'get_headers', return_value={"Authorization": "Bearer test"}):
            result = await api.enable_user("test_user")
            
        assert result == True, "Should return True for HTTP 200"
        print("✅ HTTP 200 user enable handled correctly")
    
    # Test case 2: Unauthorized (HTTP 401)
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MockResponse(401, '{"error": "Unauthorized"}')
        mock_client.return_value.__aenter__.return_value.put.return_value = mock_response
        
        with patch.object(api, 'get_headers', return_value={"Authorization": "Bearer test"}):
            result = await api.enable_user("test_user")
            
        assert result == False, "Should return False for HTTP 401"
        print("✅ HTTP 401 user enable handled correctly")
    
    # Test case 3: User validation error (HTTP 422)
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MockResponse(422, '{"error": "Validation error"}')
        mock_client.return_value.__aenter__.return_value.put.return_value = mock_response
        
        with patch.object(api, 'get_headers', return_value={"Authorization": "Bearer test"}):
            result = await api.enable_user("invalid_user")
            
        assert result == False, "Should return False for HTTP 422"
        print("✅ HTTP 422 user enable handled correctly")
    
    print("\n🎉 All user enable validation tests passed!")
    return True


async def test_remove_user_validation():
    """Test that remove_user correctly validates responses."""
    print("\n🧪 Testing User Remove Validation")
    print("=" * 50)
    
    api = MarzbanAPI()
    
    # Test case 1: Successful removal (HTTP 200)
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MockResponse(200, '{"message": "User deleted"}')
        mock_client.return_value.__aenter__.return_value.delete.return_value = mock_response
        
        with patch.object(api, 'get_headers', return_value={"Authorization": "Bearer test"}):
            result = await api.remove_user("test_user")
            
        assert result == True, "Should return True for HTTP 200"
        print("✅ HTTP 200 user remove handled correctly")
    
    # Test case 2: Successful removal (HTTP 204 - No Content)
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MockResponse(204, '')
        mock_client.return_value.__aenter__.return_value.delete.return_value = mock_response
        
        with patch.object(api, 'get_headers', return_value={"Authorization": "Bearer test"}):
            result = await api.remove_user("test_user")
            
        assert result == True, "Should return True for HTTP 204"
        print("✅ HTTP 204 user remove handled correctly")
    
    # Test case 3: User not found (HTTP 404)
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MockResponse(404, '{"error": "User not found"}')
        mock_client.return_value.__aenter__.return_value.delete.return_value = mock_response
        
        with patch.object(api, 'get_headers', return_value={"Authorization": "Bearer test"}):
            result = await api.remove_user("nonexistent_user")
            
        assert result == False, "Should return False for HTTP 404"
        print("✅ HTTP 404 user remove handled correctly")
    
    # Test case 4: Permission denied (HTTP 403)
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MockResponse(403, '{"error": "Permission denied"}')
        mock_client.return_value.__aenter__.return_value.delete.return_value = mock_response
        
        with patch.object(api, 'get_headers', return_value={"Authorization": "Bearer test"}):
            result = await api.remove_user("protected_user")
            
        assert result == False, "Should return False for HTTP 403"
        print("✅ HTTP 403 user remove handled correctly")
    
    print("\n🎉 All user remove validation tests passed!")
    return True


async def test_modify_user_validation():
    """Test that modify_user correctly validates responses."""
    print("\n🧪 Testing User Modify Validation")
    print("=" * 50)
    
    api = MarzbanAPI()
    
    # Test case 1: Successful modification (HTTP 200)
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MockResponse(200, '{"message": "User modified"}')
        mock_client.return_value.__aenter__.return_value.put.return_value = mock_response
        
        with patch.object(api, 'get_headers', return_value={"Authorization": "Bearer test"}):
            result = await api.modify_user("test_user", {"status": "active"})
            
        assert result == True, "Should return True for HTTP 200"
        print("✅ HTTP 200 user modify handled correctly")
    
    # Test case 2: Invalid data (HTTP 400)
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MockResponse(400, '{"error": "Invalid request data"}')
        mock_client.return_value.__aenter__.return_value.put.return_value = mock_response
        
        with patch.object(api, 'get_headers', return_value={"Authorization": "Bearer test"}):
            result = await api.modify_user("test_user", {"invalid_field": "value"})
            
        assert result == False, "Should return False for HTTP 400"
        print("✅ HTTP 400 user modify handled correctly")
    
    # Test case 3: Network exception
    with patch('httpx.AsyncClient') as mock_client:
        mock_client.return_value.__aenter__.return_value.put.side_effect = Exception("Connection refused")
        
        with patch.object(api, 'get_headers', return_value={"Authorization": "Bearer test"}):
            result = await api.modify_user("test_user", {"status": "active"})
            
        assert result == False, "Should return False when exception occurs"
        print("✅ Network exception during user modify handled correctly")
    
    print("\n🎉 All user modify validation tests passed!")
    return True


async def test_batch_operations_validation():
    """Test that batch operations properly handle individual failures."""
    print("\n🧪 Testing Batch Operations Validation")
    print("=" * 50)
    
    api = MarzbanAPI()
    
    # Test enable_users_batch with mixed results
    with patch.object(api, 'enable_user') as mock_enable:
        # Mock some users succeeding and some failing
        mock_enable.side_effect = [True, False, True, False]
        
        usernames = ["user1", "user2", "user3", "user4"]
        results = await api.enable_users_batch(usernames)
        
        expected_results = {
            "user1": True,
            "user2": False, 
            "user3": True,
            "user4": False
        }
        
        assert results == expected_results, f"Batch results should match. Got: {results}"
        print("✅ enable_users_batch correctly reports individual results")
    
    # Test disable_users_batch with mixed results
    with patch.object(api, 'disable_user') as mock_disable:
        # Mock some users succeeding and some failing
        mock_disable.side_effect = [True, True, False, True]
        
        usernames = ["user1", "user2", "user3", "user4"]
        results = await api.disable_users_batch(usernames)
        
        expected_results = {
            "user1": True,
            "user2": True,
            "user3": False,
            "user4": True
        }
        
        assert results == expected_results, f"Batch results should match. Got: {results}"
        print("✅ disable_users_batch correctly reports individual results")
    
    print("\n🎉 All batch operations validation tests passed!")
    return True


async def main():
    """Run all user operations validation tests."""
    print("🧪 USER OPERATIONS VALIDATION TESTS")
    print("=" * 50)
    print("Testing user operations to prevent false success messages\n")
    
    results = []
    results.append(await test_disable_user_validation())
    results.append(await test_enable_user_validation())
    results.append(await test_remove_user_validation())
    results.append(await test_modify_user_validation())
    results.append(await test_batch_operations_validation())
    
    print("\n" + "=" * 50)
    print("📋 USER OPERATIONS TEST SUMMARY")
    print("=" * 50)
    
    if all(results):
        print("🎉 ALL USER OPERATIONS VALIDATION TESTS PASSED!")
        print("\n📋 Key improvements made:")
        print("✅ User disable operations validate responses properly")
        print("✅ User enable operations validate responses properly")
        print("✅ User remove operations validate both HTTP 200 and 204 as success")
        print("✅ User modify operations validate responses properly")
        print("✅ Batch operations report individual success/failure correctly")
        print("✅ Detailed error logging with response text and exception types")
        print("✅ False success messages eliminated for all user operations")
        print("\n🔐 User operations are now reliable and accurately report status!")
        return True
    else:
        print("❌ Some user operations validation tests failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)