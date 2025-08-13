"""
Base Scraper Class
Abstract base class for all Islamic Q&A website scrapers
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Generator
import asyncio
import aiohttp
import time
import random
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
import structlog
from bs4 import BeautifulSoup
import hashlib
import json

from app.core.config import settings
from app.core.monitoring import MetricsCollector

logger = structlog.get_logger()


@dataclass
class QuestionAnswer:
    """Data class for scraped Q&A pairs"""
    question: str
    answer: str
    source_url: str
    source_name: str
    scholar_name: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    language: str = "en"
    references: Optional[Dict[str, Any]] = None
    confidence_score: float = 1.0
    is_verified: bool = True


class BaseScraper(ABC):
    """Abstract base class for all scrapers"""
    
    def __init__(self, source_name: str, base_url: str):
        self.source_name = source_name
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None
        self.scraped_urls = set()
        self.request_delay = settings.REQUEST_DELAY
        self.max_retries = settings.MAX_RETRIES
        self.user_agent = settings.USER_AGENT
        
        # Statistics
        self.stats = {
            "pages_scraped": 0,
            "questions_extracted": 0,
            "errors": 0,
            "start_time": None,
            "end_time": None
        }
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"User-Agent": self.user_agent}
        )
        self.stats["start_time"] = time.time()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
        self.stats["end_time"] = time.time()
        
        # Log statistics
        duration = self.stats["end_time"] - self.stats["start_time"]
        logger.info(
            "Scraping completed",
            source=self.source_name,
            duration=duration,
            pages_scraped=self.stats["pages_scraped"],
            questions_extracted=self.stats["questions_extracted"],
            errors=self.stats["errors"]
        )
        
        # Record metrics
        MetricsCollector.record_scraping_job(
            self.source_name,
            "completed" if exc_type is None else "failed"
        )
    
    async def fetch_page(self, url: str, retries: int = None) -> Optional[str]:
        """Fetch a single page with retry logic"""
        retries = retries or self.max_retries
        
        for attempt in range(retries + 1):
            try:
                # Add random delay to avoid rate limiting
                if attempt > 0:
                    delay = self.request_delay * (2 ** attempt) + random.uniform(0, 1)
                    await asyncio.sleep(delay)
                else:
                    await asyncio.sleep(self.request_delay)
                
                async with self.session.get(url) as response:
                    if response.status == 200:
                        content = await response.text()
                        self.stats["pages_scraped"] += 1
                        return content
                    elif response.status == 429:  # Too Many Requests
                        logger.warning(f"Rate limited on {url}, attempt {attempt + 1}")
                        continue
                    else:
                        logger.warning(f"HTTP {response.status} for {url}")
                        
            except Exception as e:
                self.stats["errors"] += 1
                logger.error(f"Error fetching {url}, attempt {attempt + 1}: {str(e)}")
                
                if attempt == retries:
                    return None
        
        return None
    
    def parse_html(self, html: str) -> BeautifulSoup:
        """Parse HTML content"""
        return BeautifulSoup(html, 'html.parser')
    
    def clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        if not text:
            return ""
        
        # Remove extra whitespace
        text = " ".join(text.split())
        
        # Remove common artifacts
        text = text.replace("\xa0", " ")  # Non-breaking space
        text = text.replace("\u200b", "")  # Zero-width space
        
        return text.strip()
    
    def generate_question_hash(self, question: str) -> str:
        """Generate unique hash for question deduplication"""
        normalized = self.clean_text(question).lower()
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    def extract_category_from_url(self, url: str) -> Optional[str]:
        """Extract category from URL path"""
        try:
            path = urlparse(url).path
            parts = [p for p in path.split('/') if p]
            
            # Common category patterns
            category_keywords = [
                'prayer', 'salah', 'namaz',
                'fasting', 'ramadan', 'sawm',
                'hajj', 'pilgrimage', 'umrah',
                'zakat', 'charity',
                'marriage', 'nikah', 'family',
                'business', 'finance', 'riba',
                'aqeedah', 'belief', 'tawheed',
                'fiqh', 'jurisprudence',
                'quran', 'hadith', 'sunnah'
            ]
            
            for part in parts:
                part_lower = part.lower()
                for keyword in category_keywords:
                    if keyword in part_lower:
                        return keyword.title()
            
            return parts[0].title() if parts else None
            
        except Exception:
            return None
    
    @abstractmethod
    async def get_question_urls(self) -> List[str]:
        """Get list of URLs containing questions"""
        pass
    
    @abstractmethod
    async def scrape_question_answer(self, url: str) -> Optional[QuestionAnswer]:
        """Scrape question and answer from a specific URL"""
        pass
    
    async def scrape_all(self, max_pages: int = None) -> List[QuestionAnswer]:
        """Scrape all questions and answers"""
        logger.info(f"Starting scraping for {self.source_name}")
        
        # Get question URLs
        question_urls = await self.get_question_urls()
        
        if max_pages:
            question_urls = question_urls[:max_pages]
        
        logger.info(f"Found {len(question_urls)} question URLs to scrape")
        
        # Scrape questions in batches to avoid overwhelming the server
        batch_size = 10
        results = []
        
        for i in range(0, len(question_urls), batch_size):
            batch = question_urls[i:i + batch_size]
            batch_results = await asyncio.gather(
                *[self.scrape_question_answer(url) for url in batch],
                return_exceptions=True
            )
            
            # Filter successful results
            for result in batch_results:
                if isinstance(result, QuestionAnswer):
                    results.append(result)
                    self.stats["questions_extracted"] += 1
                elif isinstance(result, Exception):
                    self.stats["errors"] += 1
                    logger.error(f"Scraping error: {str(result)}")
            
            # Progress logging
            progress = (i + len(batch)) / len(question_urls) * 100
            logger.info(f"Scraping progress: {progress:.1f}% ({len(results)} questions)")
            
            # Small delay between batches
            await asyncio.sleep(2)
        
        logger.info(f"Scraping completed: {len(results)} questions extracted")
        return results
    
    def validate_qa_pair(self, qa: QuestionAnswer) -> bool:
        """Validate scraped Q&A pair"""
        if not qa.question or not qa.answer:
            return False
        
        if len(qa.question.strip()) < 10:
            return False
        
        if len(qa.answer.strip()) < 20:
            return False
        
        return True
    
    async def save_to_database(self, qa_pairs: List[QuestionAnswer]):
        """Save Q&A pairs to database"""
        from app.core.database import SessionLocal, Question, Answer, DatabaseUtils
        
        db = SessionLocal()
        try:
            saved_count = 0
            
            for qa in qa_pairs:
                if not self.validate_qa_pair(qa):
                    continue
                
                # Check for duplicate
                question_hash = self.generate_question_hash(qa.question)
                existing = db.query(Question).filter(
                    Question.question_hash == question_hash
                ).first()
                
                if existing:
                    logger.debug(f"Duplicate question skipped: {qa.question[:50]}...")
                    continue
                
                # Create question record
                question = Question(
                    question_text=qa.question,
                    question_hash=question_hash,
                    language=qa.language,
                    category=qa.category,
                    tags=qa.tags or []
                )
                
                db.add(question)
                db.flush()  # Get the ID
                
                # Create answer record
                answer = Answer(
                    question_id=question.id,
                    answer_text=qa.answer,
                    source_url=qa.source_url,
                    source_name=qa.source_name,
                    scholar_name=qa.scholar_name,
                    confidence_score=qa.confidence_score,
                    is_verified=qa.is_verified,
                    language=qa.language,
                    references=qa.references or {}
                )
                
                db.add(answer)
                saved_count += 1
            
            db.commit()
            logger.info(f"Saved {saved_count} Q&A pairs to database")
            
        except Exception as e:
            db.rollback()
            logger.error(f"Database save error: {str(e)}")
            raise
        finally:
            db.close()


class ScrapingManager:
    """Manager for coordinating multiple scrapers"""
    
    def __init__(self):
        self.scrapers = []
    
    def register_scraper(self, scraper_class, *args, **kwargs):
        """Register a scraper"""
        scraper = scraper_class(*args, **kwargs)
        self.scrapers.append(scraper)
    
    async def run_all_scrapers(self, max_pages_per_source: int = None):
        """Run all registered scrapers"""
        logger.info(f"Starting scraping with {len(self.scrapers)} scrapers")
        
        all_results = []
        
        for scraper in self.scrapers:
            try:
                async with scraper:
                    results = await scraper.scrape_all(max_pages_per_source)
                    await scraper.save_to_database(results)
                    all_results.extend(results)
                    
            except Exception as e:
                logger.error(f"Scraper {scraper.source_name} failed: {str(e)}")
        
        logger.info(f"Total scraping completed: {len(all_results)} questions")
        return all_results
