import pytest
from src.agents.nutrition_lookup import nutrition_lookup
from src.agents.goal_tracker import goal_tracker
from src.agents.meal_parser import meal_parser
from src.agents.feedback_agent import feedback_agent
from src.agents.reminder_agent import reminder_agent
from src.agents.kg_agent import kg_agent
from src.agents.coordinator import coordinator
from src.database.storage import db

def test_indb_nutrition_lookup():
    # Test looking up chapati
    chapati = nutrition_lookup.lookup_food("roti")
    assert chapati is not None
    assert "Chapati" in chapati["name"]

    # Test portion calculation for 2 chapatis
    nutr = nutrition_lookup.calculate_item_nutrition("roti", quantity=2, unit="piece")
    assert nutr["calories"] > 200
    assert nutr["protein_g"] >= 7.0

    # Test dal lookup
    dal = nutrition_lookup.lookup_food("dal tadka")
    assert dal is not None

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

def test_meal_parser_heuristic():
    text = "2 chapatis with 1 bowl dal tadka and 100g paneer"
    res = meal_parser._parse_heuristic(text, modality="text")
    assert len(res["foods"]) >= 2
    food_names = [f["food_name"] for f in res["foods"]]
    assert any("chapati" in n or "roti" in n for n in food_names)
    assert any("dal" in n for n in food_names)

def test_adaptive_reminder_shift():
    # Simulate lunch logged 150 minutes late at 15:30 (scheduled at 13:00)
    user_id = "test_reminder_user"
    reminder_agent.get_schedule_for_user(user_id)
    res = reminder_agent.adapt_schedule_on_meal_logged(user_id, "Lunch", "15:30")
    assert res["adaptive_shift_applied"] is True
    assert res["slippage_minutes"] >= 100
    assert len(res["shifts"]) > 0

def test_knowledge_graph_agent():
    # Test protein density query
    top_protein = kg_agent.query_fastest_protein_foods()
    assert len(top_protein["top_foods"]) > 0
    # Boiled Egg White or Whey Protein should be top
    assert top_protein["top_foods"][0]["protein_density_score"] > 0.1

    # Test mechanistic pathway explanation
    paneer_path = kg_agent.explain_food_mechanism("paneer")
    assert paneer_path["found"] is True
    assert len(paneer_path["pathway_details"]) > 0

def test_coordinator_end_to_end_swarm():
    user_id = "test_swarm_user"
    db.clear_user_data(user_id)

    res = coordinator.process_and_log_meal(
        user_id=user_id,
        text_input="2 chapatis and 1 bowl dal tadka",
        explicit_meal_type="lunch",
        log_time_str="13:15"
    )
    assert res["success"] is True
    assert res["nutrition_totals"]["calories"] > 250
    assert res["nutrition_totals"]["protein"] > 10
    assert len(res["agent_swarm_traces"]) == 7
    assert "coach_assessment" in res["feedback"]
