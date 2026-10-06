"""
SQLite-compatible Database Configuration
Modified models for local development with SQLite
"""

from sqlalchemy import create_engine, MetaData, Column, Integer, String, Text, DateTime, Date, Float, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.dialects.sqlite import JSON
from datetime import datetime, date
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


class UserStreak(Base):
    """Per-user Quran reading/recitation streak and hasanat tally (gamification)."""
    __tablename__ = "user_streaks"

    user_id = Column(String(36), ForeignKey("users.id"), primary_key=True)
    current_streak = Column(Integer, default=0)
    longest_streak = Column(Integer, default=0)
    last_activity_date = Column(Date)  # calendar-day granularity, UTC
    total_verses_read = Column(Integer, default=0)
    total_hasanat = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MemorizationCard(Base):
    """Per-user, per-ayah spaced-repetition (SM-2) state for hifz practice."""
    __tablename__ = "memorization_cards"
    __table_args__ = (
        UniqueConstraint("user_id", "surah_number", "ayah_number", name="uq_user_ayah_card"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    surah_number = Column(Integer, nullable=False)
    ayah_number = Column(Integer, nullable=False)
    ease_factor = Column(Float, default=2.5)
    interval_days = Column(Integer, default=0)
    repetitions = Column(Integer, default=0)
    due_date = Column(Date, default=date.today)
    last_reviewed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


class RecitationSession(Base):
    """A persisted recitation-check result (Phase 2's `/recitation/check`),
    needed for the halaqa/teacher dashboard to review student history."""
    __tablename__ = "recitation_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), index=True, nullable=True)  # anonymous checks stay allowed
    surah_number = Column(Integer, nullable=False)
    ayah_number = Column(Integer, nullable=False)
    transcript = Column(Text)
    mistake_count = Column(Integer, default=0)
    is_correct = Column(Boolean, default=False)
    audio_hash = Column(String(64), index=True)  # sha256 hex of the uploaded audio bytes
    is_duplicate_submission = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class MistakeLog(Base):
    """One mistake row from a RecitationSession's diff_recitation output."""
    __tablename__ = "mistake_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("recitation_sessions.id"), index=True, nullable=False)
    mistake_type = Column(String(20))  # incorrect | missed | extra
    expected = Column(Text)
    recited = Column(Text)
    position = Column(Integer)


class Halaqa(Base):
    """A teacher's study circle/class."""
    __tablename__ = "halaqas"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    teacher_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    join_code = Column(String(12), unique=True, index=True, default=lambda: uuid.uuid4().hex[:8])
    created_at = Column(DateTime, default=datetime.utcnow)


class HalaqaMembership(Base):
    """A student's membership in a halaqa."""
    __tablename__ = "halaqa_memberships"
    __table_args__ = (
        UniqueConstraint("halaqa_id", "student_id", name="uq_halaqa_student"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    halaqa_id = Column(String(36), ForeignKey("halaqas.id"), index=True, nullable=False)
    student_id = Column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)


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
    """Mock cache for local development without Redis.

    Also implements a minimal redis-py-compatible incr/expire/pipeline
    surface, since RateLimitMiddleware._check_rate_limit calls those on
    whatever `redis_client` resolves to -- without this, every call raised
    AttributeError, which was silently caught and treated as "allow the
    request", meaning rate limiting never actually worked without real Redis.
    """

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

    def incr(self, key: str) -> int:
        """Redis-compatible INCR: create at 0 if absent, then increment."""
        current = int(self._cache.get(key, 0)) + 1
        self._cache[key] = str(current)
        return current

    def expire(self, key: str, ttl: int) -> bool:
        """No-op: this mock doesn't implement TTL-based expiry. Callers here
        rate-limit via time-bucketed key names (rate_limit:<id>:<window_start>),
        so correctness doesn't depend on active expiry, only eventual cleanup."""
        return key in self._cache

    def pipeline(self) -> "MockPipeline":
        """Immediate (non-batched) execution is fine for a local mock --
        there's no concurrent-access race to protect against here."""
        return MockPipeline(self)


class MockPipeline:
    """Queues incr/expire calls, applies them to the backing MockCache on
    execute() -- enough of redis-py's pipeline interface for
    RateLimitMiddleware._check_rate_limit to work against it."""

    def __init__(self, cache: "MockCache"):
        self._cache = cache
        self._ops = []

    def incr(self, key: str) -> "MockPipeline":
        self._ops.append(("incr", key))
        return self

    def expire(self, key: str, ttl: int) -> "MockPipeline":
        self._ops.append(("expire", key, ttl))
        return self

    def execute(self) -> list:
        results = [
            self._cache.incr(op[1]) if op[0] == "incr" else self._cache.expire(op[1], op[2])
            for op in self._ops
        ]
        self._ops = []
        return results


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
