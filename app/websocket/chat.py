"""
WebSocket Chat Implementation
Real-time chat functionality for Islamic Q&A
"""

import json
import uuid
from typing import Dict, List, Any, Optional
from datetime import datetime
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from sqlalchemy.orm import Session
import structlog

from app.core.database import get_db, User
from app.core.security import get_optional_user
from app.services.knowledge_service import KnowledgeService
from app.services.ml_service import MLService
from app.services.hybrid_ai_service import hybrid_ai_service
from app.core.monitoring import MetricsCollector

logger = structlog.get_logger()

websocket_router = APIRouter()


class ConnectionManager:
    """Manage WebSocket connections"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.user_sessions: Dict[str, str] = {}  # user_id -> session_id
        self.session_data: Dict[str, Dict[str, Any]] = {}  # session_id -> session info
    
    async def connect(self, websocket: WebSocket, session_id: str, user_id: Optional[str] = None):
        """Accept WebSocket connection"""
        await websocket.accept()
        self.active_connections[session_id] = websocket
        
        if user_id:
            self.user_sessions[user_id] = session_id
        
        # Initialize session data
        self.session_data[session_id] = {
            "user_id": user_id,
            "connected_at": datetime.utcnow(),
            "message_count": 0,
            "context": {},
            "language_preference": "auto"
        }
        
        logger.info(f"WebSocket connected: {session_id}, user: {user_id}")
    
    def disconnect(self, session_id: str):
        """Remove WebSocket connection"""
        if session_id in self.active_connections:
            del self.active_connections[session_id]
        
        # Clean up user session mapping
        user_id = self.session_data.get(session_id, {}).get("user_id")
        if user_id and user_id in self.user_sessions:
            del self.user_sessions[user_id]
        
        # Clean up session data
        if session_id in self.session_data:
            del self.session_data[session_id]
        
        logger.info(f"WebSocket disconnected: {session_id}")
    
    async def send_personal_message(self, message: dict, session_id: str):
        """Send message to specific session"""
        if session_id in self.active_connections:
            websocket = self.active_connections[session_id]
            try:
                await websocket.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Error sending message to {session_id}: {str(e)}")
                self.disconnect(session_id)
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connections"""
        disconnected_sessions = []
        
        for session_id, websocket in self.active_connections.items():
            try:
                await websocket.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Error broadcasting to {session_id}: {str(e)}")
                disconnected_sessions.append(session_id)
        
        # Clean up disconnected sessions
        for session_id in disconnected_sessions:
            self.disconnect(session_id)
    
    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session information"""
        return self.session_data.get(session_id)
    
    def update_session_context(self, session_id: str, context_update: Dict[str, Any]):
        """Update session context"""
        if session_id in self.session_data:
            self.session_data[session_id]["context"].update(context_update)
    
    def get_active_sessions_count(self) -> int:
        """Get number of active sessions"""
        return len(self.active_connections)


# Global connection manager
manager = ConnectionManager()


class ChatMessage:
    """Chat message structure"""
    
    def __init__(
        self,
        message_id: str,
        session_id: str,
        message_type: str,
        content: str,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.message_id = message_id
        self.session_id = session_id
        self.message_type = message_type  # "question", "answer", "typing", "error", "info"
        self.content = content
        self.user_id = user_id
        self.metadata = metadata or {}
        self.timestamp = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "message_id": self.message_id,
            "session_id": self.session_id,
            "message_type": self.message_type,
            "content": self.content,
            "user_id": self.user_id,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat()
        }


class ChatHandler:
    """Handle chat logic and responses"""
    
    def __init__(self):
        self.knowledge_service = None
        self.ml_service = None
        self.hybrid_ai = None
        self.response_cache = {}
    
    async def initialize(self):
        """Initialize services"""
        try:
            # Initialize hybrid AI service
            self.hybrid_ai = hybrid_ai_service
            await self.hybrid_ai.initialize()
            
            # Keep original services as backup
            if not self.knowledge_service:
                self.knowledge_service = KnowledgeService()
                await self.knowledge_service.initialize()
            
            if not self.ml_service:
                self.ml_service = MLService()
                await self.ml_service.initialize_models()
                
            logger.info("Chat handler with hybrid AI initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize chat services: {str(e)}")
            # Continue with fallback responses
    
    async def handle_question(
        self, 
        question: str, 
        session_id: str, 
        user_id: Optional[str] = None
    ) -> List[ChatMessage]:
        """Handle user question and generate response"""
        try:
            await self.initialize()
            
            # Use hybrid AI service if available
            if self.hybrid_ai:
                session_context = manager.get_session_info(session_id)
                
                # Get hybrid AI response
                ai_result = await self.hybrid_ai.get_response(
                    question, 
                    session_context=session_context
                )
                
                # Create response message
                response_message = ChatMessage(
                    message_id=str(uuid.uuid4()),
                    session_id=session_id,
                    message_type="answer",
                    content=ai_result["response"],
                    metadata={
                        "sources": ai_result["sources"],
                        "is_islamic": ai_result["is_islamic"],
                        "confidence": ai_result["confidence"],
                        "response_type": ai_result["response_type"]
                    }
                )
                
                responses = [response_message]
                
                # Add suggestions if it was an Islamic question
                if ai_result["is_islamic"] and ai_result["confidence"] > 0.5:
                    suggestions = self._get_islamic_suggestions(question)
                    if suggestions:
                        suggestions_message = ChatMessage(
                            message_id=str(uuid.uuid4()),
                            session_id=session_id,
                            message_type="suggestions",
                            content="You might also be interested in:",
                            metadata={"suggestions": suggestions}
                        )
                        responses.append(suggestions_message)
                
                return responses
            
            # Fallback to original system if hybrid AI fails
            elif not self.knowledge_service:
                # Enhanced fallback responses with Islamic knowledge
                fallback_content = self._get_enhanced_fallback_response(question)
                fallback_message = ChatMessage(
                    message_id=str(uuid.uuid4()),
                    session_id=session_id,
                    message_type="answer",
                    content=fallback_content,
                    metadata={"fallback_mode": True, "source": "Islamic Knowledge Base"}
                )
                return [fallback_message]
            
            # Get session context
            session_info = manager.get_session_info(session_id)
            context = session_info.get("context", {}) if session_info else {}
            language = session_info.get("language_preference", "auto") if session_info else "auto"
            
            # Check cache first
            cache_key = f"{question.lower().strip()}:{language}"
            if cache_key in self.response_cache:
                cached_response = self.response_cache[cache_key]
                logger.info(f"Cache hit for question: {question[:50]}...")
                MetricsCollector.record_cache_hit("chat_responses")
                
                return [ChatMessage(
                    message_id=str(uuid.uuid4()),
                    session_id=session_id,
                    message_type="answer",
                    content=cached_response["content"],
                    metadata=cached_response["metadata"]
                )]
            
            MetricsCollector.record_cache_miss("chat_responses")
            
            # Process question with knowledge service
            search_results = await self.knowledge_service.search_knowledge_base(
                query=question,
                language=language,
                filters=context,
                use_ml=True,
                limit=5
            )
            
            responses = []
            
            # Generate response based on results
            if search_results.get("results"):
                best_result = search_results["results"][0]
                
                # Main answer
                answer_content = self._format_answer(best_result, question)
                
                answer_message = ChatMessage(
                    message_id=str(uuid.uuid4()),
                    session_id=session_id,
                    message_type="answer",
                    content=answer_content,
                    metadata={
                        "confidence_score": best_result.get("similarity_score", 0),
                        "source": best_result.get("source_name", ""),
                        "scholar": best_result.get("scholar_name", ""),
                        "question_id": best_result.get("question_id", ""),
                        "language": best_result.get("language", language),
                        "search_results_count": len(search_results["results"])
                    }
                )
                responses.append(answer_message)
                
                # Add related suggestions if available
                if len(search_results["results"]) > 1:
                    suggestions = [
                        result.get("question", "")[:100] + "..."
                        for result in search_results["results"][1:4]
                    ]
                    
                    suggestions_message = ChatMessage(
                        message_id=str(uuid.uuid4()),
                        session_id=session_id,
                        message_type="suggestions",
                        content="You might also be interested in:",
                        metadata={"suggestions": suggestions}
                    )
                    responses.append(suggestions_message)
                
                # Cache the response
                self.response_cache[cache_key] = {
                    "content": answer_content,
                    "metadata": answer_message.metadata
                }
                
                # Update session context
                manager.update_session_context(session_id, {
                    "last_category": best_result.get("category"),
                    "last_language": best_result.get("language"),
                    "message_count": session_info.get("message_count", 0) + 1 if session_info else 1
                })
                
            else:
                # No results found
                no_answer_message = ChatMessage(
                    message_id=str(uuid.uuid4()),
                    session_id=session_id,
                    message_type="info",
                    content="I couldn't find a specific answer to your question in our knowledge base. Could you try rephrasing your question or being more specific?",
                    metadata={"no_results": True}
                )
                responses.append(no_answer_message)
                
                # Suggest similar questions
                suggestions = await self.ml_service.get_question_suggestions(question, language)
                if suggestions:
                    suggestions_message = ChatMessage(
                        message_id=str(uuid.uuid4()),
                        session_id=session_id,
                        message_type="suggestions",
                        content="Here are some similar questions you might ask:",
                        metadata={"suggestions": suggestions[:3]}
                    )
                    responses.append(suggestions_message)
            
            # Record interaction
            if self.knowledge_service:
                await self.knowledge_service.record_user_interaction(
                    session_id=session_id,
                    query=question,
                    results=search_results.get("results", [])
                )
            
            # Record metrics
            MetricsCollector.record_question_asked(
                language=language,
                category=search_results.get("results", [{}])[0].get("category", "general") if search_results.get("results") else "general"
            )
            
            return responses
            
        except Exception as e:
            logger.error(f"Error handling question: {str(e)}")
            
            error_message = ChatMessage(
                message_id=str(uuid.uuid4()),
                session_id=session_id,
                message_type="error",
                content="I'm sorry, I encountered an error while processing your question. Please try again.",
                metadata={"error": str(e)}
            )
            return [error_message]
    
    def _format_answer(self, result: Dict[str, Any], original_question: str) -> str:
        """Format the answer for chat response"""
        answer = result.get("answer", "")
        source = result.get("source_name", "")
        scholar = result.get("scholar_name", "")
        
        # Truncate long answers for chat
        if len(answer) > 800:
            answer = answer[:800] + "... [truncated]"
        
        formatted_answer = answer
        
        # Add source attribution
        if source or scholar:
            attribution = []
            if scholar:
                attribution.append(f"Scholar: {scholar}")
            if source:
                attribution.append(f"Source: {source}")
            
            formatted_answer += f"\n\n*{', '.join(attribution)}*"
        
        return formatted_answer
    
    def _get_enhanced_fallback_response(self, question: str) -> str:
        """Enhanced fallback responses with comprehensive Islamic knowledge"""
        question_lower = question.lower()
        
        # Comprehensive Islamic responses
        if any(word in question_lower for word in ['shahada', 'declaration', 'faith']):
            return """The Shahada is the Islamic declaration of faith and the first pillar of Islam:

