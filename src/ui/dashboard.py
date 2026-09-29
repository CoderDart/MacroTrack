import sys
from pathlib import Path

# Ensure project root is always in sys.path regardless of execution directory
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import io
import json
import streamlit as st
import pandas as pd
from datetime import datetime, date
from PIL import Image

from src.database.storage import db
from src.agents.goal_tracker import goal_tracker
from src.agents.feedback_agent import feedback_agent
from src.agents.reminder_agent import reminder_agent
from src.agents.kg_agent import kg_agent
from src.agents.coordinator import coordinator
from src.memory.episodic import memory
from src.data.repository import food_repository

st.set_page_config(
    page_title="MacroTrack: Multi-Agent Nutrition System",
    page_icon="🥗",
    layout="wide",
    initial_sidebar_state="expanded"
)

# User session state
if "user_id" not in st.session_state:
    st.session_state["user_id"] = "default_user"

user_id = st.session_state["user_id"]

# Sidebar Profile & System Status
st.sidebar.title("🥗 MacroTrack")
st.sidebar.caption("Multi-Agent Clinical Nutrition Swarm")

# Load User Data
profile = db.get_user_profile(user_id)
goals = db.get_user_goals(user_id)

st.sidebar.subheader("Active Profile")
st.sidebar.write(f"**User:** {profile.get('name', 'User')}")
st.sidebar.write(f"**Archetype:** {profile.get('goal_archetype', 'general').capitalize()}")
st.sidebar.write(f"**Dietary:** {profile.get('dietary_preference', 'veg').capitalize()}")
st.sidebar.write(f"**Target Energy:** {goals.get('calories', 2200)} kcal")
st.sidebar.write(f"**Target Protein:** {goals.get('protein', 150)}g")

st.sidebar.divider()
st.sidebar.subheader("System Architecture")
st.sidebar.markdown(f"""
- **LLM:** Gemini 3.5 Flash
- **Episodic Memory:** mem0
- **Dataset:** Anuvaad INDB ({food_repository.count()} Indian Foods)
- **Portion Standard:** 100g Baseline
- **Knowledge Graph:** INDB query graph
- **Storage:** Dual-Mode Supabase/SQLite
""")

# Top banner
st.title("MacroTrack: Intelligent Multi-Agent Nutrition System")
st.caption("Powered by the Anuvaad INDB Dataset (1,014 Indian Foods & Recipes) on 100g portion standard.")

tabs = st.tabs([
    "🍽️ Multimodal Meal Logger",
    "📊 Daily & Weekly Intake",
    "🧠 Nutrition Knowledge Graph",
    "⏰ Adaptive Reminders",
    "📖 Anuvaad Food Database",
    "⚙️ Profile & Goal Settings"
])

