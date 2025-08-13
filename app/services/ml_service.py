"""
Machine Learning Service
Advanced ML-powered question matching and similarity algorithms
"""

import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer, AutoModel
import faiss
import pickle
import asyncio
from typing import List, Dict, Any, Optional, Tuple
import structlog
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem import SnowballStemmer
import re
import json
import hashlib
from datetime import datetime
import os

from app.core.config import settings
from app.core.database import SessionLocal, Question, Answer, CacheUtils
from app.core.monitoring import monitor_performance, MetricsCollector

logger = structlog.get_logger()

# Download required NLTK data
try:
    nltk.download('punkt', quiet=True)
    nltk.download('stopwords', quiet=True)
    nltk.download('wordnet', quiet=True)
except:
    pass


class TextPreprocessor:
    """Advanced text preprocessing for Arabic and English"""
    
    def __init__(self):
        self.english_stopwords = set(stopwords.words('english'))
        self.arabic_stopwords = {
            'في', 'من', 'إلى', 'على', 'عن', 'مع', 'هذا', 'هذه', 'ذلك', 'تلك',
            'التي', 'الذي', 'التي', 'اللذان', 'اللتان', 'اللذين', 'اللتين',
            'هو', 'هي', 'أن', 'إن', 'كان', 'كانت', 'لكن', 'لكن', 'أو', 'أم'
        }
        self.stemmer = SnowballStemmer('english')
    
    def clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        if not text:
            return ""
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Remove URLs
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
        
        # Remove email addresses
        text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '', text)
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove special characters but keep Arabic diacritics
        text = re.sub(r'[^\w\s\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]', ' ', text)
        
        return text.strip()
    
    def preprocess_text(self, text: str, language: str = 'auto') -> str:
        """Preprocess text for ML processing"""
        text = self.clean_text(text)
        
        if language == 'auto':
            language = self.detect_language(text)
        
        if language == 'ar':
            return self.preprocess_arabic(text)
        else:
            return self.preprocess_english(text)
    
    def detect_language(self, text: str) -> str:
        """Detect text language (Arabic or English)"""
        if not text:
            return 'en'
        
        arabic_chars = sum(1 for char in text if '\u0600' <= char <= '\u06FF')
        total_chars = len([char for char in text if char.isalpha()])
        
        if total_chars == 0:
            return 'en'
        
        arabic_ratio = arabic_chars / total_chars
        return 'ar' if arabic_ratio > 0.3 else 'en'
    
    def preprocess_english(self, text: str) -> str:
        """Preprocess English text"""
        # Convert to lowercase
        text = text.lower()
        
        # Tokenize
        tokens = word_tokenize(text)
        
        # Remove stopwords and short words
        tokens = [token for token in tokens if token not in self.english_stopwords and len(token) > 2]
        
        # Stem words
        tokens = [self.stemmer.stem(token) for token in tokens]
        
        return ' '.join(tokens)
    
    def preprocess_arabic(self, text: str) -> str:
        """Preprocess Arabic text"""
        # Remove diacritics
        text = re.sub(r'[\u064B-\u0652\u0670\u0640]', '', text)
        
        # Normalize Arabic characters
        text = text.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
        text = text.replace('ة', 'ه')
        text = text.replace('ى', 'ي')
        
        # Tokenize (simple split for Arabic)
        tokens = text.split()
        
        # Remove stopwords and short words
        tokens = [token for token in tokens if token not in self.arabic_stopwords and len(token) > 2]
        
        return ' '.join(tokens)


