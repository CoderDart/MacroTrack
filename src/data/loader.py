import csv
import logging
from pathlib import Path
from typing import List, Optional
try:
    from src.config import ANUVAAD_CSV_PATH
except Exception:
    ANUVAAD_CSV_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "Anuvaad_INDB_2024.11.csv"
from src.data.types import FoodItem
from src.data.mapper import AnuvaadMapper

logger = logging.getLogger("macrotrack.data.loader")

REQUIRED_COLUMNS = [
    "food_code",
    "food_name",
    "energy_kcal",
    "carb_g",
    "protein_g",
    "fat_g"
]

class AnuvaadCSVLoader:
    """Robust CSV Loader for the Anuvaad INDB Dataset."""

    def __init__(self, csv_path: Optional[Path] = None):
        self.csv_path = csv_path or ANUVAAD_CSV_PATH

    def load_dataset(self) -> List[FoodItem]:
        if not self.csv_path.exists():
            error_msg = f"Anuvaad CSV dataset not found at expected path: {self.csv_path}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)

        logger.info(f"Loading Anuvaad CSV dataset from: {self.csv_path}")

        # Attempt UTF-8 with fallback to Latin-1
        try:
            with open(self.csv_path, mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                return self._parse_rows(reader)
        except UnicodeDecodeError:
            with open(self.csv_path, mode="r", encoding="latin-1") as f:
                reader = csv.DictReader(f)
                return self._parse_rows(reader)

    def _parse_rows(self, reader: csv.DictReader) -> List[FoodItem]:
        headers = [h.strip() for h in (reader.fieldnames or [])]
        missing_cols = [c for c in REQUIRED_COLUMNS if c not in headers]
        if missing_cols:
            raise ValueError(f"Anuvaad CSV is missing required columns: {missing_cols}")

        foods: List[FoodItem] = []
        for row_idx, raw_row in enumerate(reader):
            # Clean keys and values
            clean_row = {k.strip(): v for k, v in raw_row.items() if k}
            food_code = clean_row.get("food_code")
            food_name = clean_row.get("food_name")

            if not food_name or not str(food_name).strip():
                logger.warning(f"Row {row_idx} skipped: empty food_name")
                continue

            try:
                food_item = AnuvaadMapper.map_row_to_food_item(clean_row)
                foods.append(food_item)
            except Exception as e:
                logger.warning(f"Failed to map row {row_idx} ({food_name}): {e}")

        logger.info(f"Successfully loaded and validated {len(foods)} Anuvaad food items.")
        return foods
