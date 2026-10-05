"""
Recitation ASR Service
Speech-to-text for Quran recitation, using a Whisper checkpoint fine-tuned
specifically on Quranic Arabic audio (tarteel-ai/whisper-base-ar-quran),
self-hosted in-process (same lifecycle convention as the existing
sentence-transformer/cross-encoder models: load once at app startup).

Accepts WAV/MP3/FLAC/OGG (decoded via soundfile/libsndfile -- confirmed
working against a real recitation clip without needing an ffmpeg binary).
WEBM/OPUS (common browser MediaRecorder output) is not supported; the
client must upload one of the formats above.
"""

import io
from typing import Optional

import numpy as np
import soundfile as sf
import structlog
import torch
from scipy.signal import resample
from transformers import WhisperForConditionalGeneration, WhisperProcessor

logger = structlog.get_logger()

MODEL_ID = "tarteel-ai/whisper-base-ar-quran"
TARGET_SAMPLE_RATE = 16000


class UnreadableAudioError(Exception):
    """Raised when the uploaded audio can't be decoded (wrong/unsupported
    format, corrupt file) -- callers should turn this into an HTTP 400."""


class RecitationASRService:
    """Loads the Quran-finetuned Whisper model once and transcribes audio."""

    def __init__(self, model_id: str = MODEL_ID):
        self.model_id = model_id
        self.processor: Optional[WhisperProcessor] = None
        self.model: Optional[WhisperForConditionalGeneration] = None
        self.is_initialized = False

    async def initialize(self):
        if self.is_initialized:
            return

        try:
            logger.info(f"Loading recitation ASR model: {self.model_id}...")
            self.processor = WhisperProcessor.from_pretrained(self.model_id)
            self.model = WhisperForConditionalGeneration.from_pretrained(self.model_id)
            self.model.eval()
            self.is_initialized = True
            logger.info("Recitation ASR model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load recitation ASR model: {str(e)}")
            # Degrade gracefully (matches KnowledgeService/VoiceSearchService
            # convention) -- transcribe() below checks self.model is not None.
            self.is_initialized = True

    def _decode_audio(self, audio_bytes: bytes) -> np.ndarray:
        """Decode to mono float32 @ 16kHz. Raises UnreadableAudioError for
        anything libsndfile can't open (e.g. webm/opus)."""
        try:
            data, sample_rate = sf.read(io.BytesIO(audio_bytes))
        except Exception as e:
            raise UnreadableAudioError(
                "Could not decode audio -- upload WAV, MP3, FLAC, or OGG "
                "(WEBM/OPUS from browser MediaRecorder is not supported)"
            ) from e

        if data.ndim > 1:
            data = data.mean(axis=1)

        if sample_rate != TARGET_SAMPLE_RATE:
            num_samples = int(len(data) * TARGET_SAMPLE_RATE / sample_rate)
            data = resample(data, num_samples)

        return data.astype(np.float32)

    def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe recited Quran audio to Arabic text."""
        if self.model is None or self.processor is None:
            raise RuntimeError("Recitation ASR model is not loaded")

        audio = self._decode_audio(audio_bytes)

        inputs = self.processor(audio, sampling_rate=TARGET_SAMPLE_RATE, return_tensors="pt")
        with torch.no_grad():
            # Deliberately no `language=`/`task=` kwargs: this checkpoint was
            # fine-tuned exclusively on Arabic Quranic audio, and newer
            # `transformers` raises on those kwargs against its
            # generation_config.json ("generation config is outdated").
            predicted_ids = self.model.generate(inputs["input_features"])

        return self.processor.batch_decode(predicted_ids, skip_special_tokens=True)[0]


recitation_asr_service = RecitationASRService()
