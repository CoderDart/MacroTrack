import pytest
from fastapi.testclient import TestClient
from src.api.app import app

client = TestClient(app)

def test_root_endpoint():
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "operational"

def test_parse_meal_endpoint(monkeypatch):
    from src.api.routes import meal_parser
    monkeypatch.setattr(meal_parser, "parse_meal", lambda **kwargs: {
        "detected_modality": "text",
        "meal_type": "lunch",
        "foods": [{"food_name": "Lemon Rice", "quantity": 1, "unit": "100g"}]
    })
    resp = client.post("/api/meals/parse", json={"text": "2 chapatis with 1 bowl dal", "is_packaged_label": False})
    assert resp.status_code == 200
    data = resp.json()
    assert "nutrition_totals" in data
    assert data["nutrition_totals"]["calories"] > 100

def test_log_meal_text_endpoint(monkeypatch):
    from src.api.routes import meal_parser
    monkeypatch.setattr(meal_parser, "parse_meal", lambda **kwargs: {
        "detected_modality": "text",
        "meal_type": "breakfast",
        "foods": [{"food_name": "Lemon Rice", "quantity": 1, "unit": "100g"}]
    })
    resp = client.post("/api/meals/log", json={
        "user_id": "test_api_user",
        "text": "1 bowl curd and 2 boiled eggs",
        "meal_type": "breakfast"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "nutrition_totals" in data
    assert "feedback" in data

def test_food_match_endpoint_statuses():
    found = client.get("/api/foods/match", params={"query": "LEMON-RICE"}).json()
    assert found["status"] == "found"
    assert found["food"]["name"].startswith("Lemon rice")

    ambiguous = client.get("/api/foods/match", params={"query": "rice"}).json()
    assert ambiguous["status"] == "ambiguous"
    assert len(ambiguous["matches"]) > 1

    missing = client.get("/api/foods/match", params={"query": "avocado toast"}).json()
    assert missing["status"] == "not_found"
    assert missing["message"] == "I'm sorry, that food is not available in the INDB dataset."

def test_parse_endpoint_returns_unavailable_message(monkeypatch):
    from src.api.routes import meal_parser
    monkeypatch.setattr(meal_parser, "parse_meal", lambda **kwargs: {
        "detected_modality": "text",
        "meal_type": "snack",
        "foods": [{"food_name": "avocado toast", "quantity": 1, "unit": "100g"}]
    })
    response = client.post("/api/meals/parse", json={"text": "avocado toast"})
    totals = response.json()["nutrition_totals"]
    assert totals["status"] == "not_found"
    assert totals["message"] == "I'm sorry, that food is not available in the INDB dataset."

def test_get_and_set_goals_endpoint():
    # Set goals
    resp_set = client.post("/api/goals", json={
        "user_id": "test_api_user",
        "calories": 2400,
        "protein": 160.0,
        "carbs": 260.0,
        "fat": 75.0
    })
    assert resp_set.status_code == 200
    # Get goals
    resp_get = client.get("/api/goals?user_id=test_api_user")
    assert resp_get.status_code == 200
    data = resp_get.json()
    assert data["calories"] == 2400
    assert data["protein"] == 160.0

def test_kg_query_endpoint():
    resp = client.post("/api/knowledge-graph/query", json={
        "question": "Which foods help me reach protein target fastest?"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "top_foods" in data

def test_whatsapp_webhook_endpoint(monkeypatch):
    from src.api.routes import meal_parser
    monkeypatch.setattr(meal_parser, "parse_meal", lambda **kwargs: {
        "detected_modality": "text",
        "meal_type": "lunch",
        "foods": [{"food_name": "Lemon Rice", "quantity": 1, "unit": "100g"}]
    })
    resp = client.post("/api/webhook/whatsapp", json={
        "From": "whatsapp:+919876543210",
        "Body": "2 chapatis and 1 bowl dal tadka"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "response_message" in data
    assert "MacroTrack Meal Logged" in data["response_message"]

def test_graphql_endpoint():
    query = """
    query {
      goals(userId: "test_api_user") {
        calories
        protein
      }
    }
    """
    resp = client.post("/graphql", json={"query": query})
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert "goals" in data["data"]
