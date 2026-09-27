import re
from typing import Dict, Any, List, Optional
from src.data.types import FoodItem, NutrientProfile

def safe_float(value: Any, fallback: float = 0.0) -> float:
    """Safely converts string or numeric values to float."""
    if value is None:
        return fallback
    if isinstance(value, (int, float)):
        import math
        return fallback if math.isnan(value) else float(value)
    val_str = str(value).strip()
    if not val_str or val_str.lower() in ("nan", "null", "none", "-", ""):
        return fallback
    try:
        return float(val_str)
    except (ValueError, TypeError):
        return fallback

def extract_names_and_aliases(full_name: str, food_code: str) -> Dict[str, Any]:
    """
    Extracts English name, Hindi name (if present in parentheses),
    and a curated, prioritized list of lookup aliases.
    """
    raw = full_name.strip()
    match = re.match(r"^(.*?)\s*\((.*?)\)$", raw)
    if match:
        english = match.group(1).strip()
        hindi = match.group(2).strip()
    else:
        english = raw
        hindi = None

    aliases = set()
    # 1. Full raw name
    aliases.add(raw.lower())

    # 2. English name
    if english:
        aliases.add(english.lower())
        # Clean slashes, e.g. "Chapati/Roti" -> "chapati", "roti"
        for part in re.split(r"[/,]", english):
            p = part.strip().lower()
            if p and len(p) >= 2:
                aliases.add(p)

    # 3. Hindi name
    if hindi:
        aliases.add(hindi.lower())
        for part in re.split(r"[/,]", hindi):
            p = part.strip().lower()
            if p and len(p) >= 2:
                aliases.add(p)

    # 4. Standard Indian culinary aliases for core staples
    raw_lower = raw.lower()
    if "chapati" in raw_lower or "roti" in raw_lower:
        aliases.update(["chapati", "roti", "phulka", "gehu ki roti", "wheat roti"])
    if raw_lower.startswith("plain parantha") or raw_lower.startswith("plain paratha"):
        aliases.update(["paratha", "plain paratha", "parantha", "tawa paratha", "plain parantha"])
    if food_code == "ASC155" or raw_lower == "mixed dal":
        # Mixed dal is standard default dal
        aliases.update(["dal", "daal", "dal tadka", "yellow dal", "arhar dal", "toor dal", "mixed dal"])
    if "moong dal" in raw_lower or "dhuli moong" in raw_lower:
        aliases.update(["moong dal", "mung dal", "yellow moong dal", "green moong dal"])
    if raw_lower == "paneer curry":
        aliases.update(["paneer", "paneer curry", "cottage cheese curry", "paneer sabzi"])
    elif "paneer" in raw_lower:
        if "curry" in raw_lower or "gravy" in raw_lower:
            aliases.update(["paneer curry", "paneer butter masala", "paneer gravy"])
        if "bhurji" in raw_lower:
            aliases.add("paneer bhurji")
    if "curd" in raw_lower or "dahi" in raw_lower:
        aliases.update(["curd", "dahi", "plain curd", "homemade dahi", "yogurt"])
    if "boiled egg" in raw_lower or "egg curry" in raw_lower or raw_lower.startswith("egg"):
        aliases.update(["egg", "boiled egg", "anda", "boiled whole egg"])
    if "chicken" in raw_lower and ("curry" in raw_lower or "gravy" in raw_lower or "masala" in raw_lower):
        aliases.update(["chicken curry", "chicken", "murgh curry"])
    if "biryani" in raw_lower or "biriyani" in raw_lower:
        aliases.update(["biryani", "biriyani"])
    if raw_lower.startswith("idli"):
        aliases.update(["idli", "steamed idli", "idly"])
    if "dosa" in raw_lower:
        aliases.update(["dosa", "plain dosa"])
    if "khichdi" in raw_lower or "khichuri" in raw_lower:
        aliases.update(["khichdi", "dal khichdi"])
    if "poha" in raw_lower:
        aliases.update(["poha", "kanda poha"])
    if "upma" in raw_lower:
        aliases.update(["upma", "rava upma"])
    if "tea" in raw_lower or "chai" in raw_lower:
        aliases.update(["chai", "garam chai", "tea", "hot tea"])
    if "coffee" in raw_lower:
        aliases.update(["coffee", "hot coffee"])

    return {
        "english_name": english or raw,
        "hindi_name": hindi,
        "aliases": sorted(list(aliases))
    }

