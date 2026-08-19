"""Vision package — screen analysis and object detection stubs."""

from typing import Any, Dict, Optional
from core.logger import get_logger

logger = get_logger("jarvis.vision")


class ScreenAnalyzerStub:
    """Stub for screen content analysis.

    Will use LLM vision capabilities on the i5-14400 CORE.
    """

    def __init__(self):
        logger.info("Screen analyzer stub initialized")

    async def analyze_screenshot(self, image_base64: str) -> Dict[str, Any]:
        """Analyze a screenshot. STUB: returns placeholder."""
        logger.warning("Screen analysis called but not implemented")
        return {
            "description": "[Vision not implemented]",
            "objects": [],
            "text_content": "",
        }

    async def read_screen_text(self, image_base64: str) -> str:
        """Extract text from screen. STUB: returns placeholder."""
        return "[OCR not implemented]"


class ObjectDetectorStub:
    """Stub for object detection via camera."""

    def __init__(self):
        logger.info("Object detector stub initialized")

    async def detect(self, image_base64: str) -> Dict[str, Any]:
        """Detect objects in image. STUB: returns placeholder."""
        return {"objects": [], "count": 0}
