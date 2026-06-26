"""Food photo analysis using Hermes vision models.

Uses qwen2.5vl via Ollama to identify foods, estimate portions,
and calculate approximate calories and macronutrients.
"""
import base64
import json
import logging
import re
from pathlib import Path
from typing import Optional

import requests

from .config import VISION_MODEL, OLLAMA_BASE_URL

logger = logging.getLogger(__name__)

FOOD_ANALYSIS_PROMPT = """You are a professional nutritionist AI. Analyze this food photo and provide a precise nutritional estimate.

IMPORTANT INSTRUCTIONS:
1. Identify EVERY food item visible in the photo
2. Estimate the portion size for each item (in grams or ml)
3. Calculate total calories and macronutrients (protein, carbs, fat, fiber)
4. Be realistic and conservative in estimates — err on the side of underestimation
5. If you can't identify something, label it as "unknown" and give a best guess
6. Use Spanish for food names

Return ONLY a valid JSON object with this EXACT schema (no markdown, no extra text):
{
  "meal_type": "breakfast|lunch|dinner|snack",
  "foods": [
    {
      "name": "food name in Spanish",
      "portion_g": 150,
      "calories": 200,
      "protein_g": 15.0,
      "carbs_g": 20.0,
      "fat_g": 8.0,
      "fiber_g": 3.0
    }
  ],
  "totals": {
    "calories": 500,
    "protein_g": 35.0,
    "carbs_g": 45.0,
    "fat_g": 18.0,
    "fiber_g": 6.0
  },
  "confidence": "high|medium|low",
  "notes": "brief notes in Spanish about the meal quality"
}"""

# Map English meal_type to Spanish
MEAL_TYPE_MAP = {
    "breakfast": "Desayuno",
    "lunch": "Almuerzo",
    "dinner": "Cena",
    "snack": "Merienda",
}


class FoodAnalyzer:
    """Analyze food photos using vision AI (Ollama + qwen2.5vl)."""

    def __init__(self, model: str = None, base_url: str = None):
        self.model = model or VISION_MODEL
        self.base_url = base_url or OLLAMA_BASE_URL
        self.api_url = f"{self.base_url.rstrip('/')}/api/generate"

    def _image_to_base64(self, image_path: Path) -> str:
        """Convert image file to base64 string."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def analyze(self, image_path: str | Path) -> dict:
        """Analyze a food photo and return nutritional estimate.

        Returns:
            Dict with 'foods' list and 'totals' summary.
            On error: {'error': 'description'}
        """
        image_path = Path(image_path)
        if not image_path.exists():
            return {"error": f"File not found: {image_path}"}

        valid_ext = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
        if image_path.suffix.lower() not in valid_ext:
            return {"error": f"Unsupported format: {image_path.suffix}"}

        try:
            image_b64 = self._image_to_base64(image_path)
        except Exception as e:
            return {"error": f"Failed to read image: {e}"}

        payload = {
            "model": self.model,
            "prompt": FOOD_ANALYSIS_PROMPT,
            "images": [image_b64],
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 4096},
        }

        try:
            resp = requests.post(self.api_url, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            # qwen3-vl uses thinking mode — response is empty, thinking has the analysis
            response_text = data.get("response", "").strip()
            thinking_text = data.get("thinking", "").strip()

            # If response is empty but thinking has content, use thinking + LLM extraction
            if not response_text and thinking_text:
                logger.info("Vision model used thinking mode — extracting JSON via LLM")
                response_text = self._extract_json_from_thinking(thinking_text)
            elif not response_text:
                logger.warning("Vision model returned empty response and thinking")
        except requests.exceptions.ConnectionError:
            return {
                "error": f"Cannot connect to Ollama at {self.base_url}. "
                         f"Is the vision model loaded? (ollama run {self.model})"
            }
        except requests.exceptions.Timeout:
            return {"error": "Vision model timed out. The image may be too complex."}
        except Exception as e:
            return {"error": f"Ollama API error: {e}"}

        result = self._parse_response(response_text)
        if result is None:
            return {
                "error": "Failed to parse AI response as JSON",
                "raw_response": response_text[:500],
            }

        # Normalize meal_type to Spanish
        if "meal_type" in result:
            result["meal_type"] = MEAL_TYPE_MAP.get(
                result["meal_type"].lower(), result["meal_type"]
            )

        return result

    def _parse_response(self, text: str) -> Optional[dict]:
        """Extract JSON from model response. Handles markdown code blocks."""
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try markdown code block
        json_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding a JSON object
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        logger.warning("Could not parse JSON from response: %s", text[:300])
        return None

    def _extract_json_from_thinking(self, thinking_text: str) -> str:
        """Use DeepSeek to convert qwen3-vl thinking text into proper JSON."""
        import os
        from dotenv import load_dotenv
        from pathlib import Path
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
        load_dotenv(Path.home() / ".hermes" / ".env")

        api_key = (os.getenv("MISALUD_DEEPSEEK_KEY", "") or os.getenv("DEEPSEEK_API_KEY", ""))
        if not api_key:
            logger.warning("No DeepSeek API key — falling back to raw thinking text")
            return thinking_text

        # Truncate thinking text to fit
        truncated = thinking_text[:3000]

        prompt = f"""Extract the food analysis from this AI reasoning text and return ONLY a JSON object (no markdown, no extra text):

{truncated}

Return this exact JSON schema:
{{
  "meal_type": "almuerzo",
  "foods": [
    {{"name": "food name in Spanish", "portion_g": 150, "calories": 200, "protein_g": 15.0, "carbs_g": 20.0, "fat_g": 8.0, "fiber_g": 3.0}}
  ],
  "totals": {{"calories": 500, "protein_g": 35.0, "carbs_g": 45.0, "fat_g": 18.0, "fiber_g": 6.0}},
  "confidence": "medium",
  "notes": "brief notes in Spanish"
}}"""

        try:
            resp = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 800,
                },
                timeout=30,
            )
            resp.raise_for_status()
            result = resp.json()["choices"][0]["message"]["content"].strip()
            logger.info("DeepSeek extracted JSON from thinking: %s", result[:100])
            return result
        except Exception as e:
            logger.exception("DeepSeek extraction failed, falling back to thinking text")
            return thinking_text

    def analyze_and_save(self, image_path: str | Path, meal_type: str = None) -> dict:
        """Analyze photo and persist result to a JSON sidecar file.

        Sidecar saved as <image_name>.json alongside the photo.
        """
        result = self.analyze(image_path)

        if "error" not in result:
            if meal_type:
                result["meal_type"] = meal_type

            json_path = Path(image_path).with_suffix(".json")
            with open(json_path, "w") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

        return result
