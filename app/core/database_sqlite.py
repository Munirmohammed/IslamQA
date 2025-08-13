"""
SQLite-compatible Database Configuration
Modified models for local development with SQLite
"""

from sqlalchemy import create_engine, MetaData, Column, Integer, String, Text, DateTime, Float, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.dialects.sqlite import JSON
from datetime import datetime
import uuid
from typing import Generator

# Database engine for SQLite
engine = create_engine(
    "sqlite:///./islamqa_local.db",
    pool_pre_ping=True,
    echo=False
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


# SQLite-compatible Database Models
class Question(Base):
    """Questions table - SQLite compatible"""
    __tablename__ = "questions"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    question_text = Column(Text, nullable=False, index=True)
    question_hash = Column(String(64), unique=True, index=True)
    language = Column(String(10), default="en")
    category = Column(String(100), index=True)
    tags = Column(JSON)  # Use JSON instead of JSONB for SQLite
    embedding = Column(JSON)  # Store vector embeddings as JSON
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    answers = relationship("Answer", back_populates="question")
    user_interactions = relationship("UserInteraction", back_populates="question")


class Answer(Base):
    """Answers table - SQLite compatible"""
    __tablename__ = "answers"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    question_id = Column(String(36), ForeignKey("questions.id"), nullable=False)
    answer_text = Column(Text, nullable=False)
    source_url = Column(String(500))
    source_name = Column(String(200))
    scholar_name = Column(String(200))
    confidence_score = Column(Float, default=0.0)
    is_verified = Column(Boolean, default=False)
    language = Column(String(10), default="en")
    references = Column(JSON)  # Quran/Hadith references as JSON
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    question = relationship("Question", back_populates="answers")


class Source(Base):
    """Sources table for tracking scraped websites"""
    __tablename__ = "sources"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), nullable=False)
    base_url = Column(String(500), nullable=False)
    scraping_config = Column(JSON)  # Scraping configuration as JSON
    last_scraped = Column(DateTime)
    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserInteraction(Base):
    """User interactions for analytics"""
    __tablename__ = "user_interactions"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(100), index=True)
    question_id = Column(String(36), ForeignKey("questions.id"))
    user_query = Column(Text, nullable=False)
    matched_answers = Column(JSON)  # Store as JSON
    satisfaction_rating = Column(Integer)  # 1-5 scale
    feedback = Column(Text)
    ip_address = Column(String(45))
    user_agent = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    question = relationship("Question", back_populates="user_interactions")


class ScrapingJob(Base):
    """Scraping jobs tracking"""
    __tablename__ = "scraping_jobs"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id = Column(String(36), ForeignKey("sources.id"))
    status = Column(String(50), default="pending")  # pending, running, completed, failed
    pages_scraped = Column(Integer, default=0)
    questions_extracted = Column(Integer, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    """Users table for authentication"""
    __tablename__ = "users"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(100), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(128), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    api_key = Column(String(64), unique=True, index=True)
    rate_limit = Column(Integer, default=100)  # Requests per hour
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)


# Database dependency
def get_db() -> Generator[Session, None, None]:
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Create tables
def create_tables():
    """Create all tables"""
    Base.metadata.create_all(bind=engine)


# Database utilities
class DatabaseUtils:
    """Database utility functions"""
    
    @staticmethod
    def get_or_create(db: Session, model, **kwargs):
        """Get or create a database record"""
        instance = db.query(model).filter_by(**kwargs).first()
        if instance:
            return instance, False
        else:
            instance = model(**kwargs)
            db.add(instance)
            db.commit()
            return instance, True
    
    @staticmethod
    def bulk_insert(db: Session, model, data_list):
        """Bulk insert records"""
        try:
            db.bulk_insert_mappings(model, data_list)
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            raise e
    
    @staticmethod
    def update_or_create(db: Session, model, defaults=None, **kwargs):
        """Update or create a record"""
        defaults = defaults or {}
        instance = db.query(model).filter_by(**kwargs).first()
        if instance:
            for key, value in defaults.items():
                setattr(instance, key, value)
            db.commit()
            return instance, False
        else:
            params = dict((k, v) for k, v in kwargs.items())
            params.update(defaults)
            instance = model(**params)
            db.add(instance)
            db.commit()
            return instance, True


# Mock Redis for local development
class MockCache:
    """Mock cache for local development without Redis"""
    
    def __init__(self):
        self._cache = {}
    
    def get(self, key: str):
        return self._cache.get(key)
    
    def set(self, key: str, value: str, ttl: int = None):
        self._cache[key] = value
        return True
    
    def delete(self, key: str):
        return self._cache.pop(key, None) is not None
    
    def exists(self, key: str):
        return key in self._cache


# Global mock cache instance
mock_cache = MockCache()


# Cache utilities for local development
class CacheUtils:
    """Mock cache utilities for local development"""
    
    @staticmethod
    def get(key: str):
        """Get value from mock cache"""
        return mock_cache.get(key)
    
    @staticmethod
    def set(key: str, value: str, ttl: int = None):
        """Set value in mock cache"""
        return mock_cache.set(key, value, ttl)
    
    @staticmethod
    def delete(key: str):
        """Delete key from mock cache"""
        return mock_cache.delete(key)
    
    @staticmethod
    def exists(key: str):
        """Check if key exists in mock cache"""
        return mock_cache.exists(key)
