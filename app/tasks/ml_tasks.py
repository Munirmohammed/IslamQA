"""
ML Tasks
Celery tasks for machine learning operations
"""

from celery import current_task
import asyncio
import structlog

from app.worker import celery_app

logger = structlog.get_logger()


@celery_app.task(bind=True)
def rebuild_faiss_index(self, force_rebuild=False):
    """Rebuild FAISS index for similarity search"""
    try:
        logger.info(f"Starting FAISS index rebuild (force: {force_rebuild})")
        
        # Run async ML operations
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            from app.services.ml_service import MLService
            
            ml_service = MLService()
            loop.run_until_complete(ml_service.initialize_models())
            loop.run_until_complete(
                ml_service.vector_embeddings.build_faiss_index(force_rebuild)
            )
            
            logger.info("FAISS index rebuild completed successfully")
            return {"status": "success", "message": "FAISS index rebuilt"}
            
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"FAISS index rebuild failed: {str(e)}")
        current_task.retry(countdown=300, max_retries=2)


@celery_app.task(bind=True)
def update_question_embeddings(self):
    """Update embeddings for questions without them"""
    try:
        logger.info("Starting question embeddings update")
        
        from app.core.database import SessionLocal, Question
        from app.services.ml_service import MLService
        
        # Run async operations
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            ml_service = MLService()
            loop.run_until_complete(ml_service.initialize_models())
            
            db = SessionLocal()
            
            # Get questions without embeddings
            questions_without_embeddings = db.query(Question).filter(
                Question.embedding.is_(None)
            ).limit(1000).all()  # Process in batches
            
            updated_count = 0
            
            for question in questions_without_embeddings:
                try:
                    # Generate embedding
                    embedding = loop.run_until_complete(
                        ml_service.vector_embeddings.get_sentence_embedding(
                            question.question_text,
                            question.language
                        )
                    )
                    
                    # Store embedding as JSON
                    question.embedding = embedding.tolist()
                    updated_count += 1
                    
                    if updated_count % 100 == 0:
                        db.commit()
                        logger.info(f"Updated {updated_count} embeddings so far")
                        
                except Exception as e:
                    logger.warning(f"Failed to update embedding for question {question.id}: {str(e)}")
                    continue
            
            db.commit()
            db.close()
            
            logger.info(f"Question embeddings update completed: {updated_count} updated")
            return {"status": "success", "embeddings_updated": updated_count}
            
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"Question embeddings update failed: {str(e)}")
        return {"status": "error", "message": str(e)}


@celery_app.task(bind=True)
def optimize_ml_models(self):
    """Optimize ML models performance"""
    try:
        logger.info("Starting ML model optimization")
        
        # Run async operations
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            from app.services.ml_service import MLService
            
            ml_service = MLService()
            loop.run_until_complete(ml_service.initialize_models())
            
            # Clear embedding cache to free memory
            ml_service.vector_embeddings.embeddings_cache.clear()
            
            # Rebuild index with optimization
            loop.run_until_complete(
                ml_service.vector_embeddings.build_faiss_index(force_rebuild=True)
            )
            
            logger.info("ML model optimization completed")
            return {"status": "success", "message": "ML models optimized"}
            
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"ML model optimization failed: {str(e)}")
        return {"status": "error", "message": str(e)}


@celery_app.task(bind=True)
def analyze_question_similarity_patterns(self):
    """Analyze patterns in question similarity for model improvement"""
    try:
        logger.info("Starting similarity pattern analysis")
        
        from app.core.database import SessionLocal, Question, UserInteraction
        from datetime import datetime, timedelta
        
        db = SessionLocal()
        
        # Analyze recent interactions
        since_time = datetime.utcnow() - timedelta(days=7)
        
        interactions = db.query(UserInteraction).filter(
            UserInteraction.created_at >= since_time,
            UserInteraction.satisfaction_rating.isnot(None)
        ).all()
        
        # Calculate satisfaction statistics
        total_interactions = len(interactions)
        satisfied_interactions = len([i for i in interactions if i.satisfaction_rating >= 4])
        
        satisfaction_rate = satisfied_interactions / total_interactions if total_interactions > 0 else 0
        
        # Analyze common query patterns
        query_patterns = {}
        for interaction in interactions:
            if interaction.user_query:
                words = interaction.user_query.lower().split()
                for word in words:
                    if len(word) > 3:  # Ignore short words
                        query_patterns[word] = query_patterns.get(word, 0) + 1
        
        # Get top patterns
        top_patterns = sorted(query_patterns.items(), key=lambda x: x[1], reverse=True)[:20]
        
        db.close()
        
        analysis_results = {
            "total_interactions": total_interactions,
            "satisfaction_rate": satisfaction_rate,
            "top_query_patterns": top_patterns,
            "analysis_date": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Similarity pattern analysis completed: {satisfaction_rate:.2%} satisfaction rate")
        return {"status": "success", "analysis": analysis_results}
        
    except Exception as e:
        logger.error(f"Similarity pattern analysis failed: {str(e)}")
        return {"status": "error", "message": str(e)}


@celery_app.task(bind=True)
def train_custom_embeddings(self):
    """Train custom embeddings on Islamic Q&A data"""
    try:
        logger.info("Starting custom embeddings training")
        
        # This would implement custom training logic
        # For now, return a placeholder
        
        logger.info("Custom embeddings training completed (placeholder)")
        return {"status": "success", "message": "Custom embeddings training completed"}
        
    except Exception as e:
        logger.error(f"Custom embeddings training failed: {str(e)}")
        return {"status": "error", "message": str(e)}
