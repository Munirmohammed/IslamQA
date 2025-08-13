"""
Monitoring and Metrics
Prometheus metrics collection and application monitoring
"""

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Request, Response
from fastapi.responses import PlainTextResponse
import time
import structlog

logger = structlog.get_logger()

# Prometheus metrics
request_count = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code']
)

request_duration = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint']
)

active_connections = Gauge(
    'active_connections',
    'Number of active connections'
)

questions_asked = Counter(
    'questions_asked_total',
    'Total questions asked',
    ['language', 'category']
)

ml_processing_time = Histogram(
    'ml_processing_duration_seconds',
    'ML processing duration in seconds',
    ['model_type']
)

cache_hits = Counter(
    'cache_hits_total',
    'Total cache hits',
    ['cache_type']
)

cache_misses = Counter(
    'cache_misses_total',
    'Total cache misses',
    ['cache_type']
)

scraping_jobs = Counter(
    'scraping_jobs_total',
    'Total scraping jobs',
    ['source', 'status']
)

database_queries = Counter(
    'database_queries_total',
    'Total database queries',
    ['table', 'operation']
)

error_count = Counter(
    'errors_total',
    'Total errors',
    ['error_type', 'endpoint']
)


class PrometheusMiddleware:
    """Prometheus metrics middleware"""
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        request = Request(scope, receive)
        start_time = time.time()
        
        # Increment active connections
        active_connections.inc()
        
        try:
            # Process request
            response = await self.app(scope, receive, send)
            
            # Record metrics
            duration = time.time() - start_time
            method = request.method
            path = request.url.path
            status_code = getattr(response, 'status_code', 200)
            
            # Update metrics
            request_count.labels(
                method=method,
                endpoint=path,
                status_code=status_code
            ).inc()
            
            request_duration.labels(
                method=method,
                endpoint=path
            ).observe(duration)
            
            logger.info(
                "Request processed",
                method=method,
                path=path,
                status_code=status_code,
                duration=duration
            )
            
        except Exception as e:
            # Record error
            error_count.labels(
                error_type=type(e).__name__,
                endpoint=request.url.path
            ).inc()
            
            logger.error(
                "Request error",
                error=str(e),
                method=request.method,
                path=request.url.path
            )
            raise
        
        finally:
            # Decrement active connections
            active_connections.dec()


class MetricsCollector:
    """Custom metrics collector"""
    
    @staticmethod
    def record_question_asked(language: str = "en", category: str = "general"):
        """Record a question being asked"""
        questions_asked.labels(language=language, category=category).inc()
    
    @staticmethod
    def record_ml_processing(model_type: str, duration: float):
        """Record ML processing time"""
        ml_processing_time.labels(model_type=model_type).observe(duration)
    
    @staticmethod
    def record_cache_hit(cache_type: str = "redis"):
        """Record cache hit"""
        cache_hits.labels(cache_type=cache_type).inc()
    
    @staticmethod
    def record_cache_miss(cache_type: str = "redis"):
        """Record cache miss"""
        cache_misses.labels(cache_type=cache_type).inc()
    
    @staticmethod
    def record_scraping_job(source: str, status: str):
        """Record scraping job"""
        scraping_jobs.labels(source=source, status=status).inc()
    
    @staticmethod
    def record_database_query(table: str, operation: str):
        """Record database query"""
        database_queries.labels(table=table, operation=operation).inc()
    
    @staticmethod
    def record_error(error_type: str, endpoint: str):
        """Record error"""
        error_count.labels(error_type=error_type, endpoint=endpoint).inc()


# Metrics endpoint
async def metrics_endpoint():
    """Prometheus metrics endpoint"""
    return PlainTextResponse(
        generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


# Health check metrics
class HealthChecker:
    """Application health checker"""
    
    @staticmethod
    async def check_database_health():
        """Check database connectivity"""
        try:
            from app.core.database import engine
            with engine.connect() as conn:
                conn.execute("SELECT 1")
            return True
        except Exception as e:
            logger.error("Database health check failed", error=str(e))
            return False
    
    @staticmethod
    async def check_redis_health():
        """Check Redis connectivity"""
        try:
            from app.core.database import redis_client
            redis_client.ping()
            return True
        except Exception as e:
            logger.error("Redis health check failed", error=str(e))
            return False
    
    @staticmethod
    async def check_ml_models_health():
        """Check ML models availability"""
        try:
            # This would check if ML models are loaded
            # Implementation depends on your ML service
            return True
        except Exception as e:
            logger.error("ML models health check failed", error=str(e))
            return False
    
    @staticmethod
    async def get_health_status():
        """Get overall health status"""
        checks = {
            "database": await HealthChecker.check_database_health(),
            "redis": await HealthChecker.check_redis_health(),
            "ml_models": await HealthChecker.check_ml_models_health()
        }
        
        overall_health = all(checks.values())
        
        return {
            "status": "healthy" if overall_health else "unhealthy",
            "checks": checks,
            "timestamp": time.time()
        }


# Performance monitoring decorator
def monitor_performance(operation: str):
    """Decorator to monitor function performance"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                
                # Record metrics based on operation type
                if operation.startswith("ml_"):
                    MetricsCollector.record_ml_processing(operation, duration)
                
                logger.info(
                    "Operation completed",
                    operation=operation,
                    duration=duration
                )
                
                return result
            
            except Exception as e:
                duration = time.time() - start_time
                MetricsCollector.record_error(type(e).__name__, operation)
                
                logger.error(
                    "Operation failed",
                    operation=operation,
                    duration=duration,
                    error=str(e)
                )
                raise
        
        return wrapper
    return decorator
