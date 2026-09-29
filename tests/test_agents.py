import pytest
from src.data.repository import FoodRepository, food_repository
from src.data.types import FoodItem
from src.agents.nutrition_lookup import nutrition_lookup
from src.agents.goal_tracker import goal_tracker
from src.agents.meal_parser import meal_parser
from src.agents.feedback_agent import feedback_agent
from src.agents.reminder_agent import reminder_agent
from src.agents.kg_agent import kg_agent
from src.agents.coordinator import coordinator
from src.database.storage import db

def test_anuvaad_csv_data_layer():
    # Verify Anuvaad CSV loads 1014 foods
    assert food_repository.count() == 1014
    assert len(food_repository.get_categories()) >= 3

    # Test lookup of staples
    roti = food_repository.find_food("Chapati/Roti")
    assert roti is not None
    assert "Chapati" in roti.name or "Roti" in roti.name

    dal = food_repository.search_food("dal")
    assert dal.status == "ambiguous"
    assert any("Mixed dal" in item.name for item in dal.matches)

def test_anuvaad_100g_nutrition_calculation():
    # Test 100g calculation
    nutr = nutrition_lookup.calculate_item_nutrition("Chapati/Roti", quantity=2.0, unit="100g")
    assert nutr["found"] is True
    assert nutr["status"] == "found"
    assert nutr["calories"] > 150
    assert nutr["protein_g"] > 5.0
    assert nutr["database_source"] == "Anuvaad INDB 2024.11"

def test_missing_food_safe_response():
    # Non-existent item must return found=False and explicit apology message
    nutr = nutrition_lookup.calculate_item_nutrition("nonexistent_unknown_dish_xyz", quantity=1.0)
    assert nutr["found"] is False
    assert nutr["calories"] == 0.0
    assert nutr["protein_g"] == 0.0
    assert nutr["status"] == "not_found"
    assert nutr["message"] == "I'm sorry, that food is not available in the INDB dataset."

def test_food_search_strict_match_contract():
    expected = "Lemon rice (Pulihora, Elumichai sadam, Chitranna)"
    for query in ("Lemon Rice", "LEMON RICE", "lemon-rice"):
        result = food_repository.search_food(query)
        assert result.status == "found"
        assert result.food.name == expected
        assert result.match_type == "exact"
        assert result.confidence == 1.0

    missing = food_repository.search_food("avocado toast")
    assert missing.status == "not_found"
    assert missing.message == "I'm sorry, that food is not available in the INDB dataset."

    ambiguous = food_repository.search_food("rice")
    assert ambiguous.status == "ambiguous"
    assert len(ambiguous.matches) > 1
    assert any("Lemon rice" in item.name for item in ambiguous.matches)

    paneer = food_repository.search_food("paneer")
    assert paneer.status == "ambiguous"
    assert any("Paneer kaathi roll" in item.name for item in paneer.matches)

    unrelated = food_repository.search_food("lemon rice nope")
    assert unrelated.status == "not_found"
    assert unrelated.food is None
    fuzzy = food_repository.search_food("lemon rcie")
    assert fuzzy.status == "found"
    assert fuzzy.match_type == "fuzzy"
    assert fuzzy.confidence >= 0.88

    class ColdCoffeeOnlyLoader:
        def load_dataset(self):
            return [FoodItem(
                id="anuvaad_cold_coffee",
                food_code="cold_coffee",
                name="Cold Coffee with Ice Cream",
                english_name="Cold Coffee with Ice Cream"
            )]

    isolated_repository = FoodRepository(loader=ColdCoffeeOnlyLoader())
    assert isolated_repository.search_food("Lemon Rice").status == "not_found"

def test_unavailable_meal_is_not_logged(monkeypatch):
    monkeypatch.setattr(meal_parser, "parse_meal", lambda **kwargs: {
        "detected_modality": "text",
        "meal_type": "lunch",
        "foods": [{"food_name": "avocado toast", "quantity": 1, "unit": "100g"}]
    })
    user_id = "strict_unavailable_meal_test"
    result = coordinator.process_and_log_meal(user_id=user_id, text_input="avocado toast")
    assert result["success"] is False
    assert result["logged"] is False
    assert result["message"] == "I'm sorry, that food is not available in the INDB dataset."
    assert db.get_all_meals(user_id) == []

def test_ambiguous_food_is_not_logged(monkeypatch):
    monkeypatch.setattr(meal_parser, "parse_meal", lambda **kwargs: {
        "detected_modality": "text",
        "meal_type": "lunch",
        "foods": [{"food_name": "rice", "quantity": 1, "unit": "100g"}]
    })
    user_id = "strict_ambiguous_meal_test"
    result = coordinator.process_and_log_meal(user_id=user_id, text_input="rice")
    assert result["success"] is False
    assert result["status"] == "ambiguous"
    assert result["candidates"]
    assert db.get_all_meals(user_id) == []

