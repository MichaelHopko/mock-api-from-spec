#!/usr/bin/env python3
"""
Test script for the Slack Events API Mock Server
"""

import sys
import time
import requests
import json
from threading import Thread

def test_server():
    """Test the server functionality"""
    base_url = "http://127.0.0.1:5000"
    headers = {"Authorization": "Bearer test-token-12345"}
    
    print("🧪 Testing Slack Events API Mock Server")
    print("=" * 50)
    
    # Wait for server to start
    print("⏳ Waiting for server to start...")
    for i in range(10):
        try:
            response = requests.get(f"{base_url}/health", timeout=2)
            if response.status_code == 200:
                print("✅ Server is running!")
                break
        except:
            time.sleep(1)
    else:
        print("❌ Server did not start in time")
        return False
    
    success_count = 0
    total_tests = 0
    
    def test_endpoint(name, method, url, data=None, expected_status=200):
        nonlocal success_count, total_tests
        total_tests += 1
        
        try:
            if method == "GET":
                response = requests.get(url, headers=headers, timeout=5)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=data, timeout=5)
            
            if response.status_code == expected_status:
                print(f"✅ {name}")
                success_count += 1
                return True
            else:
                print(f"❌ {name} - Status: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ {name} - Error: {e}")
            return False
    
    # Test endpoints
    print("\n📡 Testing API endpoints:")
    
    test_endpoint("Health Check", "GET", f"{base_url}/health")
    test_endpoint("API Test", "GET", f"{base_url}/api/test")
    test_endpoint("Auth Test", "GET", f"{base_url}/api/auth.test")
    test_endpoint("Team Info", "GET", f"{base_url}/api/team.info")
    test_endpoint("Users List", "GET", f"{base_url}/api/users.list")
    test_endpoint("Conversations List", "GET", f"{base_url}/api/conversations.list")
    
    # Test posting a message
    test_endpoint("Post Message", "POST", f"{base_url}/api/chat.postMessage", {
        "channel": "C12345678",
        "text": "Hello from test script!",
        "user": "U12345678"
    })
    
    # Test adding a reaction
    test_endpoint("Add Reaction", "POST", f"{base_url}/api/reactions.add", {
        "name": "thumbsup",
        "channel": "C12345678", 
        "timestamp": "1234567890.123456"
    }, expected_status=404)  # Message won't exist, expect 404
    
    # Test URL verification
    test_endpoint("URL Verification", "POST", f"{base_url}/api/events", {
        "type": "url_verification",
        "challenge": "test_challenge_123"
    })
    
    print(f"\n📊 Test Results: {success_count}/{total_tests} tests passed")
    
    if success_count == total_tests:
        print("🎉 All tests passed! Server is working correctly.")
        assert True
    else:
        print("⚠️  Some tests failed. Check the server logs.")
        assert False, f"Only {success_count}/{total_tests} tests passed"

if __name__ == "__main__":
    # Import and start server in background
    try:
        import sys
        sys.path.append('.')
        
        # Import server modules
        from server.app import app, initialize_app
        
        # Initialize app
        initialize_app()
        
        # Start server in background thread
        def run_server():
            app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
        
        server_thread = Thread(target=run_server, daemon=True)
        server_thread.start()
        
        # Give server time to start
        time.sleep(2)
        
        # Run tests
        success = test_server()
        
        if success:
            print("\n🚀 Server is ready to use!")
            print("   Run: python server/run.py")
            print("   URL: http://127.0.0.1:5000")
        
        sys.exit(0 if success else 1)
        
    except Exception as e:
        print(f"❌ Error testing server: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)