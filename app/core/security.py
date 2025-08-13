"""
Security and Authentication
JWT token management, password hashing, and user authentication
"""

from datetime import datetime, timedelta
from typing import Optional, Union
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import secrets
import hashlib

from app.core.config import settings
from app.core.database import get_db, User, CacheUtils

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT token scheme
security = HTTPBearer()


class SecurityUtils:
    """Security utility functions"""
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        return pwd_context.verify(plain_password, hashed_password)
    
    @staticmethod
    def get_password_hash(password: str) -> str:
        """Generate password hash"""
        return pwd_context.hash(password)
    
    @staticmethod
    def generate_api_key() -> str:
        """Generate a secure API key"""
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def hash_string(text: str) -> str:
        """Generate SHA-256 hash of a string"""
        return hashlib.sha256(text.encode()).hexdigest()


class TokenManager:
    """JWT token management"""
    
    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT access token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return encoded_jwt
    
    @staticmethod
    def verify_token(token: str) -> Optional[dict]:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            return payload
        except JWTError:
            return None
    
    @staticmethod
    def create_refresh_token(user_id: str) -> str:
        """Create refresh token"""
        data = {"sub": user_id, "type": "refresh"}
        expire = datetime.utcnow() + timedelta(days=7)
        data.update({"exp": expire})
        return jwt.encode(data, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


class AuthService:
    """Authentication service"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Authenticate user with username and password"""
        # Try to find user by username OR email
        user = self.db.query(User).filter(
            (User.username == username) | (User.email == username)
        ).first()
        
        if not user:
            return None
            
        if not SecurityUtils.verify_password(password, user.hashed_password):
            return None
            
        return user
    
    def create_user(self, username: str, email: str, password: str, is_admin: bool = False) -> User:
        """Create a new user"""
        # Check if user already exists
        existing_user = self.db.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first()
        if existing_user:
            raise ValueError("User already exists")
        
        # Create new user
        hashed_password = SecurityUtils.get_password_hash(password)
        api_key = SecurityUtils.generate_api_key()
        
        user = User(
            username=username,
            email=email,
            hashed_password=hashed_password,
            api_key=api_key,
            is_admin=is_admin
        )
        
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
    
    def get_user_by_token(self, token: str) -> Optional[User]:
        """Get user by JWT token"""
        payload = TokenManager.verify_token(token)
        if not payload:
            return None
        
        user_id = payload.get("sub")
        if not user_id:
            return None
        
        return self.db.query(User).filter(User.id == user_id).first()
    
    def get_user_by_api_key(self, api_key: str) -> Optional[User]:
        """Get user by API key"""
        return self.db.query(User).filter(User.api_key == api_key).first()
    
    def update_last_login(self, user: User) -> None:
        """Update user's last login timestamp"""
        user.last_login = datetime.utcnow()
        self.db.commit()


# Authentication dependencies
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Get current authenticated user"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Check if it's a Bearer token
        if credentials.scheme.lower() != "bearer":
            raise credentials_exception
        
        token = credentials.credentials
        auth_service = AuthService(db)
        
        # Try to get user by JWT token
        user = auth_service.get_user_by_token(token)
        if not user:
            # Try to get user by API key
            user = auth_service.get_user_by_api_key(token)
        
        if not user:
            raise credentials_exception
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Inactive user"
            )
        
        # Update last login
        auth_service.update_last_login(user)
        
        return user
    
    except JWTError:
        raise credentials_exception


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Get current active user"""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """Get current admin user"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user


# Optional authentication (for public endpoints with optional auth)
async def get_optional_user(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Get user if authenticated, None otherwise"""
    try:
        authorization = request.headers.get("Authorization")
        if not authorization:
            return None
        
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            return None
        
        auth_service = AuthService(db)
        user = auth_service.get_user_by_token(token)
        if not user:
            user = auth_service.get_user_by_api_key(token)
        
        return user if user and user.is_active else None
    
    except Exception:
        return None


# Rate limiting decorator
class RateLimiter:
    """Rate limiting utility"""
    
    @staticmethod
    def check_rate_limit(user_id: str, limit: int = None, window: int = None) -> bool:
        """Check if user has exceeded rate limit"""
        limit = limit or settings.RATE_LIMIT_REQUESTS
        window = window or settings.RATE_LIMIT_WINDOW
        
        key = f"rate_limit:{user_id}"
        current = CacheUtils.get(key)
        
        if current is None:
            CacheUtils.set(key, "1", window)
            return True
        
        if int(current) >= limit:
            return False
        
        # Increment counter
        try:
            from app.core.database import redis_client
            redis_client.incr(key)
            return True
        except Exception:
            return True  # Allow on Redis error
    
    @staticmethod
    def get_rate_limit_info(user_id: str, limit: int = None, window: int = None) -> dict:
        """Get rate limit information"""
        limit = limit or settings.RATE_LIMIT_REQUESTS
        window = window or settings.RATE_LIMIT_WINDOW
        
        key = f"rate_limit:{user_id}"
        current = CacheUtils.get(key)
        
        if current is None:
            return {"limit": limit, "remaining": limit, "reset_time": window}
        
        remaining = max(0, limit - int(current))
        
        try:
            from app.core.database import redis_client
            ttl = redis_client.ttl(key)
            reset_time = ttl if ttl > 0 else window
        except Exception:
            reset_time = window
        
        return {
            "limit": limit,
            "remaining": remaining,
            "reset_time": reset_time
        }
