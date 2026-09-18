import logging
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from src.agents.meal_parser import meal_parser
from src.agents.nutrition_lookup import nutrition_lookup
from src.agents.goal_tracker import goal_tracker
from src.agents.feedback_agent import feedback_agent
from src.agents.reminder_agent import reminder_agent
from src.agents.kg_agent import kg_agent
from src.memory.episodic import memory
from src.database.storage import db

logger = logging.getLogger("macrotrack.coordinator")

class MacroTrackCoordinator:
    """
    Central Multi-Agent Swarm Coordinator for MacroTrack.
    Coordinates the 6 specialized agents:
      1. Meal Parser Agent (Gemini Flash Multimodal)
      2. Nutrition Lookup Agent (INDb Database)
      3. Goal Tracking Agent (Mifflin-St Jeor & Macro Deficits)
      4. Feedback & Suggestion Agent (Real-time & Next-meal Coach)
      5. Adaptive Reminder Agent (Dynamic schedule slippage & .ics)
      6. Knowledge Graph Agent (Biological pathways & Food->Nutrient->Goal)
    """
    def __init__(self):
        pass

    def process_and_log_meal(
        self,
        user_id: str = "default_user",
        text_input: Optional[str] = None,
        image_input: Optional[Any] = None,
        is_packaged_label: bool = False,
        explicit_meal_type: Optional[str] = None,
        log_time_str: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        End-to-end swarm execution pipeline:
        Input -> Parse -> Lookup INDb -> Log -> Episodic Memory -> Goal Drift -> Feedback -> Adapt Reminders -> KG Pathways.
        """
        agent_traces = []
        now_dt = datetime.now()
        log_time = log_time_str or now_dt.strftime("%H:%M")
        today_str = now_dt.date().isoformat()

        # Step 1: Meal Parser Agent
        agent_traces.append({"agent": "MealParserAgent", "status": "invoked"})
        parse_result = meal_parser.parse_meal(
            text_input=text_input,
            image_input=image_input,
            is_packaged_label=is_packaged_label
        )
        detected_meal_type = explicit_meal_type or parse_result.get("meal_type", "meal")
        food_items = parse_result.get("foods", [])
        agent_traces[-1]["output"] = {
            "modality": parse_result.get("detected_modality"),
            "items_count": len(food_items),
            "meal_type": detected_meal_type
        }

        # Step 2: Nutrition Lookup Agent (INDb)
        agent_traces.append({"agent": "NutritionLookupAgent", "status": "invoked"})
        nutrition_totals = nutrition_lookup.compute_meal_total(food_items)
        agent_traces[-1]["output"] = {
            "calories": nutrition_totals["calories"],
            "protein": nutrition_totals["protein"],
            "carbs": nutrition_totals["carbs"],
            "fat": nutrition_totals["fat"]
        }

        # Step 3: Persist Log to Database (Supabase / SQLite)
        meal_record = {
            "user_id": user_id,
            "date": today_str,
            "meal_type": detected_meal_type,
            "raw_input": text_input or ("Image upload" if image_input else "Mixed log"),
            "input_modality": parse_result.get("detected_modality", "text"),
            "items": nutrition_totals["items"],
            "calories": nutrition_totals["calories"],
            "protein": nutrition_totals["protein"],
            "carbs": nutrition_totals["carbs"],
            "fat": nutrition_totals["fat"],
            "logged_at": now_dt.isoformat()
        }
        saved_record = db.log_meal(meal_record)

        # Step 4: Episodic Memory (mem0)
        agent_traces.append({"agent": "EpisodicMemory (mem0)", "status": "invoked"})
        item_names = []
        for i in nutrition_totals["items"]:
            q = i.get("quantity", 1)
            u = i.get("unit", "")
            f_name = i.get("matched_food") or i.get("food_name")
            item_names.append(f"{q} {u} {f_name}")
        joined_items = ", ".join(item_names)

        memory_summary = (
            f"Consumed {detected_meal_type}: {joined_items} "
            f"({nutrition_totals['calories']} kcal, {nutrition_totals['protein']}g P, "
            f"{nutrition_totals['carbs']}g C, {nutrition_totals['fat']}g F)"
        )
        memory.add_meal_episode(user_id=user_id, meal_summary=memory_summary, metadata=meal_record)
        agent_traces[-1]["output"] = "Saved episode to persistent memory"

        # Step 5: Goal Tracking Agent
        agent_traces.append({"agent": "GoalTrackingAgent", "status": "invoked"})
        daily_status = goal_tracker.get_daily_status(user_id, today_str)
        agent_traces[-1]["output"] = {
            "consumed_calories": daily_status["consumed"]["calories"],
            "remaining_calories": daily_status["remaining"]["calories"],
            "remaining_protein": daily_status["remaining"]["protein"]
        }

        # Step 6: Feedback & Suggestion Agent
        agent_traces.append({"agent": "FeedbackAgent", "status": "invoked"})
        feedback = feedback_agent.generate_realtime_feedback(user_id, nutrition_totals, daily_status)
        agent_traces[-1]["output"] = feedback["coach_assessment"]

        # Step 7: Adaptive Reminder Agent
        agent_traces.append({"agent": "ReminderAgent", "status": "invoked"})
        reminder_shift = reminder_agent.adapt_schedule_on_meal_logged(
            user_id=user_id,
            logged_meal_type=detected_meal_type,
            actual_time_str=log_time
        )
        agent_traces[-1]["output"] = reminder_shift["explanation"]

        # Step 8: Knowledge Graph Agent (Enrich logged foods with biological pathways)
        agent_traces.append({"agent": "KnowledgeGraphAgent", "status": "invoked"})
        kg_pathways = []
        for it in nutrition_totals["items"]:
            name = it.get("matched_food") or it.get("food_name", "")
            pathway = kg_agent.explain_food_mechanism(name)
            if pathway.get("found"):
                kg_pathways.append(pathway)
        agent_traces[-1]["output"] = f"Mapped {len(kg_pathways)} biological pathways"

        return {
            "success": True,
            "meal_record": saved_record,
            "parsed_items": nutrition_totals["items"],
            "nutrition_totals": {
                "calories": nutrition_totals["calories"],
                "protein": nutrition_totals["protein"],
                "carbs": nutrition_totals["carbs"],
                "fat": nutrition_totals["fat"],
                "fiber": nutrition_totals.get("fiber", 0.0)
            },
            "daily_status": daily_status,
            "feedback": feedback,
            "adaptive_reminders": reminder_shift,
            "knowledge_graph_pathways": kg_pathways,
            "agent_swarm_traces": agent_traces
        }

# Global coordinator instance
coordinator = MacroTrackCoordinator()
