"""
Maintenance Tasks
Celery tasks for system maintenance and health monitoring
"""

from celery import current_task
import structlog
from datetime import datetime, timedelta
import os
import subprocess

from app.worker import celery_app

logger = structlog.get_logger()


@celery_app.task(bind=True)
def cleanup_old_data(self):
    """Clean up old data to maintain system performance"""
    try:
        logger.info("Starting data cleanup task")
        
        from app.core.database import SessionLocal, UserInteraction, ScrapingJob
        
        db = SessionLocal()
        cleanup_results = {}
        
        # Clean up old user interactions (older than 90 days)
        cleanup_date = datetime.utcnow() - timedelta(days=90)
        
        old_interactions = db.query(UserInteraction).filter(
            UserInteraction.created_at < cleanup_date
        ).delete()
        
        cleanup_results["interactions_deleted"] = old_interactions
        
        # Clean up failed scraping jobs (older than 30 days)
        job_cleanup_date = datetime.utcnow() - timedelta(days=30)
        
        old_jobs = db.query(ScrapingJob).filter(
            ScrapingJob.created_at < job_cleanup_date,
            ScrapingJob.status == "failed"
        ).delete()
        
        cleanup_results["failed_jobs_deleted"] = old_jobs
        
        # Clear Redis cache for old entries
        try:
            from app.core.database import redis_client
            
            # Get all keys and delete old cache entries
            cache_keys = redis_client.keys("*")
            deleted_cache_keys = 0
            
            for key in cache_keys:
                try:
                    ttl = redis_client.ttl(key)
                    if ttl == -1:  # No expiration set
                        redis_client.expire(key, 3600)  # Set 1 hour expiration
                        deleted_cache_keys += 1
                except Exception:
                    continue
            
            cleanup_results["cache_keys_updated"] = deleted_cache_keys
            
        except Exception as e:
            logger.warning(f"Cache cleanup failed: {str(e)}")
        
        db.commit()
        db.close()
        
        logger.info(f"Data cleanup completed: {cleanup_results}")
        return {"status": "success", "cleanup_results": cleanup_results}
        
    except Exception as e:
        logger.error(f"Data cleanup failed: {str(e)}")
        return {"status": "error", "message": str(e)}


@celery_app.task(bind=True)
def backup_database(self):
    """Create database backup"""
    try:
        logger.info("Starting database backup")
        
        from app.core.config import settings
        import urllib.parse
        
        # Parse database URL
        db_url = urllib.parse.urlparse(settings.DATABASE_URL)
        
        if db_url.scheme == 'postgresql':
            # PostgreSQL backup
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"islamqa_backup_{timestamp}.sql"
            
            try:
                # Create backup directory
                os.makedirs("backups", exist_ok=True)
                backup_path = os.path.join("backups", backup_filename)
                
                # Run pg_dump
                env = os.environ.copy()
                env['PGPASSWORD'] = db_url.password
                
                cmd = [
                    'pg_dump',
                    '-h', db_url.hostname,
                    '-p', str(db_url.port or 5432),
                    '-U', db_url.username,
                    '-d', db_url.path.lstrip('/'),
                    '-f', backup_path,
                    '--verbose'
                ]
                
                result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=1800)
                
                if result.returncode == 0:
                    # Get backup file size
                    backup_size = os.path.getsize(backup_path)
                    
                    logger.info(f"Database backup completed: {backup_filename} ({backup_size} bytes)")
                    return {
                        "status": "success",
                        "backup_file": backup_filename,
                        "backup_size": backup_size
                    }
                else:
                    logger.error(f"pg_dump failed: {result.stderr}")
                    return {"status": "error", "message": result.stderr}
                    
            except subprocess.TimeoutExpired:
                logger.error("Database backup timed out")
                return {"status": "error", "message": "Backup timed out"}
            except FileNotFoundError:
                logger.error("pg_dump not found. Please install PostgreSQL client tools.")
                return {"status": "error", "message": "pg_dump not available"}
        else:
            logger.warning("Database backup only supported for PostgreSQL")
            return {"status": "skipped", "message": "Backup only supported for PostgreSQL"}
        
    except Exception as e:
        logger.error(f"Database backup failed: {str(e)}")
        return {"status": "error", "message": str(e)}