class AnuvaadMapper:
    """Transforms raw Anuvaad CSV dictionary records into normalized FoodItem domain models."""

    @staticmethod
    def map_row_to_food_item(row: Dict[str, Any]) -> FoodItem:
        food_code = str(row.get("food_code", "")).strip()
        raw_name = str(row.get("food_name", "")).strip()
        name_info = extract_names_and_aliases(raw_name, food_code)

        serv_unit = str(row.get("servings_unit") or "100g").strip().lower()
        primary_source = str(row.get("primarysource") or "Anuvaad INDB").strip()

        # Per 100g Nutrition Profile (exact INDb ICMR-NIN values)
        per_100g = NutrientProfile(
            calories=safe_float(row.get("energy_kcal")),
            protein_g=safe_float(row.get("protein_g")),
            carbs_g=safe_float(row.get("carb_g")),
            fat_g=safe_float(row.get("fat_g")),
            fiber_g=safe_float(row.get("fibre_g")),
            calcium_mg=safe_float(row.get("calcium_mg")),
            iron_mg=safe_float(row.get("iron_mg")),
            sodium_mg=safe_float(row.get("sodium_mg")),
            potassium_mg=safe_float(row.get("potassium_mg")),
            vitamin_c_mg=safe_float(row.get("vitc_mg")),
            free_sugar_g=safe_float(row.get("freesugar_g"))
        )

        # Per Serving Nutrition Profile (from unit_serving columns)
        unit_cal = safe_float(row.get("unit_serving_energy_kcal"))
        if unit_cal > 0 or safe_float(row.get("unit_serving_protein_g")) > 0:
            per_serving = NutrientProfile(
                calories=unit_cal,
                protein_g=safe_float(row.get("unit_serving_protein_g")),
                carbs_g=safe_float(row.get("unit_serving_carb_g")),
                fat_g=safe_float(row.get("unit_serving_fat_g")),
                fiber_g=safe_float(row.get("unit_serving_fibre_g")),
                calcium_mg=safe_float(row.get("unit_serving_calcium_mg")),
                iron_mg=safe_float(row.get("unit_serving_iron_mg")),
                sodium_mg=safe_float(row.get("unit_serving_sodium_mg")),
                potassium_mg=safe_float(row.get("unit_serving_potassium_mg")),
                vitamin_c_mg=safe_float(row.get("unit_serving_vitc_mg")),
                free_sugar_g=safe_float(row.get("unit_serving_freesugar_g"))
            )
        else:
            per_serving = per_100g

        # Determine dietary category
        dietary = "veg"
        name_lower = raw_name.lower()
        if any(w in name_lower for w in ("chicken", "mutton", "fish", "prawn", "crab", "meat", "pork", "beef", "keema")):
            dietary = "non-veg"
        elif any(w in name_lower for w in ("egg", "anda", "omelette", "bhurji")):
            dietary = "ovo-veg"

        return FoodItem(
            id=f"anuvaad_{food_code}",
            food_code=food_code,
            name=raw_name,
            english_name=name_info["english_name"],
            hindi_name=name_info["hindi_name"],
            aliases=name_info["aliases"],
            category=primary_source,
            serving_unit=serv_unit,
            serving_weight_g=100.0,
            per_100g=per_100g,
            per_serving=per_serving,
            dietary=dietary,
            source="Anuvaad INDB 2024.11"
        )
