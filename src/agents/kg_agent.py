import logging
from typing import Dict, Any, List, Optional
from src.graph.kg_engine import kg
from src.config import GOOGLE_API_KEY, GEMINI_MODEL

logger = logging.getLogger("macrotrack.kg_agent")

class KnowledgeGraphAgent:
    """
    Knowledge Graph Agent for MacroTrack.
    Queries and reasons over the Nutrition Knowledge Graph (Foods -> Nutrients -> Health Outcomes -> User Goals).
    Provides clinical insights and answers natural language questions like:
    'Which foods help me reach protein target fastest?' or 'Why is moong dal recommended for fat loss?'
    """
    def __init__(self):
        self.client = None
        self._init_gemini()

    def _init_gemini(self):
        if not GOOGLE_API_KEY:
            return
        try:
            from google import genai
            self.client = genai.Client(api_key=GOOGLE_API_KEY)
        except Exception:
            self.client = None

    def query_fastest_protein_foods(self, dietary_preference: Optional[str] = None) -> Dict[str, Any]:
        """
        Answers: 'Which foods help me reach protein target fastest?'
        Returns foods ranked by protein-to-calorie density score.
        """
        leaderboard = kg.get_protein_density_leaderboard(dietary_preference)
        top_picks = leaderboard[:6]
        insight = (
            "Ranked by Protein-to-Calorie Density (g protein per kcal). "
            f"Top food: {top_picks[0]['food_name']} delivers maximum amino acids with lowest caloric overhead."
        )
        return {
            "query": "Which foods help me reach protein target fastest?",
            "metric": "Protein Density (g protein / kcal)",
            "dietary_filter": dietary_preference or "all",
            "top_foods": top_picks,
            "clinical_insight": insight
        }

    def explain_food_mechanism(self, food_name: str) -> Dict[str, Any]:
        """
        Traces how a specific food impacts health outcomes and user goals.
        """
        pathway = kg.explain_food_pathway(food_name)
        if not pathway:
            return {
                "food": food_name,
                "found": False,
                "explanation": f"No knowledge graph pathway currently mapped for '{food_name}'."
            }

        text_explanation = f"Mechanistic Pathway for {pathway['food_name']}:\n"
        for p in pathway["pathways"]:
            text_explanation += (
                f"• {pathway['food_name']} {p['food_relation']} {p['nutrient']} "
                f"→ {p['outcome_relation']} {p['health_outcome']} "
                f"→ {p['goal_relation']} {p['target_goal']}.\n"
            )

        return {
            "food": pathway["food_name"],
            "found": True,
            "category": pathway["category"],
            "dietary": pathway["dietary"],
            "pathway_details": pathway["pathways"],
            "clinical_summary": text_explanation.strip()
        }

    def answer_kg_question(self, question: str) -> Dict[str, Any]:
        """
        Natural Language QA over the Knowledge Graph.
        """
        q_lower = question.lower()

        if "protein" in q_lower and ("fastest" in q_lower or "best" in q_lower or "reach" in q_lower):
            dietary = "veg" if "veg" in q_lower and "non" not in q_lower else None
            return self.query_fastest_protein_foods(dietary)

        if "why" in q_lower or "how" in q_lower or "benefit" in q_lower or "mechanism" in q_lower:
            # Check for known food names in question
            for food_id, data in kg.graph.nodes(data=True):
                if data.get("type") == "Food":
                    name = data.get("label", "").lower()
                    if name in q_lower or any(word in q_lower for word in name.split() if len(word) > 3):
                        return self.explain_food_mechanism(name)

        if "weight loss" in q_lower or "fat loss" in q_lower:
            foods = kg.query_foods_for_goal("goal_weight_loss")
            return {
                "query": question,
                "goal": "Weight Loss & Fat Loss",
                "recommended_foods": foods,
                "clinical_insight": "Selected foods optimize gastric satiety and blunt postprandial insulin surges via dietary fiber and slow digestion."
            }

        if "muscle" in q_lower or "hypertrophy" in q_lower:
            foods = kg.query_foods_for_goal("goal_muscle_gain")
            return {
                "query": question,
                "goal": "Muscle Hypertrophy & Protein Synthesis",
                "recommended_foods": foods,
                "clinical_insight": "Foods rich in bioavailable Leucine and Casein directly trigger muscle protein synthesis (MPS) via mTOR pathway activation."
            }

        # General traversal query
        foods = kg.query_foods_for_goal(question)
        return {
            "query": question,
            "matched_foods": foods,
            "clinical_insight": "Graph traversal linked nutrients and physiological outcomes matching your inquiry."
        }

# Global knowledge graph agent instance
kg_agent = KnowledgeGraphAgent()
