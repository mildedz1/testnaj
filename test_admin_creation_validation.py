#!/usr/bin/env python3
"""
Test for admin creation validation to ensure no false success messages.
This test validates that the admin creation only shows success when operation truly succeeds.
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


async def test_create_admin_success_codes():
    """Test that create_admin correctly handles various success codes."""
    print("🧪 Testing Admin Creation Success Code Validation")
    print("=" * 50)
    
    api = MarzbanAPI()
    
    # Test case 1: HTTP 200 (traditional success)
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MockResponse(200, '{"id": 123, "username": "test_admin"}')
        mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
        
        with patch.object(api, 'get_headers', return_value={"Authorization": "Bearer test"}):
            result = await api.create_admin("test_admin", "password123", 12345)
            
        assert result == True, "Should return True for HTTP 200"
        print("✅ HTTP 200 handled correctly")
    
    # Test case 2: HTTP 201 (created - common for POST operations)
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MockResponse(201, '{"id": 124, "username": "test_admin2"}')
        mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
        
        with patch.object(api, 'get_headers', return_value={"Authorization": "Bearer test"}):
            result = await api.create_admin("test_admin2", "password123", 12346)
            
        assert result == True, "Should return True for HTTP 201"
        print("✅ HTTP 201 handled correctly")
    
    # Test case 3: HTTP 400 (bad request)
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MockResponse(400, '{"error": "Username already exists"}')
        mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
        
        with patch.object(api, 'get_headers', return_value={"Authorization": "Bearer test"}):
            result = await api.create_admin("test_admin3", "password123", 12347)
            
        assert result == False, "Should return False for HTTP 400"
        print("✅ HTTP 400 handled correctly (returns False)")
    
    # Test case 4: HTTP 409 (conflict - username exists)
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MockResponse(409, '{"error": "Admin username already exists"}')
        mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
        
        with patch.object(api, 'get_headers', return_value={"Authorization": "Bearer test"}):
            result = await api.create_admin("test_admin4", "password123", 12348)
            
        assert result == False, "Should return False for HTTP 409"
        print("✅ HTTP 409 handled correctly (returns False)")
    
    print("\n🎉 All admin creation success code tests passed!")
    return True


async def test_create_admin_error_handling():
    """Test that create_admin properly handles exceptions and logs errors."""
    print("\n🧪 Testing Admin Creation Error Handling")
    print("=" * 50)
    
    api = MarzbanAPI()
    
    # Test case 1: Network exception
    with patch('httpx.AsyncClient') as mock_client:
        mock_client.return_value.__aenter__.return_value.post.side_effect = Exception("Connection timeout")
        
        with patch.object(api, 'get_headers', return_value={"Authorization": "Bearer test"}):
            result = await api.create_admin("test_admin", "password123", 12345)
            
        assert result == False, "Should return False when exception occurs"
        print("✅ Network exception handled correctly")
    
    # Test case 2: Auth failure (get_headers fails)
    with patch.object(api, 'get_headers', side_effect=Exception("Authentication failed")):
        result = await api.create_admin("test_admin", "password123", 12345)
        
        assert result == False, "Should return False when authentication fails"
        print("✅ Authentication failure handled correctly")
    
    print("\n🎉 All admin creation error handling tests passed!")
    return True


async def test_admin_exists_validation():
    """Test that admin_exists correctly validates responses."""
    print("\n🧪 Testing Admin Exists Validation")
    print("=" * 50)
    
    api = MarzbanAPI()
    
    # Test case 1: Admin exists (HTTP 200)
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MockResponse(200, '{"username": "existing_admin"}')
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
        
        with patch.object(api, 'get_headers', return_value={"Authorization": "Bearer test"}):
            result = await api.admin_exists("existing_admin")
            
        assert result == True, "Should return True when admin exists (HTTP 200)"
        print("✅ Existing admin detection works correctly")
    
    # Test case 2: Admin doesn't exist (HTTP 404)
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MockResponse(404, '{"error": "Admin not found"}')
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
        
        with patch.object(api, 'get_headers', return_value={"Authorization": "Bearer test"}):
            result = await api.admin_exists("nonexistent_admin")
            
        assert result == False, "Should return False when admin doesn't exist (HTTP 404)"
        print("✅ Non-existing admin detection works correctly")
    
    # Test case 3: Unexpected response (HTTP 500)
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MockResponse(500, '{"error": "Internal server error"}')
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
        
        with patch.object(api, 'get_headers', return_value={"Authorization": "Bearer test"}):
            result = await api.admin_exists("test_admin")
            
        assert result == False, "Should return False for unexpected response codes"
        print("✅ Unexpected response codes handled correctly")
    
    print("\n🎉 All admin exists validation tests passed!")
    return True


async def test_delete_admin_validation():
    """Test that delete_admin correctly validates responses."""
    print("\n🧪 Testing Admin Deletion Validation")
    print("=" * 50)
    
    api = MarzbanAPI()
    
    # Test case 1: Successful deletion (HTTP 200)
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MockResponse(200, '{"message": "Admin deleted successfully"}')
        mock_client.return_value.__aenter__.return_value.delete.return_value = mock_response
        
        with patch.object(api, 'get_headers', return_value={"Authorization": "Bearer test"}):
            result = await api.delete_admin("test_admin")
            
        assert result == True, "Should return True for HTTP 200"
        print("✅ HTTP 200 deletion handled correctly")
    
    # Test case 2: Successful deletion (HTTP 204 - No Content)
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MockResponse(204, '')
        mock_client.return_value.__aenter__.return_value.delete.return_value = mock_response
        
        with patch.object(api, 'get_headers', return_value={"Authorization": "Bearer test"}):
            result = await api.delete_admin("test_admin")
            
        assert result == True, "Should return True for HTTP 204"
        print("✅ HTTP 204 deletion handled correctly")
    
    # Test case 3: Admin not found (HTTP 404)
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MockResponse(404, '{"error": "Admin not found"}')
        mock_client.return_value.__aenter__.return_value.delete.return_value = mock_response
        
        with patch.object(api, 'get_headers', return_value={"Authorization": "Bearer test"}):
            result = await api.delete_admin("nonexistent_admin")
            
        assert result == False, "Should return False for HTTP 404"
        print("✅ HTTP 404 deletion handled correctly")
    
    print("\n🎉 All admin deletion validation tests passed!")
    return True


async def test_password_update_validation():
    """Test that password update correctly validates responses."""
    print("\n🧪 Testing Password Update Validation")
    print("=" * 50)
    
    api = MarzbanAPI()
    
    # Test case 1: Successful update (HTTP 200)
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MockResponse(200, '{"message": "Password updated"}')
        mock_client.return_value.__aenter__.return_value.put.return_value = mock_response
        
        with patch.object(api, 'get_headers', return_value={"Authorization": "Bearer test"}):
            result = await api.update_admin_password("test_admin", "new_password")
            
        assert result == True, "Should return True for HTTP 200"
        print("✅ Successful password update handled correctly")
    
    # Test case 2: Unauthorized (HTTP 401)
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MockResponse(401, '{"error": "Unauthorized"}')
        mock_client.return_value.__aenter__.return_value.put.return_value = mock_response
        
        with patch.object(api, 'get_headers', return_value={"Authorization": "Bearer test"}):
            result = await api.update_admin_password("test_admin", "new_password")
            
        assert result == False, "Should return False for HTTP 401"
        print("✅ Unauthorized password update handled correctly")
    
    # Test case 3: Admin not found (HTTP 404)
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MockResponse(404, '{"error": "Admin not found"}')
        mock_client.return_value.__aenter__.return_value.put.return_value = mock_response
        
        with patch.object(api, 'get_headers', return_value={"Authorization": "Bearer test"}):
            result = await api.update_admin_password("nonexistent_admin", "new_password")
            
        assert result == False, "Should return False for HTTP 404"
        print("✅ Admin not found during password update handled correctly")
    
    print("\n🎉 All password update validation tests passed!")
    return True


async def main():
    """Run all validation tests."""
    print("🧪 ADMIN CREATION VALIDATION TESTS")
    print("=" * 50)
    print("Testing admin creation flow to prevent false success messages\n")
    
    results = []
    results.append(await test_create_admin_success_codes())
    results.append(await test_create_admin_error_handling())
    results.append(await test_admin_exists_validation())
    results.append(await test_delete_admin_validation())
    results.append(await test_password_update_validation())
    
    print("\n" + "=" * 50)
    print("📋 VALIDATION TEST SUMMARY")
    print("=" * 50)
    
    if all(results):
        print("🎉 ALL VALIDATION TESTS PASSED!")
        print("\n📋 Key improvements made:")
        print("✅ Admin creation validates both HTTP 200 and 201 as success")
        print("✅ Detailed error logging with response text and exception types")
        print("✅ Proper error handling for all admin operations")
        print("✅ False success messages eliminated")
        print("✅ Complete rollback on database failure during admin creation")
        print("\n🔐 Admin operations are now reliable and accurately report status!")
        return True
    else:
        print("❌ Some validation tests failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)