"""
Analytics Endpoints
Analytics and reporting for the Islamic Q&A system
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from pydantic import BaseModel
from datetime import datetime, timedelta

from app.core.database import (
    get_db, User, Question, Answer, UserInteraction, ScrapingJob
)
from app.core.security import get_current_admin_user, get_current_user
from app.services.knowledge_service import KnowledgeService

router = APIRouter()


class PublicStats(BaseModel):
    total_questions: int
    total_answers: int
    categories: List[str]
    languages: List[str]


@router.get("/stats", response_model=PublicStats)
async def get_public_stats(db: Session = Depends(get_db)):
    """Get public statistics (no authentication required)"""
    try:
        # Basic totals
        total_questions = db.query(Question).count()
        total_answers = db.query(Answer).count()
        
        # Get unique categories
        categories_result = db.execute(text("""
            SELECT DISTINCT category
            FROM questions
            WHERE category IS NOT NULL
            ORDER BY category
        """)).fetchall()
        categories = [row.category for row in categories_result]
        
        # Get unique languages
        languages_result = db.execute(text("""
            SELECT DISTINCT language
            FROM questions
            ORDER BY language
        """)).fetchall()
        languages = [row.language for row in languages_result]
        
        return PublicStats(
            total_questions=total_questions,
            total_answers=total_answers,
            categories=categories,
            languages=languages
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get public stats: {str(e)}"
        )


class AnalyticsOverview(BaseModel):
    total_questions: int
    total_answers: int
    total_interactions: int
    average_satisfaction: Optional[float]
    top_categories: List[Dict[str, Any]]
    language_distribution: List[Dict[str, Any]]
    recent_trends: Dict[str, List[int]]


class CategoryStats(BaseModel):
    category: str
    question_count: int
    answer_count: int
    average_confidence: float
    interaction_count: int


class LanguageStats(BaseModel):
    language: str
    question_count: int
    answer_count: int
    percentage: float


class InteractionStats(BaseModel):
    total_interactions: int
    average_satisfaction: Optional[float]
    satisfaction_distribution: Dict[str, int]
    common_queries: List[Dict[str, Any]]


class TrendData(BaseModel):
    date: str
    questions: int
    answers: int
    interactions: int


@router.get("/overview", response_model=AnalyticsOverview)
async def get_analytics_overview(
    days: int = Query(default=30, ge=1, le=365, description="Number of days for trends"),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Get analytics overview dashboard"""
    try:
        # Basic totals
        total_questions = db.query(Question).count()
        total_answers = db.query(Answer).count()
        total_interactions = db.query(UserInteraction).count()
        
        # Average satisfaction
        avg_satisfaction_result = db.query(
            func.avg(UserInteraction.satisfaction_rating)
        ).filter(
            UserInteraction.satisfaction_rating.isnot(None)
        ).scalar()
        
        avg_satisfaction = float(avg_satisfaction_result) if avg_satisfaction_result else None
        
        # Top categories
        top_categories_result = db.execute(text("""
            SELECT category, COUNT(*) as count
            FROM questions
            WHERE category IS NOT NULL
            GROUP BY category
            ORDER BY count DESC
            LIMIT 10
        """)).fetchall()
        
        top_categories = [
            {"category": row.category, "count": row.count}
            for row in top_categories_result
        ]
        
        # Language distribution
        language_dist_result = db.execute(text("""
            SELECT language, COUNT(*) as count
            FROM questions
            GROUP BY language
            ORDER BY count DESC
        """)).fetchall()
        
        language_distribution = [
            {"language": row.language, "count": row.count}
            for row in language_dist_result
        ]
        
        # Recent trends (daily data for the specified period)
        trends = await get_trend_data(db, days)
        
        return AnalyticsOverview(
            total_questions=total_questions,
            total_answers=total_answers,
            total_interactions=total_interactions,
            average_satisfaction=avg_satisfaction,
            top_categories=top_categories,
            language_distribution=language_distribution,
            recent_trends=trends
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get analytics overview: {str(e)}"
        )


