"""
API Tests
Test cases for Islamic Q&A API endpoints
"""

import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """Test health check endpoint"""
    
    def test_health_check(self, client: TestClient):
        """Test health endpoint returns 200"""
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert "service" in data
        assert "version" in data


class TestAuthEndpoints:
    """Test authentication endpoints"""
    
    def test_register_user(self, client: TestClient, sample_user_data):
        """Test user registration"""
        response = client.post("/api/v1/auth/register", json=sample_user_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["username"] == sample_user_data["username"]
        assert data["email"] == sample_user_data["email"]
        assert data["is_active"] is True
        assert "api_key" in data
    
    def test_register_duplicate_user(self, client: TestClient, sample_user_data):
        """Test registration with duplicate username fails"""
        # Register first user
        client.post("/api/v1/auth/register", json=sample_user_data)
        
        # Try to register again
        response = client.post("/api/v1/auth/register", json=sample_user_data)
        assert response.status_code == 400
    
    def test_login_user(self, client: TestClient, sample_user_data):
        """Test user login"""
        # Register user first
        client.post("/api/v1/auth/register", json=sample_user_data)
        
        # Login
        login_data = {
            "username": sample_user_data["username"],
            "password": sample_user_data["password"]
        }
        response = client.post("/api/v1/auth/login", data=login_data)
        assert response.status_code == 200
        
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
    
    def test_login_invalid_credentials(self, client: TestClient):
        """Test login with invalid credentials"""
        login_data = {
            "username": "nonexistent",
            "password": "wrongpassword"
        }
        response = client.post("/api/v1/auth/login", data=login_data)
        assert response.status_code == 401
    
    def test_get_current_user(self, client: TestClient, auth_headers):
        """Test getting current user info"""
        response = client.get("/api/v1/auth/me", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "username" in data
        assert "email" in data
        assert "is_active" in data


class TestSearchEndpoints:
    """Test search endpoints"""
    
    def test_search_questions(self, client: TestClient):
        """Test question search"""
        search_data = {
            "query": "prayer",
            "language": "en",
            "limit": 10
        }
        response = client.post("/api/v1/search/", json=search_data)
        assert response.status_code == 200
        
        data = response.json()
        assert "query" in data
        assert "results" in data
        assert "total_results" in data
    
    def test_search_with_filters(self, client: TestClient):
        """Test search with category filter"""
        search_data = {
            "query": "fasting",
            "category": "worship",
            "language": "en",
            "limit": 5
        }
        response = client.post("/api/v1/search/", json=search_data)
        assert response.status_code == 200
    
    def test_get_suggestions(self, client: TestClient):
        """Test question suggestions"""
        response = client.get("/api/v1/search/suggestions?q=pray&limit=5")
        assert response.status_code == 200
        
        data = response.json()
        assert "suggestions" in data
        assert isinstance(data["suggestions"], list)
    
    def test_get_categories(self, client: TestClient):
        """Test getting categories"""
        response = client.get("/api/v1/search/categories")
        assert response.status_code == 200
        
        data = response.json()
        assert "categories" in data
        assert "total" in data
    
    def test_search_invalid_query(self, client: TestClient):
        """Test search with too short query"""
        search_data = {
            "query": "a",  # Too short
            "language": "en"
        }
        response = client.post("/api/v1/search/", json=search_data)
        assert response.status_code == 422  # Validation error


class TestQuestionEndpoints:
    """Test question CRUD endpoints"""
    
    def test_create_question(self, client: TestClient, auth_headers, sample_question_data):
        """Test creating a new question"""
        response = client.post(
            "/api/v1/questions/", 
            json=sample_question_data,
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["question"] == sample_question_data["question_text"]
        assert data["category"] == sample_question_data["category"]
        assert "question_id" in data
    
    def test_create_question_unauthorized(self, client: TestClient, sample_question_data):
        """Test creating question without authentication"""
        response = client.post("/api/v1/questions/", json=sample_question_data)
        assert response.status_code == 401
    
    def test_list_questions(self, client: TestClient):
        """Test listing questions"""
        response = client.get("/api/v1/questions/")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
    
    def test_list_questions_with_filters(self, client: TestClient):
        """Test listing questions with filters"""
        response = client.get("/api/v1/questions/?category=prayer&limit=5")
        assert response.status_code == 200


class TestRateLimiting:
    """Test rate limiting functionality"""
    
    @pytest.mark.slow
    def test_rate_limit_anonymous(self, client: TestClient):
        """Test rate limiting for anonymous users"""
        # Make multiple requests quickly
        responses = []
        for i in range(25):  # Exceed anonymous limit
            response = client.get("/api/v1/search/categories")
            responses.append(response.status_code)
        
        # Should get some 429 responses
        assert 429 in responses
    
    def test_rate_limit_info(self, client: TestClient, auth_headers):
        """Test getting rate limit information"""
        response = client.get("/api/v1/auth/rate-limit-info", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "limit" in data
        assert "remaining" in data


class TestErrorHandling:
    """Test error handling"""
    
    def test_404_endpoint(self, client: TestClient):
        """Test non-existent endpoint returns 404"""
        response = client.get("/api/v1/nonexistent")
        assert response.status_code == 404
    
    def test_method_not_allowed(self, client: TestClient):
        """Test wrong HTTP method returns 405"""
        response = client.put("/health")
        assert response.status_code == 405
    
    def test_invalid_json(self, client: TestClient):
        """Test invalid JSON returns 422"""
        response = client.post(
            "/api/v1/search/",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422


class TestCORS:
    """Test CORS headers"""
    
    def test_cors_headers(self, client: TestClient):
        """Test CORS headers are present"""
        response = client.options("/api/v1/search/categories")
        assert response.status_code == 200
        
        # Check for CORS headers
        assert "access-control-allow-origin" in response.headers
        assert "access-control-allow-methods" in response.headers


class TestContentNegotiation:
    """Test content type handling"""
    
    def test_json_content_type(self, client: TestClient):
        """Test JSON content type is handled correctly"""
        response = client.get("/api/v1/search/categories")
        assert "application/json" in response.headers["content-type"]
    
    def test_accept_header(self, client: TestClient):
        """Test Accept header handling"""
        headers = {"Accept": "application/json"}
        response = client.get("/api/v1/search/categories", headers=headers)
        assert response.status_code == 200
