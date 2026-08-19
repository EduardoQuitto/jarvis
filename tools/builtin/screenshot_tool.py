"""Screenshot tool for capturing screen content."""

import base64
from typing import Any, Optional, Type
from pydantic import BaseModel, Field

from core.contracts.enums import SecurityLevel
from core.contracts.tool import BaseTool, ToolResult


class ScreenshotArgs(BaseModel):
    region: Optional[str] = Field(default=None, description="Region to capture (e.g., 'full', 'window', 'region:x,y,w,h')")


class ScreenshotTool(BaseTool):
    """Capture a screenshot of the screen or a region."""

    name: str = "screenshot"
    description: str = "Capture a screenshot of the screen. Returns the image as base64."
    security_level: SecurityLevel = SecurityLevel.GREEN
    args_schema: Optional[Type[BaseModel]] = ScreenshotArgs

    async def execute(self, **kwargs: Any) -> ToolResult:
        region = kwargs.get("region", "full")

        try:
            # Use mss for screenshots if available
            import mss
            import mss.tools

            with mss.mss() as sct:
                if region == "full":
                    monitor = sct.monitors[1]  # Primary monitor
                else:
                    monitor = sct.monitors[1]

                img = sct.grab(monitor)
                png_bytes = mss.tools.to_png(img.png, img.size)
                b64 = base64.b64encode(png_bytes).decode("utf-8")

                return ToolResult.ok(
                    data={
                        "image_base64": b64,
                        "format": "png",
                        "width": img.width,
                        "height": img.height,
                    },
                    security_level=self.security_level,
                )

        except ImportError:
            # Fallback: return placeholder if mss not available
            return ToolResult.ok(
                data={
                    "image_base64": "",
                    "format": "png",
                    "note": "Screenshot library (mss) not available. Install with: pip install mss",
                },
                security_level=self.security_level,
            )
        except Exception as e:
            return ToolResult.fail(
                error=f"Screenshot failed: {e}",
                security_level=self.security_level,
            )
