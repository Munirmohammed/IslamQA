"""
Database Configuration and Models
SQLAlchemy setup with SQLite for local development
"""

# Import everything from SQLite-compatible models
from app.core.database_sqlite import (
    Base, engine, SessionLocal, get_db,
    Question, Answer, Source, UserInteraction, 
    ScrapingJob, User, DatabaseUtils, CacheUtils,
    create_tables, mock_cache
)
from app.core.config import settings

# Try to create Redis client, fall back to mock if Redis not available
try:
    import redis
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    # Test connection
    redis_client.ping()
except:
    # Use mock cache if Redis is not available
    from app.core.database_sqlite import mock_cache as redis_client