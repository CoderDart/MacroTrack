import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root if it exists
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

# Paths
DATA_DIR = ROOT_DIR / "data"
INDB_PATH = DATA_DIR / "indb_foods.json"
KG_PATH = DATA_DIR / "knowledge_graph.json"
LOCAL_DB_PATH = ROOT_DIR / "macrotrack_local.db"

# LLM Configuration
# User requested Gemini 3.5 Flash
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

# Episodic Memory (mem0)
MEM0_API_KEY = os.getenv("MEM0_API_KEY", "")
MEM0_USER_ID = os.getenv("MEM0_USER_ID", "default_user")

# Database (Supabase with Local SQLite fallback)
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# Knowledge Graph (Neo4j with In-Memory NetworkX fallback)
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# Server Config
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))

# Default Nutrition Goals
DEFAULT_GOALS = {
    "calories": 2200,
    "protein": 150.0,
    "carbs": 250.0,
    "fat": 70.0
}

# Default User Profile
DEFAULT_PROFILE = {
    "user_id": "default_user",
    "name": "Chirag",
    "age": 28,
    "gender": "male",
    "weight_kg": 75.0,
    "height_cm": 178.0,
    "activity_level": "moderate",  # sedentary, light, moderate, active, very_active
    "dietary_preference": "veg",    # veg, non-veg, ovo-veg, vegan
    "goal_archetype": "general",    # athlete, weight_loss, general, muscle_gain
    "meals_per_day": 3
}
