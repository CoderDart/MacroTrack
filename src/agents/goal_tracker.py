import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
from src.database.storage import db
from src.config import DEFAULT_GOALS

logger = logging.getLogger("macrotrack.goal_tracker")

class GoalTrackingAgent:
    """
    Goal Tracking Agent for MacroTrack.
    Compares real-time and historical intake against daily and weekly caloric/macro targets.
    Auto-suggests personalized nutrition goals based on the Mifflin-St Jeor formula and activity profile.
    """
    def __init__(self):
        pass

    @staticmethod
    def calculate_auto_goals(profile: Dict[str, Any]) -> Dict[str, Any]:
        """
        Auto-calculates BMR, TDEE, and macro split using the clinical Mifflin-St Jeor equation.
        """
        age = profile.get("age", 28)
        gender = profile.get("gender", "male").lower()
        weight = float(profile.get("weight_kg", 75.0))
        height = float(profile.get("height_cm", 178.0))
        activity = profile.get("activity_level", "moderate").lower()
        archetype = profile.get("goal_archetype", "general").lower()

        # 1. Basal Metabolic Rate (BMR)
        if gender == "male":
            bmr = (10.0 * weight) + (6.25 * height) - (5.0 * age) + 5.0
        else:
            bmr = (10.0 * weight) + (6.25 * height) - (5.0 * age) - 161.0

        # 2. Total Daily Energy Expenditure (TDEE)
        multipliers = {
            "sedentary": 1.2,
            "light": 1.375,
            "moderate": 1.55,
            "active": 1.725,
            "very_active": 1.9
        }
        tdee = bmr * multipliers.get(activity, 1.55)

        # 3. Target Calorie adjustment based on archetype
        if archetype == "weight_loss":
            target_calories = int(round(tdee - 500))
            protein_g = round(max(weight * 1.8, 120.0), 1)
            fat_g = round((target_calories * 0.25) / 9.0, 1)
            remaining_cals = max(0, target_calories - (protein_g * 4.0) - (fat_g * 9.0))
            carbs_g = round(remaining_cals / 4.0, 1)
        elif archetype in ["athlete", "muscle_gain"]:
            target_calories = int(round(tdee + 300))
            protein_g = round(max(weight * 2.0, 150.0), 1)
            fat_g = round((target_calories * 0.25) / 9.0, 1)
            remaining_cals = max(0, target_calories - (protein_g * 4.0) - (fat_g * 9.0))
            carbs_g = round(remaining_cals / 4.0, 1)
        else: # general health / maintenance
            target_calories = int(round(tdee))
            protein_g = round(max(weight * 1.5, 110.0), 1)
            fat_g = round((target_calories * 0.28) / 9.0, 1)
            remaining_cals = max(0, target_calories - (protein_g * 4.0) - (fat_g * 9.0))
            carbs_g = round(remaining_cals / 4.0, 1)

        return {
            "bmr": round(bmr, 1),
            "tdee": round(tdee, 1),
            "calories": max(1400, target_calories),
            "protein": protein_g,
            "carbs": carbs_g,
            "fat": fat_g,
            "archetype": archetype,
            "formula": "Mifflin-St Jeor Clinical Equation"
        }

    def get_daily_status(self, user_id: str = "default_user", target_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Computes consumed vs target macros for a specific day.
        """
        day_str = target_date or date.today().isoformat()
        goals = db.get_user_goals(user_id)
        meals = db.get_meals_for_date(user_id, day_str)

        consumed_cal = sum(m.get("calories", 0.0) for m in meals)
        consumed_prot = sum(m.get("protein", 0.0) for m in meals)
        consumed_carb = sum(m.get("carbs", 0.0) for m in meals)
        consumed_fat = sum(m.get("fat", 0.0) for m in meals)

        target_cal = goals.get("calories", DEFAULT_GOALS["calories"])
        target_prot = goals.get("protein", DEFAULT_GOALS["protein"])
        target_carb = goals.get("carbs", DEFAULT_GOALS["carbs"])
        target_fat = goals.get("fat", DEFAULT_GOALS["fat"])

        rem_cal = max(0.0, target_cal - consumed_cal)
        rem_prot = max(0.0, target_prot - consumed_prot)
        rem_carb = max(0.0, target_carb - consumed_carb)
        rem_fat = max(0.0, target_fat - consumed_fat)

        cal_pct = round((consumed_cal / target_cal * 100.0), 1) if target_cal else 0.0
        prot_pct = round((consumed_prot / target_prot * 100.0), 1) if target_prot else 0.0
        carb_pct = round((consumed_carb / target_carb * 100.0), 1) if target_carb else 0.0
        fat_pct = round((consumed_fat / target_fat * 100.0), 1) if target_fat else 0.0

        return {
            "user_id": user_id,
            "date": day_str,
            "meal_count": len(meals),
            "consumed": {
                "calories": round(consumed_cal, 1),
                "protein": round(consumed_prot, 1),
                "carbs": round(consumed_carb, 1),
                "fat": round(consumed_fat, 1)
            },
            "targets": {
                "calories": target_cal,
                "protein": target_prot,
                "carbs": target_carb,
                "fat": target_fat
            },
            "remaining": {
                "calories": round(rem_cal, 1),
                "protein": round(rem_prot, 1),
                "carbs": round(rem_carb, 1),
                "fat": round(rem_fat, 1)
            },
            "percentages": {
                "calories": cal_pct,
                "protein": prot_pct,
                "carbs": carb_pct,
                "fat": fat_pct
            },
            "meals": meals
        }

    def get_weekly_status(self, user_id: str = "default_user", end_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Aggregates past 7 days of nutrition data.
        """
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else date.today()
        start_dt = end_dt - timedelta(days=6)
        start_str = start_dt.isoformat()
        end_str = end_dt.isoformat()

        goals = db.get_user_goals(user_id)
        meals = db.get_meals_for_range(user_id, start_str, end_str)

        # Bucket meals per date
        daily_buckets = {}
        curr = start_dt
        while curr <= end_dt:
            daily_buckets[curr.isoformat()] = {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0, "count": 0}
            curr += timedelta(days=1)

        for m in meals:
            d = m.get("date")
            if d in daily_buckets:
                daily_buckets[d]["calories"] += m.get("calories", 0.0)
                daily_buckets[d]["protein"] += m.get("protein", 0.0)
                daily_buckets[d]["carbs"] += m.get("carbs", 0.0)
                daily_buckets[d]["fat"] += m.get("fat", 0.0)
                daily_buckets[d]["count"] += 1

        days_logged = sum(1 for b in daily_buckets.values() if b["count"] > 0)
        tot_cals = sum(b["calories"] for b in daily_buckets.values())
        tot_prot = sum(b["protein"] for b in daily_buckets.values())
        tot_carb = sum(b["carbs"] for b in daily_buckets.values())
        tot_fat = sum(b["fat"] for b in daily_buckets.values())

        avg_cals = round(tot_cals / 7.0, 1)
        avg_prot = round(tot_prot / 7.0, 1)
        avg_carb = round(tot_carb / 7.0, 1)
        avg_fat = round(tot_fat / 7.0, 1)

        target_weekly_cals = goals.get("calories", DEFAULT_GOALS["calories"]) * 7
        target_weekly_prot = goals.get("protein", DEFAULT_GOALS["protein"]) * 7

        weekly_deficit_surplus = round(tot_cals - target_weekly_cals, 1)

        return {
            "user_id": user_id,
            "period": f"{start_str} to {end_str}",
            "days_active": days_logged,
            "daily_history": daily_buckets,
            "weekly_totals": {
                "calories": round(tot_cals, 1),
                "protein": round(tot_prot, 1),
                "carbs": round(tot_carb, 1),
                "fat": round(tot_fat, 1)
            },
            "daily_averages": {
                "calories": avg_cals,
                "protein": avg_prot,
                "carbs": avg_carb,
                "fat": avg_fat
            },
            "net_weekly_balance": {
                "calorie_difference": weekly_deficit_surplus,
                "status": "surplus" if weekly_deficit_surplus > 0 else "deficit"
            }
        }

# Global goal tracking instance
goal_tracker = GoalTrackingAgent()
