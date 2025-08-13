#!/usr/bin/env python3
"""
Integration Test for Islamic Q&A Frontend and Backend
Tests the complete functionality of the application
"""

import asyncio
import aiohttp
import json
import time
from typing import Dict, Any

# Configuration
BACKEND_URL = "http://localhost:8000"
FRONTEND_URL = "http://localhost:3000"

class IntegrationTester:
    def __init__(self):
        self.session = None
        self.auth_token = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def test_backend_health(self) -> bool:
        """Test backend health endpoint"""
        try:
            async with self.session.get(f"{BACKEND_URL}/health") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Backend Health: {data['status']}")
                    return True
                else:
                    print(f"❌ Backend Health Check Failed: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Backend Connection Failed: {e}")
            return False
    
    async def test_frontend_accessibility(self) -> bool:
        """Test frontend accessibility"""
        try:
            async with self.session.get(FRONTEND_URL) as response:
                if response.status == 200:
                    content = await response.text()
                    if "Islamic Q&A" in content:
                        print("✅ Frontend Accessible")
                        return True
                    else:
                        print("❌ Frontend Content Invalid")
                        return False
                else:
                    print(f"❌ Frontend Not Accessible: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Frontend Connection Failed: {e}")
            return False
    
    async def test_questions_api(self) -> bool:
        """Test questions API endpoint"""
        try:
            async with self.session.get(f"{BACKEND_URL}/api/v1/questions") as response:
                if response.status == 200:
                    questions = await response.json()
                    print(f"✅ Questions API: {len(questions)} questions loaded")
                    return True
                else:
                    print(f"❌ Questions API Failed: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Questions API Error: {e}")
            return False
    
    async def test_search_api(self) -> bool:
        """Test search API endpoint"""
        try:
            url = f"{BACKEND_URL}/api/v1/search?query=prayer&use_ml=true"
            async with self.session.get(url) as response:
                if response.status == 200:
                    results = await response.json()
                    result_count = len(results.get('results', []))
                    print(f"✅ Search API: {result_count} results for 'prayer'")
                    return True
                else:
                    print(f"❌ Search API Failed: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Search API Error: {e}")
            return False
    
    async def test_auth_endpoints(self) -> bool:
        """Test authentication endpoints"""
        try:
            # Test register endpoint (expect error for duplicate or validation)
            register_data = {
                "email": f"test_{int(time.time())}@example.com",
                "password": "testpassword123",
                "full_name": "Test User"
            }
            
            async with self.session.post(
                f"{BACKEND_URL}/api/v1/auth/register",
                json=register_data
            ) as response:
                if response.status in [200, 201, 400]:  # 400 might be validation error
                    print("✅ Auth Register Endpoint Accessible")
                    return True
                else:
                    print(f"❌ Auth Register Failed: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Auth API Error: {e}")
            return False
    
    async def test_analytics_api(self) -> bool:
        """Test analytics API endpoint"""
        try:
            async with self.session.get(f"{BACKEND_URL}/api/v1/analytics/stats") as response:
                if response.status == 200:
                    stats = await response.json()
                    print(f"✅ Analytics API: {stats}")
                    return True
                else:
                    print(f"❌ Analytics API Failed: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Analytics API Error: {e}")
            return False
    
    async def test_cors_headers(self) -> bool:
        """Test CORS headers for frontend integration"""
        try:
            headers = {
                'Origin': FRONTEND_URL,
                'Access-Control-Request-Method': 'GET',
                'Access-Control-Request-Headers': 'Content-Type'
            }
            
            async with self.session.options(
                f"{BACKEND_URL}/api/v1/questions",
                headers=headers
            ) as response:
                cors_headers = response.headers
                if 'Access-Control-Allow-Origin' in cors_headers:
                    print("✅ CORS Headers Present")
                    return True
                else:
                    print("❌ CORS Headers Missing")
                    return False
        except Exception as e:
            print(f"❌ CORS Test Error: {e}")
            return False
    
    async def run_all_tests(self):
        """Run all integration tests"""
        print("🕌 Islamic Q&A Integration Test Suite")
        print("=" * 50)
        
        tests = [
            ("Backend Health", self.test_backend_health),
            ("Frontend Accessibility", self.test_frontend_accessibility),
            ("Questions API", self.test_questions_api),
            ("Search API", self.test_search_api),
            ("Authentication API", self.test_auth_endpoints),
            ("Analytics API", self.test_analytics_api),
            ("CORS Configuration", self.test_cors_headers),
        ]
        
        results = {}
        
        for test_name, test_func in tests:
            print(f"\n🧪 Testing {test_name}...")
            try:
                result = await test_func()
                results[test_name] = result
            except Exception as e:
                print(f"❌ {test_name} Error: {e}")
                results[test_name] = False
        
        # Summary
        print("\n" + "=" * 50)
        print("📊 Test Results Summary")
        print("=" * 50)
        
        passed = sum(results.values())
        total = len(results)
        
        for test_name, result in results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{test_name:.<30} {status}")
        
        print(f"\nOverall: {passed}/{total} tests passed")
        
        if passed == total:
            print("\n🎉 All tests passed! Your Islamic Q&A application is ready!")
            print("\n🚀 Access your application:")
            print(f"   Frontend: {FRONTEND_URL}")
            print(f"   Backend API: {BACKEND_URL}/docs")
            print(f"   Health Check: {BACKEND_URL}/health")
        else:
            print(f"\n⚠️  {total - passed} test(s) failed. Please check the issues above.")
        
        return passed == total

async def main():
    """Main test runner"""
    async with IntegrationTester() as tester:
        success = await tester.run_all_tests()
        return success

if __name__ == "__main__":
    print("Starting Integration Tests...")
    print("Make sure both frontend and backend servers are running!")
    print("Backend: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000")
    print("Frontend: cd frontend && python server.py 3000")
    print()
    
    try:
        success = asyncio.run(main())
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⏹️  Tests interrupted by user")
        exit(1)
    except Exception as e:
        print(f"\n❌ Test runner error: {e}")
        exit(1)
