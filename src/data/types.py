from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Literal

NOT_FOUND_MESSAGE = "I'm sorry, that food is not available in the INDB dataset."
AMBIGUOUS_MESSAGE = "I found multiple matching foods in the INDB dataset. Please select one:"

@dataclass
class NutrientProfile:
    """Standard macronutrient and micronutrient values per 100g or per serving."""
    calories: float = 0.0          # energy_kcal
    protein_g: float = 0.0         # protein_g
    carbs_g: float = 0.0           # carb_g
    fat_g: float = 0.0             # fat_g
    fiber_g: float = 0.0           # fibre_g
    calcium_mg: float = 0.0        # calcium_mg
    iron_mg: float = 0.0           # iron_mg
    sodium_mg: float = 0.0         # sodium_mg
    potassium_mg: float = 0.0      # potassium_mg
    vitamin_c_mg: float = 0.0      # vitc_mg
    free_sugar_g: float = 0.0      # freesugar_g

    def to_dict(self) -> Dict[str, float]:
        return {
            "calories": round(self.calories, 1),
            "protein_g": round(self.protein_g, 1),
            "carbs_g": round(self.carbs_g, 1),
            "fat_g": round(self.fat_g, 1),
            "fiber_g": round(self.fiber_g, 1),
            "calcium_mg": round(self.calcium_mg, 1),
            "iron_mg": round(self.iron_mg, 1),
            "sodium_mg": round(self.sodium_mg, 1),
            "potassium_mg": round(self.potassium_mg, 1),
            "vitamin_c_mg": round(self.vitamin_c_mg, 1),
            "free_sugar_g": round(self.free_sugar_g, 1)
        }

@dataclass
class FoodItem:
    """Normalized food entity representation in the Anuvaad INDB Dataset."""
    id: str
    food_code: str
    name: str
    english_name: str
    hindi_name: Optional[str] = None
    aliases: List[str] = field(default_factory=list)
    category: str = "Anuvaad INDB"
    serving_unit: str = "100g"
    serving_weight_g: float = 100.0
    per_100g: NutrientProfile = field(default_factory=NutrientProfile)
    per_serving: NutrientProfile = field(default_factory=NutrientProfile)
    dietary: str = "general"
    source: str = "Anuvaad INDB 2024.11"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "food_code": self.food_code,
            "name": self.name,
            "english_name": self.english_name,
            "hindi_name": self.hindi_name,
            "aliases": self.aliases,
            "category": self.category,
            "serving_unit": self.serving_unit,
            "serving_weight_g": self.serving_weight_g,
            "per_100g": self.per_100g.to_dict(),
            "per_serving": self.per_serving.to_dict(),
            "dietary": self.dietary,
            "source": self.source
        }

@dataclass
class FoodSearchResult:
    """
    Explicit search contract for food queries:
    - status: 'found' | 'ambiguous' | 'not_found'
    - match_type: 'exact' | 'token' | 'fuzzy' | 'semantic' (if found)
    - confidence: float (0.0 to 1.0)
    - message: required error/ambiguity message
    """
    status: Literal["found", "ambiguous", "not_found"]
    query: str
    food: Optional[FoodItem] = None
    matches: List[FoodItem] = field(default_factory=list)
    match_type: Optional[Literal["exact", "token", "fuzzy", "semantic"]] = None
    confidence: float = 0.0
    message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "query": self.query,
            "food": self.food.to_dict() if self.food else None,
            "matches": [f.to_dict() for f in self.matches],
            "match_type": self.match_type,
            "confidence": round(self.confidence, 2),
            "message": self.message
        }

@dataclass
class NutritionLookupResult:
    """
    Result of evaluating an item against the INDb dataset.
    If the food is NOT in the dataset, found=False, nutrition=0.0,
    and message='I\\'m sorry, that food is not available in the INDB dataset.'
    """
    food_name: str
    matched_food: Optional[str]
    food_code: Optional[str]
    category: str
    quantity: float
    unit: str
    found: bool
    status: Literal["found", "ambiguous", "not_found"]
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    calcium_mg: float
    iron_mg: float
    database_source: str
    match_type: Optional[str] = None
    confidence: float = 0.0
    message: Optional[str] = None
    candidates: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "food_name": self.food_name,
            "matched_food": self.matched_food,
            "food_code": self.food_code,
            "category": self.category,
            "quantity": self.quantity,
            "unit": self.unit,
            "found": self.found,
            "status": self.status,
            "calories": round(self.calories, 1),
            "protein_g": round(self.protein_g, 1),
            "carbs_g": round(self.carbs_g, 1),
            "fat_g": round(self.fat_g, 1),
            "fiber_g": round(self.fiber_g, 1),
            "calcium_mg": round(self.calcium_mg, 1),
            "iron_mg": round(self.iron_mg, 1),
            "database_source": self.database_source,
            "match_type": self.match_type,
            "confidence": round(self.confidence, 2),
            "message": self.message,
            "candidates": self.candidates
        }
