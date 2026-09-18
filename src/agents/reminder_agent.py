import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
from src.database.storage import db

logger = logging.getLogger("macrotrack.reminder_agent")

class ReminderAgent:
    """
    Adaptive Reminder Agent for MacroTrack.
    Manages meal timing reminders (3 to 6 meals/day), calculates adaptive schedule slippage
    when meals are logged late, outputs push notification payloads, and generates
    iCalendar (.ics) calendar files.
    """
    def __init__(self):
        self.default_templates = {
            3: [
                {"meal_type": "Breakfast", "scheduled_time": "08:30"},
                {"meal_type": "Lunch", "scheduled_time": "13:00"},
                {"meal_type": "Dinner", "scheduled_time": "20:00"}
            ],
            4: [
                {"meal_type": "Breakfast", "scheduled_time": "08:30"},
                {"meal_type": "Lunch", "scheduled_time": "13:00"},
                {"meal_type": "Evening Snack", "scheduled_time": "17:00"},
                {"meal_type": "Dinner", "scheduled_time": "20:30"}
            ],
            5: [
                {"meal_type": "Breakfast", "scheduled_time": "08:00"},
                {"meal_type": "Mid-Morning Snack", "scheduled_time": "11:00"},
                {"meal_type": "Lunch", "scheduled_time": "13:30"},
                {"meal_type": "Evening Snack", "scheduled_time": "17:00"},
                {"meal_type": "Dinner", "scheduled_time": "20:30"}
            ],
            6: [
                {"meal_type": "Meal 1 (Breakfast)", "scheduled_time": "07:30"},
                {"meal_type": "Meal 2 (Mid-Morning)", "scheduled_time": "10:30"},
                {"meal_type": "Meal 3 (Lunch)", "scheduled_time": "13:30"},
                {"meal_type": "Meal 4 (Pre-Workout)", "scheduled_time": "16:30"},
                {"meal_type": "Meal 5 (Dinner)", "scheduled_time": "19:30"},
                {"meal_type": "Meal 6 (Bedtime Protein)", "scheduled_time": "22:00"}
            ]
        }

    def get_schedule_for_user(self, user_id: str = "default_user") -> List[Dict[str, Any]]:
        """
        Retrieves current schedule or builds standard template based on profile meal count.
        """
        profile = db.get_user_profile(user_id)
        meal_count = int(profile.get("meals_per_day", 3))
        template = self.default_templates.get(meal_count, self.default_templates[3])

        stored = db.get_reminders(user_id)
        if stored:
            return stored

        # Initialize from template
        initialized = []
        for idx, item in enumerate(template):
            initialized.append({
                "id": f"rem_{user_id}_{idx}_{item['meal_type'].lower().replace(' ', '_')}",
                "user_id": user_id,
                "meal_type": item["meal_type"],
                "scheduled_time": item["scheduled_time"],
                "actual_logged_time": None,
                "slippage_minutes": 0,
                "status": "scheduled"
            })
        db.save_reminders(initialized)
        return initialized

    def adapt_schedule_on_meal_logged(
        self,
        user_id: str,
        logged_meal_type: str,
        actual_time_str: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Adaptive Reminders: If user logged a meal late, shift subsequent reminders
        to maintain digestive spacing and avoid meal overlap.
        """
        now = datetime.now()
        actual_time = actual_time_str or now.strftime("%H:%M")
        schedule = self.get_schedule_for_user(user_id)

        # Match meal in schedule
        matched_idx = None
        for i, item in enumerate(schedule):
            if item["meal_type"].lower() in logged_meal_type.lower() or logged_meal_type.lower() in item["meal_type"].lower():
                matched_idx = i
                break

        if matched_idx is None:
            # Fallback to earliest uncompleted meal
            for i, item in enumerate(schedule):
                if item.get("status") == "scheduled":
                    matched_idx = i
                    break
        if matched_idx is None:
            matched_idx = 0

        # Calculate time difference in minutes
        sched_time_str = schedule[matched_idx]["scheduled_time"]
        t_sched = datetime.strptime(sched_time_str, "%H:%M")
        t_act = datetime.strptime(actual_time, "%H:%M")
        delta_minutes = int((t_act - t_sched).total_seconds() / 60)

        # Update logged meal status
        schedule[matched_idx]["actual_logged_time"] = actual_time
        schedule[matched_idx]["slippage_minutes"] = delta_minutes
        schedule[matched_idx]["status"] = "completed"

        shift_applied = False
        shifts_summary = []

        # If logged more than 40 minutes late, adaptively shift subsequent meals
        if delta_minutes >= 40:
            shift_applied = True
            # Shift downstream meals proportionally
            subsequent_shift = min(delta_minutes - 15, 180) # Cap shift at 3 hours
            for j in range(matched_idx + 1, len(schedule)):
                orig_str = schedule[j]["scheduled_time"]
                t_orig = datetime.strptime(orig_str, "%H:%M")
                t_shifted = t_orig + timedelta(minutes=subsequent_shift)
                # Don't shift past 23:30
                if t_shifted.hour >= 23 and t_shifted.minute > 30:
                    t_shifted = t_shifted.replace(hour=23, minute=30)
                new_time_str = t_shifted.strftime("%H:%M")
                shifts_summary.append({
                    "meal": schedule[j]["meal_type"],
                    "original_time": orig_str,
                    "new_time": new_time_str,
                    "delayed_by_min": subsequent_shift
                })
                schedule[j]["scheduled_time"] = new_time_str
                schedule[j]["status"] = "shifted"
                # Decay downstream shift slightly for spacing
                subsequent_shift = max(0, subsequent_shift - 20)

        db.save_reminders(schedule)

        explanation = (
            f"Logged {schedule[matched_idx]['meal_type']} at {actual_time} "
            f"({delta_minutes} min late vs planned {sched_time_str}). "
        )
        if shift_applied:
            explanation += f"Adaptively shifted {len(shifts_summary)} subsequent meals forward to maintain metabolic digestive rhythm."
        else:
            explanation += "Meal was logged on-time. Remaining schedule maintained."

        return {
            "user_id": user_id,
            "logged_meal": schedule[matched_idx]["meal_type"],
            "scheduled_time": sched_time_str,
            "actual_time": actual_time,
            "slippage_minutes": delta_minutes,
            "adaptive_shift_applied": shift_applied,
            "shifts": shifts_summary,
            "explanation": explanation,
            "updated_schedule": schedule
        }

    def generate_calendar_ics(self, user_id: str = "default_user", event_date: Optional[str] = None) -> str:
        """
        Generates standard iCalendar (.ics) content for import into Google/Apple/Outlook Calendar.
        """
        schedule = self.get_schedule_for_user(user_id)
        d_str = event_date or date.today().isoformat()
        clean_date = d_str.replace("-", "")

        ics_lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//MacroTrack Nutrition Swarm//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH"
        ]

        for item in schedule:
            time_parts = item["scheduled_time"].split(":")
            hh = time_parts[0].zfill(2)
            mm = time_parts[1].zfill(2)
            start_dt = f"{clean_date}T{hh}{mm}00"
            # 30 min duration
            end_min = (int(mm) + 30) % 60
            end_hr = int(hh) + ((int(mm) + 30) // 60)
            end_dt = f"{clean_date}T{str(end_hr).zfill(2)}{str(end_min).zfill(2)}00"

            ics_lines.extend([
                "BEGIN:VEVENT",
                f"UID:{item.get('id', 'event')}@{clean_date}",
                f"DTSTAMP:{clean_date}T000000Z",
                f"DTSTART:{start_dt}",
                f"DTEND:{end_dt}",
                f"SUMMARY:MacroTrack: {item['meal_type']}",
                f"DESCRIPTION:Target nutritional window for {item['meal_type']}. Open MacroTrack to log your food items or plate photo.",
                "STATUS:CONFIRMED",
                "END:VEVENT"
            ])

        ics_lines.append("END:VCALENDAR")
        return "\n".join(ics_lines)

    def generate_push_notification_payload(self, reminder_item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates web/mobile push notification JSON payload.
        """
        return {
            "title": f"🍽️ Time for {reminder_item.get('meal_type')}!",
            "body": f"Scheduled for {reminder_item.get('scheduled_time')}. Snap a plate photo or log your meal in MacroTrack to stay on target.",
            "data": {
                "user_id": reminder_item.get("user_id"),
                "meal_type": reminder_item.get("meal_type"),
                "scheduled_time": reminder_item.get("scheduled_time"),
                "action": "open_logger"
            }
        }

# Global reminder agent instance
reminder_agent = ReminderAgent()
