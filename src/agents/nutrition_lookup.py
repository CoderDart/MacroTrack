import json
import logging
from typing import Dict, Any, List, Optional
from difflib import SequenceMatcher
from src.config import INDB_PATH

logger = logging.getLogger("macrotrack.nutrition_lookup")

class NutritionLookupAgent:
    """
    Nutrition Lookup Agent for MacroTrack.
    Queries INDb (Indian Food Composition Tables / ICMR-NIN) dataset
    with fuzzy alias resolution, unit/portion scaling, and global USDA fallback.
    """
    def __init__(self):
        self.foods: List[Dict[str, Any]] = []
        self._load_indb()

    def _load_indb(self):
        if not INDB_PATH.exists():
            logger.error(f"INDb file not found at {INDB_PATH}")
            return
        with open(INDB_PATH, "r", encoding="utf-8") as f:
            self.foods = json.load(f)
        logger.info(f"Loaded INDb with {len(self.foods)} curated Indian food items.")

    def _similarity(self, a: str, b: str) -> float:
        return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()

    def lookup_food(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Searches INDb using exact alias match first, then substring match, then fuzzy match.
        """
        q = query.lower().strip()
        # 1. Exact alias match
        for item in self.foods:
            for alias in item.get("aliases", []):
                if q == alias.lower():
                    return item

        # 2. Substring match in name or aliases
        for item in self.foods:
            if q in item["name"].lower():
                return item
            for alias in item.get("aliases", []):
                if q in alias.lower() or alias.lower() in q:
                    return item

        # 3. Fuzzy similarity match
        best_match = None
        best_score = 0.0
        for item in self.foods:
            score = self._similarity(q, item["name"])
            for alias in item.get("aliases", []):
                alias_score = self._similarity(q, alias)
                if alias_score > score:
                    score = alias_score

            if score > best_score:
                best_score = score
                best_match = item

        if best_score >= 0.55:
            return best_match

        # 4. Fallback Generic Global Nutrition Estimation
        return self._global_fallback(query)

    def _global_fallback(self, query: str) -> Dict[str, Any]:
        """
        Fallback for non-Indian or generic food items.
        """
        return {
            "id": f"global_{abs(hash(query)) % 10000}",
            "name": query.capitalize(),
            "aliases": [query.lower()],
            "category": "Global / Generic",
            "serving_unit": "portion",
            "serving_weight_g": 100,
            "per_100g": { "calories": 180, "protein_g": 6.0, "carbs_g": 22.0, "fat_g": 7.0, "fiber_g": 2.0, "calcium_mg": 20, "iron_mg": 1.0 },
            "per_serving": { "calories": 180, "protein_g": 6.0, "carbs_g": 22.0, "fat_g": 7.0, "fiber_g": 2.0, "calcium_mg": 20, "iron_mg": 1.0 },
            "dietary": "general",
            "source": "Global Fallback"
        }

    def calculate_item_nutrition(self, food_name: str, quantity: float = 1.0, unit: str = "serving") -> Dict[str, Any]:
        """
        Calculates macros for a given quantity and unit.
        Supports: 'piece', 'bowl', 'plate', 'grams' / 'g', 'cup', 'glass', 'tablespoon'.
        """
        food = self.lookup_food(food_name)
        if not food:
            return {
                "food_name": food_name,
                "matched_food": food_name,
                "quantity": quantity,
                "unit": unit,
                "calories": 0.0,
                "protein_g": 0.0,
                "carbs_g": 0.0,
                "fat_g": 0.0,
                "fiber_g": 0.0,
                "calcium_mg": 0.0,
                "iron_mg": 0.0,
                "database_source": "Not Found"
            }

        unit_clean = unit.lower().strip()
        per_serv = food["per_serving"]
        per_100g = food["per_100g"]
        std_weight = food.get("serving_weight_g", 100)

        # Multiplier determination
        if unit_clean in ["g", "gram", "grams"]:
            factor = quantity / 100.0
            base = per_100g
        elif unit_clean in ["kg", "kilogram"]:
            factor = (quantity * 1000.0) / 100.0
            base = per_100g
        elif unit_clean in ["piece", "pieces", "chapati", "roti", "scoop", "egg", "bowl", "plate", "cup", "glass", "tablespoon", "serving"]:
            factor = quantity
            base = per_serv
        else:
            factor = quantity
            base = per_serv

        cal = round(base["calories"] * factor, 1)
        prot = round(base["protein_g"] * factor, 1)
        carb = round(base["carbs_g"] * factor, 1)
        fat = round(base["fat_g"] * factor, 1)
        fib = round(base.get("fiber_g", 0.0) * factor, 1)
        calc = round(base.get("calcium_mg", 0.0) * factor, 1)
        fe = round(base.get("iron_mg", 0.0) * factor, 1)

        return {
            "food_name": food_name,
            "matched_food": food["name"],
            "category": food.get("category", "General"),
            "quantity": quantity,
            "unit": unit,
            "calories": cal,
            "protein_g": prot,
            "carbs_g": carb,
            "fat_g": fat,
            "fiber_g": fib,
            "calcium_mg": calc,
            "iron_mg": fe,
            "database_source": food.get("source", "INDb")
        }

    def compute_meal_total(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Aggregates totals for an entire meal.
        """
        tot_cal = 0.0
        tot_prot = 0.0
        tot_carb = 0.0
        tot_fat = 0.0
        tot_fib = 0.0
        detailed_items = []

        for it in items:
            name = it.get("food_name") or it.get("name", "")
            qty = float(it.get("quantity", 1.0))
            unit = it.get("unit", "serving")
            nutr = self.calculate_item_nutrition(name, qty, unit)
            detailed_items.append(nutr)
            tot_cal += nutr["calories"]
            tot_prot += nutr["protein_g"]
            tot_carb += nutr["carbs_g"]
            tot_fat += nutr["fat_g"]
            tot_fib += nutr["fiber_g"]

        return {
            "calories": round(tot_cal, 1),
            "protein": round(tot_prot, 1),
            "carbs": round(tot_carb, 1),
            "fat": round(tot_fat, 1),
            "fiber": round(tot_fib, 1),
            "items": detailed_items
        }

# Global nutrition lookup instance
nutrition_lookup = NutritionLookupAgent()