**Arabic:** "Ash-hadu an la ilaha illa Allah, wa ash-hadu anna Muhammadan rasul Allah"
**English:** "I bear witness that there is no god but Allah, and I bear witness that Muhammad is the messenger of Allah"

To become Muslim, one must recite the Shahada with sincere belief. This declaration affirms the oneness of Allah and the prophethood of Muhammad (peace be upon him)."""

        if any(word in question_lower for word in ['prayer', 'salah', 'pray']):
            if 'how' in question_lower:
                return """To perform Islamic prayer (Salah):

**Preparation:**
1. Perform Wudu (ablution)
2. Face the Qibla (direction of Mecca)
3. Make intention (Niyyah)

**Prayer steps:**
1. Say "Allahu Akbar" (Takbir)
2. Recite Al-Fatiha and another Surah
3. Perform Ruku (bowing) saying "Subhana Rabbiyal Adheem"
4. Stand and say "Sami Allahu liman hamidah"
5. Perform Sujud (prostration) twice saying "Subhana Rabbiyal A'la"
6. Repeat for each Rakah
7. End with Tashahhud and Tasleem

Muslims pray 5 times daily: Fajr, Dhuhr, Asr, Maghrib, and Isha."""
            elif 'when' in question_lower:
                return """Muslims pray 5 times daily at these times:

