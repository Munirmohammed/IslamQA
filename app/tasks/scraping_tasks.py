"""
Scraping Tasks
Celery tasks for web scraping operations
"""

from celery import current_task
import asyncio
import structlog

from app.worker import celery_app
from app.scrapers.base_scraper import ScrapingManager
from app.scrapers.islamqa_scraper import IslamQAScraper, IslamQAArabicScraper
from app.scrapers.daralifta_scraper import DarAlIftaScraper, DarAlIftaArabicScraper

logger = structlog.get_logger()


@celery_app.task(bind=True)
def scrape_islamqa(self, max_pages=50):
    """Scrape IslamQA.info for new content"""
    try:
        logger.info(f"Starting IslamQA scraping task (max_pages: {max_pages})")
        
        # Run async scraping
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            scraping_manager = ScrapingManager()
            scraping_manager.register_scraper(IslamQAScraper)
            scraping_manager.register_scraper(IslamQAArabicScraper)
            
            results = loop.run_until_complete(
                scraping_manager.run_all_scrapers(max_pages_per_source=max_pages)
            )
            
            logger.info(f"IslamQA scraping completed: {len(results)} questions scraped")
            return {
                "status": "success",
                "questions_scraped": len(results),
                "source": "IslamQA"
            }
            
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"IslamQA scraping task failed: {str(e)}")
        current_task.retry(countdown=300, max_retries=3)


@celery_app.task(bind=True)
def scrape_dar_al_ifta(self, max_pages=30):
    """Scrape Dar al-Ifta for new content"""
    try:
        logger.info(f"Starting Dar al-Ifta scraping task (max_pages: {max_pages})")
        
        # Run async scraping
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            scraping_manager = ScrapingManager()
            scraping_manager.register_scraper(DarAlIftaScraper)
            scraping_manager.register_scraper(DarAlIftaArabicScraper)
            
            results = loop.run_until_complete(
                scraping_manager.run_all_scrapers(max_pages_per_source=max_pages)
            )
            
            logger.info(f"Dar al-Ifta scraping completed: {len(results)} questions scraped")
            return {
                "status": "success",
                "questions_scraped": len(results),
                "source": "Dar al-Ifta"
            }
            
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"Dar al-Ifta scraping task failed: {str(e)}")
        current_task.retry(countdown=300, max_retries=3)


@celery_app.task(bind=True)
def scrape_all_sources(self, max_pages_per_source=25):
    """Scrape all configured sources"""
    try:
        logger.info("Starting comprehensive scraping of all sources")
        
        total_results = 0
        source_results = {}
        
        # Scrape IslamQA
        islamqa_result = scrape_islamqa.delay(max_pages_per_source)
        islamqa_data = islamqa_result.get(timeout=1800)  # 30 minutes timeout
        total_results += islamqa_data.get("questions_scraped", 0)
        source_results["IslamQA"] = islamqa_data
        
        # Scrape Dar al-Ifta
        dar_result = scrape_dar_al_ifta.delay(max_pages_per_source)
        dar_data = dar_result.get(timeout=1800)
        total_results += dar_data.get("questions_scraped", 0)
        source_results["Dar al-Ifta"] = dar_data
        
        logger.info(f"All sources scraping completed: {total_results} total questions")
        return {
            "status": "success",
            "total_questions_scraped": total_results,
            "source_results": source_results
        }
        
    except Exception as e:
        logger.error(f"All sources scraping failed: {str(e)}")
        return {"status": "error", "message": str(e)}


@celery_app.task(bind=True)
def validate_scraped_data(self):
    """Validate recently scraped data quality"""
    try:
        logger.info("Starting data validation task")
        
        from app.core.database import SessionLocal, Question, Answer
        from datetime import datetime, timedelta
        
        db = SessionLocal()
        
        # Check recent data (last 24 hours)
        since_time = datetime.utcnow() - timedelta(hours=24)
        
        recent_questions = db.query(Question).filter(
            Question.created_at >= since_time
        ).count()
        
        recent_answers = db.query(Answer).filter(
            Answer.created_at >= since_time
        ).count()
        
        # Check for duplicate questions
        duplicate_hashes = db.execute("""
            SELECT question_hash, COUNT(*) as count
            FROM questions
            GROUP BY question_hash
            HAVING COUNT(*) > 1
        """).fetchall()
        
        # Check for questions without answers
        questions_without_answers = db.execute("""
            SELECT COUNT(*) as count
            FROM questions q
            LEFT JOIN answers a ON q.id = a.question_id
            WHERE a.id IS NULL
        """).scalar()
        
        db.close()
        
        validation_results = {
            "recent_questions": recent_questions,
            "recent_answers": recent_answers,
            "duplicate_questions": len(duplicate_hashes),
            "questions_without_answers": questions_without_answers,
            "data_quality_score": 1.0 - (len(duplicate_hashes) + questions_without_answers) / max(recent_questions, 1)
        }
        
        logger.info(f"Data validation completed: {validation_results}")
        return {"status": "success", "validation_results": validation_results}
        
    except Exception as e:
        logger.error(f"Data validation failed: {str(e)}")
        return {"status": "error", "message": str(e)}


@celery_app.task(bind=True)
def cleanup_duplicate_questions(self):
    """Clean up duplicate questions from database"""
    try:
        logger.info("Starting duplicate cleanup task")
        
        from app.core.database import SessionLocal, Question, Answer
        
        db = SessionLocal()
        
        # Find duplicates
        duplicate_query = """
            SELECT question_hash, MIN(id) as keep_id, COUNT(*) as count
            FROM questions
            GROUP BY question_hash
            HAVING COUNT(*) > 1
        """
        
        duplicates = db.execute(duplicate_query).fetchall()
        
        total_removed = 0
        
        for duplicate in duplicates:
            # Keep the first occurrence, remove others
            question_hash = duplicate.question_hash
            keep_id = duplicate.keep_id
            
            # Get all questions with this hash
            duplicate_questions = db.query(Question).filter(
                Question.question_hash == question_hash,
                Question.id != keep_id
            ).all()
            
            for question in duplicate_questions:
                # Delete associated answers first
                db.query(Answer).filter(Answer.question_id == question.id).delete()
                
                # Delete question
                db.delete(question)
                total_removed += 1
        
        db.commit()
        db.close()
        
        logger.info(f"Duplicate cleanup completed: {total_removed} duplicates removed")
        return {"status": "success", "duplicates_removed": total_removed}
        
    except Exception as e:
        logger.error(f"Duplicate cleanup failed: {str(e)}")
        db.rollback()
        db.close()
        return {"status": "error", "message": str(e)}