@celery_app.task(bind=True)
def system_health_check(self):
    """Perform comprehensive system health check"""
    try:
        logger.info("Starting system health check")
        
        from app.core.monitoring import HealthChecker
        import asyncio
        
        # Run async health check
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            health_status = loop.run_until_complete(HealthChecker.get_health_status())
            
            # Additional system checks
            health_status.update({
                "disk_usage": get_disk_usage(),
                "memory_usage": get_memory_usage(),
                "system_load": get_system_load()
            })
            
            # Determine overall health
            all_checks_passed = all(health_status["checks"].values())
            
            if all_checks_passed:
                logger.info("System health check passed")
            else:
                logger.warning(f"System health check found issues: {health_status}")
            
            return {"status": "success", "health_status": health_status}
            
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"System health check failed: {str(e)}")
        return {"status": "error", "message": str(e)}


@celery_app.task(bind=True)
def optimize_database(self):
    """Optimize database performance"""
    try:
        logger.info("Starting database optimization")
        
        from app.core.database import SessionLocal
        
        db = SessionLocal()
        optimization_results = {}
        
        try:
            # PostgreSQL specific optimizations
            from app.core.config import settings
            import urllib.parse
            
            db_url = urllib.parse.urlparse(settings.DATABASE_URL)
            
            if db_url.scheme == 'postgresql':
                # Run VACUUM and ANALYZE
                db.execute("VACUUM ANALYZE;")
                
                # Update table statistics
                db.execute("ANALYZE;")
                
                # Get database size
                size_result = db.execute("""
                    SELECT pg_size_pretty(pg_database_size(current_database())) as size
                """).fetchone()
                
                optimization_results["database_size"] = size_result.size if size_result else "Unknown"
                
                # Get index usage statistics
                index_stats = db.execute("""
                    SELECT schemaname, tablename, indexname, idx_scan
                    FROM pg_stat_user_indexes
                    ORDER BY idx_scan DESC
                    LIMIT 10
                """).fetchall()
                
                optimization_results["top_used_indexes"] = [
                    {"table": row.tablename, "index": row.indexname, "scans": row.idx_scan}
                    for row in index_stats
                ]
            
            db.commit()
            
        finally:
            db.close()
        
        logger.info(f"Database optimization completed: {optimization_results}")
        return {"status": "success", "optimization_results": optimization_results}
        
    except Exception as e:
        logger.error(f"Database optimization failed: {str(e)}")
        return {"status": "error", "message": str(e)}


@celery_app.task(bind=True)
def monitor_resource_usage(self):
    """Monitor system resource usage"""
    try:
        logger.info("Monitoring resource usage")
        
        resources = {
            "timestamp": datetime.utcnow().isoformat(),
            "disk_usage": get_disk_usage(),
            "memory_usage": get_memory_usage(),
            "system_load": get_system_load(),
            "active_connections": get_active_connections()
        }
        
        # Log warnings for high usage
        if resources["disk_usage"] > 80:
            logger.warning(f"High disk usage: {resources['disk_usage']}%")
        
        if resources["memory_usage"] > 80:
            logger.warning(f"High memory usage: {resources['memory_usage']}%")
        
        logger.info(f"Resource monitoring completed: {resources}")
        return {"status": "success", "resources": resources}
        
    except Exception as e:
        logger.error(f"Resource monitoring failed: {str(e)}")
        return {"status": "error", "message": str(e)}


# Helper functions
def get_disk_usage():
    """Get disk usage percentage"""
    try:
        import shutil
        total, used, free = shutil.disk_usage("/")
        return round((used / total) * 100, 2)
    except Exception:
        return 0


def get_memory_usage():
    """Get memory usage percentage"""
    try:
        import psutil
        return psutil.virtual_memory().percent
    except ImportError:
        # Fallback without psutil
        try:
            with open('/proc/meminfo', 'r') as f:
                lines = f.readlines()
            
            meminfo = {}
            for line in lines:
                key, value = line.split(':')
                meminfo[key] = int(value.split()[0])
            
            total = meminfo['MemTotal']
            available = meminfo['MemAvailable']
            used = total - available
            
            return round((used / total) * 100, 2)
        except Exception:
            return 0
    except Exception:
        return 0


def get_system_load():
    """Get system load average"""
    try:
        return os.getloadavg()[0]
    except Exception:
        return 0


def get_active_connections():
    """Get number of active database connections"""
    try:
        from app.core.database import SessionLocal
        
        db = SessionLocal()
        
        result = db.execute("""
            SELECT count(*) as connections
            FROM pg_stat_activity
            WHERE state = 'active'
        """).fetchone()
        
        db.close()
        
        return result.connections if result else 0
        
    except Exception:
        return 0
