"""
Seed a handful of genuine Arabic Q&A pairs into the database.

Without this, the local dev/demo dataset has zero real Arabic content, which
undercuts the whole point of the Arabic-focused hybrid retrieval work (BM25 +
FAISS + RRF fusion, char n-gram OCR tolerance) -- there'd be nothing real to
search in Arabic. Idempotent: safe to run multiple times, skips questions
that already exist (matched by question_hash, same scheme the API uses for
duplicate detection).

Usage:
    python scripts/seed_arabic_demo_data.py
"""

import hashlib
import io
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Windows' console defaults to cp1252, which can't encode Arabic -- force
# UTF-8 stdout so this script is runnable without manually setting
# PYTHONIOENCODING first.
if sys.stdout.encoding is not None and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from app.core.database import SessionLocal, Question, Answer, create_tables

ARABIC_QA = [
    {
        "question": "ما هي أركان الإسلام الخمسة؟",
        "category": "pillars",
        "answer": (
            "أركان الإسلام الخمسة هي: الشهادتان (شهادة أن لا إله إلا الله وأن محمداً "
            "رسول الله)، وإقامة الصلاة، وإيتاء الزكاة، وصوم رمضان، وحج البيت لمن "
            "استطاع إليه سبيلاً."
        ),
    },
    {
        "question": "متى يبدأ وقت صلاة الفجر؟",
        "category": "prayer",
        "answer": (
            "يبدأ وقت صلاة الفجر من طلوع الفجر الصادق ويستمر حتى شروق الشمس، "
            "وهي صلاة ركعتان."
        ),
    },
    {
        "question": "ما معنى قول الله أكبر؟",
        "category": "basics",
        "answer": (
            "قول الله أكبر يعني أن الله أعظم وأكبر من كل شيء، وهي عبارة تكبير "
            "يستخدمها المسلمون في الصلاة وفي مواضع أخرى للتعبير عن تعظيم الله."
        ),
    },
    {
        "question": "كم عدد ركعات صلاة الظهر؟",
        "category": "prayer",
        "answer": "صلاة الظهر تتكون من أربع ركعات، وهي من الصلوات المفروضة الخمس.",
    },
    {
        "question": "ما هو حكم الزكاة في الإسلام؟",
        "category": "zakat",
        "answer": (
            "الزكاة ركن من أركان الإسلام الخمسة، وهي واجبة على كل مسلم بالغ عاقل "
            "يملك النصاب الشرعي وحال عليه الحول، وتُصرف في مصارفها الثمانية "
            "المذكورة في القرآن الكريم."
        ),
    },
]


def seed():
    create_tables()
    db = SessionLocal()

    try:
        inserted = 0
        for item in ARABIC_QA:
            question_hash = hashlib.sha256(item["question"].encode()).hexdigest()

            existing = db.query(Question).filter(Question.question_hash == question_hash).first()
            if existing:
                print(f"Skipping (already exists): {item['question']}")
                continue

            question = Question(
                question_text=item["question"],
                question_hash=question_hash,
                language="ar",
                category=item["category"],
                tags=[],
                created_at=datetime.utcnow(),
            )
            db.add(question)
            db.flush()  # populate question.id before creating the answer

            answer = Answer(
                question_id=question.id,
                answer_text=item["answer"],
                source_url="local://seed",
                source_name="Islamic Knowledge Base",
                scholar_name="Islamic Q&A Team",
                confidence_score=1.0,
                is_verified=True,
                language="ar",
                references={},
                created_at=datetime.utcnow(),
            )
            db.add(answer)
            inserted += 1
            print(f"Inserted: {item['question']}")

        db.commit()
        print(f"\nDone. Inserted {inserted} new question(s).")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