# ----------------- TAB 1: Meal Logger -----------------
with tabs[0]:
    st.subheader("Log Meal (Text or Photo)")
    col1, col2 = st.columns([1, 1])

    with col1:
        meal_type_input = st.selectbox("Meal Category", ["Breakfast", "Lunch", "Evening Snack", "Dinner"], index=1)
        log_time_input = st.time_input("Meal Timestamp", datetime.now().time())
        time_str = log_time_input.strftime("%H:%M")

        st.markdown("**1. Describe Your Meal (Free-Form Text):**")
        meal_text_input = st.text_area(
            "e.g., '2 chapatis with 1 bowl dal and 100g paneer'",
            placeholder="Type your meal description here (Indian dishes, e.g. roti, dal, paneer, biryani, idli)...",
            height=90
        )

        st.markdown("**2. Or Upload Food Photo / Packaged Label:**")
        uploaded_file = st.file_uploader("Plate Photo or Nutrition Facts Label", type=["png", "jpg", "jpeg"])
        is_packaged = st.checkbox("This image is a packaged food nutrition label (OCR)", value=False)

        submit_btn = st.button("🚀 Process with Agent Swarm", type="primary", use_container_width=True)

    with col2:
        if uploaded_file is not None:
            image_preview = Image.open(uploaded_file)
            st.image(image_preview, caption="Uploaded Food Image", use_container_width=True)

        if submit_btn:
            with st.spinner("Agent Swarm collaborating: Parser -> Anuvaad Lookup -> Goal Analysis -> Feedback -> Reminders..."):
                img_arg = image_preview if uploaded_file else None
                swarm_result = coordinator.process_and_log_meal(
                    user_id=user_id,
                    text_input=meal_text_input if meal_text_input.strip() else None,
                    image_input=img_arg,
                    is_packaged_label=is_packaged,
                    explicit_meal_type=meal_type_input,
                    log_time_str=time_str
                )
                st.session_state["pending_food_result"] = swarm_result
                st.session_state["pending_food_request"] = {
                    "user_id": user_id,
                    "text_input": meal_text_input if meal_text_input.strip() else None,
                    "image_input": img_arg,
                    "is_packaged_label": is_packaged,
                    "explicit_meal_type": meal_type_input,
                    "log_time_str": time_str
                }

            if not swarm_result["success"]:
                st.error(swarm_result["message"])
            else:
                st.session_state["pending_food_result"] = None
                st.success("✅ Meal Logged and Processed Successfully!")

                # Display Swarm Output
                st.subheader("Agent Swarm Execution Summary")
                nt = swarm_result["nutrition_totals"]

                m_col1, m_col2, m_col3, m_col4 = st.columns(4)
                m_col1.metric("Calories", f"{nt['calories']} kcal")
                m_col2.metric("Protein", f"{nt['protein']}g")
                m_col3.metric("Carbohydrates", f"{nt['carbs']}g")
                m_col4.metric("Fat", f"{nt['fat']}g")

                # Show nutrition only for verified dataset records.
                verified_items = [it for it in swarm_result["parsed_items"] if it.get("found")]
                if verified_items:
                    st.markdown("#### Verified Items in Anuvaad INDB (100g standard basis):")
                    items_df = pd.DataFrame([
                        {
                            "Input Item": it.get("food_name"),
                            "Matched Anuvaad Food": it.get("matched_food"),
                            "Portion / Qty": f"{it.get('quantity')} {it.get('unit')}",
                            "Calories": f"{it.get('calories')} kcal",
                            "Protein": f"{it.get('protein_g')}g",
                            "Carbs": f"{it.get('carbs_g')}g",
                            "Fat": f"{it.get('fat_g')}g",
                            "Status": "✅ Verified",
                            "Source": it.get("database_source", "Anuvaad INDB")
                        }
                        for it in verified_items
                    ])
                    st.dataframe(items_df, use_container_width=True)

                # Unresolved items have no nutrition row.
                for item in swarm_result["parsed_items"]:
                    if item.get("status") == "not_found":
                        st.warning(item["message"])
                    elif item.get("status") == "ambiguous":
                        st.info(item["message"])

                # Feedback and Coach Advice
                fb = swarm_result["feedback"]
                st.info(f"💡 **Coach Assessment:** {fb['coach_assessment']}")

                if fb.get("next_meal_recommendations"):
                    st.markdown("#### 🎯 Next Meal Recommendations (Tailored Indian Foods):")
                    for rec in fb["next_meal_recommendations"]:
                        st.markdown(f"- **{rec['suggestion']}**: {rec['why']}")

                # Adaptive Reminders Note
                rem_info = swarm_result["adaptive_reminders"]
                if rem_info.get("adaptive_shift_applied"):
                    st.warning(f"⏰ **Adaptive Reminder Alert:** {rem_info['explanation']}")

                # Knowledge Graph Biological Pathways
                kg_paths = swarm_result.get("knowledge_graph_pathways", [])
                if kg_paths:
                    st.markdown("#### INDB Nutrient Composition (per 100g):")
                    for kp in kg_paths:
                        st.markdown(f"**{kp['food']}**:")
                        for path in kp["pathway_details"]:
                            st.caption(f"{path['nutrient']}: {path['value_per_100g']} {path['unit']}")

    pending_result = st.session_state.get("pending_food_result")
    if pending_result and pending_result.get("status") == "ambiguous":
        ambiguous_items = pending_result["nutrition_totals"].get("ambiguous_items", [])
        with st.form("resolve_ambiguous_foods"):
            selections = {
                item["food_name"]: st.selectbox(
                    f"Select the intended INDB food for {item['food_name']}",
                    item["candidates"],
                    key=f"food_match_{index}_{item['food_name']}"
                )
                for index, item in enumerate(ambiguous_items)
            }
            resolve_button = st.form_submit_button("Log selected foods")

        if resolve_button:
            pending_request = st.session_state["pending_food_request"]
            resolved = coordinator.process_and_log_meal(
                **pending_request,
                food_selections=selections
            )
            if resolved["success"]:
                st.session_state["pending_food_result"] = None
                st.success("Meal logged using the selected INDB food records.")
                totals = resolved["nutrition_totals"]
                st.write(
                    f"{totals['calories']} kcal · {totals['protein']}g protein · "
                    f"{totals['carbs']}g carbs · {totals['fat']}g fat"
                )
            else:
                st.session_state["pending_food_result"] = resolved
                st.error(resolved["message"])

