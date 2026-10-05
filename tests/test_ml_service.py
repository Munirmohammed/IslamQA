"""
ML Service Tests
Covers Arabic text normalization (pyarabic wiring) and the N+1 query fix in
find_similar_questions.
"""

import pytest

from app.services.ml_service import TextPreprocessor


class TestArabicPreprocessing:
    """Verify preprocess_arabic uses pyarabic's real normalization rather
    than the previous hand-rolled regex."""

    @pytest.fixture
    def preprocessor(self):
        return TextPreprocessor()

    def test_strips_tashkeel_diacritics(self, preprocessor):
        result = preprocessor.preprocess_arabic("الْقُرْآنُ الْكَرِيمُ")
        assert "ً" not in result  # fathatan
        assert "َ" not in result  # fatha
        assert "ْ" not in result  # sukun

    def test_normalizes_hamza_alef_variants_to_plain_alef(self, preprocessor):
        # أ إ آ should all collapse to ا
        result = preprocessor.preprocess_text("أحمد إبراهيم آدم", language="ar")
        assert "أ" not in result
        assert "إ" not in result
        assert "آ" not in result

    def test_normalizes_teh_marbuta_to_heh(self, preprocessor):
        result = preprocessor.preprocess_text("المكتبة الجميلة", language="ar")
        assert "ة" not in result

    def test_real_gold_query_normalizes_as_expected(self, preprocessor):
        """Matches the hand-verified output for one of the gold-set queries
        (see tests/fixtures/gold_queries.json)."""
        result = preprocessor.preprocess_arabic("ما هي أركان الإسلام الخمسة؟")
        assert result == "اركان الاسلام الخمسه؟"

    def test_removes_short_words_and_stopwords(self, preprocessor):
        result = preprocessor.preprocess_arabic("هذا في من على الإسلام")
        # all short/stopwords filtered; only a real content word should remain
        assert "الاسلام" in result
        assert "هذا" not in result
        assert "في" not in result

    def test_strips_arabic_question_mark_so_word_matches_without_it(self, preprocessor):
        """Regression test: the Arabic question mark (؟) shares the same
        Unicode block as Arabic letters, so clean_text's whitelist regex used
        to keep it attached to the preceding word (e.g. "الفجر؟")
        -- silently breaking exact-token matches (BM25, keyword search) for
        essentially every question-ending word in this dataset."""
        with_question_mark = preprocessor.preprocess_text("متى يبدأ وقت صلاة الفجر؟", language="ar")
        without_question_mark = preprocessor.preprocess_text("الفجر", language="ar")
        assert without_question_mark in with_question_mark.split()


class TestFindSimilarQuestionsBatching:
    """Regression test for the N+1 query fix: batch-fetching Questions/
    Answers for FAISS hits instead of one round-trip per hit."""

    @pytest.mark.asyncio
    async def test_batches_db_queries_instead_of_one_per_hit(self, monkeypatch):
        from app.services import ml_service as ml_service_module

        query_log = []

        class FakeQuery:
            def __init__(self, model):
                self.model = model

            def filter(self, *args, **kwargs):
                query_log.append(self.model.__name__)
                return self

            def all(self):
                return []

            def first(self):
                return None

        class FakeSession:
            def query(self, model):
                return FakeQuery(model)

            def close(self):
                pass

        vector_embeddings = ml_service_module.VectorEmbeddings()

        class FakeFaissIndex:
            def search(self, query_vector, top_k):
                import numpy as np
                # 5 hits, all above threshold
                similarities = np.array([[0.9, 0.85, 0.8, 0.75, 0.7]], dtype="float32")
                indices = np.array([[0, 1, 2, 3, 4]])
                return similarities, indices

        vector_embeddings.faiss_index = FakeFaissIndex()
        vector_embeddings.question_ids = ["q0", "q1", "q2", "q3", "q4"]

        async def fake_get_sentence_embedding(text, language="auto"):
            import numpy as np
            return np.zeros(384, dtype="float32")

        monkeypatch.setattr(
            vector_embeddings, "get_sentence_embedding", fake_get_sentence_embedding
        )
        monkeypatch.setattr(
            ml_service_module, "SessionLocal", lambda: FakeSession()
        )

        await vector_embeddings.find_similar_questions("test query", "en", top_k=5)

        # Exactly one Question query and one Answer query, regardless of hit count
        # (previously: one Question query per hit = O(top_k)).
        assert query_log.count("Question") == 1
        assert query_log.count("Answer") == 1

    @pytest.mark.asyncio
    async def test_ignores_faiss_padding_index_negative_one(self, monkeypatch):
        """FAISS pads results with idx == -1 when the index has fewer real
        vectors than requested top_k*2 (the common case for this project's
        tiny dataset). Without the -1 guard, question_ids[-1] would resolve
        via Python's negative indexing to the *last* question in the list.

        The fake DB below is deliberately permissive (returns every question
        it knows about regardless of filter args), so the only thing that
        can keep "LAST" out of the results is the candidate-building loop's
        -1 guard itself, not an incidental DB-side filter.
        """
        from app.services import ml_service as ml_service_module

        class FakeQuestion:
            def __init__(self, qid):
                self.id = qid
                self.question_text = f"question {qid}"
                self.category = "test"
                self.language = "en"

        all_fake_questions = [FakeQuestion("q0"), FakeQuestion("LAST")]

        class FakeQuery:
            def __init__(self, model):
                self.model = model

            def filter(self, *args, **kwargs):
                return self

            def all(self):
                return all_fake_questions if self.model is ml_service_module.Question else []

        class FakeSession:
            def query(self, model):
                return FakeQuery(model)

            def close(self):
                pass

        vector_embeddings = ml_service_module.VectorEmbeddings()

        class FakeFaissIndex:
            def search(self, query_vector, top_k):
                import numpy as np
                # Only 1 real match; the rest is FAISS's -1 padding.
                similarities = np.array([[0.9, 0.8, 0.8, 0.8, 0.8]], dtype="float32")
                indices = np.array([[0, -1, -1, -1, -1]])
                return similarities, indices

        vector_embeddings.faiss_index = FakeFaissIndex()
        # question_ids[-1] would be "LAST" if the -1 guard were missing.
        vector_embeddings.question_ids = ["q0", "LAST"]

        async def fake_get_sentence_embedding(text, language="auto"):
            import numpy as np
            return np.zeros(384, dtype="float32")

        monkeypatch.setattr(vector_embeddings, "get_sentence_embedding", fake_get_sentence_embedding)
        monkeypatch.setattr(ml_service_module, "SessionLocal", lambda: FakeSession())

        # min_similarity=0.0 so every padded slot's 0.8 score would pass the
        # threshold too -- the -1 guard is what must exclude them, not the score filter.
        results = await vector_embeddings.find_similar_questions(
            "test query", "en", top_k=5, min_similarity=0.0
        )

        returned_ids = {r["question_id"] for r in results}
        assert "LAST" not in returned_ids
        assert returned_ids == {"q0"}
