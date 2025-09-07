"""
IslamQA.info Scraper
Specialized scraper for IslamQA.info website
"""

import re
from typing import List, Optional
from urllib.parse import urljoin, urlparse
import asyncio

from app.scrapers.base_scraper import BaseScraper, QuestionAnswer


class IslamQAScraper(BaseScraper):
    """Scraper for IslamQA.info"""
    
    def __init__(self):
        super().__init__(
            source_name="IslamQA.info",
            base_url="https://islamqa.info"
        )
        # Use topic IDs as per the new URL structure
        self.topic_ids = [55, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54]  # Add more as needed
    
    async def get_question_urls(self) -> List[str]:
        """Get question URLs from IslamQA using topic IDs"""
        urls = []
        for topic_id in self.topic_ids:
            category_urls = await self._get_category_urls(topic_id)
            urls.extend(category_urls)
            await asyncio.sleep(1)
        return list(set(urls))
    
    async def _get_category_urls(self, topic_id: int) -> List[str]:
        """Get question URLs from a specific topic/category by ID (no pagination)"""
        urls = []
        category_url = f"{self.base_url}/en/categories/topics/{topic_id}"
        html = await self.fetch_page(category_url)
        if not html:
            return urls
        soup = self.parse_html(html)
        question_links = soup.find_all('a', href=re.compile(r'/en/answers/\d+'))
        for link in question_links:
            href = link.get('href')
            if href:
                full_url = urljoin(self.base_url, href)
                urls.append(full_url)
        return urls
    
    async def scrape_question_answer(self, url: str) -> Optional[QuestionAnswer]:
        """Scrape question and answer from IslamQA URL"""
        try:
            html = await self.fetch_page(url)
            if not html:
                return None
            
            soup = self.parse_html(html)
            
            # Extract question
            question = self._extract_question(soup)
            if not question:
                return None
            
            # Extract answer
            answer = self._extract_answer(soup)
            if not answer:
                return None
            
            # Extract additional metadata
            category = self._extract_category(soup, url)
            references = self._extract_references(soup)
            
            return QuestionAnswer(
                question=question,
                answer=answer,
                source_url=url,
                source_name=self.source_name,
                scholar_name="IslamQA Team",
                category=category,
                language="en",
                references=references,
                confidence_score=0.9,
                is_verified=True
            )
            
        except Exception as e:
            self.logger.error(f"Error scraping {url}: {str(e)}")
            return None
    
    def _extract_question(self, soup) -> Optional[str]:
        """Extract question text from soup"""
        # Try multiple selectors for question
        selectors = [
            'h1.question-title',
            '.question-content',
            '.fatwa-title',
            'h1',
            '.question'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                question = self.clean_text(element.get_text())
                if len(question) > 10:
                    return question
        
        return None
    
    def _extract_answer(self, soup) -> Optional[str]:
        """Extract answer text from soup"""
        # Try multiple selectors for answer
        selectors = [
            '.fatwa-answer',
            '.answer-content',
            '.fatwa-content',
            '#answer',
            '.answer'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                # Remove unwanted elements
                for unwanted in element.find_all(['script', 'style', 'iframe']):
                    unwanted.decompose()
                
                answer = self.clean_text(element.get_text())
                if len(answer) > 50:
                    return answer
        
        # Fallback: look for divs with substantial text content
        content_divs = soup.find_all('div')
        for div in content_divs:
            text = self.clean_text(div.get_text())
            if len(text) > 200 and 'praise be to allah' in text.lower():
                return text
        
        return None
    
    def _extract_category(self, soup, url: str) -> Optional[str]:
        """Extract category from page or URL"""
        # Try to extract from breadcrumbs
        breadcrumbs = soup.find_all('a', href=re.compile(r'/categories/'))
        if breadcrumbs:
            return self.clean_text(breadcrumbs[-1].get_text())
        
        # Extract from URL
        return self.extract_category_from_url(url)
    
    def _extract_references(self, soup) -> dict:
        """Extract Quranic and Hadith references"""
        references = {
            "quran_verses": [],
            "hadith_references": [],
            "scholarly_opinions": []
        }
        
        text = soup.get_text().lower()
        
        # Find Quran references
        quran_patterns = [
            r'(\d+):(\d+)',  # 2:255 format
            r'surah? (\w+)',  # Surah name
            r'al-(\w+)',  # Al-Baqarah format
        ]
        
        for pattern in quran_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if isinstance(match, tuple):
                    references["quran_verses"].append(":".join(match))
                else:
                    references["quran_verses"].append(match)
        
        # Find Hadith references
        hadith_patterns = [
            r'bukhari',
            r'muslim',
            r'abu dawud',
            r'tirmidhi',
            r'ibn majah',
            r'ahmad'
        ]
        
        for pattern in hadith_patterns:
            if pattern in text:
                references["hadith_references"].append(pattern.title())
        
        return references


class IslamQAArabicScraper(BaseScraper):
    """Scraper for Arabic IslamQA"""
    
    def __init__(self):
        super().__init__(
            source_name="IslamQA.info (Arabic)",
            base_url="https://islamqa.info"
        )
    
    async def get_question_urls(self) -> List[str]:
        """Get Arabic question URLs"""
        urls = []
        
        # Arabic sections
        sections = [
            "العقيدة-والإيمان",
            "العبادات",
            "الفقه",
            "الأخلاق-والآداب",
            "الدعوة-والجهاد"
        ]
        
        for section in sections:
            section_urls = await self._get_arabic_section_urls(section)
            urls.extend(section_urls)
            await asyncio.sleep(1)
        
        return list(set(urls))
    
    async def _get_arabic_section_urls(self, section: str, max_pages: int = 30) -> List[str]:
        """Get URLs from Arabic section"""
        urls = []
        
        for page in range(1, max_pages + 1):
            section_url = f"{self.base_url}/ar/categories/{section}?page={page}"
            
            html = await self.fetch_page(section_url)
            if not html:
                break
            
            soup = self.parse_html(html)
            question_links = soup.find_all('a', href=re.compile(r'/ar/answers/\d+'))
            
            if not question_links:
                break
            
            page_urls = []
            for link in question_links:
                href = link.get('href')
                if href:
                    full_url = urljoin(self.base_url, href)
                    page_urls.append(full_url)
            
            urls.extend(page_urls)
            
            if len(page_urls) < 10:
                break
        
        return urls
    
    async def scrape_question_answer(self, url: str) -> Optional[QuestionAnswer]:
        """Scrape Arabic question and answer"""
        try:
            html = await self.fetch_page(url)
            if not html:
                return None
            
            soup = self.parse_html(html)
            
            # Extract question and answer using similar logic
            question = self._extract_question(soup)
            answer = self._extract_answer(soup)
            
            if not question or not answer:
                return None
            
            category = self._extract_category(soup, url)
            
            return QuestionAnswer(
                question=question,
                answer=answer,
                source_url=url,
                source_name=self.source_name,
                scholar_name="فريق الإسلام سؤال وجواب",
                category=category,
                language="ar",
                confidence_score=0.9,
                is_verified=True
            )
            
        except Exception as e:
            self.logger.error(f"Error scraping Arabic {url}: {str(e)}")
            return None
    
    def _extract_question(self, soup) -> Optional[str]:
        """Extract Arabic question"""
        selectors = [
            'h1.question-title',
            '.question-content',
            'h1',
            '.question'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                question = self.clean_text(element.get_text())
                if len(question) > 10 and self._is_arabic_text(question):
                    return question
        
        return None
    
    def _extract_answer(self, soup) -> Optional[str]:
        """Extract Arabic answer"""
        selectors = [
            '.fatwa-answer',
            '.answer-content',
            '.fatwa-content'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                answer = self.clean_text(element.get_text())
                if len(answer) > 50 and self._is_arabic_text(answer):
                    return answer
        
        return None
    
    def _extract_category(self, soup, url: str) -> Optional[str]:
        """Extract Arabic category"""
        # Extract from URL
        return self.extract_category_from_url(url)
    
    def _is_arabic_text(self, text: str) -> bool:
        """Check if text contains Arabic characters"""
        arabic_chars = sum(1 for char in text if '\u0600' <= char <= '\u06FF')
        return arabic_chars > len(text) * 0.3  # At least 30% Arabic characters
