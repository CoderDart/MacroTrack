import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal, Optional

from src.data.repository import FoodRepository, food_repository
from src.data.types import AMBIGUOUS_MESSAGE, NOT_FOUND_MESSAGE
from src.graph.kg_engine import NutritionKnowledgeGraph

logger = logging.getLogger("macrotrack.kg_agent")

NO_RESULTS_MESSAGE = "I couldn't find any foods in the INDB dataset matching those criteria."
CLARIFICATION_MESSAGE = "What would you like to optimize for: protein, carbohydrates, calories, fat, or fiber?"

METRICS = {
    "protein": {"field": "protein_g", "label": "Protein", "unit": "g", "aliases": ("protein", "proteins")},
    "carbohydrates": {"field": "carbs_g", "label": "Carbohydrates", "unit": "g", "aliases": ("carbohydrates", "carbohydrate", "carbs", "carb")},
    "fat": {"field": "fat_g", "label": "Fat", "unit": "g", "aliases": ("fat", "fats")},
    "fiber": {"field": "fiber_g", "label": "Fiber", "unit": "g", "aliases": ("fiber", "fibre")},
    "calories": {"field": "calories", "label": "Calories", "unit": "kcal", "aliases": ("calories", "calorie", "kcal", "energy")},
    "sugar": {"field": "free_sugar_g", "label": "Free sugar", "unit": "g", "aliases": ("sugar", "sugars")},
    "sodium": {"field": "sodium_mg", "label": "Sodium", "unit": "mg", "aliases": ("sodium", "salt")},
}

HIGH_WORDS = {"high", "rich", "lots", "lot", "much", "more", "plenty"}
LOW_WORDS = {"low", "less", "little", "few", "fewer"}
STOP_WORDS = {
    "a", "an", "the", "what", "which", "show", "me", "give", "find", "list", "suggest",
    "recommend", "foods", "food", "with", "in", "of", "are", "is", "and", "but", "for", "that",
    "can", "i", "eat", "if", "need", "have", "has", "help", "reach", "target", "fastest",
    "quickly", "containing", "contains", "based",
    "indian", "per", "100g", "g", "mg", "kcal", "high", "rich", "lots", "lot", "much",
    "more", "plenty", "low", "less", "little", "few", "fewer", "not", "at", "least",
    "most", "minimum", "maximum", "min", "max", "under", "below", "above", "over",
    "than", "something", "anything", "good", "healthy", "best", "want", "to", "optimize",
}
VAGUE_WORDS = {"something", "anything", "good", "healthy", "best", "recommend", "suggest"}
@dataclass
class NutrientConstraint:
    nutrient: str
    comparison: Literal["high", "low"]
    threshold_per_100g: Optional[float] = None
    operator: Optional[Literal["min", "max"]] = None


@dataclass
class FoodQueryIntent:
    raw_query: str
    nutrient: Optional[str] = None
    comparison: Optional[Literal["high", "low"]] = None
    food_name: Optional[str] = None
    constraints: List[NutrientConstraint] = field(default_factory=list)
    clarification_needed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_query": self.raw_query,
            "nutrient": self.nutrient,
            "comparison": self.comparison,
            "food_name": self.food_name,
            "constraints": [asdict(constraint) for constraint in self.constraints],
            "clarification_needed": self.clarification_needed,
        }


