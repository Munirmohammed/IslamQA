"""
Hybrid AI Service
Combines free AI APIs with Islamic knowledge base for comprehensive responses
"""

import asyncio
import aiohttp
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import structlog

from app.core.config import settings
from app.services.knowledge_service import KnowledgeService
from app.services.ml_service import MLService

logger = structlog.get_logger()


class IslamicContentDetector:
    """Detects if a question is Islamic-related"""
    
    ISLAMIC_KEYWORDS = {
        # Core Islamic terms
        'allah', 'god', 'islam', 'muslim', 'islamic', 'quran', 'qur\'an', 'koran',
        'muhammad', 'prophet', 'messenger', 'rasul', 'nabi',
        
        # Five Pillars
        'shahada', 'kalima', 'declaration', 'faith', 'belief',
        'salah', 'prayer', 'pray', 'namaz', 'dua', 'du\'a',
        'zakat', 'charity', 'alms', 'sadaqah',
        'sawm', 'fasting', 'ramadan', 'fast', 'iftar', 'suhoor',
        'hajj', 'pilgrimage', 'mecca', 'kaaba', 'umrah',
        
        # Islamic practices
        'wudu', 'ablution', 'ghusl', 'tahajjud', 'witr',
        'dhikr', 'zikr', 'tasbih', 'istighfar', 'salawat',
        'qibla', 'mecca', 'medina', 'mosque', 'masjid',
        'imam', 'khutbah', 'friday', 'jummah', 'eid',
        
        # Islamic concepts
        'halal', 'haram', 'makruh', 'sunnah', 'fard', 'wajib',
        'jihad', 'ummah', 'aqeedah', 'tawhid', 'shirk',
        'heaven', 'hell', 'paradise', 'jannah', 'jahannam',
        'angel', 'jinn', 'shaytan', 'satan', 'devil',
        
        # Quranic terms
        'surah', 'ayah', 'verse', 'chapter', 'revelation',
        'hadith', 'bukhari', 'muslim', 'tirmidhi', 'sunnah',
        
        # Arabic greetings/phrases
        'assalam', 'salaam', 'wa alaikum', 'bismillah', 'inshallah',
        'mashallah', 'subhanallah', 'alhamdulillah', 'allahu akbar',
        'astaghfirullah', 'barakallahu', 'jazakallahu'
    }
    
    ISLAMIC_PATTERNS = [
        r'\b(how\s+to\s+)?(pray|perform\s+prayer|make\s+salah)\b',
        r'\b(what\s+is\s+)?(islam|muslim|islamic)\b',
        r'\b(five\s+)?pillars?\s+of\s+islam\b',
        r'\bmuslims?\s+(believe|do|practice)\b',
        r'\bin\s+islam\b',
        r'\baccording\s+to\s+islam\b',
        r'\bislamic\s+(law|rule|teaching|practice)\b'
    ]
    
    @classmethod
    def is_islamic_question(cls, text: str) -> Tuple[bool, float]:
        """
        Determine if a question is Islamic-related
        Returns (is_islamic, confidence_score)
        """
        text_lower = text.lower()
        
        # Check for direct keyword matches
        keyword_matches = sum(1 for keyword in cls.ISLAMIC_KEYWORDS if keyword in text_lower)
        keyword_score = min(keyword_matches / 3.0, 1.0)  # Normalize to 0-1
        
        # Check for pattern matches
        pattern_matches = sum(1 for pattern in cls.ISLAMIC_PATTERNS if re.search(pattern, text_lower))
        pattern_score = min(pattern_matches / 2.0, 1.0)
        
        # Combined confidence score
        confidence = max(keyword_score, pattern_score)
        
        # Threshold for Islamic classification
        is_islamic = confidence > 0.3
        
        return is_islamic, confidence