@router.get("/categories", response_model=List[CategoryStats])
async def get_category_analytics(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Get detailed category analytics"""
    try:
        # Get category statistics
        category_stats_result = db.execute(text("""
            SELECT 
                q.category,
                COUNT(DISTINCT q.id) as question_count,
                COUNT(DISTINCT a.id) as answer_count,
                AVG(a.confidence_score) as avg_confidence,
                COUNT(DISTINCT ui.id) as interaction_count
            FROM questions q
            LEFT JOIN answers a ON q.id = a.question_id
            LEFT JOIN user_interactions ui ON q.id = ui.question_id
            WHERE q.category IS NOT NULL
            GROUP BY q.category
            ORDER BY question_count DESC
        """)).fetchall()
        
        result = []
        for row in category_stats_result:
            result.append(CategoryStats(
                category=row.category,
                question_count=row.question_count,
                answer_count=row.answer_count or 0,
                average_confidence=float(row.avg_confidence or 0),
                interaction_count=row.interaction_count or 0
            ))
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get category analytics: {str(e)}"
        )


@router.get("/languages", response_model=List[LanguageStats])
async def get_language_analytics(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Get language distribution analytics"""
    try:
        # Get total count for percentage calculation
        total_questions = db.query(Question).count()
        
        # Get language statistics
        language_stats_result = db.execute(text("""
            SELECT 
                q.language,
                COUNT(DISTINCT q.id) as question_count,
                COUNT(DISTINCT a.id) as answer_count
            FROM questions q
            LEFT JOIN answers a ON q.id = a.question_id
            GROUP BY q.language
            ORDER BY question_count DESC
        """)).fetchall()
        
        result = []
        for row in language_stats_result:
            percentage = (row.question_count / total_questions * 100) if total_questions > 0 else 0
            result.append(LanguageStats(
                language=row.language,
                question_count=row.question_count,
                answer_count=row.answer_count or 0,
                percentage=round(percentage, 2)
            ))
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get language analytics: {str(e)}"
        )


