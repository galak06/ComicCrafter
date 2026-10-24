"""OpenRouter image generation client."""

import base64
import os
from typing import Optional

import requests

from utils import get_logger

logger = get_logger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-3.1-flash-lite-image"
ASPECT_RATIOS = ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]


def closest_aspect_ratio(width: int, height: int) -> str:
    """Pick the supported aspect ratio closest to width:height."""
    target = width / height
    return min(ASPECT_RATIOS, key=lambda r: abs(int(r.split(":")[0]) / int(r.split(":")[1]) - target))


class OpenRouterImageClient:
    """Client for image generation through OpenRouter's chat completions API."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """Initialize OpenRouter image client.

        Args:
            api_key: OpenRouter API key. If None, uses OPENROUTER_API_KEY
            model: Image model id. If None, uses OPENROUTER_IMAGE_MODEL
        """
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.model = model or os.getenv("OPENROUTER_IMAGE_MODEL", DEFAULT_MODEL)

        if not self.api_key:
            logger.warning("OPENROUTER_API_KEY is not set; panels will be gray placeholders")

        self.headers = {"Authorization": f"Bearer {self.api_key}"}
        self.last_cost = 0.0  # USD charged for the most recent image, from OpenRouter's usage report
        logger.info(f"Initialized OpenRouterImageClient with model: {self.model}")

    def generate_image(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        aspect_ratio: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """Generate image using an OpenRouter image model.

        Args:
            prompt: Image generation prompt
            negative_prompt: Things to avoid, appended to the prompt
            aspect_ratio: Output shape such as "16:9"
            **kwargs: Ignored diffusion-specific parameters

        Returns:
            Image data as bytes
        """
        if negative_prompt:
            prompt = f"{prompt}\n\nAvoid: {negative_prompt}"

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "modalities": ["image", "text"],
        }
        if aspect_ratio:
            payload["image_config"] = {"aspect_ratio": aspect_ratio}

        try:
            response = requests.post(OPENROUTER_URL, headers=self.headers, json=payload, timeout=120)
            response.raise_for_status()
            body = response.json()
            self.last_cost = float(body.get("usage", {}).get("cost") or 0)
            images = body["choices"][0]["message"].get("images") or []
            if not images:
                raise ValueError("OpenRouter response contained no image")

            data_url = images[0]["image_url"]["url"]
            logger.debug(f"Generated image for prompt: {prompt[:50]}...")
            return base64.b64decode(data_url.split(",", 1)[1])
        except Exception as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            logger.warning(f"OpenRouter image request failed (HTTP {status}); panel will be a gray placeholder: {e}")
            raise
