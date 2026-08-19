"""Voice package — STT, TTS, and wake word detection stubs."""

from typing import Optional
from core.logger import get_logger

logger = get_logger("jarvis.voice")


class SpeechToTextStub:
    """Stub for Speech-to-Text service.

    Will be implemented with Whisper or Vosk on the i5-14400 CORE.
    """

    def __init__(self):
        logger.info("STT stub initialized (not yet functional)")

    async def transcribe(self, audio_data: bytes, language: str = "pt") -> str:
        """Transcribe audio to text. STUB: returns placeholder."""
        logger.warning("STT transcribe called but not implemented")
        return "[STT not implemented]"


class TextToSpeechStub:
    """Stub for Text-to-Speech service.

    Will be implemented with Piper or Coqui TTS on the i5-14400 CORE.
    """

    def __init__(self):
        logger.info("TTS stub initialized (not yet functional)")

    async def synthesize(self, text: str, voice: str = "default") -> bytes:
        """Synthesize text to audio. STUB: returns empty bytes."""
        logger.warning("TTS synthesize called but not implemented")
        return b""


class WakeWordDetectorStub:
    """Stub for wake word detection.

    Will be implemented with openWakeWord on the i5-14400 CORE.
    """

    def __init__(self, wake_word: str = "JARVIS"):
        self._wake_word = wake_word
        logger.info("Wake word detector stub initialized for '%s'", wake_word)

    async def detect(self, audio_chunk: bytes) -> bool:
        """Detect wake word in audio chunk. STUB: always returns False."""
        return False
