from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.agents.kg_agent import METRICS, kg_agent
from src.data.repository import food_repository


@pytest.mark.parametrize(
    ("query", "metric", "direction"),
    [
        ("high protein food", "protein", "DESC"),
        ("carb rich food", "carbohydrates", "DESC"),
        ("low calorie foods", "calories", "ASC"),
        ("Show foods that are low in calories", "calories", "ASC"),
        ("foods high in fiber", "fiber", "DESC"),
        ("What can I eat if I need more fiber?", "fiber", "DESC"),
    ],
)
def test_nutrient_query_ranks_actual_indb_values(query, metric, direction):
    result = kg_agent.answer_kg_question(query)

    assert result["status"] == "found"
    assert result["ranking"]["nutrient"] == METRICS[metric]["label"]
    assert result["ranking"]["direction"] == direction
    assert result["ranking"]["basis"] == "per 100g"
    values = [row["ranked_value_per_100g"] for row in result["results"]]
    assert values == sorted(values, reverse=direction == "DESC")

    food_nodes = {node["id"] for node in result["graph"]["nodes"] if node["type"] == "food"}
    assert food_nodes == {row["food_id"] for row in result["results"]}
    for row in result["results"]:
        food = food_repository.get_food_by_id(row["food_id"])
        assert food is not None
        assert food.food_code == row["food_code"]
        assert row["nutrition_per_100g"][metric] == round(
            getattr(food.per_100g, METRICS[metric]["field"]), 1
        )


def test_multi_constraint_query_uses_dataset_relative_cutoffs():
    result = kg_agent.answer_kg_question("high protein low fat foods")

    assert result["status"] == "found"
    thresholds = result["ranking"]["thresholds"]
    assert thresholds["protein"]["source"] == "dataset percentile"
    assert thresholds["fat"]["source"] == "dataset percentile"
    for row in result["results"]:
        assert row["nutrition_per_100g"]["protein"] >= thresholds["protein"]["value_per_100g"]
        assert row["nutrition_per_100g"]["fat"] <= thresholds["fat"]["value_per_100g"]

    protein_and_calories = kg_agent.answer_kg_question("foods high in protein and low in calories")
    assert protein_and_calories["status"] == "found"
    calorie_threshold = protein_and_calories["ranking"]["thresholds"]["calories"]["value_per_100g"]
    assert all(row["nutrition_per_100g"]["calories"] <= calorie_threshold for row in protein_and_calories["results"])

    explicit_max = kg_agent.answer_kg_question("foods under 100 calories")
    assert explicit_max["status"] == "found"
    assert explicit_max["ranking"]["direction"] == "ASC"
    assert all(row["nutrition_per_100g"]["calories"] <= 100 for row in explicit_max["results"])


def test_rice_filter_ranks_only_matching_indb_foods():
    result = kg_agent.answer_kg_question("rice based foods high in carbohydrates")

    assert result["status"] == "found"
    assert result["interpreted_intent"]["food_name"] == "rice"
    assert all("rice" in row["food_name"].casefold() for row in result["results"])
    values = [row["nutrition_per_100g"]["carbohydrates"] for row in result["results"]]
    assert values == sorted(values, reverse=True)


def test_unavailable_no_results_ambiguity_and_clarification_are_distinct():
    unavailable = kg_agent.answer_kg_question("avocado toast")
    assert unavailable["status"] == "not_found"
    assert unavailable["message"] == "I'm sorry, that food is not available in the INDB dataset."
    assert not [node for node in unavailable["graph"]["nodes"] if node["type"] == "food"]

    no_results = kg_agent.answer_kg_question("foods containing 200g protein per 100g")
    assert no_results["status"] == "no_results"
    assert no_results["message"] == "I couldn't find any foods in the INDB dataset matching those criteria."

    vague = kg_agent.answer_kg_question("I want something good")
    assert vague["status"] == "clarification"

    ambiguous = kg_agent.answer_kg_question("paneer")
    assert ambiguous["status"] == "ambiguous"
    assert any("Paneer kaathi roll" in name for name in ambiguous["candidates"])


def test_each_query_builds_a_fresh_graph_from_its_results():
    protein = kg_agent.answer_kg_question("high protein food")
    carbohydrates = kg_agent.answer_kg_question("carb rich food")
    protein_ids = {node["id"] for node in protein["graph"]["nodes"] if node["type"] == "food"}
    carb_ids = {node["id"] for node in carbohydrates["graph"]["nodes"] if node["type"] == "food"}

    assert protein_ids == {row["food_id"] for row in protein["results"]}
    assert carb_ids == {row["food_id"] for row in carbohydrates["results"]}
    assert protein_ids != carb_ids
    assert {edge["relation"] for edge in carbohydrates["graph"]["edges"]} <= {
        "targets", "ranked_by", "has_nutrition"
    }


def test_dashboard_query_input_renders_results_and_graph():
    dashboard_path = Path(__file__).resolve().parents[1] / "src" / "ui" / "dashboard.py"
    app = AppTest.from_file(dashboard_path, default_timeout=45).run()
    app.text_input(key="kg_question_input").set_value("carb rich food").run()

    assert not app.exception
    assert app.session_state["kg_query_result"]["status"] == "found"
    assert any("Ranked value / 100g" in frame.value.columns for frame in app.dataframe)
    assert len(app.get("graphviz_chart")) == 1