import logging
from typing import Dict, Any, List, Optional
from src.config import GOOGLE_API_KEY, GEMINI_MODEL
from src.agents.nutrition_lookup import nutrition_lookup
from src.database.storage import db

logger = logging.getLogger("macrotrack.feedback_agent")

class FeedbackAgent:
    """
    Feedback & Suggestion Agent for MacroTrack.
    Provides immediate real-time post-meal analysis, next-meal recommendations
    prioritizing Indian staples, and daily/weekly nutritional summaries tailored
    by user archetype (athlete, weight loss, general).
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

    def generate_realtime_feedback(
        self,
        user_id: str,
        meal_data: Dict[str, Any],
        daily_status: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Provides immediate feedback after a meal is logged, plus next-meal recommendations.
        """
        profile = db.get_user_profile(user_id)
        dietary = profile.get("dietary_preference", "veg")
        archetype = profile.get("goal_archetype", "general")

        consumed_meal_cals = meal_data.get("calories", 0.0)
        consumed_meal_prot = meal_data.get("protein", 0.0)
        rem_cals = daily_status["remaining"]["calories"]
        rem_prot = daily_status["remaining"]["protein"]
        rem_carb = daily_status["remaining"]["carbs"]
        rem_fat = daily_status["remaining"]["fat"]

        # Calculate macro ratio of the meal
        total_meal_macros = (meal_data.get("protein", 0) * 4) + (meal_data.get("carbs", 0) * 4) + (meal_data.get("fat", 0) * 9)
        prot_pct = round((meal_data.get("protein", 0) * 4 / total_meal_macros * 100), 1) if total_meal_macros > 0 else 0

        # Assess meal qualities
        strengths = []
        cautions = []
        if consumed_meal_prot >= 25.0:
            strengths.append(f"Excellent protein density ({consumed_meal_prot}g), stimulating muscle protein synthesis.")
        elif consumed_meal_prot < 10.0 and consumed_meal_cals > 300:
            cautions.append("Relatively low protein content for the caloric load. Consider pairing with curd, dal, or paneer.")

        if meal_data.get("fiber", 0) >= 6.0:
            strengths.append("High dietary fiber content promoting satiety and steady blood glucose.")

        if meal_data.get("fat", 0) > 25.0:
            cautions.append("High fat content observed; be mindful of added oil, butter, or fried items in subsequent meals.")

        # Next meal suggestions (Prioritizing Indian foods)
        next_meal_suggestions = self._recommend_next_meal(rem_cals, rem_prot, rem_carb, rem_fat, dietary, archetype)

        coach_assessment = f"Meal successfully logged: {consumed_meal_cals} kcal and {consumed_meal_prot}g protein. "
        if rem_prot > 0:
            coach_assessment += f"You have {rem_cals:.0f} kcal and {rem_prot:.1f}g protein remaining for today."
        else:
            coach_assessment += f"Target protein for today achieved! Remaining calories: {rem_cals:.0f} kcal."

        return {
            "meal_calories": consumed_meal_cals,
            "meal_protein": consumed_meal_prot,
            "protein_energy_ratio": f"{prot_pct}%",
            "coach_assessment": coach_assessment,
            "strengths": strengths if strengths else ["Balanced portion size logged."],
            "cautions": cautions,
            "next_meal_recommendations": next_meal_suggestions
        }

    def _recommend_next_meal(
        self,
        rem_cals: float,
        rem_prot: float,
        rem_carb: float,
        rem_fat: float,
        dietary: str,
        archetype: str
    ) -> List[Dict[str, Any]]:
        """
        Calculates complementary Indian food suggestions to hit remaining macro targets.
        """
        recommendations = []

        # High protein needed with limited calories
        if rem_prot >= 30.0:
            if dietary in ["non-veg", "ovo-veg"]:
                recommendations.append({
                    "suggestion": "Tandoori Chicken Breast or Boiled Egg Whites (4-5 whites)",
                    "why": f"Delivers ~25-33g pure protein with under 200 calories to hit your remaining {rem_prot:.0f}g protein target.",
                    "indian_staple": True
                })
            recommendations.append({
                "suggestion": "Soya Chunks Curry (1 bowl) or Raw Paneer Salad (100g)",
                "why": "High-protein Indian staples providing 18-24g bioavailable protein with low glycemic impact.",
                "indian_staple": True
            })
            recommendations.append({
                "suggestion": "1 Scoop Whey Protein in 200ml Toned Milk or Water",
                "why": "Rapid 25g protein infusion with minimal carbs and fat.",
                "indian_staple": False
            })

        elif rem_prot >= 15.0:
            recommendations.append({
                "suggestion": "Moong Dal Sprouts Salad with Lemon & Cucumber + 1 Bowl Dahi",
                "why": "Light meal providing ~12-15g protein, high fiber, and gut-friendly probiotics.",
                "indian_staple": True
            })
            recommendations.append({
                "suggestion": "2 Chapatis with 1 Bowl Dal Tadka",
                "why": "Classic balanced Indian staple providing ~13g protein and steady complex carbs.",
                "indian_staple": True
            })
        else:
            # Protein nearly met, needs balanced energy or light dinner
            if rem_cals > 400:
                recommendations.append({
                    "suggestion": "Moong Dal Khichdi with a side of Spiced Curd",
                    "why": "Comforting, easily digestible complete meal that fits cleanly into remaining energy budget.",
                    "indian_staple": True
                })
            else:
                recommendations.append({
                    "suggestion": "Warm Turmeric Milk (Haldi Doodh) or Plain Curd Bowl",
                    "why": "Light evening snack supporting nocturnal recovery and restful sleep.",
                    "indian_staple": True
                })

        return recommendations

    def generate_daily_summary(self, user_id: str, daily_status: Dict[str, Any]) -> str:
        """
        Generates a comprehensive daily summary report.
        """
        cals = daily_status["consumed"]["calories"]
        target_cals = daily_status["targets"]["calories"]
        prot = daily_status["consumed"]["protein"]
        target_prot = daily_status["targets"]["protein"]
        meals_logged = daily_status["meal_count"]

        prot_compliance = round((prot / target_prot * 100.0), 1) if target_prot else 0
        cal_compliance = round((cals / target_cals * 100.0), 1) if target_cals else 0

        summary = (
            f"Daily Nutrition Summary for {daily_status['date']}:\n"
            f"- Meals Logged: {meals_logged}\n"
            f"- Total Energy: {cals} / {target_cals} kcal ({cal_compliance}% of target)\n"
            f"- Protein: {prot}g / {target_prot}g ({prot_compliance}% achieved)\n"
            f"- Carbohydrates: {daily_status['consumed']['carbs']}g / {daily_status['targets']['carbs']}g\n"
            f"- Fat: {daily_status['consumed']['fat']}g / {daily_status['targets']['fat']}g\n"
        )

        if prot_compliance >= 90:
            summary += "\nOverall verdict: Outstanding discipline on protein intake! Keep up this consistency."
        elif prot_compliance >= 70:
            summary += "\nOverall verdict: Good daily intake. Try adding an extra bowl of curd, sprouts, or paneer to hit your protein ceiling."
        else:
            summary += "\nOverall verdict: Protein fell behind today. Plan high-protein breakfasts (eggs/poha with sprouts/cheela) tomorrow."

        return summary

    def generate_weekly_summary(self, user_id: str, weekly_status: Dict[str, Any]) -> str:
        """
        Generates a weekly review report.
        """
        days_active = weekly_status["days_active"]
        avg_cals = weekly_status["daily_averages"]["calories"]
        avg_prot = weekly_status["daily_averages"]["protein"]
        bal = weekly_status["net_weekly_balance"]

        report = (
            f"Weekly Nutrition Performance Report ({weekly_status['period']}):\n"
            f"- Active Logging Days: {days_active} / 7 days\n"
            f"- Daily Average Intake: {avg_cals} kcal | {avg_prot}g Protein\n"
            f"- Net Calorie Balance: {abs(bal['calorie_difference']):.0f} kcal {bal['status']}\n"
        )

        if days_active >= 5:
            report += "- Consistency Rating: Excellent (High data fidelity)\n"
        else:
            report += "- Consistency Rating: Moderate (Aim for continuous 7-day tracking for precise metabolic adjustments)\n"

        return report

# Global feedback agent instance
feedback_agent = FeedbackAgent()
