"""
Admin Endpoints
Administrative functions for managing the Islamic Q&A system
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timedelta

from app.core.database import get_db, User, Question, Answer, Source, ScrapingJob
from app.core.security import get_current_admin_user
from app.services.knowledge_service import KnowledgeService
from app.services.ml_service import MLService
from app.scrapers.base_scraper import ScrapingManager
from app.scrapers.islamqa_scraper import IslamQAScraper, IslamQAArabicScraper
from app.scrapers.daralifta_scraper import DarAlIftaScraper, DarAlIftaArabicScraper

router = APIRouter()


class SystemStats(BaseModel):
    total_questions: int
    total_answers: int
    total_users: int
    total_sources: int
    recent_activity: Dict[str, int]


class ScrapingJobCreate(BaseModel):
    source_name: str
    max_pages: Optional[int] = None
    force_update: bool = False


class ScrapingJobStatus(BaseModel):
    job_id: str
    source_name: str
    status: str
    pages_scraped: int
    questions_extracted: int
    started_at: Optional[str]
    completed_at: Optional[str]
    error_message: Optional[str]


class RebuildIndexRequest(BaseModel):
    force_rebuild: bool = False
    rebuild_ml_index: bool = True
    rebuild_search_index: bool = True


@router.get("/stats", response_model=SystemStats)
async def get_system_stats(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Get system statistics"""
    try:
        # Basic counts
        total_questions = db.query(Question).count()
        total_answers = db.query(Answer).count()
        total_users = db.query(User).count()
        total_sources = db.query(Source).count()
        
        # Recent activity (last 7 days)
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_questions = db.query(Question).filter(
            Question.created_at >= week_ago
        ).count()
        recent_answers = db.query(Answer).filter(
            Answer.created_at >= week_ago
        ).count()
        recent_users = db.query(User).filter(
            User.created_at >= week_ago
        ).count()
        
        return SystemStats(
            total_questions=total_questions,
            total_answers=total_answers,
            total_users=total_users,
            total_sources=total_sources,
            recent_activity={
                "questions_this_week": recent_questions,
                "answers_this_week": recent_answers,
                "new_users_this_week": recent_users
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get system stats: {str(e)}"
        )


@router.get("/sources")
async def list_sources(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """List all scraping sources"""
    try:
        sources = db.query(Source).all()
        
        result = []
        for source in sources:
            result.append({
                "id": str(source.id),
                "name": source.name,
                "base_url": source.base_url,
                "is_active": source.is_active,
                "priority": source.priority,
                "last_scraped": source.last_scraped.isoformat() if source.last_scraped else None,
                "created_at": source.created_at.isoformat() if source.created_at else None
            })
        
        return {"sources": result}
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list sources: {str(e)}"
        )


@router.post("/scraping/start")
async def start_scraping_job(
    job_request: ScrapingJobCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Start a scraping job"""
    try:
        # Create scraping job record
        job = ScrapingJob(
            status="pending",
            started_at=datetime.utcnow()
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        
        # Start scraping in background
        background_tasks.add_task(
            run_scraping_job,
            str(job.id),
            job_request.source_name,
            job_request.max_pages,
            job_request.force_update
        )
        
        return {
            "job_id": str(job.id),
            "message": f"Scraping job started for {job_request.source_name}",
            "status": "pending"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start scraping job: {str(e)}"
        )


@router.get("/scraping/jobs")
async def list_scraping_jobs(
    limit: int = 50,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """List recent scraping jobs"""
    try:
        jobs = db.query(ScrapingJob).order_by(
            ScrapingJob.created_at.desc()
        ).limit(limit).all()
        
        result = []
        for job in jobs:
            result.append(ScrapingJobStatus(
                job_id=str(job.id),
                source_name=job.source_id or "Unknown",  # Would need to join with Source
                status=job.status,
                pages_scraped=job.pages_scraped,
                questions_extracted=job.questions_extracted,
                started_at=job.started_at.isoformat() if job.started_at else None,
                completed_at=job.completed_at.isoformat() if job.completed_at else None,
                error_message=job.error_message
            ))
        
        return {"jobs": result}
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list scraping jobs: {str(e)}"
        )


@router.post("/rebuild-indexes")
async def rebuild_indexes(
    request: RebuildIndexRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_admin_user)
):
    """Rebuild system indexes"""
    try:
        # Start rebuild in background
        background_tasks.add_task(
            rebuild_system_indexes,
            request.force_rebuild,
            request.rebuild_ml_index,
            request.rebuild_search_index
        )
        
        return {
            "message": "Index rebuild started",
            "force_rebuild": request.force_rebuild,
            "rebuild_ml_index": request.rebuild_ml_index,
            "rebuild_search_index": request.rebuild_search_index
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start index rebuild: {str(e)}"
        )


@router.get("/analytics/summary")
async def get_analytics_summary(
    days: int = 30,
    current_user: User = Depends(get_current_admin_user)
):
    """Get analytics summary"""
    try:
        knowledge_service = KnowledgeService()
        summary = await knowledge_service.get_analytics_summary(days)
        
        return summary
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get analytics summary: {str(e)}"
        )


@router.post("/maintenance/cleanup")
async def run_maintenance_cleanup(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_admin_user)
):
    """Run database cleanup and maintenance tasks"""
    try:
        background_tasks.add_task(run_cleanup_tasks)
        
        return {"message": "Maintenance cleanup started"}
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start cleanup: {str(e)}"
        )


@router.get("/system/health")
async def get_system_health(
    current_user: User = Depends(get_current_admin_user)
):
    """Get detailed system health information"""
    try:
        from app.core.monitoring import HealthChecker
        
        health_status = await HealthChecker.get_health_status()
        
        return health_status
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get system health: {str(e)}"
        )


# Background task functions
async def run_scraping_job(
    job_id: str,
    source_name: str,
    max_pages: Optional[int],
    force_update: bool
):
    """Run scraping job in background"""
    db = SessionLocal()
    try:
        # Update job status
        job = db.query(ScrapingJob).filter(ScrapingJob.id == job_id).first()
        if job:
            job.status = "running"
            db.commit()
        
        # Initialize scraping manager
        scraping_manager = ScrapingManager()
        
        # Register appropriate scraper based on source name
        if source_name.lower() == "islamqa":
            scraping_manager.register_scraper(IslamQAScraper)
            scraping_manager.register_scraper(IslamQAArabicScraper)
        elif source_name.lower() == "dar-al-ifta":
            scraping_manager.register_scraper(DarAlIftaScraper)
            scraping_manager.register_scraper(DarAlIftaArabicScraper)
        else:
            raise ValueError(f"Unknown source: {source_name}")
        
        # Run scraping
        results = await scraping_manager.run_all_scrapers(max_pages)
        
        # Update job status
        if job:
            job.status = "completed"
            job.pages_scraped = len(results)  # Approximate
            job.questions_extracted = len(results)
            job.completed_at = datetime.utcnow()
            db.commit()
        
    except Exception as e:
        # Update job with error
        if job:
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            db.commit()
        
        import structlog
        logger = structlog.get_logger()
        logger.error(f"Scraping job {job_id} failed: {str(e)}")
    
    finally:
        db.close()


async def rebuild_system_indexes(
    force_rebuild: bool,
    rebuild_ml_index: bool,
    rebuild_search_index: bool
):
    """Rebuild system indexes in background"""
    try:
        import structlog
        logger = structlog.get_logger()
        logger.info("Starting index rebuild")
        
        if rebuild_search_index:
            knowledge_service = KnowledgeService()
            await knowledge_service.initialize()
            logger.info("Search indexes rebuilt")
        
        if rebuild_ml_index:
            ml_service = MLService()
            await ml_service.initialize_models()
            # Rebuild FAISS index
            await ml_service.vector_embeddings.build_faiss_index(force_rebuild)
            logger.info("ML indexes rebuilt")
        
        logger.info("Index rebuild completed")
        
    except Exception as e:
        import structlog
        logger = structlog.get_logger()
        logger.error(f"Index rebuild failed: {str(e)}")


async def run_cleanup_tasks():
    """Run database cleanup tasks"""
    try:
        import structlog
        logger = structlog.get_logger()
        logger.info("Starting cleanup tasks")
        
        db = SessionLocal()
        
        # Clean up old user interactions (older than 90 days)
        cleanup_date = datetime.utcnow() - timedelta(days=90)
        from app.core.database import UserInteraction
        deleted_interactions = db.query(UserInteraction).filter(
            UserInteraction.created_at < cleanup_date
        ).delete()
        
        # Clean up failed scraping jobs (older than 30 days)
        job_cleanup_date = datetime.utcnow() - timedelta(days=30)
        deleted_jobs = db.query(ScrapingJob).filter(
            ScrapingJob.created_at < job_cleanup_date,
            ScrapingJob.status == "failed"
        ).delete()
        
        db.commit()
        db.close()
        
        logger.info(
            "Cleanup completed",
            deleted_interactions=deleted_interactions,
            deleted_jobs=deleted_jobs
        )
        
    except Exception as e:
        import structlog
        logger = structlog.get_logger()
        logger.error(f"Cleanup tasks failed: {str(e)}")


# Import SessionLocal at module level
from app.core.database import SessionLocal