1. **Fajr** - Before sunrise (dawn)
2. **Dhuhr** - After midday sun passes its zenith
3. **Asr** - Late afternoon
4. **Maghrib** - Just after sunset
5. **Isha** - After twilight (night)

Prayer times vary by location and season. Many mosques and Islamic apps provide local prayer times."""
            else:
                return """Prayer (Salah) is the second pillar of Islam and a direct connection with Allah. Muslims pray 5 times daily facing Mecca. Each prayer consists of units called Rakah, involving standing, bowing, and prostration while reciting verses from the Quran."""

        if any(word in question_lower for word in ['pillar', 'pillars']):
            return """The Five Pillars of Islam are the foundation of Muslim practice:

1. **Shahada** - Declaration of faith in Allah and Prophet Muhammad
2. **Salah** - Five daily prayers
3. **Zakat** - Obligatory charity (2.5% of wealth annually)
4. **Sawm** - Fasting during the month of Ramadan
5. **Hajj** - Pilgrimage to Mecca (once in lifetime if able)

These pillars unite Muslims worldwide in worship and community."""

        if any(word in question_lower for word in ['wudu', 'ablution']):
            return """Wudu (ablution) is ritual purification required before prayer:

**Steps:**
1. Say "Bismillah" (In the name of Allah)
2. Wash hands 3 times
3. Rinse mouth 3 times
4. Rinse nose 3 times
5. Wash face 3 times
6. Wash arms up to elbows 3 times (right then left)
7. Wipe head once
8. Wash feet up to ankles 3 times (right then left)

