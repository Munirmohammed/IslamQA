"""
Application Configuration
Centralized configuration management with environment variable support
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List, Optional
import os


class Settings(BaseSettings):
    """Application settings"""
    
    # Database Configuration
    DATABASE_URL: str = Field(
        default="sqlite:///./islamqa_local.db",
        description="Database connection URL"
    )
    REDIS_URL: str = Field(
        default="redis://localhost:6379",
        description="Redis connection URL"
    )
    
    # API Configuration
    SECRET_KEY: str = Field(
        default="your-super-secret-key-here-change-this-in-production",
        description="Secret key for JWT tokens"
    )
    ALGORITHM: str = Field(default="HS256", description="JWT algorithm")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, description="Token expiration time")
    
    # Application Settings
    DEBUG: bool = Field(default=True, description="Debug mode")
    ALLOWED_HOSTS: List[str] = Field(default=["*"], description="Allowed hosts")
    ALLOWED_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        description="CORS allowed origins"
    )
    
    # External APIs
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="OpenAI API key")
    HUGGINGFACE_API_KEY: Optional[str] = Field(default=None, description="HuggingFace API key")
    GROQ_API_KEY: Optional[str] = Field(default=None, description="Groq API key")
    
    # Scraping Configuration
    USER_AGENT: str = Field(default="IslamQA-Bot/1.0", description="User agent for scraping")
    REQUEST_DELAY: float = Field(default=1.0, description="Delay between requests")
    MAX_RETRIES: int = Field(default=3, description="Maximum retries for failed requests")
    
    # Feature Flags
    ENABLE_ML_MATCHING: bool = Field(default=True, description="Enable ML-based matching")
    ENABLE_WEBSOCKETS: bool = Field(default=True, description="Enable WebSocket support")
    ENABLE_RATE_LIMITING: bool = Field(default=True, description="Enable rate limiting")
    ENABLE_ANALYTICS: bool = Field(default=True, description="Enable analytics")
    
    # Monitoring
    PROMETHEUS_PORT: int = Field(default=9090, description="Prometheus metrics port")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    
    # GitHub Automation
    GITHUB_TOKEN: Optional[str] = Field(default=None, description="GitHub API token")
    GITHUB_REPO: Optional[str] = Field(default=None, description="GitHub repository")
    COMMIT_SCHEDULE: str = Field(default="0 20 * * *", description="Cron schedule for commits")
    
    # WhatsApp Integration
    WHATSAPP_TOKEN: Optional[str] = Field(default=None, description="WhatsApp API token")
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = Field(
        default=None, 
        description="WhatsApp phone number ID"
    )
    
    # ML Models Configuration
    SENTENCE_TRANSFORMER_MODEL: str = Field(
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        description="Sentence transformer model"
    )
    ARABIC_MODEL: str = Field(
        default="aubmindlab/bert-base-arabertv02",
        description="Arabic BERT model"
    )
    
    # Knowledge Base Settings
    MIN_SIMILARITY_SCORE: float = Field(default=0.7, description="Minimum similarity score")
    MAX_RESULTS: int = Field(default=10, description="Maximum results per query")
    ENABLE_FUZZY_MATCHING: bool = Field(default=True, description="Enable fuzzy matching")
    
    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = Field(default=100, description="Requests per minute")
    RATE_LIMIT_WINDOW: int = Field(default=60, description="Rate limit window in seconds")
    
    # Cache Settings
    CACHE_TTL: int = Field(default=3600, description="Cache TTL in seconds")
    ENABLE_CACHE: bool = Field(default=True, description="Enable caching")
    
    class Config:
        env_file = "config.env"
        case_sensitive = True


# Global settings instance
settings = Settings()


# Validate critical settings
def validate_settings():
    """Validate critical application settings"""
    if settings.SECRET_KEY == "your-super-secret-key-here-change-this-in-production":
        if not settings.DEBUG:
            raise ValueError("SECRET_KEY must be changed in production")
    
    if settings.ENABLE_ML_MATCHING and not settings.HUGGINGFACE_API_KEY:
        print("Warning: ML matching enabled but no HuggingFace API key provided")
    
    return True


# Initialize validation
validate_settings()