class VectorEmbeddings:
    """Handle vector embeddings for questions and answers"""
    
    def __init__(self):
        self.multilingual_model = None
        self.arabic_model = None
        self.tfidf_vectorizer = None
        self.faiss_index = None
        self.question_ids = []
        self.embeddings_cache = {}
    
    async def initialize_models(self):
        """Initialize ML models"""
        logger.info("Initializing ML models...")
        
        try:
            # Load multilingual sentence transformer
            self.multilingual_model = SentenceTransformer(
                settings.SENTENCE_TRANSFORMER_MODEL,
                device='cpu'  # Use CPU for better compatibility
            )
            
            # Initialize TF-IDF vectorizer
            self.tfidf_vectorizer = TfidfVectorizer(
                max_features=10000,
                ngram_range=(1, 3),
                stop_words='english'
            )
            
            logger.info("ML models initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing ML models: {str(e)}")
            raise
    
    @monitor_performance("ml_sentence_embedding")
    async def get_sentence_embedding(self, text: str, language: str = 'auto') -> np.ndarray:
        """Get sentence embedding using transformer model"""
        try:
            # Check cache first
            cache_key = f"embedding:{hashlib.md5(text.encode()).hexdigest()}"
            cached = CacheUtils.get(cache_key)
            if cached:
                MetricsCollector.record_cache_hit("embeddings")
                return np.frombuffer(cached, dtype=np.float32)
            
            MetricsCollector.record_cache_miss("embeddings")
            
            # Preprocess text
            preprocessor = TextPreprocessor()
            processed_text = preprocessor.preprocess_text(text, language)
            
            # Get embedding
            if self.multilingual_model:
                embedding = self.multilingual_model.encode([processed_text])[0]
            else:
                # Fallback to TF-IDF if transformer model fails
                embedding = self._get_tfidf_embedding(processed_text)
            
            # Cache the embedding
            if settings.ENABLE_CACHE:
                CacheUtils.set(cache_key, embedding.tobytes(), settings.CACHE_TTL)
            
            return embedding
            
        except Exception as e:
            logger.error(f"Error getting sentence embedding: {str(e)}")
            # Fallback to simple TF-IDF
            return self._get_tfidf_embedding(text)
    
    def _get_tfidf_embedding(self, text: str) -> np.ndarray:
        """Fallback TF-IDF embedding"""
        try:
            if self.tfidf_vectorizer:
                tfidf_matrix = self.tfidf_vectorizer.fit_transform([text])
                return tfidf_matrix.toarray()[0]
            else:
                # Simple word count vector as last resort
                words = text.split()
                return np.array([len(words), len(set(words))] + [0] * 298)  # 300-dim vector
        except:
            return np.zeros(300)  # Default embedding size
    
    async def build_faiss_index(self, force_rebuild: bool = False):
        """Build FAISS index for fast similarity search"""
        try:
            index_path = "data/faiss_index.bin"
            ids_path = "data/question_ids.pkl"
            
            # Check if index exists and is recent
            if not force_rebuild and os.path.exists(index_path) and os.path.exists(ids_path):
                try:
                    self.faiss_index = faiss.read_index(index_path)
                    with open(ids_path, 'rb') as f:
                        self.question_ids = pickle.load(f)
                    logger.info(f"Loaded existing FAISS index with {len(self.question_ids)} questions")
                    return
                except:
                    logger.warning("Failed to load existing index, rebuilding...")
            
            # Build new index
            logger.info("Building new FAISS index...")
            
            db = SessionLocal()
            try:
                questions = db.query(Question).all()
                
                if not questions:
                    logger.warning("No questions found in database")
                    return
                
                # Get embeddings for all questions
                embeddings = []
                question_ids = []
                
                for i, question in enumerate(questions):
                    if i % 100 == 0:
                        logger.info(f"Processing question {i+1}/{len(questions)}")
                    
                    embedding = await self.get_sentence_embedding(
                        question.question_text, 
                        question.language
                    )
                    embeddings.append(embedding)
                    question_ids.append(str(question.id))
                
                # Create FAISS index
                embeddings_matrix = np.array(embeddings).astype('float32')
                dimension = embeddings_matrix.shape[1]
                
                # Use IndexFlatIP for cosine similarity
                index = faiss.IndexFlatIP(dimension)
                
                # Normalize vectors for cosine similarity
                faiss.normalize_L2(embeddings_matrix)
                index.add(embeddings_matrix)
                
                self.faiss_index = index
                self.question_ids = question_ids
                
                # Save index
                os.makedirs("data", exist_ok=True)
                faiss.write_index(index, index_path)
                with open(ids_path, 'wb') as f:
                    pickle.dump(question_ids, f)
                
                logger.info(f"Built FAISS index with {len(questions)} questions")
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error building FAISS index: {str(e)}")
    
    @monitor_performance("ml_similarity_search")
    async def find_similar_questions(
        self, 
        query: str, 
        language: str = 'auto',
        top_k: int = 10,
        min_similarity: float = None
    ) -> List[Dict[str, Any]]:
        """Find similar questions using FAISS index"""
        try:
            min_similarity = min_similarity or settings.MIN_SIMILARITY_SCORE
            
            if not self.faiss_index or not self.question_ids:
                logger.warning("FAISS index not available, falling back to database search")
                return await self._fallback_similarity_search(query, language, top_k)
            
            # Get query embedding
            query_embedding = await self.get_sentence_embedding(query, language)
            query_vector = np.array([query_embedding]).astype('float32')
            faiss.normalize_L2(query_vector)
            
            # Search in FAISS index
            similarities, indices = self.faiss_index.search(query_vector, top_k * 2)  # Get more to filter
            
            # Get question details from database
            db = SessionLocal()
            try:
                results = []
                for i, (similarity, idx) in enumerate(zip(similarities[0], indices[0])):
                    if similarity < min_similarity:
                        continue
                    
                    if idx >= len(self.question_ids):
                        continue
                    
                    question_id = self.question_ids[idx]
                    question = db.query(Question).filter(Question.id == question_id).first()
                    
                    if question:
                        # Get best answer for this question
                        best_answer = db.query(Answer).filter(
                            Answer.question_id == question.id
                        ).order_by(Answer.confidence_score.desc()).first()
                        
                        result = {
                            'question_id': str(question.id),
                            'question': question.question_text,
                            'answer': best_answer.answer_text if best_answer else "No answer available",
                            'similarity_score': float(similarity),
                            'source_name': best_answer.source_name if best_answer else "Unknown",
                            'source_url': best_answer.source_url if best_answer else "",
                            'scholar_name': best_answer.scholar_name if best_answer else "",
                            'category': question.category,
                            'language': question.language,
                            'confidence_score': best_answer.confidence_score if best_answer else 0.0
                        }
                        results.append(result)
                        
                        if len(results) >= top_k:
                            break
                
                return results
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error in similarity search: {str(e)}")
            return await self._fallback_similarity_search(query, language, top_k)
    
    async def _fallback_similarity_search(
        self, 
        query: str, 
        language: str, 
        top_k: int
    ) -> List[Dict[str, Any]]:
        """Fallback similarity search using database full-text search"""
        try:
            db = SessionLocal()
            
            # Simple text matching fallback
            query_words = query.lower().split()
            
            questions = db.query(Question).filter(
                Question.language == language if language != 'auto' else True
            ).all()
            
            scored_questions = []
            for question in questions:
                # Simple word overlap scoring
                question_words = question.question_text.lower().split()
                overlap = len(set(query_words) & set(question_words))
                score = overlap / max(len(query_words), len(question_words))
                
                if score > 0.1:  # Minimum overlap threshold
                    scored_questions.append((question, score))
            
            # Sort by score and take top_k
            scored_questions.sort(key=lambda x: x[1], reverse=True)
            
            results = []
            for question, score in scored_questions[:top_k]:
                best_answer = db.query(Answer).filter(
                    Answer.question_id == question.id
                ).order_by(Answer.confidence_score.desc()).first()
                
                result = {
                    'question_id': str(question.id),
                    'question': question.question_text,
                    'answer': best_answer.answer_text if best_answer else "No answer available",
                    'similarity_score': score,
                    'source_name': best_answer.source_name if best_answer else "Unknown",
                    'source_url': best_answer.source_url if best_answer else "",
                    'scholar_name': best_answer.scholar_name if best_answer else "",
                    'category': question.category,
                    'language': question.language,
                    'confidence_score': best_answer.confidence_score if best_answer else 0.0
                }
                results.append(result)
            
            db.close()
            return results
            
        except Exception as e:
            logger.error(f"Error in fallback search: {str(e)}")
            return []


