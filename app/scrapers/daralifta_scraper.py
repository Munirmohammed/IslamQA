"""
Dar al-Ifta Scraper
Specialized scraper for Dar al-Ifta Egypt and other Dar al-Ifta websites
"""

import re
from typing import List, Optional
from urllib.parse import urljoin
import asyncio

from app.scrapers.base_scraper import BaseScraper, QuestionAnswer


class DarAlIftaScraper(BaseScraper):
    """Scraper for Dar al-Ifta Egypt"""
    
    def __init__(self):
        super().__init__(
            source_name="Dar al-Ifta Egypt",
            base_url="https://www.dar-alifta.org"
        )
        self.fatwa_sections = [
            "family-fatwas",
            "worship-fatwas", 
            "business-fatwas",
            "medical-fatwas",
            "social-fatwas",
            "contemporary-fatwas"
        ]
    
    async def get_question_urls(self) -> List[str]:
        """Get fatwa URLs from Dar al-Ifta"""
        urls = []
        
        # Get fatwa list pages
        for section in self.fatwa_sections:
            section_urls = await self._get_section_urls(section)
            urls.extend(section_urls)
            await asyncio.sleep(2)  # Be respectful with delays
        
        # Also scrape from general fatwa archive
        archive_urls = await self._get_archive_urls()
        urls.extend(archive_urls)
        
        return list(set(urls))
    
    async def _get_section_urls(self, section: str, max_pages: int = 20) -> List[str]:
        """Get URLs from a specific fatwa section"""
        urls = []
        
        for page in range(1, max_pages + 1):
            section_url = f"{self.base_url}/Foreign/English/{section}?page={page}"
            
            html = await self.fetch_page(section_url)
            if not html:
                break
            
            soup = self.parse_html(html)
            
            # Find fatwa links
            fatwa_links = soup.find_all('a', href=re.compile(r'/Foreign/English/\d+'))
            
            if not fatwa_links:
                break
            
            page_urls = []
            for link in fatwa_links:
                href = link.get('href')
                if href:
                    full_url = urljoin(self.base_url, href)
                    page_urls.append(full_url)
            
            urls.extend(page_urls)
            
            if len(page_urls) < 5:
                break
        
        return urls
    
    async def _get_archive_urls(self, max_pages: int = 50) -> List[str]:
        """Get URLs from fatwa archive"""
        urls = []
        
        for page in range(1, max_pages + 1):
            archive_url = f"{self.base_url}/Foreign/English/fatwa-archive?page={page}"
            
            html = await self.fetch_page(archive_url)
            if not html:
                break
            
            soup = self.parse_html(html)
            links = soup.find_all('a', href=re.compile(r'/Foreign/English/\d+'))
            
            if not links:
                break
            
            for link in links:
                href = link.get('href')
                if href:
                    full_url = urljoin(self.base_url, href)
                    urls.append(full_url)
        
        return urls
    
    async def scrape_question_answer(self, url: str) -> Optional[QuestionAnswer]:
        """Scrape fatwa question and answer from Dar al-Ifta"""
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
            
            # Extract scholar name
            scholar = self._extract_scholar(soup)
            
            # Extract category
            category = self._extract_category(soup, url)
            
            return QuestionAnswer(
                question=question,
                answer=answer,
                source_url=url,
                source_name=self.source_name,
                scholar_name=scholar,
                category=category,
                language="en",
                confidence_score=0.95,  # High confidence for official source
                is_verified=True
            )
            
        except Exception as e:
            self.logger.error(f"Error scraping Dar al-Ifta {url}: {str(e)}")
            return None
    
    def _extract_question(self, soup) -> Optional[str]:
        """Extract question from Dar al-Ifta page"""
        selectors = [
            '.fatwa-question',
            '.question-text',
            '.fatwa-title',
            'h1',
            '.question'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                question = self.clean_text(element.get_text())
                if len(question) > 15:
                    return question
        
        # Look for strong/bold text that might be the question
        strong_elements = soup.find_all(['strong', 'b'])
        for element in strong_elements:
            text = self.clean_text(element.get_text())
            if len(text) > 20 and '?' in text:
                return text
        
        return None
    
    def _extract_answer(self, soup) -> Optional[str]:
        """Extract answer from Dar al-Ifta page"""
        selectors = [
            '.fatwa-answer',
            '.answer-text',
            '.fatwa-content',
            '.answer',
            '.content'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                # Remove unwanted elements
                for unwanted in element.find_all(['script', 'style', 'nav', 'header', 'footer']):
                    unwanted.decompose()
                
                answer = self.clean_text(element.get_text())
                if len(answer) > 100:
                    return answer
        
        # Fallback: look for the main content div
        main_content = soup.find('div', class_=re.compile(r'content|main|article'))
        if main_content:
            answer = self.clean_text(main_content.get_text())
            if len(answer) > 100:
                return answer
        
        return None
    
    def _extract_scholar(self, soup) -> Optional[str]:
        """Extract scholar/mufti name"""
        # Look for scholar attribution
        scholar_selectors = [
            '.scholar-name',
            '.mufti-name', 
            '.fatwa-author',
            '.author'
        ]
        
        for selector in scholar_selectors:
            element = soup.select_one(selector)
            if element:
                scholar = self.clean_text(element.get_text())
                if scholar and len(scholar) < 100:  # Reasonable name length
                    return scholar
        
        # Look for "By:" or "Mufti:" patterns
        text = soup.get_text()
        patterns = [
            r'(?:By|Mufti|Scholar):\s*([^\n\r.]+)',
            r'Dr\.\s+([A-Z][a-z]+ [A-Z][a-z]+)',
            r'Sheikh\s+([A-Z][a-z]+ [A-Z][a-z]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        
        return "Dar al-Ifta Egypt"
    
    def _extract_category(self, soup, url: str) -> Optional[str]:
        """Extract fatwa category"""
        # Extract from URL path
        category_from_url = self.extract_category_from_url(url)
        if category_from_url:
            return category_from_url
        
        # Look for category in breadcrumbs
        breadcrumbs = soup.find_all('a', href=re.compile(r'fatwa'))
        if breadcrumbs:
            for crumb in breadcrumbs:
                text = self.clean_text(crumb.get_text())
                if text and text.lower() not in ['home', 'fatwa', 'fatwas']:
                    return text
        
        return "General"


class DarAlIftaArabicScraper(BaseScraper):
    """Scraper for Arabic Dar al-Ifta content"""
    
    def __init__(self):
        super().__init__(
            source_name="Dar al-Ifta Egypt (Arabic)",
            base_url="https://www.dar-alifta.org"
        )
    
    async def get_question_urls(self) -> List[str]:
        """Get Arabic fatwa URLs"""
        urls = []
        
        # Arabic fatwa sections
        arabic_sections = [
            "فتاوى-الأسرة",
            "فتاوى-العبادات",
            "فتاوى-المعاملات",
            "فتاوى-طبية",
            "فتاوى-معاصرة"
        ]
        
        for section in arabic_sections:
            section_urls = await self._get_arabic_section_urls(section)
            urls.extend(section_urls)
            await asyncio.sleep(2)
        
        return list(set(urls))
    
    async def _get_arabic_section_urls(self, section: str, max_pages: int = 20) -> List[str]:
        """Get URLs from Arabic section"""
        urls = []
        
        for page in range(1, max_pages + 1):
            section_url = f"{self.base_url}/ar/{section}?page={page}"
            
            html = await self.fetch_page(section_url)
            if not html:
                break
            
            soup = self.parse_html(html)
            links = soup.find_all('a', href=re.compile(r'/ar/\d+'))
            
            if not links:
                break
            
            for link in links:
                href = link.get('href')
                if href:
                    full_url = urljoin(self.base_url, href)
                    urls.append(full_url)
        
        return urls
    
    async def scrape_question_answer(self, url: str) -> Optional[QuestionAnswer]:
        """Scrape Arabic fatwa"""
        try:
            html = await self.fetch_page(url)
            if not html:
                return None
            
            soup = self.parse_html(html)
            
            question = self._extract_arabic_question(soup)
            answer = self._extract_arabic_answer(soup)
            
            if not question or not answer:
                return None
            
            scholar = self._extract_arabic_scholar(soup)
            
            return QuestionAnswer(
                question=question,
                answer=answer,
                source_url=url,
                source_name=self.source_name,
                scholar_name=scholar,
                language="ar",
                confidence_score=0.95,
                is_verified=True
            )
            
        except Exception as e:
            self.logger.error(f"Error scraping Arabic Dar al-Ifta {url}: {str(e)}")
            return None
    
    def _extract_arabic_question(self, soup) -> Optional[str]:
        """Extract Arabic question"""
        selectors = [
            '.fatwa-question',
            '.question-text',
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
    
    def _extract_arabic_answer(self, soup) -> Optional[str]:
        """Extract Arabic answer"""
        selectors = [
            '.fatwa-answer',
            '.answer-text',
            '.content'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                answer = self.clean_text(element.get_text())
                if len(answer) > 50 and self._is_arabic_text(answer):
                    return answer
        
        return None
    
    def _extract_arabic_scholar(self, soup) -> Optional[str]:
        """Extract Arabic scholar name"""
        return "دار الإفتاء المصرية"
    
    def _is_arabic_text(self, text: str) -> bool:
        """Check if text is predominantly Arabic"""
        arabic_chars = sum(1 for char in text if '\u0600' <= char <= '\u06FF')
        return arabic_chars > len(text) * 0.3