class FreeAIProvider:
    """Interface to free AI providers"""
    
    def __init__(self):
        self.session = None
    
    async def get_session(self):
        """Get or create aiohttp session"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close(self):
        """Close the session"""
        if self.session:
            await self.session.close()
    
    async def chat_with_huggingface(self, message: str, context: str = "") -> str:
        """Use Hugging Face Inference API for chat"""
        try:
            session = await self.get_session()
            
            # Use a conversational model from Hugging Face
            api_url = "https://api-inference.huggingface.co/models/microsoft/DialoGPT-large"
            headers = {"Authorization": f"Bearer {settings.HUGGINGFACE_API_KEY}"}
            
            # Prepare the prompt with Islamic context if needed
            prompt = f"{context}\nUser: {message}\nAssistant:"
            
            payload = {
                "inputs": prompt,
                "parameters": {
                    "max_length": 200,
                    "temperature": 0.7,
                    "do_sample": True,
                    "top_p": 0.9
                }
            }
            
            async with session.post(api_url, headers=headers, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    if result and len(result) > 0:
                        return result[0].get('generated_text', '').split('Assistant:')[-1].strip()
                else:
                    logger.warning(f"Hugging Face API error: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error with Hugging Face API: {str(e)}")
            return None
    
    async def chat_with_openai_free(self, message: str, context: str = "") -> str:
        """Use OpenAI API (if available) for chat"""
        try:
            # This would use OpenAI's API with context
            # For now, return None to fall back to other methods
            return None
        except Exception as e:
            logger.error(f"Error with OpenAI API: {str(e)}")
            return None
    
    async def get_ai_response(self, message: str, context: str = "") -> Optional[str]:
        """Get response from free AI provider"""
        
        # Try Hugging Face first
        if settings.HUGGINGFACE_API_KEY:
            response = await self.chat_with_huggingface(message, context)
            if response:
                return response
        
        # Try OpenAI if available
        if settings.OPENAI_API_KEY:
            response = await self.chat_with_openai_free(message, context)
            if response:
                return response
        
        # Fallback to local simple responses
        return self._get_fallback_response(message)
    
    def _get_fallback_response(self, message: str) -> str:
        """Simple fallback responses"""
        message_lower = message.lower()
        
        if any(word in message_lower for word in ['hello', 'hi', 'hey']):
            return "Hello! I'm here to help you with any questions you have. Feel free to ask me anything!"
        
        if any(word in message_lower for word in ['how are you', 'how do you do']):
            return "I'm doing well, thank you for asking! I'm here to help you with information and answer your questions."
        
        if any(word in message_lower for word in ['thank', 'thanks']):
            return "You're very welcome! I'm glad I could help. Feel free to ask if you have any other questions."
        
        if '?' in message:
            return "That's an interesting question! Let me try to help you with that. Could you provide a bit more context so I can give you a better answer?"
        
        return "I understand what you're saying. How can I help you with that? Feel free to ask me any questions you have."


class HybridAIService:
    """Main hybrid AI service combining free AI with Islamic knowledge"""
    
    def __init__(self):
        self.content_detector = IslamicContentDetector()
        self.free_ai = FreeAIProvider()
        self.knowledge_service = None
        self.ml_service = None
        self.is_initialized = False
    
    async def initialize(self):
        """Initialize the hybrid AI service"""
        try:
            # Initialize knowledge service
            self.knowledge_service = KnowledgeService()
            await self.knowledge_service.initialize()
            
            # Initialize ML service
            self.ml_service = MLService()
            await self.ml_service.initialize_models()
            
            self.is_initialized = True
            logger.info("Hybrid AI service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize hybrid AI service: {str(e)}")
            # Continue with limited functionality
            self.is_initialized = True
    
    async def get_response(self, message: str, session_context: Dict = None) -> Dict:
        """
        Get response using hybrid approach:
        1. Detect if question is Islamic
        2. Use appropriate AI system
        3. Combine responses if needed
        """
        try:
            # Detect if the question is Islamic
            is_islamic, confidence = self.content_detector.is_islamic_question(message)
            
            responses = []
            response_sources = []
            
            if is_islamic and confidence > 0.5:
                # High confidence Islamic question - prioritize Islamic knowledge
                islamic_response = await self._get_islamic_response(message)
                if islamic_response:
                    responses.append(islamic_response)
                    response_sources.append("Islamic Knowledge Base")
                
                # Also get AI perspective for natural conversation
                if confidence < 0.8:  # Only if not 100% Islamic
                    ai_context = "Please provide a helpful and respectful response about Islamic topics."
                    ai_response = await self.free_ai.get_ai_response(message, ai_context)
                    if ai_response and len(ai_response) > 20:
                        responses.append(ai_response)
                        response_sources.append("AI Assistant")
            
            elif is_islamic and confidence > 0.3:
                # Medium confidence - try both approaches
                ai_response = await self.free_ai.get_ai_response(message)
                islamic_response = await self._get_islamic_response(message)
                
                if islamic_response:
                    responses.append(islamic_response)
                    response_sources.append("Islamic Knowledge")
                
                if ai_response and len(ai_response) > 20:
                    responses.append(ai_response)
                    response_sources.append("AI Assistant")
            
            else:
                # Non-Islamic question - use free AI
                ai_response = await self.free_ai.get_ai_response(message)
                if ai_response:
                    responses.append(ai_response)
                    response_sources.append("AI Assistant")
                
                # Check if user might benefit from Islamic perspective
                if any(word in message.lower() for word in ['meaning', 'purpose', 'life', 'guidance', 'help']):
                    islamic_wisdom = self._get_islamic_wisdom_for_general_question(message)
                    if islamic_wisdom:
                        responses.append(islamic_wisdom)
                        response_sources.append("Islamic Wisdom")
            
            # Combine responses if multiple
            if len(responses) > 1:
                combined_response = self._combine_responses(responses, response_sources)
            elif len(responses) == 1:
                combined_response = responses[0]
            else:
                combined_response = "I'd be happy to help you with that! Could you tell me a bit more about what you're looking for?"
            
            return {
                "response": combined_response,
                "is_islamic": is_islamic,
                "confidence": confidence,
                "sources": response_sources,
                "response_type": "hybrid"
            }
            
        except Exception as e:
            logger.error(f"Error in hybrid AI response: {str(e)}")
            return {
                "response": "I apologize, but I'm having some technical difficulties. Please try asking your question again.",
                "is_islamic": False,
                "confidence": 0.0,
                "sources": ["Error Handler"],
                "response_type": "error"
            }
    
    async def _get_islamic_response(self, message: str) -> Optional[str]:
        """Get response from Islamic knowledge base"""
        try:
            if not self.knowledge_service:
                return self._get_basic_islamic_response(message)
            
            # Search the knowledge base
            search_results = await self.knowledge_service.search_knowledge_base(
                query=message,
                language="auto",
                use_ml=True,
                limit=3
            )
            
            if search_results.get("results"):
                best_result = search_results["results"][0]
                answer = best_result.get("answer", "")
                source = best_result.get("source_name", "Islamic Knowledge Base")
                
                # Format the response
                formatted_response = f"{answer}\n\n*Source: {source}*"
                return formatted_response
            else:
                return self._get_basic_islamic_response(message)
                
        except Exception as e:
            logger.error(f"Error getting Islamic response: {str(e)}")
            return self._get_basic_islamic_response(message)
    
    def _get_basic_islamic_response(self, message: str) -> str:
        """Basic Islamic responses when knowledge base is unavailable"""
        message_lower = message.lower()
        
        if any(word in message_lower for word in ['shahada', 'declaration', 'faith']):
            return 'The Shahada is: "La ilaha illa Allah, Muhammad rasul Allah" (There is no god but Allah, and Muhammad is His messenger). This is the first pillar of Islam and the declaration of faith.'
        
        if any(word in message_lower for word in ['prayer', 'salah', 'pray']):
            return 'Muslims pray 5 times daily: Fajr (dawn), Dhuhr (midday), Asr (afternoon), Maghrib (sunset), and Isha (night). Prayer involves physical and spiritual purification, facing Mecca, and reciting from the Quran.'
        
        if any(word in message_lower for word in ['pillar', 'pillars']):
            return 'The Five Pillars of Islam are: 1) Shahada (Declaration of Faith), 2) Salah (Prayer), 3) Zakat (Charity), 4) Sawm (Fasting in Ramadan), 5) Hajj (Pilgrimage to Mecca).'
        
        return 'I can help you with Islamic questions. Please feel free to ask about prayer, Quran, Islamic practices, or any other Islamic topic.'
    
    def _get_islamic_wisdom_for_general_question(self, message: str) -> Optional[str]:
        """Provide Islamic wisdom for general life questions"""
        message_lower = message.lower()
        
        if any(word in message_lower for word in ['sad', 'depressed', 'difficult', 'hard', 'struggle']):
            return 'In Islam, we believe that Allah does not burden a soul beyond what it can bear. "And it is He who created the heavens and earth in truth. And the day He says, \'Be,\' and it is, His word is the truth." (Quran 6:73). Remember to make Dua and trust in Allah\'s wisdom.'
        
        if any(word in message_lower for word in ['purpose', 'meaning', 'why']):
            return 'In Islam, our purpose is to worship Allah and be His stewards on Earth. "And I did not create the jinn and mankind except to worship Me." (Quran 51:56). This worship includes being kind to others, seeking knowledge, and doing good deeds.'
        
        return None
    
    def _combine_responses(self, responses: List[str], sources: List[str]) -> str:
        """Combine multiple responses into a coherent answer"""
        if len(responses) == 2:
            return f"{responses[0]}\n\n---\n\n**Alternative perspective:**\n{responses[1]}"
        
        combined = ""
        for i, (response, source) in enumerate(zip(responses, sources)):
            if i == 0:
                combined += response
            else:
                combined += f"\n\n**From {source}:**\n{response}"
        
        return combined
    
    async def close(self):
        """Clean up resources"""
        await self.free_ai.close()


# Global instance
hybrid_ai_service = HybridAIService()