# ----------------- TAB 2: Daily & Weekly Dashboard -----------------
with tabs[1]:
    st.subheader("Daily & Weekly Intake Analytics")
    day_status = goal_tracker.get_daily_status(user_id)

    c1, c2, c3, c4 = st.columns(4)
    cal_pct = day_status["percentages"]["calories"]
    prot_pct = day_status["percentages"]["protein"]

    c1.metric("Calories Consumed", f"{day_status['consumed']['calories']} kcal", f"{day_status['remaining']['calories']} kcal left")
    c2.metric("Protein Consumed", f"{day_status['consumed']['protein']}g", f"{day_status['remaining']['protein']}g left")
    c3.metric("Carbs Consumed", f"{day_status['consumed']['carbs']}g", f"{day_status['remaining']['carbs']}g left")
    c4.metric("Fat Consumed", f"{day_status['consumed']['fat']}g", f"{day_status['remaining']['fat']}g left")

    st.markdown("**Calorie Goal Progress:**")
    st.progress(min(1.0, cal_pct / 100.0), text=f"{day_status['consumed']['calories']} / {day_status['targets']['calories']} kcal ({cal_pct}%)")

    st.markdown("**Protein Goal Progress:**")
    st.progress(min(1.0, prot_pct / 100.0), text=f"{day_status['consumed']['protein']} / {day_status['targets']['protein']}g ({prot_pct}%)")

    st.divider()

    st.subheader("Today's Meal Log History")
    today_meals = day_status.get("meals", [])
    if today_meals:
        for m in reversed(today_meals):
            with st.expander(f"🕒 {m.get('meal_type', 'Meal').capitalize()} - {m.get('calories')} kcal | {m.get('protein')}g Protein ({m.get('logged_at')[:16]})"):
                st.write(f"**Input ({m.get('input_modality')}):** {m.get('raw_input')}")
                if isinstance(m.get("items"), list):
                    item_names = [f"{i.get('quantity')} {i.get('unit')} {i.get('matched_food', i.get('food_name'))}" for i in m.get("items")]
                    st.write(f"**Items:** {', '.join(item_names)}")
                st.write(f"**Nutrients:** {m.get('protein')}g Protein, {m.get('carbs')}g Carbs, {m.get('fat')}g Fat")
    else:
        st.write("No meals logged yet today.")

    st.divider()

    # Weekly Digest
    st.subheader("Weekly Consistency Report")
    weekly_status = goal_tracker.get_weekly_status(user_id)
    weekly_summary_text = feedback_agent.generate_weekly_summary(user_id, weekly_status)
    st.code(weekly_summary_text, language="markdown")