Wudu must be renewed after using bathroom, sleeping, or other invalidating acts."""

        if any(word in question_lower for word in ['zakat', 'charity']):
            return """Zakat is obligatory charity and the third pillar of Islam:

**Key points:**
- 2.5% of wealth given annually
- Only required from those above poverty threshold (Nisab)
- Purifies wealth and soul
- Helps poor, needy, and other categories mentioned in Quran
- Creates social justice and community solidarity

Zakat is different from voluntary charity (Sadaqah) which can be given anytime."""

        if any(word in question_lower for word in ['ramadan', 'fasting', 'sawm']):
            return """Ramadan is the holy month of fasting and the fourth pillar of Islam:

**Fasting rules:**
- Fast from dawn (Fajr) to sunset (Maghrib)
- No food, drink, or marital relations during daylight
- Exemptions for sick, traveling, pregnant, elderly
- Pre-dawn meal (Suhoor) and breaking fast (Iftar)

**Benefits:**
- Spiritual purification and self-control
- Empathy for the poor and hungry
- Increased prayer and Quran reading
- Community unity and charity"""

        if any(word in question_lower for word in ['hajj', 'pilgrimage']):
            return """Hajj is the pilgrimage to Mecca and the fifth pillar of Islam:

**Requirements:**
- Every Muslim must perform once in lifetime if physically and financially able
- Occurs during month of Dhul-Hijjah
- Involves specific rituals over several days

**Main rituals:**
- Tawaf (circling the Kaaba)
- Sa'i (walking between Safa and Marwah hills)
- Standing at Arafat
- Stoning the pillars at Mina
- Animal sacrifice

Hajj brings Muslims from all backgrounds together in worship."""

        if any(word in question_lower for word in ['quran', "qur'an"]):
            return """The Quran is the holy book of Islam and Allah's final revelation:

**Key facts:**
- Revealed to Prophet Muhammad (peace be upon him) through Angel Jibril (Gabriel)
- Contains 114 chapters (Surahs) and over 6,000 verses (Ayahs)
- Written in Arabic, but translated into many languages
- Primary source of Islamic guidance and law
- Memorized by millions of Muslims (Huffaz)

The Quran covers theology, morality, guidance for personal conduct, law, and stories of earlier prophets."""

        if any(word in question_lower for word in ['muhammad', 'prophet']):
            return """Prophet Muhammad (peace be upon him) is the final messenger of Allah:

**Life highlights:**
- Born in Mecca in 570 CE
- Received first revelation at age 40 in cave of Hira
- Preached Islam for 23 years
- Migrated to Medina (Hijra) in 622 CE
- Died in 632 CE in Medina

**Significance:**
- Final prophet in chain including Adam, Noah, Abraham, Moses, Jesus
- Perfect example (Uswah Hasanah) for Muslims to follow
- His sayings and actions (Hadith and Sunnah) guide Islamic practice"""

        if any(word in question_lower for word in ['allah', 'god']):
            return """Allah is the Arabic name for God, used by Muslims and Arabic-speaking Christians:

