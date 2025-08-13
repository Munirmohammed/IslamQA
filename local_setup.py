"""
Local Setup Script for Islamic Q&A Backend
Creates a simple SQLite database for local development
"""

import os
import secrets
from sqlalchemy import create_engine
from app.core.database_sqlite import Base, SessionLocal, create_tables
from app.core.security import SecurityUtils, AuthService

def setup_local_environment():
    """Setup local development environment"""
    print("🕌 Setting up Local Islamic Q&A Backend...")
    
    # 1. Create .env file if it doesn't exist
    if not os.path.exists('.env'):
        print("📝 Creating .env file...")
        
        secret_key = secrets.token_urlsafe(32)
        
        env_content = f"""# Local Development Configuration
# Database (SQLite for local development)
DATABASE_URL=sqlite:///./islamqa_local.db

# Redis (Optional for local - will work without it)
REDIS_URL=redis://localhost:6379

# Security
SECRET_KEY={secret_key}
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Features (Enable what works locally)
ENABLE_ML_MATCHING=true
ENABLE_WEBSOCKETS=true
ENABLE_RATE_LIMITING=false
ENABLE_ANALYTICS=true

# Development
DEBUG=true
LOG_LEVEL=INFO

# GitHub (Optional - for later setup)
GITHUB_TOKEN=your-github-token-here
GITHUB_REPO=Munirmohammed/IslamQA

# API Settings
ALLOWED_HOSTS=["*"]
ALLOWED_ORIGINS=["http://localhost:3000", "http://localhost:8080", "http://localhost:8000"]

# ML Models (Will download automatically)
SENTENCE_TRANSFORMER_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
MIN_SIMILARITY_SCORE=0.7
MAX_RESULTS=10
"""
        
        with open('.env', 'w') as f:
            f.write(env_content)
        
        print("✅ .env file created with local settings")
    
    # 2. Create local SQLite database
    print("🗄️ Setting up local database...")
    
    # Create all tables using SQLite-compatible models
    create_tables()
    print("✅ Database tables created")
    
    # 3. Create admin user
    print("👤 Creating admin user...")
    
    # Use the SQLite session
    db = SessionLocal()
    
    try:
        auth_service = AuthService(db)
        
        # Create admin user
        admin_user = auth_service.create_user(
            username='munir_admin',
            email='munirmohammed038@gmail.com',
            password='munir123',
            is_admin=True
        )
        print(f"✅ Admin user created: {admin_user.username}")
        print(f"📧 Email: munirmohammed038@gmail.com")
        print(f"🔑 Password: munir123")
        print(f"🔗 API Key: {admin_user.api_key}")
        
    except Exception as e:
        print(f"ℹ️ Admin user might already exist: {e}")
    
    finally:
        db.close()
    
    # 4. Add some sample Islamic Q&A data
    print("📚 Adding sample Islamic Q&A data...")
    
    db = SessionLocal()
    
    try:
        from app.core.database_sqlite import Question, Answer
        import uuid
        from datetime import datetime
        
        # Sample Islamic questions and answers
        sample_qa = [
            {
                "question": "What are the five pillars of Islam?",
                "answer": "The five pillars of Islam are: 1) Shahada (Declaration of Faith) - There is no god but Allah, and Muhammad is His messenger. 2) Salah (Prayer) - Five daily prayers. 3) Zakat (Charity) - Giving to those in need. 4) Sawm (Fasting) - Fasting during Ramadan. 5) Hajj (Pilgrimage) - Pilgrimage to Mecca for those who are able.",
                "category": "basics",
                "language": "en"
            },
            {
                "question": "How many times do Muslims pray per day?",
                "answer": "Muslims pray five times a day: Fajr (dawn), Dhuhr (midday), Asr (afternoon), Maghrib (sunset), and Isha (night). These prayers are one of the five pillars of Islam and are obligatory for all adult Muslims.",
                "category": "prayer",
                "language": "en"
            },
            {
                "question": "What is the meaning of 'Bismillah'?",
                "answer": "Bismillah means 'In the name of Allah' in Arabic. The full phrase is 'Bismillah-ir-Rahman-ir-Raheem' which means 'In the name of Allah, the Most Gracious, the Most Merciful.' Muslims say this before starting any task to seek Allah's blessing.",
                "category": "basics",
                "language": "en"
            },
            {
                "question": "What is the importance of Friday prayers?",
                "answer": "Friday prayers (Jumu'ah) are very important in Islam. It is obligatory for adult Muslim men to attend the congregational prayer at the mosque on Fridays. The prayer includes a sermon (khutbah) and replaces the regular Dhuhr prayer. It strengthens community bonds and spiritual connection.",
                "category": "prayer",
                "language": "en"
            },
            {
                "question": "What is Ramadan?",
                "answer": "Ramadan is the ninth month of the Islamic lunar calendar and the holy month of fasting for Muslims. During Ramadan, Muslims fast from dawn to sunset, abstaining from food, drink, and other physical needs. It is a time of spiritual reflection, self-discipline, and increased devotion to Allah.",
                "category": "fasting",
                "language": "en"
            }
        ]
        
        for qa_data in sample_qa:
            # Create question
            question_hash = SecurityUtils.hash_string(qa_data["question"])
            
            # Check if question already exists
            existing = db.query(Question).filter(Question.question_hash == question_hash).first()
            if existing:
                continue
            
            question = Question(
                id=uuid.uuid4(),
                question_text=qa_data["question"],
                question_hash=question_hash,
                category=qa_data["category"],
                language=qa_data["language"],
                tags=[qa_data["category"], "islam", "basics"],
                created_at=datetime.utcnow()
            )
            
            db.add(question)
            db.flush()  # Get the ID
            
            # Create answer
            answer = Answer(
                id=uuid.uuid4(),
                question_id=question.id,
                answer_text=qa_data["answer"],
                source_name="Local Islamic Knowledge",
                source_url="local://sample",
                scholar_name="Islamic Q&A Team",
                confidence_score=1.0,
                is_verified=True,
                language=qa_data["language"],
                references={},
                created_at=datetime.utcnow()
            )
            
            db.add(answer)
        
        db.commit()
        print("✅ Sample Islamic Q&A data added")
        
    except Exception as e:
        print(f"⚠️ Error adding sample data: {e}")
        db.rollback()
    
    finally:
        db.close()
    
    print("\n🎉 Local setup complete!")
    print("\n📋 Next steps:")
    print("1. Start the server: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000")
    print("2. Open API docs: http://localhost:8000/docs")
    print("3. Test the chat: Connect to ws://localhost:8000/ws/chat")
    print("4. Login with: munirmohammed038@gmail.com / munir123")
    print("\n🔗 Useful URLs:")
    print("- API Documentation: http://localhost:8000/docs")
    print("- Health Check: http://localhost:8000/health")
    print("- Search Test: POST http://localhost:8000/api/v1/search/")
    
if __name__ == "__main__":
    setup_local_environment()