class MLService:
    """Main ML service class"""
    
    def __init__(self):
        self.vector_embeddings = VectorEmbeddings()
        self.text_preprocessor = TextPreprocessor()
        self.is_initialized = False
    
    async def initialize_models(self):
        """Initialize all ML models and services"""
        if self.is_initialized:
            return
        
        try:
            logger.info("Initializing ML Service...")
            
            await self.vector_embeddings.initialize_models()
            await self.vector_embeddings.build_faiss_index()
            
            self.is_initialized = True
            logger.info("ML Service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize ML Service: {str(e)}")
            raise
    
    async def process_question(
        self, 
        question: str, 
        language: str = 'auto',
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Process a question and find relevant answers"""
        try:
            # Detect language if auto
            if language == 'auto':
                language = self.text_preprocessor.detect_language(question)
            
            # Find similar questions
            similar_questions = await self.vector_embeddings.find_similar_questions(
                question, 
                language, 
                top_k=settings.MAX_RESULTS
            )
            
            # Apply context-aware filtering if context provided
            if context:
                similar_questions = self._apply_context_filtering(similar_questions, context)
            
            # Calculate confidence scores
            final_results = self._calculate_final_scores(question, similar_questions)
            
            # Record metrics
            MetricsCollector.record_question_asked(language, final_results[0]['category'] if final_results else 'unknown')
            
            return {
                'query': question,
                'language': language,
                'results': final_results,
                'total_found': len(final_results),
                'processing_time': 0  # Would be calculated in middleware
            }
            
        except Exception as e:
            logger.error(f"Error processing question: {str(e)}")
            return {
                'query': question,
                'language': language,
                'results': [],
                'total_found': 0,
                'error': str(e)
            }
    
    def _apply_context_filtering(
        self, 
        questions: List[Dict[str, Any]], 
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Apply context-aware filtering to results"""
        if not context:
            return questions
        
        filtered = []
        
        for q in questions:
            score_adjustment = 0
            
            # Category preference
            if context.get('preferred_category') and q.get('category'):
                if context['preferred_category'].lower() in q['category'].lower():
                    score_adjustment += 0.1
            
            # Scholar preference
            if context.get('preferred_scholar') and q.get('scholar_name'):
                if context['preferred_scholar'].lower() in q['scholar_name'].lower():
                    score_adjustment += 0.05
            
            # Language preference
            if context.get('language') and q.get('language'):
                if context['language'] == q['language']:
                    score_adjustment += 0.05
            
            # Update similarity score
            q['similarity_score'] += score_adjustment
            q['context_adjusted'] = True
            
            filtered.append(q)
        
        # Re-sort by adjusted scores
        filtered.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        return filtered
    
    def _calculate_final_scores(
        self, 
        query: str, 
        similar_questions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Calculate final confidence scores combining multiple factors"""
        for q in similar_questions:
            # Base similarity score
            base_score = q['similarity_score']
            
            # Source reliability factor
            source_factor = 1.0
            if 'islamqa' in q.get('source_name', '').lower():
                source_factor = 1.1
            elif 'dar al-ifta' in q.get('source_name', '').lower():
                source_factor = 1.15
            
            # Length similarity factor (prefer similar length answers)
            query_length = len(query.split())
            answer_length = len(q.get('answer', '').split())
            length_ratio = min(query_length, answer_length) / max(query_length, answer_length)
            length_factor = 0.8 + (0.4 * length_ratio)  # 0.8 to 1.2 range
            
            # Combine factors
            final_score = base_score * source_factor * length_factor
            
            q['final_score'] = final_score
            q['factors'] = {
                'base_similarity': base_score,
                'source_reliability': source_factor,
                'length_similarity': length_factor
            }
        
        # Sort by final score
        similar_questions.sort(key=lambda x: x['final_score'], reverse=True)
        
        return similar_questions
    
    async def get_question_suggestions(self, partial_query: str, language: str = 'auto') -> List[str]:
        """Get question suggestions for autocomplete"""
        try:
            if len(partial_query) < 3:
                return []
            
            db = SessionLocal()
            
            # Simple prefix matching for now
            # In production, you might want to use more sophisticated methods
            questions = db.query(Question).filter(
                Question.question_text.ilike(f"%{partial_query}%")
            ).limit(10).all()
            
            suggestions = [q.question_text for q in questions]
            db.close()
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Error getting suggestions: {str(e)}")
            return []
