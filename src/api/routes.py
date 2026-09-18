import io
import json
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Response
from pydantic import BaseModel
from PIL import Image

from src.database.storage import db
from src.agents.meal_parser import meal_parser
from src.agents.nutrition_lookup import nutrition_lookup
from src.agents.goal_tracker import goal_tracker
from src.agents.feedback_agent import feedback_agent
from src.agents.reminder_agent import reminder_agent
from src.agents.kg_agent import kg_agent
from src.agents.coordinator import coordinator
from src.memory.episodic import memory
from src.graph.kg_engine import kg

router = APIRouter(prefix="/api")

# ----------------- Request Models -----------------
class ParseMealRequest(BaseModel):
    text: str
    is_packaged_label: bool = False

class LogMealTextRequest(BaseModel):
    user_id: str = "default_user"
    text: str
    meal_type: Optional[str] = None
    log_time: Optional[str] = None

class GoalUpdateRequest(BaseModel):
    user_id: str = "default_user"
    calories: int
    protein: float
    carbs: float
    fat: float

class ProfileUpdateRequest(BaseModel):
    user_id: str = "default_user"
    name: str = "User"
    age: int = 28
    gender: str = "male"
    weight_kg: float = 75.0
    height_cm: float = 178.0
    activity_level: str = "moderate"
    dietary_preference: str = "veg"
    goal_archetype: str = "general"
    meals_per_day: int = 3
    auto_recalculate_goals: bool = True

class KGQueryRequest(BaseModel):
    question: str
    dietary_preference: Optional[str] = None

class WhatsAppWebhookRequest(BaseModel):
    From: Optional[str] = "whatsapp:+919876543210"
    Body: str

# ----------------- Meal Parsing & Logging -----------------
@router.post("/meals/parse")
def parse_meal_endpoint(req: ParseMealRequest):
    parsed = meal_parser.parse_meal(text_input=req.text, is_packaged_label=req.is_packaged_label)
    totals = nutrition_lookup.compute_meal_total(parsed.get("foods", []))
    return {
        "parsed_foods": parsed.get("foods", []),
        "detected_modality": parsed.get("detected_modality"),
        "meal_type": parsed.get("meal_type"),
        "nutrition_totals": totals
    }

@router.post("/meals/log")
def log_meal_text_endpoint(req: LogMealTextRequest):
    result = coordinator.process_and_log_meal(
        user_id=req.user_id,
        text_input=req.text,
        explicit_meal_type=req.meal_type,
        log_time_str=req.log_time
    )
    return result

@router.post("/meals/log-image")
async def log_meal_image_endpoint(
    image: UploadFile = File(...),
    user_id: str = Form("default_user"),
    text_notes: Optional[str] = Form(None),
    is_packaged_label: bool = Form(False),
    meal_type: Optional[str] = Form(None),
    log_time: Optional[str] = Form(None)
):
    try:
        contents = await image.read()
        pil_img = Image.open(io.BytesIO(contents))
        result = coordinator.process_and_log_meal(
            user_id=user_id,
            text_input=text_notes,
            image_input=pil_img,
            is_packaged_label=is_packaged_label,
            explicit_meal_type=meal_type,
            log_time_str=log_time
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process image meal log: {e}")

# ----------------- Goals & Profiles -----------------
@router.get("/goals")
def get_goals_endpoint(user_id: str = "default_user"):
    return db.get_user_goals(user_id)

@router.post("/goals")
def set_goals_endpoint(req: GoalUpdateRequest):
    return db.save_user_goals(req.user_id, req.model_dump())

@router.get("/profile")
def get_profile_endpoint(user_id: str = "default_user"):
    return db.get_user_profile(user_id)

@router.post("/profile")
def update_profile_endpoint(req: ProfileUpdateRequest):
    saved = db.save_user_profile(req.model_dump())
    auto_goals = None
    if req.auto_recalculate_goals:
        calculated = goal_tracker.calculate_auto_goals(saved)
        auto_goals = db.save_user_goals(req.user_id, calculated)
    return {
        "profile": saved,
        "goals": auto_goals or db.get_user_goals(req.user_id)
    }

# ----------------- Summaries & Dashboard -----------------
@router.get("/summary/daily")
def get_daily_summary_endpoint(user_id: str = "default_user", date_str: Optional[str] = None):
    status = goal_tracker.get_daily_status(user_id, date_str)
    report = feedback_agent.generate_daily_summary(user_id, status)
    return {
        "status": status,
        "clinical_summary": report
    }

@router.get("/summary/weekly")
def get_weekly_summary_endpoint(user_id: str = "default_user", end_date: Optional[str] = None):
    status = goal_tracker.get_weekly_status(user_id, end_date)
    report = feedback_agent.generate_weekly_summary(user_id, status)
    return {
        "status": status,
        "weekly_report": report
    }

# ----------------- Adaptive Reminders -----------------
@router.get("/reminders/schedule")
def get_reminder_schedule_endpoint(user_id: str = "default_user"):
    return reminder_agent.get_schedule_for_user(user_id)

@router.post("/reminders/adapt")
def adapt_schedule_endpoint(user_id: str = "default_user", meal_type: str = "Lunch", actual_time: str = "15:30"):
    return reminder_agent.adapt_schedule_on_meal_logged(user_id, meal_type, actual_time)

@router.get("/reminders/calendar.ics")
def download_calendar_ics(user_id: str = "default_user"):
    ics_content = reminder_agent.generate_calendar_ics(user_id)
    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={"Content-Disposition": f"attachment; filename=macrotrack_schedule_{user_id}.ics"}
    )

# ----------------- Knowledge Graph -----------------
@router.post("/knowledge-graph/query")
def query_kg_endpoint(req: KGQueryRequest):
    return kg_agent.answer_kg_question(req.question)

@router.get("/knowledge-graph/protein-density")
def get_protein_density_endpoint(dietary: Optional[str] = None):
    return kg_agent.query_fastest_protein_foods(dietary)

@router.get("/knowledge-graph/schema")
def get_kg_schema_endpoint():
    return kg.get_all_graph_elements()

# ----------------- Memory Management -----------------
@router.post("/memory/reset")
def reset_memory_endpoint(user_id: str = "default_user"):
    db.clear_user_data(user_id)
    memory.reset_memory(user_id)
    return {"success": True, "message": f"Episodic memory and logs reset for user {user_id}"}

# ----------------- External WhatsApp Webhook -----------------
@router.post("/webhook/whatsapp")
def whatsapp_webhook(req: WhatsAppWebhookRequest):
    """
    Inbound WhatsApp message webhook.
    Parses meal text, runs swarm, returns clean WhatsApp-ready message response.
    """
    user_id = req.From.replace("whatsapp:", "").strip() if req.From else "default_user"
    swarm_res = coordinator.process_and_log_meal(
        user_id=user_id,
        text_input=req.Body
    )
    nt = swarm_res["nutrition_totals"]
    rem = swarm_res["daily_status"]["remaining"]
    wa_reply = (
        f"✅ *MacroTrack Meal Logged!*\n\n"
        f"🔥 *Calories:* {nt['calories']} kcal\n"
        f"💪 *Protein:* {nt['protein']}g\n"
        f"🌾 *Carbs:* {nt['carbs']}g | 🥑 *Fat:* {nt['fat']}g\n\n"
        f"🎯 *Today's Remaining:* {rem['calories']:.0f} kcal | {rem['protein']:.1f}g Protein\n\n"
        f"💡 *Coach Tip:* {swarm_res['feedback']['coach_assessment']}"
    )
    return {"response_message": wa_reply, "swarm_result": swarm_res}
