import typing
import strawberry
from src.database.storage import db
from src.agents.goal_tracker import goal_tracker
from src.agents.reminder_agent import reminder_agent
from src.agents.kg_agent import kg_agent
from src.agents.coordinator import coordinator
from src.memory.episodic import memory

@strawberry.type
class MacroBreakdownType:
    calories: float
    protein: float
    carbs: float
    fat: float

@strawberry.type
class UserProfileType:
    user_id: str
    name: str
    age: int
    gender: str
    weight_kg: float
    height_cm: float
    activity_level: str
    dietary_preference: str
    goal_archetype: str
    meals_per_day: int

@strawberry.type
class UserGoalsType:
    user_id: str
    calories: int
    protein: float
    carbs: float
    fat: float

@strawberry.type
class DailyStatusType:
    user_id: str
    date: str
    meal_count: int
    consumed_calories: float
    consumed_protein: float
    consumed_carbs: float
    consumed_fat: float
    remaining_calories: float
    remaining_protein: float
    remaining_carbs: float
    remaining_fat: float

@strawberry.type
class FoodLeaderboardItemType:
    food_id: str
    food_name: str
    category: str
    dietary: str
    protein_density_score: float

@strawberry.type
class MealLogResponseType:
    success: bool
    calories: float
    protein: float
    carbs: float
    fat: float
    coach_assessment: str

@strawberry.type
class Query:
    @strawberry.field
    def profile(self, user_id: str = "default_user") -> UserProfileType:
        p = db.get_user_profile(user_id)
        return UserProfileType(
            user_id=p["user_id"],
            name=p["name"],
            age=p["age"],
            gender=p["gender"],
            weight_kg=float(p["weight_kg"]),
            height_cm=float(p["height_cm"]),
            activity_level=p["activity_level"],
            dietary_preference=p["dietary_preference"],
            goal_archetype=p["goal_archetype"],
            meals_per_day=p["meals_per_day"]
        )

    @strawberry.field
    def goals(self, user_id: str = "default_user") -> UserGoalsType:
        g = db.get_user_goals(user_id)
        return UserGoalsType(
            user_id=g["user_id"],
            calories=int(g["calories"]),
            protein=float(g["protein"]),
            carbs=float(g["carbs"]),
            fat=float(g["fat"])
        )

    @strawberry.field
    def daily_status(self, user_id: str = "default_user", target_date: typing.Optional[str] = None) -> DailyStatusType:
        s = goal_tracker.get_daily_status(user_id, target_date)
        return DailyStatusType(
            user_id=s["user_id"],
            date=s["date"],
            meal_count=s["meal_count"],
            consumed_calories=s["consumed"]["calories"],
            consumed_protein=s["consumed"]["protein"],
            consumed_carbs=s["consumed"]["carbs"],
            consumed_fat=s["consumed"]["fat"],
            remaining_calories=s["remaining"]["calories"],
            remaining_protein=s["remaining"]["protein"],
            remaining_carbs=s["remaining"]["carbs"],
            remaining_fat=s["remaining"]["fat"]
        )

    @strawberry.field
    def protein_leaderboard(self, dietary: typing.Optional[str] = None) -> typing.List[FoodLeaderboardItemType]:
        res = kg_agent.query_fastest_protein_foods(dietary)
        items = []
        for tf in res["top_foods"]:
            items.append(FoodLeaderboardItemType(
                food_id=tf["food_id"],
                food_name=tf["food_name"],
                category=tf.get("category", ""),
                dietary=tf.get("dietary", ""),
                protein_density_score=float(tf.get("protein_density_score", 0.0))
            ))
        return items

    @strawberry.field
    def food_search(self, query: str = "", limit: int = 10) -> typing.List[FoodLeaderboardItemType]:
        from src.data.repository import food_repository
        foods = food_repository.search_foods(query=query, limit=limit)
        return [
            FoodLeaderboardItemType(
                food_id=f.food_code,
                food_name=f.name,
                category=f.category,
                dietary=f.dietary,
                protein_density_score=round(f.per_100g.protein_g / max(f.per_100g.calories, 1.0), 3)
            )
            for f in foods
        ]

@strawberry.type
class Mutation:
    @strawberry.mutation
    def log_meal_text(self, user_id: str, text: str, meal_type: typing.Optional[str] = None) -> MealLogResponseType:
        res = coordinator.process_and_log_meal(
            user_id=user_id,
            text_input=text,
            explicit_meal_type=meal_type
        )
        return MealLogResponseType(
            success=res["success"],
            calories=res["nutrition_totals"]["calories"],
            protein=res["nutrition_totals"]["protein"],
            carbs=res["nutrition_totals"]["carbs"],
            fat=res["nutrition_totals"]["fat"],
            coach_assessment=res["feedback"]["coach_assessment"]
        )

    @strawberry.mutation
    def update_goals(self, user_id: str, calories: int, protein: float, carbs: float, fat: float) -> UserGoalsType:
        updated = db.save_user_goals(user_id, {"calories": calories, "protein": protein, "carbs": carbs, "fat": fat})
        return UserGoalsType(
            user_id=updated["user_id"],
            calories=updated["calories"],
            protein=updated["protein"],
            carbs=updated["carbs"],
            fat=updated["fat"]
        )

    @strawberry.mutation
    def reset_user_memory(self, user_id: str) -> bool:
        db.clear_user_data(user_id)
        memory.reset_memory(user_id)
        return True

schema = strawberry.Schema(query=Query, mutation=Mutation)
