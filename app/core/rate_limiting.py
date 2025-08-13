"""
Rate Limiting Middleware
Advanced rate limiting with Redis backend and user-specific limits
"""

from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
import time
import json
from typing import Optional, Dict, Any
import structlog

from app.core.config import settings
from app.core.database import redis_client

logger = structlog.get_logger()


class RateLimitMiddleware:
    """Advanced rate limiting middleware"""
    
    def __init__(self, app):
        self.app = app
        self.default_limit = settings.RATE_LIMIT_REQUESTS
        self.default_window = settings.RATE_LIMIT_WINDOW
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        request = Request(scope, receive)
        
        # Skip rate limiting for certain paths
        if self._should_skip_rate_limiting(request.url.path):
            await self.app(scope, receive, send)
            return
        
        # Get client identifier
        client_id = self._get_client_identifier(request)
        
        # Check rate limit
        rate_limit_result = await self._check_rate_limit(client_id, request)
        
        if not rate_limit_result["allowed"]:
            # Rate limit exceeded
            response = JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "detail": f"Too many requests. Limit: {rate_limit_result['limit']} per {self.default_window} seconds",
                    "retry_after": rate_limit_result["retry_after"]
                },
                headers={
                    "X-RateLimit-Limit": str(rate_limit_result["limit"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(rate_limit_result["reset_time"]),
                    "Retry-After": str(rate_limit_result["retry_after"])
                }
            )
            await response(scope, receive, send)
            return
        
        # Add rate limit headers to response
        async def add_rate_limit_headers(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                headers[b"x-ratelimit-limit"] = str(rate_limit_result["limit"]).encode()
                headers[b"x-ratelimit-remaining"] = str(rate_limit_result["remaining"]).encode()
                headers[b"x-ratelimit-reset"] = str(rate_limit_result["reset_time"]).encode()
                message["headers"] = list(headers.items())
            await send(message)
        
        await self.app(scope, receive, add_rate_limit_headers)
    
    def _should_skip_rate_limiting(self, path: str) -> bool:
        """Check if rate limiting should be skipped for this path"""
        skip_paths = [
            "/health",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json"
        ]
        return any(path.startswith(skip_path) for skip_path in skip_paths)
    
    def _get_client_identifier(self, request: Request) -> str:
        """Get client identifier for rate limiting"""
        # Try to get user ID from token
        try:
            authorization = request.headers.get("Authorization")
            if authorization and authorization.startswith("Bearer "):
                token = authorization.split(" ", 1)[1]
                # Here you would decode the token to get user ID
                # For now, we'll use the token itself as identifier
                return f"user:{token[:20]}"  # Use first 20 chars of token
        except Exception:
            pass
        
        # Fall back to IP address
        client_ip = self._get_client_ip(request)
        return f"ip:{client_ip}"
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address"""
        # Check for forwarded headers
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fall back to direct connection
        if hasattr(request, "client") and request.client:
            return request.client.host
        
        return "unknown"
    
    async def _check_rate_limit(self, client_id: str, request: Request) -> Dict[str, Any]:
        """Check rate limit for client"""
        try:
            # Get user-specific limits if available
            limit, window = await self._get_user_limits(client_id)
            
            # Create Redis key
            current_time = int(time.time())
            window_start = current_time - (current_time % window)
            key = f"rate_limit:{client_id}:{window_start}"
            
            # Get current count
            current_count = redis_client.get(key)
            current_count = int(current_count) if current_count else 0
            
            # Check if limit exceeded
            if current_count >= limit:
                reset_time = window_start + window
                retry_after = reset_time - current_time
                
                logger.warning(
                    "Rate limit exceeded",
                    client_id=client_id,
                    current_count=current_count,
                    limit=limit,
                    path=request.url.path
                )
                
                return {
                    "allowed": False,
                    "limit": limit,
                    "remaining": 0,
                    "reset_time": reset_time,
                    "retry_after": retry_after
                }
            
            # Increment counter
            pipeline = redis_client.pipeline()
            pipeline.incr(key)
            pipeline.expire(key, window)
            pipeline.execute()
            
            # Calculate remaining requests
            remaining = max(0, limit - current_count - 1)
            reset_time = window_start + window
            
            return {
                "allowed": True,
                "limit": limit,
                "remaining": remaining,
                "reset_time": reset_time,
                "retry_after": 0
            }
        
        except Exception as e:
            logger.error("Rate limiting error", error=str(e))
            # Allow request on error
            return {
                "allowed": True,
                "limit": self.default_limit,
                "remaining": self.default_limit,
                "reset_time": int(time.time()) + self.default_window,
                "retry_after": 0
            }
    
    async def _get_user_limits(self, client_id: str) -> tuple[int, int]:
        """Get user-specific rate limits"""
        # Default limits
        limit = self.default_limit
        window = self.default_window
        
        # If it's a user-based identifier, try to get custom limits
        if client_id.startswith("user:"):
            try:
                # Here you would query the database for user-specific limits
                # For now, return default limits
                pass
            except Exception:
                pass
        
        # Different limits for different client types
        if client_id.startswith("ip:"):
            # More restrictive for IP-based limiting
            limit = min(limit, 50)
        
        return limit, window


class AdvancedRateLimiter:
    """Advanced rate limiting with multiple strategies"""
    
    @staticmethod
    async def check_sliding_window(client_id: str, limit: int, window: int) -> bool:
        """Sliding window rate limiting"""
        try:
            current_time = time.time()
            key = f"sliding:{client_id}"
            
            # Remove old entries
            redis_client.zremrangebyscore(key, 0, current_time - window)
            
            # Count current requests
            current_count = redis_client.zcard(key)
            
            if current_count >= limit:
                return False
            
            # Add current request
            redis_client.zadd(key, {str(current_time): current_time})
            redis_client.expire(key, window)
            
            return True
        
        except Exception as e:
            logger.error("Sliding window rate limiting error", error=str(e))
            return True
    
    @staticmethod
    async def check_token_bucket(client_id: str, capacity: int, refill_rate: float) -> bool:
        """Token bucket rate limiting"""
        try:
            current_time = time.time()
            key = f"bucket:{client_id}"
            
            # Get bucket state
            bucket_data = redis_client.get(key)
            if bucket_data:
                bucket = json.loads(bucket_data)
                last_refill = bucket["last_refill"]
                tokens = bucket["tokens"]
            else:
                last_refill = current_time
                tokens = capacity
            
            # Calculate tokens to add
            time_passed = current_time - last_refill
            tokens_to_add = time_passed * refill_rate
            tokens = min(capacity, tokens + tokens_to_add)
            
            # Check if request can be served
            if tokens < 1:
                return False
            
            # Consume token
            tokens -= 1
            
            # Update bucket state
            bucket_data = {
                "tokens": tokens,
                "last_refill": current_time
            }
            redis_client.setex(key, 3600, json.dumps(bucket_data))
            
            return True
        
        except Exception as e:
            logger.error("Token bucket rate limiting error", error=str(e))
            return True
    
    @staticmethod
    async def check_distributed_rate_limit(
        client_id: str, 
        limit: int, 
        window: int,
        nodes: int = 1
    ) -> bool:
        """Distributed rate limiting across multiple nodes"""
        try:
            # Adjust limit for distributed environment
            node_limit = limit // nodes
            
            current_time = int(time.time())
            window_start = current_time - (current_time % window)
            key = f"distributed:{client_id}:{window_start}"
            
            # Use distributed counter
            current_count = redis_client.get(key)
            current_count = int(current_count) if current_count else 0
            
            if current_count >= node_limit:
                return False
            
            # Increment with expiration
            pipeline = redis_client.pipeline()
            pipeline.incr(key)
            pipeline.expire(key, window)
            pipeline.execute()
            
            return True
        
        except Exception as e:
            logger.error("Distributed rate limiting error", error=str(e))
            return True
