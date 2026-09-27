import logging
from typing import Dict, Any, List, Optional
from src.data.repository import food_repository
from src.data.types import (
    AMBIGUOUS_MESSAGE,
    NOT_FOUND_MESSAGE,
    NutritionLookupResult,
)

logger = logging.getLogger("macrotrack.nutrition_lookup")

class NutritionLookupAgent:
    """
    Nutrition Lookup Agent for MacroTrack.
    Queries the official Anuvaad INDB (Indian Food Composition Tables / ICMR-NIN) dataset
    via the centralized FoodRepository.
    Calculates exact macronutrients and micronutrients on a 100g basis.
    """
    def __init__(self):
        self.repository = food_repository

    def lookup_food(self, query: str) -> Optional[Any]:
        """Looks up a food item in the Anuvaad dataset. Returns None if not found."""
        return self.repository.find_food(query)

    def calculate_item_nutrition(
        self,
        food_name: str,
        quantity: float = 1.0,
        unit: str = "100g"
    ) -> Dict[str, Any]:
        """
        Calculates macros on a 100g food baseline.
        If an item is not found, returns a safe result with found=False and
        'Sorry, I don't have data for this item' without generating fake numbers.
        """
        search_result = self.repository.search_food(food_name)
        if search_result.status != "found":
            ambiguous = search_result.status == "ambiguous"
            result = NutritionLookupResult(
                food_name=food_name,
                matched_food=None,
                food_code=None,
                category="Uncategorized",
                quantity=quantity,
                unit=unit,
                found=False,
                status=search_result.status,
                calories=0.0,
                protein_g=0.0,
                carbs_g=0.0,
                fat_g=0.0,
                fiber_g=0.0,
                calcium_mg=0.0,
                iron_mg=0.0,
                database_source="Not Found",
                message=AMBIGUOUS_MESSAGE if ambiguous else NOT_FOUND_MESSAGE,
                candidates=[food.name for food in search_result.matches]
            )
            return result.to_dict()

        food = search_result.food

        # Nutrition calculation based on 100g standard baseline
        unit_clean = (unit or "100g").lower().strip()
        per_100g = food.per_100g

        if unit_clean in ("g", "gram", "grams"):
            factor = quantity / 100.0
        elif unit_clean in ("kg", "kilogram"):
            factor = (quantity * 1000.0) / 100.0
        elif unit_clean in ("100g", "100gms", "100gm"):
            factor = quantity
        else:
            # Default to 100g portion unit factor
            factor = quantity

        cal = per_100g.calories * factor
        prot = per_100g.protein_g * factor
        carb = per_100g.carbs_g * factor
        fat = per_100g.fat_g * factor
        fib = per_100g.fiber_g * factor
        calc = per_100g.calcium_mg * factor
        fe = per_100g.iron_mg * factor

        result = NutritionLookupResult(
            food_name=food_name,
            matched_food=food.name,
            food_code=food.food_code,
            category=food.category,
            quantity=quantity,
            unit=unit,
            found=True,
            status="found",
            calories=cal,
            protein_g=prot,
            carbs_g=carb,
            fat_g=fat,
            fiber_g=fib,
            calcium_mg=calc,
            iron_mg=fe,
            database_source="Anuvaad INDB 2024.11",
            match_type=search_result.match_type,
            confidence=search_result.confidence,
            message=None
        )
        return result.to_dict()

    def compute_meal_total(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Aggregates totals for an entire meal.
        Sums nutrients ONLY for verified items in Anuvaad INDB.
        Collects any missing items with explicit apologies.
        """
        tot_cal = 0.0
        tot_prot = 0.0
        tot_carb = 0.0
        tot_fat = 0.0
        tot_fib = 0.0
        tot_calc = 0.0
        tot_fe = 0.0
        detailed_items = []
        missing_items = []
        ambiguous_items = []

        for it in items:
            name = it.get("food_name") or it.get("name", "")
            qty = float(it.get("quantity", 1.0))
            unit = it.get("unit", "100g")
            nutr = self.calculate_item_nutrition(name, qty, unit)
            detailed_items.append(nutr)

            if nutr["found"]:
                tot_cal += nutr["calories"]
                tot_prot += nutr["protein_g"]
                tot_carb += nutr["carbs_g"]
                tot_fat += nutr["fat_g"]
                tot_fib += nutr["fiber_g"]
                tot_calc += nutr["calcium_mg"]
                tot_fe += nutr["iron_mg"]
            else:
                missing_items.append(name)
                if nutr["status"] == "ambiguous":
                    ambiguous_items.append({
                        "food_name": name,
                        "candidates": nutr["candidates"]
                    })

        found_count = sum(1 for item in detailed_items if item["found"])
        if ambiguous_items:
            status = "ambiguous"
            message = AMBIGUOUS_MESSAGE
        elif missing_items:
            status = "partial" if found_count else "not_found"
            message = NOT_FOUND_MESSAGE
        else:
            status = "found"
            message = None

        return {
            "status": status,
            "message": message,
            "calories": round(tot_cal, 1),
            "protein": round(tot_prot, 1),
            "carbs": round(tot_carb, 1),
            "fat": round(tot_fat, 1),
            "fiber": round(tot_fib, 1),
            "calcium_mg": round(tot_calc, 1),
            "iron_mg": round(tot_fe, 1),
            "items": detailed_items,
            "found_count": found_count,
            "missing_items": missing_items,
            "ambiguous_items": ambiguous_items
        }

# Global nutrition lookup instance
nutrition_lookup = NutritionLookupAgent()