**Key beliefs about Allah:**
- One and unique (Tawhid) - no partners or children
- Creator and sustainer of all existence
- All-knowing, all-powerful, all-merciful
- Has 99 Beautiful Names (Asma ul-Husna) describing His attributes
- Beyond human comprehension but close to those who worship Him

**Famous verse:** "Say: He is Allah, the One! Allah, the Eternal, Absolute; He begets not, nor is He begotten; And there is none like unto Him." (Quran 112:1-4)"""

        # Handle greetings
        if any(word in question_lower for word in ['hi', 'hello', 'salaam', 'salam']):
            return """Assalamu Alaikum wa Rahmatullahi wa Barakatuh! 
(Peace and blessings of Allah be upon you)

Welcome to Islamic Q&A! I'm here to help answer your questions about:
- The Five Pillars of Islam
- Prayer, Quran, and Islamic practices  
- Prophet Muhammad (peace be upon him)
- Islamic beliefs and values
- Daily Islamic life

What would you like to learn about Islam today?"""

        # Default comprehensive response
        return f"""Thank you for your question about "{question}". While I'm currently in simplified mode, I can provide guidance on Islamic topics.

**Common topics I can help with:**
- Five Pillars: Shahada, Prayer, Zakat, Fasting, Hajj
- Quran and Prophet Muhammad (peace be upon him)
- Islamic practices: Wudu, Dhikr, Dua
- Islamic beliefs and values

Please feel free to ask about any Islamic topic, and I'll do my best to provide authentic guidance based on Quran and Sunnah."""

    def _get_islamic_suggestions(self, question: str) -> List[str]:
        """Get related Islamic questions based on the current question"""
        question_lower = question.lower()
        
        suggestions = []
        
        if any(word in question_lower for word in ['prayer', 'salah']):
            suggestions = [
                "How to perform Wudu (ablution)?",
                "What are the prayer times?",
                "What to recite in prayer?",
                "How many Rakah in each prayer?"
            ]
        elif any(word in question_lower for word in ['shahada', 'faith']):
            suggestions = [
                "What are the Five Pillars of Islam?",
                "How to convert to Islam?",
                "What do Muslims believe?",
                "Who is Prophet Muhammad?"
            ]
        elif any(word in question_lower for word in ['ramadan', 'fasting']):
            suggestions = [
                "When is Ramadan?",
                "Who must fast in Ramadan?",
                "What breaks the fast?",
                "What is Suhoor and Iftar?"
            ]
        elif any(word in question_lower for word in ['hajj', 'pilgrimage']):
            suggestions = [
                "What are the steps of Hajj?",
                "When is Hajj performed?",
                "What is the difference between Hajj and Umrah?",
                "What is Tawaf?"
            ]
        elif any(word in question_lower for word in ['zakat', 'charity']):
            suggestions = [
                "How much Zakat to give?",
                "Who should receive Zakat?",
                "What is the difference between Zakat and Sadaqah?",
                "When to pay Zakat?"
            ]
        else:
            # General Islamic suggestions
            suggestions = [
                "What are the Five Pillars of Islam?",
                "How to pray in Islam?",
                "What is the meaning of Quran?",
                "Who is Prophet Muhammad?"
            ]
        
        return suggestions[:3]  # Return top 3 suggestions
    
    async def handle_typing_indicator(self, session_id: str, is_typing: bool):
        """Handle typing indicator"""
        typing_message = ChatMessage(
            message_id=str(uuid.uuid4()),
            session_id=session_id,
            message_type="typing",
            content="",
            metadata={"is_typing": is_typing}
        )
        
        await manager.send_personal_message(typing_message.to_dict(), session_id)
    
    async def handle_feedback(self, session_id: str, feedback: Dict[str, Any]):
        """Handle user feedback"""
        try:
            if self.knowledge_service:
                await self.knowledge_service.record_user_interaction(
                    session_id=session_id,
                    query="",
                    results=[],
                    feedback=feedback
                )
            
            feedback_message = ChatMessage(
                message_id=str(uuid.uuid4()),
                session_id=session_id,
                message_type="info",
                content="Thank you for your feedback!",
                metadata={"feedback_received": True}
            )
            
            return [feedback_message]
            
        except Exception as e:
            logger.error(f"Error handling feedback: {str(e)}")
            return []


# Global chat handler
chat_handler = ChatHandler()