# ----------------- TAB 3: Knowledge Graph -----------------
with tabs[2]:
    st.subheader("Nutrition Knowledge Graph Explorer")
    st.caption("Query results and nutrient values are sourced from Anuvaad INDB per 100g.")

    def run_kg_query():
        question = st.session_state.get("kg_question_input", "").strip()
        if not question:
            return
        st.session_state.pop("kg_query_result", None)
        st.session_state["kg_active_query"] = question
        st.session_state["kg_query_result"] = kg_agent.answer_kg_question(question)

    kg_question = st.text_input(
        "Natural Language Graph Query",
        value="",
        key="kg_question_input",
        on_change=run_kg_query,
    )
    st.button("Run Graph Query", type="primary", on_click=run_kg_query)

    kg_res = st.session_state.get("kg_query_result")
    valid_kg_statuses = {"found", "ambiguous", "not_found", "no_results", "clarification"}
    if kg_res is not None and (
        not isinstance(kg_res, dict) or kg_res.get("status") not in valid_kg_statuses
    ):
        st.session_state.pop("kg_query_result", None)
        kg_res = None

    if kg_res:
        if kg_res["status"] == "clarification":
            st.info(kg_res["message"])
        elif kg_res["status"] == "not_found":
            st.error(kg_res["message"])
        elif kg_res["status"] == "no_results":
            st.info(kg_res["message"])
        elif kg_res["status"] == "ambiguous":
            st.info(kg_res["message"])
            with st.form("resolve_kg_food"):
                selected_kg_food = st.selectbox("Select an INDB record", kg_res["candidates"])
                resolve_kg_food = st.form_submit_button("Show selected food")
            if resolve_kg_food:
                st.session_state["kg_query_result"] = kg_agent.answer_kg_question(
                    kg_res["query"], selected_food=selected_kg_food
                )
                st.rerun()
        elif kg_res["status"] == "found":
            with st.expander("Query interpretation", expanded=True):
                st.json(kg_res["interpreted_intent"])
                if kg_res.get("ranking"):
                    st.caption(f"Dataset: INDB · Ranking: {kg_res['ranking']['sort']}")
                    if kg_res["ranking"].get("thresholds"):
                        st.json(kg_res["ranking"]["thresholds"])

            rows = []
            for result in kg_res["results"]:
                nutrition = result["nutrition_per_100g"]
                rows.append({
                    "Rank": result["rank"],
                    "Food": result["food_name"],
                    "INDB ID": result["food_id"],
                    "Ranked value / 100g": result["ranked_value_per_100g"],
                    "Calories / 100g": nutrition["calories"],
                    "Protein / 100g": nutrition["protein"],
                    "Carbohydrates / 100g": nutrition["carbohydrates"],
                    "Fat / 100g": nutrition["fat"],
                    "Fiber / 100g": nutrition["fiber"],
                    "Why selected": result["selection_reason"],
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            st.graphviz_chart(kg_res["graph"]["graphviz"], use_container_width=True)

# ----------------- TAB 4: Adaptive Reminders -----------------
with tabs[3]:
    st.subheader("Adaptive Meal Timing Reminders")
    st.caption("Shifts downstream reminders when meals are logged late to preserve digestive rhythm.")

    schedule = reminder_agent.get_schedule_for_user(user_id)
    sched_df = pd.DataFrame(schedule)[["meal_type", "scheduled_time", "actual_logged_time", "slippage_minutes", "status"]]
    st.dataframe(sched_df, use_container_width=True)

    st.divider()
    st.markdown("#### Test Adaptive Schedule Slippage Simulator")
    sim_col1, sim_col2, sim_col3 = st.columns(3)
    with sim_col1:
        sim_meal = st.selectbox("Delayed Meal", [item["meal_type"] for item in schedule], index=1 if len(schedule) > 1 else 0)
    with sim_col2:
        sim_actual_time = st.text_input("Actual Time Eaten (HH:MM)", value="15:30")
    with sim_col3:
        st.write("")
        st.write("")
        adapt_btn = st.button("Simulate Late Meal Log", type="primary")

    if adapt_btn:
        res_shift = reminder_agent.adapt_schedule_on_meal_logged(user_id, sim_meal, sim_actual_time)
        st.info(f"**Adaptive Agent Decision:** {res_shift['explanation']}")
        if res_shift["shifts"]:
            st.table(pd.DataFrame(res_shift["shifts"]))
            st.rerun()

    st.divider()
    st.markdown("#### Calendar Integration")
    ics_text = reminder_agent.generate_calendar_ics(user_id)
    st.download_button(
        label="📅 Download Calendar Schedule (.ics)",
        data=ics_text,
        file_name=f"macrotrack_schedule_{user_id}.ics",
        mime="text/calendar"
    )

# ----------------- TAB 5: Anuvaad Food Database Browser -----------------
with tabs[4]:
    st.subheader("📖 Anuvaad Database Search")
    st.caption("Official INDB foods plus your personal custom meals. Custom foods are stored locally and remain editable.")

    b_col1, b_col2 = st.columns([3, 1])
    with b_col1:
        search_kw = st.text_input("Search food or meal name", value="")
    with b_col2:
        cat_filter = st.selectbox("Category Filter", ["All"] + food_repository.get_categories() + ["Custom Food"])

    if st.button("+ Add Custom Food / Meal", type="secondary"):
        st.session_state["show_custom_food_form"] = True

    if st.session_state.get("show_custom_food_form"):
        with st.form("custom_food_form"):
            st.markdown("#### Add Custom Food / Meal")
            name = st.text_input("Food / Meal Name", value="")
            description = st.text_area("What did you eat?", value="", placeholder="100g oats, 1 scoop whey, 1 banana and 1 teaspoon peanut butter")
            basis = st.radio("Nutrition basis", ["Per serving", "Per 100g"], horizontal=True)
            serving_size = st.number_input("Serving size", min_value=0.1, value=1.0, step=0.1)
            serving_name = st.text_input("Serving name", value="1 serving")
            st.markdown("#### Nutrition Information")
            calories = st.number_input("Calories", min_value=0.0, value=0.0, step=1.0)
            protein = st.number_input("Protein (g)", min_value=0.0, value=0.0, step=1.0)
            carbs = st.number_input("Carbohydrates (g)", min_value=0.0, value=0.0, step=1.0)
            fat = st.number_input("Fat (g)", min_value=0.0, value=0.0, step=1.0)
            fiber = st.number_input("Fiber (g)", min_value=0.0, value=0.0, step=1.0)
            sugar = st.number_input("Sugar (g)", min_value=0.0, value=0.0, step=1.0)
            sodium = st.number_input("Sodium (mg)", min_value=0.0, value=0.0, step=1.0)
            save_custom = st.form_submit_button("Save Custom Food")

        if save_custom:
            try:
                db.save_custom_food({
                    "user_id": user_id,
                    "name": name,
                    "description": description,
                    "nutrition_basis": "serving" if basis == "Per serving" else "100g",
                    "serving_size": serving_size,
                    "serving_name": serving_name,
                    "nutrition": {
                        "calories": calories,
                        "protein": protein,
                        "carbohydrates": carbs,
                        "fat": fat,
                        "fiber": fiber,
                        "sugar": sugar,
                        "sodium": sodium,
                    }
                })
                st.success(f'"{name}" has been added as a custom food.')
                st.session_state["show_custom_food_form"] = False
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    searched_foods = food_repository.search_foods(search_kw, limit=50, category=cat_filter, user_id=user_id)
    st.write(f"Showing **{len(searched_foods)}** foods matching criteria:")

    if searched_foods:
        browse_df = pd.DataFrame([
            {
                "Source": "MY FOOD" if f.source == "user_custom" else "INDB",
                "Food Name": f.name,
                "Description": getattr(f, "aliases", [""])[1] if len(getattr(f, "aliases", ["", ""])) > 1 else "",
                "Category": f.category,
                "Energy": round(f.per_100g.calories if f.source != "user_custom" else (f.per_serving.calories if getattr(f, "nutrition_basis", "serving") == "serving" else f.per_100g.calories), 1),
                "Protein": round(f.per_100g.protein_g if f.source != "user_custom" else (f.per_serving.protein_g if getattr(f, "nutrition_basis", "serving") == "serving" else f.per_100g.protein_g), 1),
                "Carbs": round(f.per_100g.carbs_g if f.source != "user_custom" else (f.per_serving.carbs_g if getattr(f, "nutrition_basis", "serving") == "serving" else f.per_100g.carbs_g), 1),
                "Fat": round(f.per_100g.fat_g if f.source != "user_custom" else (f.per_serving.fat_g if getattr(f, "nutrition_basis", "serving") == "serving" else f.per_100g.fat_g), 1),
            }
            for f in searched_foods
        ])
        st.dataframe(browse_df, use_container_width=True)

# ----------------- TAB 6: Profile & Goals -----------------
with tabs[5]:
    st.subheader("User Profile & Nutrition Goals")

    p_col1, p_col2 = st.columns(2)
    with p_col1:
        st.markdown("#### Physical Attributes")
        u_name = st.text_input("Name", value=profile.get("name", "User"))
        u_age = st.number_input("Age", min_value=12, max_value=100, value=int(profile.get("age", 28)))
        u_gender = st.selectbox("Gender", ["male", "female"], index=0 if profile.get("gender") == "male" else 1)
        u_weight = st.number_input("Weight (kg)", min_value=30.0, max_value=250.0, value=float(profile.get("weight_kg", 75.0)), step=0.5)
        u_height = st.number_input("Height (cm)", min_value=100.0, max_value=230.0, value=float(profile.get("height_cm", 178.0)), step=0.5)
        u_activity = st.selectbox(
            "Physical Activity Level",
            ["sedentary", "light", "moderate", "active", "very_active"],
            index=["sedentary", "light", "moderate", "active", "very_active"].index(profile.get("activity_level", "moderate"))
        )
        u_dietary = st.selectbox(
            "Dietary Preference",
            ["veg", "non-veg", "ovo-veg", "vegan"],
            index=["veg", "non-veg", "ovo-veg", "vegan"].index(profile.get("dietary_preference", "veg"))
        )
        u_archetype = st.selectbox(
            "Goal Archetype",
            ["general", "weight_loss", "muscle_gain", "athlete"],
            index=["general", "weight_loss", "muscle_gain", "athlete"].index(profile.get("goal_archetype", "general"))
        )
        u_meals = st.slider("Meals per Day", min_value=3, max_value=6, value=int(profile.get("meals_per_day", 3)))

    with p_col2:
        st.markdown("#### Caloric & Macro Targets")
        auto_calc = goal_tracker.calculate_auto_goals({
            "age": u_age, "gender": u_gender, "weight_kg": u_weight, "height_cm": u_height,
            "activity_level": u_activity, "goal_archetype": u_archetype
        })
        st.caption(f"Estimated BMR: {auto_calc['bmr']} kcal | TDEE: {auto_calc['tdee']} kcal")

        target_cals = st.number_input("Daily Calories (kcal)", value=int(goals.get("calories", auto_calc["calories"])))
        target_prot = st.number_input("Protein Target (g)", value=float(goals.get("protein", auto_calc["protein"])), step=1.0)
        target_carbs = st.number_input("Carbohydrates Target (g)", value=float(goals.get("carbs", auto_calc["carbs"])), step=1.0)
        target_fat = st.number_input("Fat Target (g)", value=float(goals.get("fat", auto_calc["fat"])), step=1.0)

        use_auto_btn = st.button("⚡ Apply Auto-Calculated Goals (Mifflin-St Jeor)")
        if use_auto_btn:
            db.save_user_goals(user_id, auto_calc)
            st.success(f"Applied auto-calculated targets: {auto_calc['calories']} kcal, {auto_calc['protein']}g protein.")
            st.rerun()

        save_profile_btn = st.button("Save Profile & Manual Goals", type="primary", use_container_width=True)
        if save_profile_btn:
            new_prof = {
                "user_id": user_id,
                "name": u_name,
                "age": u_age,
                "gender": u_gender,
                "weight_kg": u_weight,
                "height_cm": u_height,
                "activity_level": u_activity,
                "dietary_preference": u_dietary,
                "goal_archetype": u_archetype,
                "meals_per_day": u_meals
            }
            db.save_user_profile(new_prof)
            db.save_user_goals(user_id, {
                "calories": target_cals,
                "protein": target_prot,
                "carbs": target_carbs,
                "fat": target_fat
            })
            st.success("Profile and goals updated successfully!")
            st.rerun()

        st.divider()
        st.markdown("#### Privacy & Data Reset")
        if st.button("⚠️ Clear Episodic Memory & Meal Logs", type="secondary"):
            db.clear_user_data(user_id)
            memory.reset_memory(user_id)
            st.success("Episodic memory and meal logs cleared.")
            st.rerun()