def test_goal_tracker_auto_calc():
    profile = {
        "age": 28,
        "gender": "male",
        "weight_kg": 75.0,
        "height_cm": 178.0,
        "activity_level": "moderate",
        "goal_archetype": "general"
    }
    goals = goal_tracker.calculate_auto_goals(profile)
    assert goals["bmr"] > 1600
    assert goals["tdee"] > 2400
    assert goals["protein"] >= 100.0


def test_custom_food_search_and_logging_round_trip():
    user_id = "custom_food_user"
    db.delete_custom_food_by_user(user_id)
    custom = db.save_custom_food({
        "user_id": user_id,
        "id": user_id,
        "name": "My Morning Oats",
        "description": "100g oats, 1 scoop whey, 1 banana and 1 teaspoon peanut butter",
        "nutrition_basis": "serving",
        "serving_size": 1.0,
        "serving_name": "1 bowl",
        "nutrition": {
            "calories": 650,
            "protein": 40,
            "carbohydrates": 75,
            "fat": 20,
            "fiber": 10,
            "sugar": 15,
            "sodium": 200
        }
    })

    search_result = food_repository.search_food("My Morning Oats")
    assert search_result.status == "found"
    assert search_result.food.source == "user_custom"
    assert search_result.food.name == "My Morning Oats"

    nutrition = nutrition_lookup.calculate_item_nutrition("My Morning Oats", quantity=1.0, unit="serving")
    assert nutrition["found"] is True
    assert nutrition["calories"] == 650.0
    assert nutrition["protein_g"] == 40.0
    assert nutrition["carbs_g"] == 75.0
    assert nutrition["fat_g"] == 20.0

    meal_total = nutrition_lookup.compute_meal_total([{"food_name": "My Morning Oats", "quantity": 0.5, "unit": "serving"}])
    assert meal_total["status"] == "found"
    assert meal_total["calories"] == 325.0
    assert meal_total["protein"] == 20.0
    assert meal_total["carbs"] == 37.5
    assert meal_total["fat"] == 10.0
    assert custom["source"] == "user_custom"


def test_custom_food_defaults_to_one_serving_when_quantity_not_stated():
    parsed = meal_parser._parse_heuristic("anabolic bowl", modality="text")
    assert parsed["foods"][0]["quantity"] == 1.0
    assert parsed["foods"][0]["unit"] == "serving"


def test_meal_parser_heuristic():
    text = "2 chapatis with 1 bowl dal and 100g paneer"
    res = meal_parser._parse_heuristic(text, modality="text")
    assert len(res["foods"]) >= 2
    food_names = [f["food_name"] for f in res["foods"]]
    assert any("chapati" in n or "roti" in n for n in food_names)
    assert any("dal" in n for n in food_names)

def test_adaptive_reminder_shift():
    user_id = "test_reminder_user"
    db.clear_user_data(user_id)
    reminder_agent.get_schedule_for_user(user_id)
    res = reminder_agent.adapt_schedule_on_meal_logged(user_id, "Lunch", "15:30")
    assert res["adaptive_shift_applied"] is True
    assert res["slippage_minutes"] >= 100
    assert len(res["shifts"]) > 0

def test_knowledge_graph_agent():
    top_protein = kg_agent.query_fastest_protein_foods()
    assert len(top_protein["top_foods"]) > 0
    assert top_protein["top_foods"][0]["ranked_nutrient"] == "Protein"
    assert top_protein["top_foods"][0]["ranked_value_per_100g"] > 0
    assert top_protein["top_foods"][0]["source"] == "INDB"

    paneer_path = kg_agent.explain_food_mechanism("Paneer, apple and pineapple salad")
    assert paneer_path["found"] is True
    assert len(paneer_path["pathway_details"]) > 0

def test_coordinator_end_to_end_swarm(monkeypatch):
    user_id = "test_swarm_user"
    db.clear_user_data(user_id)
    monkeypatch.setattr(meal_parser, "parse_meal", lambda **kwargs: {
        "detected_modality": "text",
        "meal_type": "lunch",
        "foods": [
            {"food_name": "Chapati/Roti", "quantity": 2, "unit": "100g"},
            {"food_name": "Lemon Rice", "quantity": 1, "unit": "100g"}
        ]
    })

    res = coordinator.process_and_log_meal(
        user_id=user_id,
        text_input="2 chapatis and 1 bowl dal",
        explicit_meal_type="lunch",
        log_time_str="13:15"
    )
    assert res["success"] is True
    assert res["nutrition_totals"]["calories"] > 100
    assert res["nutrition_totals"]["protein"] > 5
    assert len(res["agent_swarm_traces"]) == 7
    assert "coach_assessment" in res["feedback"]
