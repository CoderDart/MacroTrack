import json
import re
from typing import Any, Dict, List, Optional

import networkx as nx


class NutritionKnowledgeGraph:
    """Builds an isolated graph from the food records selected for one query."""

    def build_query_graph(
        self,
        query: str,
        nutrient_label: Optional[str],
        results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        graph = nx.DiGraph()
        graph.add_node("query", label=f'Query: {query}', type="query")

        nutrient_id = None
        if nutrient_label:
            nutrient_id = f"nutrient:{self._slug(nutrient_label)}"
            graph.add_node(nutrient_id, label=nutrient_label, type="nutrient")
            graph.add_edge("query", nutrient_id, relation="targets")

        units = {
            "protein": ("Protein", "g"),
            "carbohydrates": ("Carbohydrates", "g"),
            "fat": ("Fat", "g"),
            "fiber": ("Fiber", "g"),
            "calories": ("Calories", "kcal"),
            "sugar": ("Free sugar", "g"),
            "sodium": ("Sodium", "mg"),
        }

        for result in results:
            food_id = result["food_id"]
            graph.add_node(
                food_id,
                label=result["food_name"],
                type="food",
                source="INDB",
                food_code=result["food_code"],
                category=result["category"],
                rank=result.get("rank"),
                value_per_100g=result.get("ranked_value_per_100g"),
            )
            if nutrient_id:
                graph.add_edge(nutrient_id, food_id, relation="ranked_by")
                metrics = [(result.get("ranked_nutrient"), result.get("ranked_value_per_100g"), result.get("unit"))]
            else:
                graph.add_edge("query", food_id, relation="matched")
                metrics = [
                    (label, result["nutrition_per_100g"].get(key), unit)
                    for key, (label, unit) in units.items()
                ]

            for label, value, unit in metrics:
                if label is None or value is None:
                    continue
                nutrition_id = f"nutrition:{food_id}:{self._slug(label)}"
                graph.add_node(
                    nutrition_id,
                    label=f"{label}: {value:.1f} {unit} / 100g",
                    type="nutrition",
                    value_per_100g=value,
                    unit=unit,
                    source="INDB",
                )
                graph.add_edge(food_id, nutrition_id, relation="has_nutrition")

        nodes = [
            {"id": node_id, **attributes}
            for node_id, attributes in graph.nodes(data=True)
        ]
        edges = [
            {"source": source, "target": target, **attributes}
            for source, target, attributes in graph.edges(data=True)
        ]
        return {"nodes": nodes, "edges": edges, "graphviz": self._to_graphviz(graph)}

    @staticmethod
    def _slug(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")

    @staticmethod
    def _to_graphviz(graph: nx.DiGraph) -> str:
        shapes = {"query": "oval", "nutrient": "diamond", "food": "box", "nutrition": "note"}
        lines = ["digraph INDBQuery {", "rankdir=LR;", 'node [fontname="Arial"];']
        for node_id, attributes in graph.nodes(data=True):
            identifier = json.dumps(str(node_id))
            label = json.dumps(str(attributes.get("label", node_id)))
            shape = shapes.get(attributes.get("type"), "box")
            lines.append(f"{identifier} [label={label}, shape={shape}];")
        for source, target, attributes in graph.edges(data=True):
            lines.append(
                f"{json.dumps(str(source))} -> {json.dumps(str(target))} "
                f"[label={json.dumps(str(attributes.get('relation', '')))}];"
            )
        lines.append("}")
        return "\n".join(lines)
