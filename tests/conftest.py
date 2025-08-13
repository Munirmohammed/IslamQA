"""
Test Configuration and Fixtures
Shared test configuration for Islamic Q&A backend tests
"""

import pytest
import asyncio
from typing import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import tempfile
import os

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings


# Test database setup
@pytest.fixture(scope="session")
def test_engine():
    """Create test database engine"""
    # Use in-memory SQLite for tests
    engine = create_engine(
        "sqlite:///./test.db",
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    
    # Cleanup
    try:
        os.remove("./test.db")
    except FileNotFoundError:
        pass


@pytest.fixture(scope="function")
def db_session(test_engine):
    """Create test database session"""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()
    
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="function")
def client(db_session):
    """Create test client with test database"""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()


@pytest.fixture
def sample_question_data():
    """Sample question data for testing"""
    return {
        "question_text": "What is the ruling on praying in congregation?",
        "category": "prayer",
        "language": "en",
        "tags": ["prayer", "congregation", "salah"]
    }


@pytest.fixture
def sample_answer_data():
    """Sample answer data for testing"""
    return {
        "answer_text": "Praying in congregation is highly recommended in Islam...",
        "source_name": "Test Source",
        "source_url": "https://example.com/test",
        "scholar_name": "Test Scholar",
        "confidence_score": 0.9,
        "is_verified": True,
        "references": {"quran": ["2:43"], "hadith": ["Bukhari 646"]}
    }


@pytest.fixture
def sample_user_data():
    """Sample user data for testing"""
    return {
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpassword123"
    }


@pytest.fixture
def admin_user_data():
    """Sample admin user data for testing"""
    return {
        "username": "admin",
        "email": "admin@example.com",
        "password": "adminpassword123"
    }


@pytest.fixture
def auth_headers(client, sample_user_data):
    """Get authentication headers for testing"""
    # Register user
    client.post("/api/v1/auth/register", json=sample_user_data)
    
    # Login to get token
    login_data = {
        "username": sample_user_data["username"],
        "password": sample_user_data["password"]
    }
    response = client.post("/api/v1/auth/login", data=login_data)
    token = response.json()["access_token"]
    
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(client, admin_user_data):
    """Get admin authentication headers for testing"""
    # Create admin user directly in database
    from app.core.database import User
    from app.core.security import SecurityUtils
    
    admin_user = User(
        username=admin_user_data["username"],
        email=admin_user_data["email"],
        hashed_password=SecurityUtils.get_password_hash(admin_user_data["password"]),
        is_admin=True,
        api_key=SecurityUtils.generate_api_key()
    )
    
    # Add to session (this would be handled by the db_session fixture)
    # For testing, we'll use the API key approach
    return {"Authorization": f"Bearer {admin_user.api_key}"}


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_ml_service():
    """Mock ML service for testing"""
    class MockMLService:
        async def initialize_models(self):
            pass
        
        async def process_question(self, question, language="en", context=None):
            return {
                "query": question,
                "language": language,
                "results": [{
                    "question_id": "test-id",
                    "question": "Test question",
                    "answer": "Test answer",
                    "similarity_score": 0.8,
                    "source_name": "Test Source",
                    "confidence_score": 0.9
                }],
                "total_found": 1
            }
        
        async def get_question_suggestions(self, query, language="en"):
            return ["Test suggestion 1", "Test suggestion 2"]
    
    return MockMLService()


@pytest.fixture
def mock_knowledge_service():
    """Mock knowledge service for testing"""
    class MockKnowledgeService:
        async def initialize(self):
            pass
        
        async def search_knowledge_base(self, query, language="en", filters=None, use_ml=True, limit=10):
            return {
                "query": query,
                "language": language,
                "total_results": 1,
                "results": [{
                    "question_id": "test-id",
                    "question": "Test question",
                    "answer": "Test answer",
                    "similarity_score": 0.8,
                    "source_name": "Test Source"
                }]
            }
        
        async def get_question_by_id(self, question_id):
            return {
                "question_id": question_id,
                "question": "Test question",
                "answers": [{"answer_text": "Test answer"}]
            }
    
    return MockKnowledgeService()


@pytest.fixture
def temp_file():
    """Create temporary file for testing"""
    temp_fd, temp_path = tempfile.mkstemp()
    yield temp_path
    os.close(temp_fd)
    os.unlink(temp_path)


@pytest.fixture
def mock_scraper():
    """Mock scraper for testing"""
    class MockScraper:
        def __init__(self, source_name, base_url):
            self.source_name = source_name
            self.base_url = base_url
        
        async def get_question_urls(self):
            return ["http://example.com/question1", "http://example.com/question2"]
        
        async def scrape_question_answer(self, url):
            from app.scrapers.base_scraper import QuestionAnswer
            return QuestionAnswer(
                question="Test question from scraper",
                answer="Test answer from scraper",
                source_url=url,
                source_name=self.source_name,
                scholar_name="Test Scholar"
            )
        
        async def scrape_all(self, max_pages=None):
            urls = await self.get_question_urls()
            results = []
            for url in urls:
                result = await self.scrape_question_answer(url)
                if result:
                    results.append(result)
            return results
    
    return MockScraper


# Async test helpers
@pytest.fixture
def anyio_backend():
    return "asyncio"


# Markers for different test types
pytest.mark.unit = pytest.mark.unit
pytest.mark.integration = pytest.mark.integration
pytest.mark.e2e = pytest.mark.e2e
pytest.mark.slow = pytest.mark.slow
pytest.mark.scraping = pytest.mark.scraping
pytest.mark.ml = pytest.mark.ml
pytest.mark.api = pytest.mark.api
pytest.mark.websocket = pytest.mark.websocket