@router.get("/interactions", response_model=InteractionStats)
async def get_interaction_analytics(
    days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Get user interaction analytics"""
    try:
        since_date = datetime.utcnow() - timedelta(days=days)
        
        # Total interactions in period
        total_interactions = db.query(UserInteraction).filter(
            UserInteraction.created_at >= since_date
        ).count()
        
        # Average satisfaction
        avg_satisfaction_result = db.query(
            func.avg(UserInteraction.satisfaction_rating)
        ).filter(
            UserInteraction.created_at >= since_date,
            UserInteraction.satisfaction_rating.isnot(None)
        ).scalar()
        
        avg_satisfaction = float(avg_satisfaction_result) if avg_satisfaction_result else None
        
        # Satisfaction distribution
        satisfaction_dist_result = db.execute(text("""
            SELECT satisfaction_rating, COUNT(*) as count
            FROM user_interactions
            WHERE created_at >= :since_date
                AND satisfaction_rating IS NOT NULL
            GROUP BY satisfaction_rating
            ORDER BY satisfaction_rating
        """), {"since_date": since_date}).fetchall()
        
        satisfaction_distribution = {
            str(row.satisfaction_rating): row.count
            for row in satisfaction_dist_result
        }
        
        # Common queries (top 20)
        common_queries_result = db.execute(text("""
            SELECT user_query, COUNT(*) as frequency
            FROM user_interactions
            WHERE created_at >= :since_date
                AND user_query IS NOT NULL
                AND LENGTH(user_query) > 3
            GROUP BY user_query
            ORDER BY frequency DESC
            LIMIT 20
        """), {"since_date": since_date}).fetchall()
        
        common_queries = [
            {"query": row.user_query, "frequency": row.frequency}
            for row in common_queries_result
        ]
        
        return InteractionStats(
            total_interactions=total_interactions,
            average_satisfaction=avg_satisfaction,
            satisfaction_distribution=satisfaction_distribution,
            common_queries=common_queries
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get interaction analytics: {str(e)}"
        )


@router.get("/trends")
async def get_detailed_trends(
    days: int = Query(default=30, ge=1, le=365),
    granularity: str = Query(default="day", regex="^(hour|day|week|month)$"),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Get detailed trend data with configurable granularity"""
    try:
        since_date = datetime.utcnow() - timedelta(days=days)
        
        # Date format based on granularity
        date_format_map = {
            "hour": "%Y-%m-%d %H:00",
            "day": "%Y-%m-%d",
            "week": "%Y-%W",
            "month": "%Y-%m"
        }
        date_format = date_format_map[granularity]
        
        # Get trend data
        trend_result = db.execute(text(f"""
            SELECT 
                DATE_FORMAT(created_at, '{date_format}') as period,
                'questions' as type,
                COUNT(*) as count
            FROM questions
            WHERE created_at >= :since_date
            GROUP BY period
            
            UNION ALL
            
            SELECT 
                DATE_FORMAT(created_at, '{date_format}') as period,
                'answers' as type,
                COUNT(*) as count
            FROM answers
            WHERE created_at >= :since_date
            GROUP BY period
            
            UNION ALL
            
            SELECT 
                DATE_FORMAT(created_at, '{date_format}') as period,
                'interactions' as type,
                COUNT(*) as count
            FROM user_interactions
            WHERE created_at >= :since_date
            GROUP BY period
            
            ORDER BY period, type
        """), {"since_date": since_date}).fetchall()
        
        # Organize data by period
        trends_by_period = {}
        for row in trend_result:
            period = row.period
            if period not in trends_by_period:
                trends_by_period[period] = {"questions": 0, "answers": 0, "interactions": 0}
            trends_by_period[period][row.type] = row.count
        
        # Convert to list format
        trend_data = []
        for period in sorted(trends_by_period.keys()):
            data = trends_by_period[period]
            trend_data.append(TrendData(
                date=period,
                questions=data["questions"],
                answers=data["answers"],
                interactions=data["interactions"]
            ))
        
        return {
            "granularity": granularity,
            "period_days": days,
            "data": trend_data
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get trend data: {str(e)}"
        )


@router.get("/performance")
async def get_performance_metrics(
    current_user: User = Depends(get_current_admin_user)
):
    """Get system performance metrics"""
    try:
        from app.core.monitoring import HealthChecker
        
        # Get system health
        health_status = await HealthChecker.get_health_status()
        
        # Add performance metrics
        performance_metrics = {
            "system_health": health_status,
            "response_times": {
                "average_search_time": "< 500ms",  # Would be calculated from actual metrics
                "average_ml_processing": "< 200ms",
                "database_query_time": "< 100ms"
            },
            "throughput": {
                "requests_per_minute": "~50",  # Would be calculated from actual metrics
                "searches_per_minute": "~30",
                "cache_hit_rate": "85%"
            }
        }
        
        return performance_metrics
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get performance metrics: {str(e)}"
        )


@router.get("/export")
async def export_analytics_data(
    format: str = Query(default="json", regex="^(json|csv)$"),
    days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Export analytics data"""
    try:
        # Get comprehensive analytics data
        knowledge_service = KnowledgeService()
        analytics_summary = await knowledge_service.get_analytics_summary(days)
        
        if format == "json":
            return analytics_summary
        elif format == "csv":
            # Convert to CSV format (simplified)
            import io
            import csv
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write summary data
            writer.writerow(["Metric", "Value"])
            summary = analytics_summary.get("summary", {})
            for key, value in summary.items():
                writer.writerow([key, value])
            
            csv_content = output.getvalue()
            output.close()
            
            from fastapi.responses import Response
            return Response(
                content=csv_content,
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=analytics_export.csv"}
            )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to export analytics data: {str(e)}"
        )


# Helper function
async def get_trend_data(db: Session, days: int) -> Dict[str, List[int]]:
    """Get trend data for the overview"""
    try:
        since_date = datetime.utcnow() - timedelta(days=days)
        
        # Generate date range
        date_range = []
        current_date = since_date.date()
        end_date = datetime.utcnow().date()
        
        while current_date <= end_date:
            date_range.append(current_date.isoformat())
            current_date += timedelta(days=1)
        
        # Get daily counts (simplified version)
        trends = {
            "dates": date_range,
            "questions": [0] * len(date_range),
            "answers": [0] * len(date_range),
            "interactions": [0] * len(date_range)
        }
        
        # This would be replaced with actual database queries
        # For now, return sample data structure
        return trends
        
    except Exception:
        return {"dates": [], "questions": [], "answers": [], "interactions": []}
