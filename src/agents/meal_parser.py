import re
import json
import logging
from typing import Dict, Any, List, Optional
from PIL import Image
from src.config import GOOGLE_API_KEY, GEMINI_MODEL

logger = logging.getLogger("macrotrack.meal_parser")

class MealParserAgent:
    """
    Meal Parser Agent for MacroTrack powered by Gemini 3.5 Flash.
    Parses free-form meal descriptions, plate photos (food recognition & portion estimation),
    and packaged food nutrition labels (OCR), as well as mixed inputs.
    """
    def __init__(self):
        self.client = None
        self.model_name = GEMINI_MODEL
        self._init_gemini()

    def _init_gemini(self):
        if not GOOGLE_API_KEY:
            logger.warning("GOOGLE_API_KEY not found; falling back to heuristic NLP parser.")
            return

        try:
            from google import genai
            self.client = genai.Client(api_key=GOOGLE_API_KEY)
            logger.info(f"Gemini Client initialized with model target: {self.model_name}")
        except Exception as e:
            logger.warning(f"Failed to initialize google.genai Client ({e}); fallback enabled.")
            self.client = None

    def parse_meal(
        self,
        text_input: Optional[str] = None,
        image_input: Optional[Any] = None,
        is_packaged_label: bool = False
    ) -> Dict[str, Any]:
        """
        Parses text, image, or mixed inputs into structured food items and quantities.
        """
        has_text = bool(text_input and text_input.strip())
        has_image = image_input is not None

        if not has_text and not has_image:
            return {
                "detected_modality": "none",
                "meal_type": "snack",
                "foods": [],
                "confidence_notes": "No input provided."
            }

        modality = "mixed" if (has_text and has_image) else ("plate_photo" if has_image and not is_packaged_label else ("packaged_label_ocr" if has_image and is_packaged_label else "text"))

        # Try Gemini Flash first if client is available
        if self.client:
            try:
                return self._parse_with_gemini(text_input, image_input, modality, is_packaged_label)
            except Exception as e:
                logger.warning(f"Gemini Flash parsing encountered exception: {e}. Executing heuristic fallback.")

        # Fallback heuristic parser
        return self._parse_heuristic(text_input or "", modality)

    def _parse_with_gemini(
        self,
        text_input: Optional[str],
        image_input: Optional[Any],
        modality: str,
        is_packaged_label: bool
    ) -> Dict[str, Any]:
        prompt = f"""
You are an expert Indian Clinical Dietitian and Computer Vision Nutritionist.
Analyze the user's food log input ({modality}).
Input text: "{text_input or 'None'}"
Is Packaged Label OCR: {is_packaged_label}

Instructions:
1. Identify all distinct food items, with a strong focus on Indian culinary items (e.g. roti/chapati, dal tadka, paneer, curd/dahi, rice, idli, dosa, sabzi, etc.) or global foods.
2. Estimate the numeric quantity and serving unit (e.g. 'piece', 'bowl', 'plate', 'grams', 'tablespoon', 'cup', 'glass', 'scoop').
3. Infer the meal type ('breakfast', 'lunch', 'dinner', or 'snack').
4. If this is a packaged food label (OCR), extract the item name and serving size.
5. Return ONLY a valid JSON object matching this schema:
{{
  "detected_modality": "{modality}",
  "meal_type": "breakfast|lunch|dinner|snack",
  "foods": [
    {{
      "food_name": "string (e.g. chapati)",
      "quantity": float (e.g. 2.0),
      "unit": "string (e.g. piece, bowl, grams)",
      "confidence": float (0.0 to 1.0)
    }}
  ],
  "confidence_notes": "string summary of recognition"
}}
"""
        contents = [prompt]
        if image_input is not None:
            if isinstance(image_input, str):
                # File path
                img = Image.open(image_input)
                contents.append(img)
            elif isinstance(image_input, Image.Image):
                contents.append(image_input)
            elif hasattr(image_input, "read"):
                # File-like / BytesIO
                img = Image.open(image_input)
                contents.append(img)

        # Generate using Gemini
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=contents
        )

        resp_text = response.text or ""
        # Clean markdown codeblocks if present
        clean_json = re.sub(r"^```(?:json)?\s*", "", resp_text.strip(), flags=re.MULTILINE)
        clean_json = re.sub(r"```$", "", clean_json.strip(), flags=re.MULTILINE).strip()

        parsed = json.loads(clean_json)
        return parsed

    def _parse_heuristic(self, text: str, modality: str) -> Dict[str, Any]:
        """
        Rule-based heuristic NLP parser for Indian meals when Gemini is offline.
        """
        foods = []
        clean_text = text.lower()

        # Word number map
        num_map = {
            "one": 1.0, "two": 2.0, "three": 3.0, "four": 4.0, "five": 5.0,
            "half": 0.5, "a": 1.0, "an": 1.0, "single": 1.0, "double": 2.0
        }

        # Common food items dictionary
        known_items = [
            ("chapati", "piece"), ("roti", "piece"), ("phulka", "piece"), ("paratha", "piece"),
            ("dal tadka", "bowl"), ("dal", "bowl"), ("daal", "bowl"), ("moong dal", "bowl"),
            ("rajma", "bowl"), ("chole", "bowl"), ("sambar", "bowl"), ("rice", "bowl"),
            ("poha", "plate"), ("upma", "bowl"), ("khichdi", "bowl"), ("biryani", "plate"),
            ("paneer butter masala", "bowl"), ("palak paneer", "bowl"), ("paneer", "grams"),
            ("curd", "bowl"), ("dahi", "bowl"), ("yogurt", "cup"), ("milk", "glass"),
            ("ghee", "tablespoon"), ("boiled egg", "piece"), ("egg white", "piece"),
            ("egg bhurji", "plate"), ("chicken curry", "bowl"), ("tandoori chicken", "piece"),
            ("whey protein", "scoop"), ("whey", "scoop"), ("samosa", "piece"), ("dhokla", "piece"),
            ("sprouts", "bowl"), ("bhindi", "bowl"), ("aloo gobi", "bowl"), ("idli", "piece"),
            ("dosa", "piece")
        ]

        # Tokenize by comma, 'and', 'with', '+'
        clauses = re.split(r",|\band\b|\bwith\b|\+", clean_text)
        for clause in clauses:
            sub = clause.strip()
            if not sub:
                continue

            matched_item = None
            for item_name, default_unit in known_items:
                if item_name in sub:
                    matched_item = (item_name, default_unit)
                    break

            if matched_item:
                name, unit = matched_item
                # Extract quantity
                qty = 1.0
                # Check for explicit grammage: e.g. "100g paneer"
                gm_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:g|grams?|gm)\b", sub)
                if gm_match:
                    qty = float(gm_match.group(1))
                    unit = "grams"
                else:
                    # Check for digits: e.g. "2 chapatis"
                    digit_match = re.search(r"(\d+(?:\.\d+)?)", sub)
                    if digit_match:
                        qty = float(digit_match.group(1))
                    else:
                        for word, val in num_map.items():
                            if re.search(rf"\b{word}\b", sub):
                                qty = val
                                break

                # Check for unit words
                if "bowl" in sub:
                    unit = "bowl"
                elif "plate" in sub:
                    unit = "plate"
                elif "piece" in sub or "slice" in sub:
                    unit = "piece"
                elif "scoop" in sub:
                    unit = "scoop"
                elif "cup" in sub:
                    unit = "cup"
                elif "glass" in sub:
                    unit = "glass"
                elif "tbsp" in sub or "tablespoon" in sub:
                    unit = "tablespoon"

                foods.append({
                    "food_name": name,
                    "quantity": qty,
                    "unit": unit,
                    "confidence": 0.88
                })

        # Infer meal type
        meal_type = "lunch"
        if any(w in clean_text for w in ["breakfast", "poha", "upma", "idli", "dosa", "oats", "morning"]):
            meal_type = "breakfast"
        elif any(w in clean_text for w in ["dinner", "night", "supper"]):
            meal_type = "dinner"
        elif any(w in clean_text for w in ["snack", "tea", "coffee", "biscuit", "samosa"]):
            meal_type = "snack"

        return {
            "detected_modality": modality,
            "meal_type": meal_type,
            "foods": foods if foods else [{"food_name": text.strip(), "quantity": 1.0, "unit": "serving", "confidence": 0.5}],
            "confidence_notes": f"Parsed {len(foods)} items using heuristic rule engine."
        }

# Global meal parser instance
meal_parser = MealParserAgent()
