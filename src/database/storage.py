import json
import sqlite3
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from src.config import SUPABASE_URL, SUPABASE_KEY, LOCAL_DB_PATH, DEFAULT_PROFILE, DEFAULT_GOALS

class DatabaseManager:
    """
    Dual-mode Database Manager for MacroTrack.
    Supports Supabase Cloud PostgreSQL with automatic local SQLite fallback
    ensuring 100% out-of-the-box zero-configuration operation.
    """
    def __init__(self):
        self.use_supabase = bool(SUPABASE_URL and SUPABASE_KEY)
        self.supabase_client = None
        if self.use_supabase:
            try:
                from supabase import create_client
                self.supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            except Exception as e:
                print(f"[DatabaseManager] Warning: Failed to connect to Supabase ({e}). Falling back to SQLite.")
                self.use_supabase = False

        if not self.use_supabase:
            self._init_sqlite()

    def _get_sqlite_conn(self):
        conn = sqlite3.connect(str(LOCAL_DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_sqlite(self):
        with self._get_sqlite_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                age INTEGER NOT NULL,
                gender TEXT NOT NULL,
                weight_kg REAL NOT NULL,
                height_cm REAL NOT NULL,
                activity_level TEXT NOT NULL,
                dietary_preference TEXT NOT NULL,
                goal_archetype TEXT NOT NULL,
                meals_per_day INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_goals (
                user_id TEXT PRIMARY KEY,
                calories_goal INTEGER NOT NULL,
                protein_goal REAL NOT NULL,
                carbs_goal REAL NOT NULL,
                fat_goal REAL NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES user_profiles(user_id)
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS meal_logs (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                date TEXT NOT NULL,
                meal_type TEXT NOT NULL,
                raw_input TEXT NOT NULL,
                input_modality TEXT NOT NULL,
                items TEXT NOT NULL,
                calories REAL NOT NULL,
                protein REAL NOT NULL,
                carbs REAL NOT NULL,
                fat REAL NOT NULL,
                logged_at TEXT NOT NULL
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS custom_foods (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                source TEXT NOT NULL DEFAULT 'user_custom',
                nutrition_basis TEXT NOT NULL DEFAULT 'serving',
                serving_size REAL NOT NULL DEFAULT 1.0,
                serving_name TEXT NOT NULL DEFAULT '1 serving',
                nutrition TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS meal_reminders (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                meal_type TEXT NOT NULL,
                scheduled_time TEXT NOT NULL,
                actual_logged_time TEXT,
                slippage_minutes INTEGER NOT NULL,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """)
            # Seed default user if not exists
            cursor.execute("SELECT user_id FROM user_profiles WHERE user_id = ?", ("default_user",))
            if not cursor.fetchone():
                now_iso = datetime.now().isoformat()
                cursor.execute("""
                INSERT INTO user_profiles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    DEFAULT_PROFILE["user_id"],
                    DEFAULT_PROFILE["name"],
                    DEFAULT_PROFILE["age"],
                    DEFAULT_PROFILE["gender"],
                    DEFAULT_PROFILE["weight_kg"],
                    DEFAULT_PROFILE["height_cm"],
                    DEFAULT_PROFILE["activity_level"],
                    DEFAULT_PROFILE["dietary_preference"],
                    DEFAULT_PROFILE["goal_archetype"],
                    DEFAULT_PROFILE["meals_per_day"],
                    now_iso,
                    now_iso
                ))
                cursor.execute("""
                INSERT INTO user_goals VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    DEFAULT_PROFILE["user_id"],
                    DEFAULT_GOALS["calories"],
                    DEFAULT_GOALS["protein"],
                    DEFAULT_GOALS["carbs"],
                    DEFAULT_GOALS["fat"],
                    now_iso
                ))
            conn.commit()

    # ------------------ Profiles ------------------
    def get_user_profile(self, user_id: str = "default_user") -> Dict[str, Any]:
        if self.use_supabase:
            try:
                res = self.supabase_client.table("user_profiles").select("*").eq("user_id", user_id).execute()
                if res.data:
                    return res.data[0]
            except Exception as e:
                print(f"[Supabase] get_user_profile error: {e}")

        with self._get_sqlite_conn() as conn:
            row = conn.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)).fetchone()
            if row:
                return dict(row)
            return DEFAULT_PROFILE

    def save_user_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        user_id = profile.get("user_id", "default_user")
        now_iso = datetime.now().isoformat()
        clean_profile = {
            "user_id": user_id,
            "name": profile.get("name", "User"),
            "age": int(profile.get("age", 28)),
            "gender": profile.get("gender", "male"),
            "weight_kg": float(profile.get("weight_kg", 75.0)),
            "height_cm": float(profile.get("height_cm", 178.0)),
            "activity_level": profile.get("activity_level", "moderate"),
            "dietary_preference": profile.get("dietary_preference", "veg"),
            "goal_archetype": profile.get("goal_archetype", "general"),
            "meals_per_day": int(profile.get("meals_per_day", 3)),
            "updated_at": now_iso
        }

        if self.use_supabase:
            try:
                self.supabase_client.table("user_profiles").upsert(clean_profile).execute()
            except Exception as e:
                print(f"[Supabase] save_user_profile error: {e}")

        with self._get_sqlite_conn() as conn:
            conn.execute("""
            INSERT INTO user_profiles (user_id, name, age, gender, weight_kg, height_cm, activity_level, dietary_preference, goal_archetype, meals_per_day, created_at, updated_at)
            VALUES (:user_id, :name, :age, :gender, :weight_kg, :height_cm, :activity_level, :dietary_preference, :goal_archetype, :meals_per_day, :updated_at, :updated_at)
            ON CONFLICT(user_id) DO UPDATE SET
                name=excluded.name,
                age=excluded.age,
                gender=excluded.gender,
                weight_kg=excluded.weight_kg,
                height_cm=excluded.height_cm,
                activity_level=excluded.activity_level,
                dietary_preference=excluded.dietary_preference,
                goal_archetype=excluded.goal_archetype,
                meals_per_day=excluded.meals_per_day,
                updated_at=excluded.updated_at
            """, clean_profile)
            conn.commit()
        return clean_profile

    # ------------------ Goals ------------------
    def get_user_goals(self, user_id: str = "default_user") -> Dict[str, Any]:
        if self.use_supabase:
            try:
                res = self.supabase_client.table("user_goals").select("*").eq("user_id", user_id).execute()
                if res.data:
                    d = res.data[0]
                    return {
                        "user_id": user_id,
                        "calories": d.get("calories_goal", DEFAULT_GOALS["calories"]),
                        "protein": float(d.get("protein_goal", DEFAULT_GOALS["protein"])),
                        "carbs": float(d.get("carbs_goal", DEFAULT_GOALS["carbs"])),
                        "fat": float(d.get("fat_goal", DEFAULT_GOALS["fat"]))
                    }
            except Exception as e:
                print(f"[Supabase] get_user_goals error: {e}")

        with self._get_sqlite_conn() as conn:
            row = conn.execute("SELECT * FROM user_goals WHERE user_id = ?", (user_id,)).fetchone()
            if row:
                return {
                    "user_id": user_id,
                    "calories": int(row["calories_goal"]),
                    "protein": float(row["protein_goal"]),
                    "carbs": float(row["carbs_goal"]),
                    "fat": float(row["fat_goal"])
                }
            return {"user_id": user_id, **DEFAULT_GOALS}

    def save_user_goals(self, user_id: str, goals: Dict[str, Any]) -> Dict[str, Any]:
        now_iso = datetime.now().isoformat()
        calories = int(goals.get("calories", goals.get("calories_goal", DEFAULT_GOALS["calories"])))
        protein = float(goals.get("protein", goals.get("protein_goal", DEFAULT_GOALS["protein"])))
        carbs = float(goals.get("carbs", goals.get("carbs_goal", DEFAULT_GOALS["carbs"])))
        fat = float(goals.get("fat", goals.get("fat_goal", DEFAULT_GOALS["fat"])))

        clean = {
            "user_id": user_id,
            "calories_goal": calories,
            "protein_goal": protein,
            "carbs_goal": carbs,
            "fat_goal": fat,
            "updated_at": now_iso
        }

        if self.use_supabase:
            try:
                self.supabase_client.table("user_goals").upsert(clean).execute()
            except Exception as e:
                print(f"[Supabase] save_user_goals error: {e}")

        with self._get_sqlite_conn() as conn:
            conn.execute("""
            INSERT INTO user_goals (user_id, calories_goal, protein_goal, carbs_goal, fat_goal, updated_at)
            VALUES (:user_id, :calories_goal, :protein_goal, :carbs_goal, :fat_goal, :updated_at)
            ON CONFLICT(user_id) DO UPDATE SET
                calories_goal=excluded.calories_goal,
                protein_goal=excluded.protein_goal,
                carbs_goal=excluded.carbs_goal,
                fat_goal=excluded.fat_goal,
                updated_at=excluded.updated_at
            """, clean)
            conn.commit()

        return {"user_id": user_id, "calories": calories, "protein": protein, "carbs": carbs, "fat": fat}

    # ------------------ Custom Foods ------------------
    def save_custom_food(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        user_id = payload.get("user_id", "default_user")
        food_id = payload.get("id") or f"custom_{user_id}_{int(datetime.now().timestamp() * 1000)}"
        name = str(payload.get("name") or "").strip()
        description = str(payload.get("description") or "").strip()
        if not name:
            raise ValueError("Food name is required.")

        nutrition = payload.get("nutrition") or {}
        if not isinstance(nutrition, dict):
            raise ValueError("Nutrition values must be provided as an object.")

        cleaned_nutrition = {
            "calories": float(nutrition.get("calories", 0.0) or 0.0),
            "protein": float(nutrition.get("protein", 0.0) or 0.0),
            "carbohydrates": float(nutrition.get("carbohydrates", 0.0) or 0.0),
            "fat": float(nutrition.get("fat", 0.0) or 0.0),
            "fiber": float(nutrition.get("fiber", 0.0) or 0.0),
            "sugar": float(nutrition.get("sugar", 0.0) or 0.0),
            "sodium": float(nutrition.get("sodium", 0.0) or 0.0),
        }
        if any(value < 0 for value in cleaned_nutrition.values()):
            raise ValueError("Nutrition values cannot be negative.")
        if not any(cleaned_nutrition.values()):
            raise ValueError("At least one nutrition value is required.")

        serving_size = float(payload.get("serving_size", 1.0) or 1.0)
        if serving_size <= 0:
            raise ValueError("Serving size must be positive.")

        record = {
            "id": food_id,
            "user_id": user_id,
            "name": name,
            "description": description,
            "source": "user_custom",
            "nutrition_basis": str(payload.get("nutrition_basis") or "serving").lower() or "serving",
            "serving_size": serving_size,
            "serving_name": str(payload.get("serving_name") or "1 serving").strip() or "1 serving",
            "nutrition": cleaned_nutrition,
            "created_at": payload.get("created_at") or datetime.now().isoformat(),
            "updated_at": payload.get("updated_at") or datetime.now().isoformat(),
        }

        if self.use_supabase:
            try:
                self.supabase_client.table("custom_foods").upsert(record).execute()
            except Exception as e:
                print(f"[Supabase] save_custom_food error: {e}")

        with self._get_sqlite_conn() as conn:
            conn.execute("""
            INSERT INTO custom_foods (id, user_id, name, description, source, nutrition_basis, serving_size, serving_name, nutrition, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                user_id=excluded.user_id,
                name=excluded.name,
                description=excluded.description,
                source=excluded.source,
                nutrition_basis=excluded.nutrition_basis,
                serving_size=excluded.serving_size,
                serving_name=excluded.serving_name,
                nutrition=excluded.nutrition,
                updated_at=excluded.updated_at
            """, (
                record["id"], record["user_id"], record["name"], record["description"], record["source"],
                record["nutrition_basis"], record["serving_size"], record["serving_name"], json.dumps(record["nutrition"]),
                record["created_at"], record["updated_at"]
            ))
            conn.commit()
        return record

    def get_all_custom_foods(self) -> List[Dict[str, Any]]:
        with self._get_sqlite_conn() as conn:
            rows = conn.execute("SELECT * FROM custom_foods ORDER BY name ASC").fetchall()
            results = []
            for row in rows:
                data = dict(row)
                data["nutrition"] = json.loads(data["nutrition"]) if isinstance(data["nutrition"], str) else data["nutrition"]
                data["source"] = "user_custom"
                results.append(data)
            return results

    def get_custom_foods_for_user(self, user_id: str = "default_user") -> List[Dict[str, Any]]:
        with self._get_sqlite_conn() as conn:
            rows = conn.execute("SELECT * FROM custom_foods WHERE user_id = ? ORDER BY name ASC", (user_id,)).fetchall()
            results = []
            for row in rows:
                data = dict(row)
                data["nutrition"] = json.loads(data["nutrition"]) if isinstance(data["nutrition"], str) else data["nutrition"]
                data["source"] = "user_custom"
                results.append(data)
            return results

    def get_custom_food_by_id(self, custom_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self._get_sqlite_conn() as conn:
            if user_id:
                row = conn.execute("SELECT * FROM custom_foods WHERE id = ? AND user_id = ?", (custom_id, user_id)).fetchone()
            else:
                row = conn.execute("SELECT * FROM custom_foods WHERE id = ?", (custom_id,)).fetchone()
            if not row:
                return None
            data = dict(row)
            data["nutrition"] = json.loads(data["nutrition"]) if isinstance(data["nutrition"], str) else data["nutrition"]
            data["source"] = "user_custom"
            return data

    def delete_custom_food_by_user(self, custom_id: str, user_id: Optional[str] = None) -> bool:
        target_user_id = user_id or custom_id
        if user_id is None and custom_id and custom_id != "default_user":
            lookup = self.get_custom_foods_for_user(custom_id)
            if lookup:
                target_user_id = custom_id
        if self.use_supabase:
            try:
                query = self.supabase_client.table("custom_foods").delete().eq("user_id", target_user_id)
                if custom_id and user_id is not None:
                    query = query.eq("id", custom_id)
                query.execute()
            except Exception as e:
                print(f"[Supabase] delete_custom_food_by_user error: {e}")

        with self._get_sqlite_conn() as conn:
            if user_id is not None:
                conn.execute("DELETE FROM custom_foods WHERE id = ? AND user_id = ?", (custom_id, user_id))
            else:
                conn.execute("DELETE FROM custom_foods WHERE user_id = ?", (target_user_id,))
            conn.commit()
        return True

    def delete_custom_foods_for_user(self, user_id: str) -> None:
        with self._get_sqlite_conn() as conn:
            conn.execute("DELETE FROM custom_foods WHERE user_id = ?", (user_id,))
            conn.commit()

    # ------------------ Meal Logs ------------------
    def log_meal(self, meal: Dict[str, Any]) -> Dict[str, Any]:
        meal_id = meal.get("id") or f"meal_{int(datetime.now().timestamp() * 1000)}"
        user_id = meal.get("user_id", "default_user")
        entry_date = meal.get("date") or date.today().isoformat()
        meal_type = meal.get("meal_type", "meal")
        raw_input = meal.get("raw_input", "")
        input_modality = meal.get("input_modality", "text")
        items = meal.get("items", [])
        items_json = json.dumps(items) if isinstance(items, list) else str(items)
        calories = float(meal.get("calories", 0.0))
        protein = float(meal.get("protein", 0.0))
        carbs = float(meal.get("carbs", 0.0))
        fat = float(meal.get("fat", 0.0))
        logged_at = meal.get("logged_at") or datetime.now().isoformat()

        record = {
            "id": meal_id,
            "user_id": user_id,
            "date": entry_date,
            "meal_type": meal_type,
            "raw_input": raw_input,
            "input_modality": input_modality,
            "items": items,
            "calories": calories,
            "protein": protein,
            "carbs": carbs,
            "fat": fat,
            "logged_at": logged_at
        }

        if self.use_supabase:
            try:
                self.supabase_client.table("meal_logs").insert(record).execute()
            except Exception as e:
                print(f"[Supabase] log_meal error: {e}")

        with self._get_sqlite_conn() as conn:
            conn.execute("""
            INSERT INTO meal_logs (id, user_id, date, meal_type, raw_input, input_modality, items, calories, protein, carbs, fat, logged_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (meal_id, user_id, entry_date, meal_type, raw_input, input_modality, items_json, calories, protein, carbs, fat, logged_at))
            conn.commit()

        return record

    def get_meals_for_date(self, user_id: str, date_str: str) -> List[Dict[str, Any]]:
        with self._get_sqlite_conn() as conn:
            rows = conn.execute("""
            SELECT * FROM meal_logs WHERE user_id = ? AND date = ? ORDER BY logged_at ASC
            """, (user_id, date_str)).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                if isinstance(d["items"], str):
                    try:
                        d["items"] = json.loads(d["items"])
                    except Exception:
                        d["items"] = []
                results.append(d)
            return results

    def get_meals_for_range(self, user_id: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        with self._get_sqlite_conn() as conn:
            rows = conn.execute("""
            SELECT * FROM meal_logs WHERE user_id = ? AND date BETWEEN ? AND ? ORDER BY date ASC, logged_at ASC
            """, (user_id, start_date, end_date)).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                if isinstance(d["items"], str):
                    try:
                        d["items"] = json.loads(d["items"])
                    except Exception:
                        d["items"] = []
                results.append(d)
            return results

    def get_all_meals(self, user_id: str = "default_user", limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_sqlite_conn() as conn:
            rows = conn.execute("""
            SELECT * FROM meal_logs WHERE user_id = ? ORDER BY logged_at DESC LIMIT ?
            """, (user_id, limit)).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                if isinstance(d["items"], str):
                    try:
                        d["items"] = json.loads(d["items"])
                    except Exception:
                        d["items"] = []
                results.append(d)
            return results

    def clear_user_data(self, user_id: str = "default_user") -> bool:
        if self.use_supabase:
            try:
                self.supabase_client.table("meal_logs").delete().eq("user_id", user_id).execute()
            except Exception as e:
                print(f"[Supabase] clear error: {e}")

        with self._get_sqlite_conn() as conn:
            conn.execute("DELETE FROM meal_logs WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM meal_reminders WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM custom_foods WHERE user_id = ?", (user_id,))
            conn.commit()
        return True

    # ------------------ Reminders ------------------
    def get_reminders(self, user_id: str = "default_user") -> List[Dict[str, Any]]:
        with self._get_sqlite_conn() as conn:
            rows = conn.execute("SELECT * FROM meal_reminders WHERE user_id = ? ORDER BY scheduled_time ASC", (user_id,)).fetchall()
            return [dict(r) for r in rows]

    def save_reminders(self, reminders: List[Dict[str, Any]]) -> None:
        with self._get_sqlite_conn() as conn:
            now_iso = datetime.now().isoformat()
            for rem in reminders:
                conn.execute("""
                INSERT INTO meal_reminders (id, user_id, meal_type, scheduled_time, actual_logged_time, slippage_minutes, status, updated_at)
                VALUES (:id, :user_id, :meal_type, :scheduled_time, :actual_logged_time, :slippage_minutes, :status, :updated_at)
                ON CONFLICT(id) DO UPDATE SET
                    scheduled_time=excluded.scheduled_time,
                    actual_logged_time=excluded.actual_logged_time,
                    slippage_minutes=excluded.slippage_minutes,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """, {
                    "id": rem.get("id", f"rem_{rem['user_id']}_{rem['meal_type']}"),
                    "user_id": rem.get("user_id", "default_user"),
                    "meal_type": rem.get("meal_type", "meal"),
                    "scheduled_time": rem.get("scheduled_time", "12:00"),
                    "actual_logged_time": rem.get("actual_logged_time"),
                    "slippage_minutes": rem.get("slippage_minutes", 0),
                    "status": rem.get("status", "scheduled"),
                    "updated_at": now_iso
                })
            conn.commit()

# Global database instance
db = DatabaseManager()
