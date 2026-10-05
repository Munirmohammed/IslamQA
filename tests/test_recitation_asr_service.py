"""
Recitation ASR Service Tests
The ASR model itself can't be meaningfully tested with fakes -- this runs
the real tarteel-ai/whisper-base-ar-quran checkpoint against a real,
public-domain recitation clip (Surah Al-Ikhlas 112:1, Alafasy reciter, via
everyayah.com's per-ayah archive) and checks the transcript against the
canonical ayah text, after the same normalization recitation_diff_service
uses. Slow (model download/load) and network-dependent on first run --
marked accordingly, same convention as the project's other model-loading
tests.
"""

import os

import pytest

from app.services.quran_corpus_service import QuranCorpusService
from app.services.recitation_asr_service import RecitationASRService, UnreadableAudioError
from app.services.recitation_diff_service import diff_recitation

FIXTURE_AUDIO_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "audio", "112_001_alafasy.mp3")


@pytest.mark.slow
@pytest.mark.integration
class TestRecitationASRService:
    @pytest.mark.asyncio
    async def test_transcribes_known_ayah_correctly(self):
        service = RecitationASRService()
        await service.initialize()

        with open(FIXTURE_AUDIO_PATH, "rb") as f:
            audio_bytes = f.read()

        transcript = service.transcribe(audio_bytes)

        corpus_service = QuranCorpusService()
        corpus_service.load_or_fetch()
        canonical = corpus_service.get_ayah(112, 1)

        mistakes = diff_recitation(canonical["text_simple"], transcript)
        assert mistakes == [], f"expected an exact transcription, got mistakes: {mistakes}"

    @pytest.mark.asyncio
    async def test_unreadable_audio_raises_clear_error(self):
        service = RecitationASRService()
        await service.initialize()

        with pytest.raises(UnreadableAudioError):
            service.transcribe(b"this is not a real audio file")
