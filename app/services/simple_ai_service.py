"""
Simple AI Service
Free AI-powered conversational responses using Hugging Face Inference API
"""

import requests
import asyncio
import json
from typing import Dict, Any, Optional, List
import structlog
from datetime import datetime

from app.core.config import settings

logger = structlog.get_logger()


class SimpleAIService:
    """Simple AI service using free APIs for conversational responses"""
    
    def __init__(self):
        self.hf_api_url = "https://api-inference.huggingface.co/models/microsoft/DialoGPT-medium"
        self.backup_api_url = "https://api-inference.huggingface.co/models/facebook/blenderbot-400M-distill"
        self.islamic_context = """You are an Islamic Q&A assistant. You provide helpful, respectful, and accurate responses about Islamic topics. 
        Always be respectful of Islamic principles and teachings. If you're unsure about a religious ruling, suggest consulting with a qualified Islamic scholar.
        Keep responses conversational and helpful."""
    
    async def get_ai_response(
        self, 
        question: str, 
        language: str = "en",
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get AI response to a question"""
        try:
            # Prepare the conversation context
            full_context = self.islamic_context
            if context:
                full_context += f"\n\nPrevious context: {context}"
            
            # Try primary AI service (Hugging Face)
            response = await self._get_huggingface_response(question, full_context, language)
            
            if response:
                return {
                    "answer": response,
                    "source": "AI Assistant",
                    "confidence": 0.8,
                    "language": language,
                    "timestamp": datetime.utcnow().isoformat(),
                    "service": "huggingface"
                }
            
            # Fallback to backup service
            backup_response = await self._get_backup_response(question, language)
            
            if backup_response:
                return {
                    "answer": backup_response,
                    "source": "AI Assistant",
                    "confidence": 0.7,
                    "language": language,
                    "timestamp": datetime.utcnow().isoformat(),
                    "service": "backup"
                }
            
            # Final fallback - simple template response
            return self._get_fallback_response(question, language)
            
        except Exception as e:
            logger.error(f"Error getting AI response: {str(e)}")
            return self._get_fallback_response(question, language)
    
    async def _get_huggingface_response(
        self, 
        question: str, 
        context: str, 
        language: str
    ) -> Optional[str]:
        """Get response from Hugging Face Inference API"""
        try:
            headers = {
                "Authorization": f"Bearer {settings.HUGGINGFACE_API_KEY}" if settings.HUGGINGFACE_API_KEY else "",
                "Content-Type": "application/json"
            }
            
            # If no API key, use the free inference endpoint (with rate limits)
            if not settings.HUGGINGFACE_API_KEY:
                headers.pop("Authorization", None)
            
            # Prepare conversation input
            conversation_input = f"{context}\n\nHuman: {question}\nAssistant:"
            
            payload = {
                "inputs": conversation_input,
                "parameters": {
                    "max_length": 200,
                    "temperature": 0.7,
                    "do_sample": True,
                    "top_p": 0.9
                }
            }
            
            # Make async request
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: requests.post(
                    self.hf_api_url,
                    headers=headers,
                    json=payload,
                    timeout=10
                )
            )
            
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, list) and len(result) > 0:
                    generated_text = result[0].get("generated_text", "")
                    # Extract only the assistant's response
                    if "Assistant:" in generated_text:
                        ai_response = generated_text.split("Assistant:")[-1].strip()
                        return self._clean_response(ai_response)
                elif isinstance(result, dict) and "generated_text" in result:
                    ai_response = result["generated_text"].replace(conversation_input, "").strip()
                    return self._clean_response(ai_response)
            
            logger.warning(f"HuggingFace API returned status {response.status_code}")
            return None
            
        except Exception as e:
            logger.error(f"Error with HuggingFace API: {str(e)}")
            return None
    
    async def _get_backup_response(self, question: str, language: str) -> Optional[str]:
        """Backup AI service using another free model"""
        try:
            headers = {"Content-Type": "application/json"}
            
            payload = {
                "inputs": question,
                "parameters": {
                    "max_length": 150,
                    "temperature": 0.7
                }
            }
            
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: requests.post(
                    self.backup_api_url,
                    headers=headers,
                    json=payload,
                    timeout=8
                )
            )
            
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, list) and len(result) > 0:
                    return self._clean_response(result[0].get("generated_text", ""))
                elif isinstance(result, dict):
                    return self._clean_response(result.get("generated_text", ""))
            
            return None
            
        except Exception as e:
            logger.error(f"Error with backup AI service: {str(e)}")
            return None
    
    def _clean_response(self, response: str) -> str:
        """Clean and format AI response"""
        if not response:
            return ""
        
        # Remove common AI artifacts
        response = response.replace("Human:", "").replace("Assistant:", "")
        response = response.replace("AI:", "").replace("Bot:", "")
        
        # Remove excessive newlines
        response = response.strip()
        lines = [line.strip() for line in response.split('\n') if line.strip()]
        response = '\n'.join(lines)
        
        # Ensure response doesn't exceed reasonable length
        if len(response) > 500:
            response = response[:500] + "..."
        
        return response
    
    def _get_fallback_response(self, question: str, language: str) -> Dict[str, Any]:
        """Fallback response when AI services fail"""
        
        # Simple keyword-based responses for common Islamic topics
        question_lower = question.lower()
        
        fallback_responses = {
            "en": {
                "prayer": "Prayer (Salah) is one of the Five Pillars of Islam. Muslims pray five times a day facing the Qibla. I understand what you're saying. How can I help you with that? Feel free to ask me any questions you have.",
                "shahada": "The Shahada is the Islamic declaration of faith: 'There is no god but Allah, and Muhammad is His messenger.' I understand what you're saying. How can I help you with that? Feel free to ask me any questions you have.",
                "zakat": "Zakat is the obligatory charitable giving in Islam, one of the Five Pillars. It helps purify wealth and support those in need. I understand what you're saying. How can I help you with that? Feel free to ask me any questions you have.",
                "hajj": "Hajj is the pilgrimage to Mecca, one of the Five Pillars of Islam, required once in a lifetime for those who are able. I understand what you're saying. How can I help you with that? Feel free to ask me any questions you have.",
                "fasting": "Fasting during Ramadan (Sawm) is one of the Five Pillars of Islam. Muslims fast from dawn to sunset. I understand what you're saying. How can I help you with that? Feel free to ask me any questions you have.",
                "default": "I understand what you're saying. How can I help you with that? Feel free to ask me any questions you have."
            },
            "ar": {
                "default": "أفهم ما تقوله. كيف يمكنني مساعدتك في ذلك؟ لا تتردد في طرح أي أسئلة لديك."
            }
        }
        
        # Find appropriate response
        response_lang = language if language in fallback_responses else "en"
        responses = fallback_responses[response_lang]
        
        response_text = responses.get("default")
        
        # Check for specific topics
        for topic, topic_response in responses.items():
            if topic in question_lower:
                response_text = topic_response
                break
        
        return {
            "answer": response_text,
            "source": "AI Assistant (Fallback)",
            "confidence": 0.5,
            "language": language,
            "timestamp": datetime.utcnow().isoformat(),
            "service": "fallback"
        }
    
    async def get_conversation_response(
        self, 
        messages: List[Dict[str, str]], 
        language: str = "en"
    ) -> Dict[str, Any]:
        """Get response for a conversation with message history"""
        try:
            # Build conversation context from messages
            context_parts = []
            for msg in messages[-5:]:  # Use last 5 messages for context
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    context_parts.append(f"Human: {content}")
                elif role == "assistant":
                    context_parts.append(f"Assistant: {content}")
            
            # Get the latest user message
            latest_message = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    latest_message = msg.get("content", "")
                    break
            
            # Build full context
            conversation_context = "\n".join(context_parts[:-1])  # Exclude the latest message from context
            
            return await self.get_ai_response(latest_message, language, conversation_context)
            
        except Exception as e:
            logger.error(f"Error in conversation response: {str(e)}")
            return self._get_fallback_response(latest_message or "Hello", language)
    
    def is_available(self) -> bool:
        """Check if AI service is available"""
        try:
            # Simple health check
            response = requests.get("https://api-inference.huggingface.co/", timeout=5)
            return response.status_code in [200, 404]  # 404 is expected for root endpoint
        except:
            return False


# Global instance
simple_ai_service = SimpleAIService()
