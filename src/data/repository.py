import re
import logging
from typing import Dict, Any, List, Optional, Tuple
from difflib import SequenceMatcher
from src.data.types import AMBIGUOUS_MESSAGE, FoodItem, FoodSearchResult, NOT_FOUND_MESSAGE
from src.data.loader import AnuvaadCSVLoader
from src.database.storage import db

logger = logging.getLogger("macrotrack.data.repository")

class FoodRepository:
    """
    Centralized Data Access Layer for the Anuvaad INDB Dataset.
    Maintains indexed mappings for fast O(1) alias lookups and fuzzy matching.
    """
    def __init__(self, loader: Optional[AnuvaadCSVLoader] = None):
        self.loader = loader or AnuvaadCSVLoader()
        self._foods: List[FoodItem] = []
        self._by_code: Dict[str, FoodItem] = {}
        self._by_id: Dict[str, FoodItem] = {}
        self._alias_index: Dict[str, List[FoodItem]] = {}
        self._is_loaded: bool = False
        self.load()

    def _get_custom_foods(self, user_id: Optional[str] = None) -> List[FoodItem]:
        if user_id in (None, "default_user"):
            rows = db.get_all_custom_foods()
        else:
            rows = db.get_custom_foods_for_user(user_id)
        return [FoodItem.from_custom_food(item) for item in rows]

    def _search_custom_items(self, query: str, user_id: Optional[str] = None) -> List[FoodItem]:
        q = self._normalize(query)
        if not q:
            return []
        custom_items = self._get_custom_foods(user_id)
        matches: List[FoodItem] = []
        for item in custom_items:
            searchable = [item.name, item.english_name, *item.aliases]
            normalized_values = [self._normalize(v) for v in searchable if v]
            if q in normalized_values:
                matches.append(item)
                continue
            candidate_tokens = set(q.split())
            if candidate_tokens and any(
                candidate_tokens.issubset(set(self._normalize(value).split()))
                for value in normalized_values
            ):
                matches.append(item)
                continue
            if any(SequenceMatcher(None, q, self._normalize(value)).ratio() >= 0.7 for value in normalized_values if value):
                matches.append(item)
        return matches

    def load(self, force: bool = False) -> None:
        """Loads and indexes the Anuvaad dataset."""
        if self._is_loaded and not force:
            return
        self._foods = self.loader.load_dataset()
        self._by_code.clear()
        self._by_id.clear()
        self._alias_index.clear()

        for item in self._foods:
            self._by_code[item.food_code.lower()] = item
            self._by_id[item.id.lower()] = item

            # Index all aliases
            for alias in item.aliases:
                alias_clean = alias.strip().lower()
                if alias_clean:
                    self._alias_index.setdefault(self._normalize(alias_clean), []).append(item)

            # Index exact full name
            full_name_clean = item.name.strip().lower()
            if full_name_clean:
                self._alias_index.setdefault(self._normalize(full_name_clean), []).append(item)

        self._is_loaded = True
        logger.info(f"FoodRepository loaded: {len(self._foods)} foods, {len(self._alias_index)} aliases indexed.")

    def count(self) -> int:
        return len(self._foods)

    def get_all_foods(self) -> List[FoodItem]:
        return self._foods

    def get_food_by_code(self, food_code: str) -> Optional[FoodItem]:
        return self._by_code.get(food_code.strip().lower())

    def get_food_by_id(self, food_id: str) -> Optional[FoodItem]:
        return self._by_id.get(food_id.strip().lower())

    def get_categories(self) -> List[str]:
        return sorted(list({f.category for f in self._foods if f.category}))

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))

    @staticmethod
    def _result(query: str, matches: List[FoodItem], match_type: str, confidence: float) -> FoodSearchResult:
        unique = list({item.food_code: item for item in matches}.values())
        if len(unique) == 1:
            return FoodSearchResult(
                status="found", query=query, food=unique[0], match_type=match_type,
                confidence=confidence
            )
        return FoodSearchResult(
            status="ambiguous", query=query, matches=unique, message=AMBIGUOUS_MESSAGE
        )

    def search_food(self, query: str, user_id: Optional[str] = None) -> FoodSearchResult:
        """Find a dataset record only when the match is sufficiently reliable."""
        normalized = self._normalize(query)
        if not normalized:
            return FoodSearchResult(status="not_found", query=query, message=NOT_FOUND_MESSAGE)

        exact_matches = self._alias_index.get(normalized, [])
        if exact_matches:
            if len(normalized.split()) == 1:
                exact_matches = [
                    *exact_matches,
                    *(
                        item for item in self._foods
                        if normalized in self._normalize(item.english_name).split()
                    )
                ]
            result = self._result(query, exact_matches, "exact", 1.0)
            self._log_result(result)
            return result

        custom_matches = self._search_custom_items(query, user_id=user_id)
        if custom_matches:
            result = self._result(query, custom_matches, "exact", 1.0)
            self._log_result(result)
            return result

        query_tokens = set(normalized.split())
        token_matches = [
            item for item in self._foods
            if query_tokens.issubset(set(self._normalize(item.english_name).split()))
        ]
        if token_matches:
            result = self._result(query, token_matches, "token", 0.9)
            self._log_result(result)
            return result

        scored = [
            (SequenceMatcher(None, normalized, self._normalize(item.english_name)).ratio(), item)
            for item in self._foods
        ]
        scored.sort(key=lambda candidate: candidate[0], reverse=True)
        if scored and scored[0][0] >= 0.88:
            best_score = scored[0][0]
            close_matches = [item for score, item in scored if best_score - score <= 0.04]
            result = self._result(query, close_matches, "fuzzy", best_score)
            self._log_result(result)
            return result

        logger.info("Food search: query=%r result=NOT_FOUND reason=no reliable INDB match", query)
        return FoodSearchResult(status="not_found", query=query, message=NOT_FOUND_MESSAGE)

    @staticmethod
    def _log_result(result: FoodSearchResult) -> None:
        if result.status == "found":
            logger.info(
                "Food search: query=%r result=FOUND matched_food=%r match_type=%s confidence=%.2f",
                result.query, result.food.name, result.match_type, result.confidence
            )
        else:
            logger.info(
                "Food search: query=%r result=AMBIGUOUS candidates=%s",
                result.query, [item.name for item in result.matches]
            )

    def find_food(self, query: str) -> Optional[FoodItem]:
        """Compatibility helper; ambiguous and unavailable queries return None."""
        result = self.search_food(query)
        return result.food if result.status == "found" else None

    def search_foods(self, query: str, limit: int = 20, category: Optional[str] = None, user_id: Optional[str] = None) -> List[FoodItem]:
        """Search foods with optional category filter for UI/Autocomplete."""
        q = query.strip().lower()
        results: List[Tuple[float, FoodItem]] = []
        all_items = self._foods + self._get_custom_foods(user_id)

        for item in all_items:
            if category and category.lower() != "all" and item.category.lower() != category.lower():
                continue

            score = 0.0
            name_lower = item.name.lower()
            if q in name_lower:
                score = 1.0 if q == name_lower else 0.8
            else:
                for alias in item.aliases:
                    if q in alias.lower():
                        score = max(score, 0.75)
                        break

            if score == 0.0 and len(q) >= 3:
                sim = SequenceMatcher(None, q, name_lower).ratio()
                if sim >= 0.5:
                    score = sim

            if score > 0:
                results.append((score, item))

        results.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in results[:limit]]

# Global singleton repository
food_repository = FoodRepository()