class KnowledgeGraphAgent:
    """Interprets food queries, ranks only INDB records, then builds their graph."""

    def __init__(self, repository: FoodRepository = food_repository):
        self.repository = repository
        self.graph_builder = NutritionKnowledgeGraph()
        self._records = []
        self._sorted_values: Dict[str, List[float]] = {metric: [] for metric in METRICS}
        for food in repository.get_all_foods():
            values = {
                metric: float(getattr(food.per_100g, definition["field"]))
                for metric, definition in METRICS.items()
            }
            searchable = " ".join((food.name, food.english_name, *food.aliases)).casefold()
            record = {"food": food, "values": values, "searchable": self._normalize(searchable)}
            self._records.append(record)
            for metric, value in values.items():
                self._sorted_values[metric].append(value)
        for values in self._sorted_values.values():
            values.sort()

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))

    @staticmethod
    def _canonical_metric(value: str) -> Optional[str]:
        normalized = value.casefold()
        for metric, definition in METRICS.items():
            if normalized in definition["aliases"]:
                return metric
        return None

    def understand_query(self, query: str) -> FoodQueryIntent:
        normalized = self._normalize(query)
        word_matches = list(re.finditer(r"[a-z0-9]+", normalized))
        nutrient_occurrences = []
        for metric, definition in METRICS.items():
            aliases = sorted(definition["aliases"], key=len, reverse=True)
            metric_matches = []
            for alias in aliases:
                match = re.search(rf"\b{re.escape(alias)}\b", normalized)
                if match:
                    metric_matches.append(match)
            if metric_matches:
                match = min(metric_matches, key=lambda candidate: candidate.start())
                word_index = next(
                    (index for index, word in enumerate(word_matches) if word.start() <= match.start() < word.end()),
                    0,
                )
                nutrient_occurrences.append((match.start(), word_index, metric))
        nutrient_occurrences.sort()

        comparison_positions = [
            (index, word.group())
            for index, word in enumerate(word_matches)
            if word.group() in HIGH_WORDS | LOW_WORDS
        ]
        constraints: List[NutrientConstraint] = []
        for _, nutrient_index, metric in nutrient_occurrences:
            nearby = [
                (abs(index - nutrient_index), index, word)
                for index, word in comparison_positions
                if abs(index - nutrient_index) <= 3
            ]
            comparison: Literal["high", "low"] = "high"
            if nearby:
                _, nearest_index, nearest_word = min(nearby)
                comparison = "low" if nearest_word in LOW_WORDS else "high"
                if nearest_word == "much" and nearest_index > 0 and word_matches[nearest_index - 1].group() == "not":
                    comparison = "low"
            if not any(existing.nutrient == metric for existing in constraints):
                constraints.append(NutrientConstraint(nutrient=metric, comparison=comparison))

        for match in re.finditer(
            r"\b(?P<operator>at least|minimum|min|more than|over|above|containing|contains|"
            r"at most|maximum|max|less than|under|below)\s+"
            r"(?P<value>\d+(?:\.\d+)?)\s*(?:g|mg|kcal)?\s*(?:of\s*)?"
            r"(?P<metric>carbohydrates?|carbs?|proteins?|fats?|fiber|fibre|calories?|kcal|sugars?|sodium)\b",
            normalized,
        ):
            metric = self._canonical_metric(match.group("metric"))
            if not metric:
                continue
            operator = "max" if match.group("operator") in {"at most", "maximum", "max", "less than", "under", "below"} else "min"
            constraint = next((item for item in constraints if item.nutrient == metric), None)
            if constraint is None:
                constraint = NutrientConstraint(nutrient=metric, comparison="low" if operator == "max" else "high")
                constraints.append(constraint)
            constraint.comparison = "low" if operator == "max" else "high"
            constraint.threshold_per_100g = float(match.group("value"))
            constraint.operator = operator

        nutrient_tokens = {
            token
            for definition in METRICS.values()
            for alias in definition["aliases"]
            for token in alias.split()
        }
        filter_tokens = [
            word.group()
            for word in word_matches
            if word.group() not in STOP_WORDS | nutrient_tokens
            and not re.fullmatch(r"\d+(?:\.\d+)?(?:g|mg|kcal)?", word.group())
        ]
        food_name = " ".join(filter_tokens) or None
        vague = bool(filter_tokens) and set(filter_tokens).issubset(VAGUE_WORDS)
        clarification_needed = not constraints and (not food_name or vague)
        primary = next((item for item in constraints if item.comparison == "high"), constraints[0] if constraints else None)
        return FoodQueryIntent(
            raw_query=query,
            nutrient=primary.nutrient if primary else None,
            comparison=primary.comparison if primary else None,
            food_name=food_name,
            constraints=constraints,
            clarification_needed=clarification_needed,
        )

    def _quantile(self, metric: str, percentile: int) -> float:
        values = self._sorted_values[metric]
        return values[round((len(values) - 1) * percentile / 100)]

    def _record_result(self, record: Dict[str, Any], rank: Optional[int], metric: Optional[str]) -> Dict[str, Any]:
        food = record["food"]
        values = record["values"]
        metric_definition = METRICS.get(metric) if metric else None
        ranked_value = values[metric] if metric else None
        reason = None
        if metric_definition and rank is not None:
            reason = (
                f"Rank #{rank} by {metric_definition['label']}: "
                f"{ranked_value:.1f} {metric_definition['unit']} / 100g"
            )
        return {
            "food_id": food.id,
            "food_code": food.food_code,
            "food_name": food.name,
            "category": food.category,
            "dietary": food.dietary,
            "source": "INDB",
            "rank": rank,
            "ranked_nutrient": metric_definition["label"] if metric_definition else None,
            "ranked_value_per_100g": round(ranked_value, 1) if ranked_value is not None else None,
            "unit": metric_definition["unit"] if metric_definition else None,
            "nutrition_per_100g": {key: round(value, 1) for key, value in values.items()},
            "selection_reason": reason or "Matched INDB food record",
            "protein_density_score": round(values["protein"] / max(values["calories"], 1.0), 3),
            "key_nutrients": [
                METRICS[name]["label"] for name, value in values.items()
                if name != "calories" and value > 0
            ],
        }

    def _empty_graph(self, query: str) -> Dict[str, Any]:
        return self.graph_builder.build_query_graph(query, None, [])

    def _base_response(self, query: str, intent: FoodQueryIntent, status: str, message: Optional[str] = None) -> Dict[str, Any]:
        return {
            "query": query,
            "status": status,
            "message": message,
            "interpreted_intent": intent.to_dict(),
            "dataset": "Anuvaad INDB",
            "results": [],
            "graph": self._empty_graph(query),
        }

    def answer_kg_question(
        self,
        question: str,
        selected_food: Optional[str] = None,
        dietary_preference: Optional[str] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        intent = self.understand_query(question)
        logger.info("INDB graph query=%r intent=%s", question, intent.to_dict())

        if intent.clarification_needed:
            return self._base_response(question, intent, "clarification", CLARIFICATION_MESSAGE)

        if not intent.constraints:
            search = self.repository.search_food(intent.food_name or question)
            if search.status == "not_found":
                return self._base_response(question, intent, "not_found", NOT_FOUND_MESSAGE)
            if search.status == "ambiguous":
                candidates = search.matches
                if selected_food and any(food.name == selected_food for food in candidates):
                    selected = next(food for food in candidates if food.name == selected_food)
                else:
                    response = self._base_response(question, intent, "ambiguous", AMBIGUOUS_MESSAGE)
                    response["candidates"] = [food.name for food in candidates]
                    return response
            else:
                selected = search.food
                if selected_food and selected and selected.name != selected_food:
                    response = self._base_response(question, intent, "ambiguous", AMBIGUOUS_MESSAGE)
                    response["candidates"] = [selected.name]
                    return response
            record = next((item for item in self._records if item["food"].food_code == selected.food_code), None)
            results = [self._record_result(record, 1, None)] if record else []
            graph = self.graph_builder.build_query_graph(question, None, results)
            response = self._base_response(question, intent, "found")
            response["results"] = results
            response["graph"] = graph
            return response

        if intent.food_name:
            entity_match = self.repository.search_food(intent.food_name)
            if entity_match.status == "not_found":
                return self._base_response(question, intent, "not_found", NOT_FOUND_MESSAGE)

        records = list(self._records)
        if intent.food_name:
            filter_tokens = set(intent.food_name.split())
            records = [record for record in records if filter_tokens.issubset(set(record["searchable"].split()))]
        if dietary_preference and dietary_preference != "all":
            if dietary_preference == "ovo-veg":
                allowed = {"veg", "ovo-veg"}
            else:
                allowed = {dietary_preference}
            records = [record for record in records if record["food"].dietary in allowed]

        primary_metric = intent.nutrient or intent.constraints[0].nutrient
        thresholds: Dict[str, Dict[str, Any]] = {}
        for constraint in intent.constraints:
            threshold = constraint.threshold_per_100g
            operator = constraint.operator
            if threshold is None and len(intent.constraints) > 1:
                percentile = 75 if constraint.comparison == "high" else 25
                threshold = self._quantile(constraint.nutrient, percentile)
                operator = "min" if constraint.comparison == "high" else "max"
            if threshold is not None and operator:
                value_field = constraint.nutrient
                records = [
                    record for record in records
                    if (record["values"][value_field] >= threshold if operator == "min"
                        else record["values"][value_field] <= threshold)
                ]
                thresholds[constraint.nutrient] = {
                    "operator": operator,
                    "value_per_100g": round(threshold, 1),
                    "source": "user-specified" if constraint.threshold_per_100g is not None else "dataset percentile",
                }

        descending = intent.comparison != "low"
        records.sort(key=lambda record: (
            -record["values"][primary_metric] if descending else record["values"][primary_metric],
            record["food"].food_code,
        ))
        records = records[:max(1, min(limit, 25))]
        if not records:
            return self._base_response(question, intent, "no_results", NO_RESULTS_MESSAGE)

        results = [self._record_result(record, index, primary_metric) for index, record in enumerate(records, 1)]
        definition = METRICS[primary_metric]
        direction = "DESC" if descending else "ASC"
        ranking = {
            "nutrient": definition["label"],
            "basis": "per 100g",
            "direction": direction,
            "sort": f"{primary_metric} per 100g {direction}",
            "thresholds": thresholds,
        }
        graph = self.graph_builder.build_query_graph(question, definition["label"], results)
        response = self._base_response(question, intent, "found")
        response.update({
            "results": results,
            "graph": graph,
            "ranking": ranking,
            "clinical_insight": f"Dataset records ranked by {definition['label'].lower()} per 100g ({direction.lower()}).",
            "top_foods": results if primary_metric == "protein" else [],
        })
        logger.info(
            "INDB graph result=%s ranking=%s results=%s",
            response["status"], ranking, [row["food_name"] for row in results]
        )
        return response

    def query_fastest_protein_foods(self, dietary_preference: Optional[str] = None) -> Dict[str, Any]:
        result = self.answer_kg_question(
            "high protein foods", dietary_preference=dietary_preference, limit=6
        )
        return {
            "query": "high protein foods",
            "metric": "Protein per 100g",
            "dietary_filter": dietary_preference or "all",
            "top_foods": result["results"],
            "clinical_insight": result.get("clinical_insight"),
            "graph": result["graph"],
        }

    def explain_food_mechanism(self, food_name: str) -> Dict[str, Any]:
        search = self.repository.search_food(food_name)
        if search.status != "found" or not search.food:
            return {
                "food": food_name,
                "found": False,
                "status": search.status,
                "message": search.message or NOT_FOUND_MESSAGE,
                "candidates": [item.name for item in search.matches],
            }
        food = search.food
        values = food.per_100g.to_dict()
        pathway_details = [
            {"nutrient": METRICS[metric]["label"], "value_per_100g": values[definition["field"]], "unit": definition["unit"]}
            for metric, definition in METRICS.items()
            if metric != "calories" and values[definition["field"]] > 0
        ]
        return {
            "food": food.name,
            "found": True,
            "category": food.category,
            "dietary": food.dietary,
            "pathway_details": pathway_details,
            "clinical_summary": f"INDB nutrient composition for {food.name} per 100g.",
        }


kg_agent = KnowledgeGraphAgent()