@websocket_router.websocket("/chat")
async def websocket_chat(
    websocket: WebSocket,
    token: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """WebSocket endpoint for real-time chat"""
    session_id = str(uuid.uuid4())
    user_id = None
    
    try:
        # Authenticate user if token provided
        if token:
            try:
                from app.core.security import TokenManager, AuthService
                payload = TokenManager.verify_token(token)
                if payload:
                    auth_service = AuthService(db)
                    user = auth_service.get_user_by_token(token)
                    if user:
                        user_id = str(user.id)
            except Exception as e:
                logger.warning(f"Token authentication failed: {str(e)}")
        
        # Connect to manager
        await manager.connect(websocket, session_id, user_id)
        
        # Send welcome message
        welcome_message = ChatMessage(
            message_id=str(uuid.uuid4()),
            session_id=session_id,
            message_type="info",
            content="Welcome! I'm here to help answer your Islamic questions. Feel free to ask me anything.",
            metadata={"welcome": True, "session_id": session_id}
        )
        
        await manager.send_personal_message(welcome_message.to_dict(), session_id)
        
        # Handle messages
        while True:
            try:
                # Receive message
                data = await websocket.receive_text()
                logger.info(f"Received raw message: {data}")
                message_data = json.loads(data)
                logger.info(f"Parsed message data: {message_data}")
                
                message_type = message_data.get("type", "question")
                content = message_data.get("content", "")
                
                if message_type == "question" and content.strip():
                    # Handle question
                    responses = await chat_handler.handle_question(
                        content, session_id, user_id
                    )
                    
                    # Send responses
                    for response in responses:
                        await manager.send_personal_message(response.to_dict(), session_id)
                
                elif message_type == "typing":
                    # Handle typing indicator
                    is_typing = message_data.get("is_typing", False)
                    await chat_handler.handle_typing_indicator(session_id, is_typing)
                
                elif message_type == "feedback":
                    # Handle feedback
                    feedback = message_data.get("feedback", {})
                    responses = await chat_handler.handle_feedback(session_id, feedback)
                    
                    for response in responses:
                        await manager.send_personal_message(response.to_dict(), session_id)
                
                elif message_type == "ping":
                    # Handle ping/keepalive
                    pong_message = ChatMessage(
                        message_id=str(uuid.uuid4()),
                        session_id=session_id,
                        message_type="pong",
                        content="",
                        metadata={"timestamp": datetime.utcnow().isoformat()}
                    )
                    await manager.send_personal_message(pong_message.to_dict(), session_id)
                
            except json.JSONDecodeError:
                error_message = ChatMessage(
                    message_id=str(uuid.uuid4()),
                    session_id=session_id,
                    message_type="error",
                    content="Invalid message format. Please send valid JSON.",
                    metadata={"error_type": "json_decode_error"}
                )
                await manager.send_personal_message(error_message.to_dict(), session_id)
            
            except WebSocketDisconnect:
                # Client disconnected during message processing
                logger.info(f"Client disconnected during message processing: {session_id}")
                break
                
            except Exception as e:
                # Check if it's a disconnect-related error
                error_msg = str(e).lower()
                if any(keyword in error_msg for keyword in ["disconnect", "receive", "connection", "closed"]):
                    logger.info(f"Connection disconnected: {session_id}, error: {str(e)}")
                    break
                
                logger.error(f"Error processing message: {str(e)}")
                
                # Try to send error message, but break if it fails (connection likely dead)
                try:
                    error_message = ChatMessage(
                        message_id=str(uuid.uuid4()),
                        session_id=session_id,
                        message_type="error",
                        content="An error occurred while processing your message.",
                        metadata={"error": str(e)}
                    )
                    await manager.send_personal_message(error_message.to_dict(), session_id)
                except Exception:
                    # If we can't send the error message, connection is likely dead
                    logger.info(f"Failed to send error message, connection likely dead: {session_id}")
                    break
    
    except WebSocketDisconnect:
        manager.disconnect(session_id)
        logger.info(f"WebSocket disconnected: {session_id}")
    
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        manager.disconnect(session_id)


@websocket_router.get("/chat/stats")
async def get_chat_stats():
    """Get chat statistics"""
    return {
        "active_sessions": manager.get_active_sessions_count(),
        "total_sessions_today": len(manager.session_data),  # Simplified
        "uptime": "N/A"  # Would track actual uptime
    }
