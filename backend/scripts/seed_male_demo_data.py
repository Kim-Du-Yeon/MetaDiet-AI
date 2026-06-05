"""
Seed data for the male InBody demo scenario.

Scenario:
- 2026-03-01: 29-year-old male, 181cm, 90kg starts a diet goal.
- Body composition is based on a trained male profile.
- 2026-03-01 ~ 2026-06-05: realistic cutting meals are inserted.
- March exceeds the calorie target only on weekends.
- April exceeds the calorie target only on Sundays.
- May exceeds the calorie target only on every other Sunday, two times total.
- Early June stays under the target.
- 2026-06: upload a new InBody image during the demo and let the agent
  compare it with the stored history.

Run from backend:
    python scripts/seed_male_demo_data.py

Optional:
    set DEMO_USER_ID=<supabase users.id>
    set INCLUDE_JUNE_INBODY=true

Notes:
- The uploaded reference InBody looks like a high-muscle, low-fat male profile:
  83.5kg body weight, 42.7kg skeletal muscle, and 10.3% body fat.
- This seed keeps the 3/4/5 month history consistent with that profile instead
  of using an average male body composition.
"""
import os
import random
import sys
from datetime import date, timedelta

from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from app.db.supabase_client import get_supabase  # noqa: E402


USER_ID = os.getenv("DEMO_USER_ID", "17691249-f22f-4447-a6e4-fca7a8e57cc8")
INCLUDE_JUNE_INBODY = os.getenv("INCLUDE_JUNE_INBODY", "false").lower() == "true"

sb = get_supabase()
random.seed(20260605)


def ensure_demo_user() -> None:
    existing = sb.table("users").select("id").eq("id", USER_ID).limit(1).execute().data
    if not existing:
        sb.table("users").insert({
            "id": USER_ID,
            "auth_id": USER_ID,
            "name": "Male Demo User",
            "goal": "diet",
            "height_cm": 181,
        }).execute()
        return

    sb.table("users").update({
        "name": "Male Demo User",
        "goal": "diet",
        "height_cm": 181,
    }).eq("id", USER_ID).execute()


def reset_demo_data() -> None:
    print("Deleting existing demo rows...")
    sb.table("meal_logs").delete().eq("user_id", USER_ID).execute()
    sb.table("diet_strategies").delete().eq("user_id", USER_ID).execute()
    sb.table("inbody_logs").delete().eq("user_id", USER_ID).execute()


def insert_inbody_history() -> None:
    rows = [
        {
            "user_id": USER_ID,
            "measured_date": "2026-03-01",
            "weight_kg": 90.0,
            "skeletal_muscle_kg": 43.2,
            "body_fat_kg": 16.2,
            "body_fat_pct": 18.0,
            "bmi": 27.5,
            "bmr_kcal": 2050,
            "raw_ocr_text": "demo seed: initial trained male inbody",
        },
        {
            "user_id": USER_ID,
            "measured_date": "2026-04-01",
            "weight_kg": 87.6,
            "skeletal_muscle_kg": 43.0,
            "body_fat_kg": 13.9,
            "body_fat_pct": 15.9,
            "bmi": 26.7,
            "bmr_kcal": 2028,
            "raw_ocr_text": "demo seed: month 1 check",
        },
        {
            "user_id": USER_ID,
            "measured_date": "2026-05-01",
            "weight_kg": 85.5,
            "skeletal_muscle_kg": 42.8,
            "body_fat_kg": 11.4,
            "body_fat_pct": 13.3,
            "bmi": 26.1,
            "bmr_kcal": 2005,
            "raw_ocr_text": "demo seed: month 2 check",
        },
    ]

    if INCLUDE_JUNE_INBODY:
        rows.append({
            "user_id": USER_ID,
            "measured_date": "2026-06-01",
            "weight_kg": 83.5,
            "skeletal_muscle_kg": 42.7,
            "body_fat_kg": 8.6,
            "body_fat_pct": 10.3,
            "bmi": 25.5,
            "bmr_kcal": 1988,
            "raw_ocr_text": "demo seed: uploaded june inbody fallback",
        })

    print("Inserting InBody history...")
    for row in rows:
        sb.table("inbody_logs").insert(row).execute()


def insert_strategy_history() -> None:
    rows = [
        {
            "user_id": USER_ID,
            "daily_calories": 2650,
            "protein_g": 190,
            "carbs_g": 298,
            "fat_g": 74,
            "strategy_note": (
                "Initial cutting target for a trained 29-year-old male, 181cm/90kg. "
                "Calories are set below estimated maintenance, while protein is kept high "
                "to preserve skeletal muscle during fat loss."
            ),
            "triggered_by": "initial",
            "is_active": False,
        },
        {
            "user_id": USER_ID,
            "daily_calories": 2550,
            "protein_g": 190,
            "carbs_g": 287,
            "fat_g": 71,
            "strategy_note": (
                "After March, body weight and fat mass decreased while skeletal muscle was "
                "nearly maintained. Calories are slightly reduced and protein is increased "
                "to keep the cut controlled."
            ),
            "triggered_by": "inbody_update",
            "is_active": False,
        },
        {
            "user_id": USER_ID,
            "daily_calories": 2600,
            "protein_g": 190,
            "carbs_g": 292,
            "fat_g": 72,
            "strategy_note": (
                "The two-month loss is fast, but most of the change comes from fat mass. "
                "Calories are not reduced further so training performance and muscle retention "
                "can be protected."
            ),
            "triggered_by": "inbody_update",
            "is_active": True,
        },
    ]

    print("Inserting strategy history...")
    for row in rows:
        sb.table("diet_strategies").insert(row).execute()


FOODS = {
    "breakfast": [
        ("brown rice", 150, 218, 5, 46, 2),
        ("oatmeal", 80, 304, 10, 54, 6),
        ("egg", 100, 155, 13, 1, 11),
        ("greek yogurt", 200, 173, 20, 12, 4),
        ("banana", 120, 107, 1, 27, 0),
        ("protein shake", 300, 150, 25, 8, 3),
    ],
    "lunch": [
        ("chicken breast", 220, 363, 68, 0, 8),
        ("salmon", 170, 318, 44, 0, 16),
        ("tuna", 170, 249, 45, 0, 6),
        ("brown rice", 220, 319, 7, 68, 2),
        ("sweet potato", 220, 253, 4, 58, 0),
        ("mixed salad", 250, 100, 4, 15, 4),
        ("tofu", 220, 176, 19, 4, 10),
    ],
    "dinner": [
        ("chicken breast", 200, 330, 62, 0, 7),
        ("lean beef", 170, 351, 44, 0, 18),
        ("salmon", 150, 281, 39, 0, 14),
        ("tofu soup", 350, 210, 18, 10, 10),
        ("brown rice", 170, 247, 6, 53, 2),
        ("broccoli", 200, 68, 6, 12, 1),
        ("mixed vegetables", 250, 100, 5, 18, 1),
    ],
    "snack": [
        ("protein shake", 300, 150, 25, 8, 3),
        ("greek yogurt", 150, 130, 15, 10, 3),
        ("almond", 25, 145, 5, 5, 13),
        ("boiled egg", 100, 156, 13, 1, 10),
        ("apple", 180, 94, 1, 25, 0),
    ],
}

WEEKEND_EXTRA = [
    ("sushi", 350, 580, 28, 80, 12),
    ("pasta", 350, 650, 22, 90, 18),
    ("burger", 300, 750, 35, 70, 32),
    ("fried chicken", 350, 858, 51, 54, 46),
]

CALORIE_ADJUSTERS = [
    ("brown rice", 100, 145, 3, 31, 1),
    ("sweet potato", 100, 115, 2, 27, 0),
    ("protein shake", 300, 150, 25, 8, 3),
    ("greek yogurt", 150, 130, 15, 10, 3),
    ("banana", 120, 107, 1, 27, 0),
    ("almond", 25, 145, 5, 5, 13),
]

MONTH_PLANS = {
    3: {"target": 2650, "under_range": (2320, 2580), "over_range": (2700, 2920)},
    4: {"target": 2550, "under_range": (2250, 2480), "over_range": (2600, 2780)},
    5: {"target": 2600, "under_range": (2200, 2460), "over_range": (2650, 2800)},
    6: {"target": 2600, "under_range": (2300, 2500), "over_range": (2650, 2750)},
}

MAY_OVER_TARGET_DATES = {date(2026, 5, 10), date(2026, 5, 24)}


def meal_row(day: date, meal_type: str, item: tuple) -> dict:
    return {
        "user_id": USER_ID,
        "log_date": day.isoformat(),
        "meal_type": meal_type,
        "food_name": item[0],
        "quantity_g": item[1],
        "calories": item[2],
        "protein_g": item[3],
        "carbs_g": item[4],
        "fat_g": item[5],
    }


def day_total(items: list[tuple]) -> float:
    return sum(item[2] for _, item in items)


def is_over_target_day(current: date) -> bool:
    if current.month == 3:
        return current.weekday() >= 5
    if current.month == 4:
        return current.weekday() == 6
    if current.month == 5:
        return current in MAY_OVER_TARGET_DATES
    return False


def add_adjusters(day_items: list[tuple], desired_min: int, desired_max: int) -> None:
    attempts = 0
    while day_total(day_items) < desired_min and attempts < 8:
        possible = [item for item in CALORIE_ADJUSTERS if day_total(day_items) + item[2] <= desired_max]
        item = random.choice(possible or CALORIE_ADJUSTERS)
        meal_type = "snack" if item[0] in {"protein shake", "greek yogurt", "banana", "almond"} else random.choice(["lunch", "dinner"])
        day_items.append((meal_type, item))
        attempts += 1

    day_items.sort(key=lambda x: ["breakfast", "lunch", "dinner", "snack"].index(x[0]))


def trim_to_max(day_items: list[tuple], desired_max: int) -> None:
    removable_foods = {
        "brown rice", "sweet potato", "banana", "almond",
        "protein shake", "greek yogurt", "mixed vegetables",
    }

    while day_total(day_items) > desired_max and len(day_items) > 5:
        counts = {}
        for meal_type, _ in day_items:
            counts[meal_type] = counts.get(meal_type, 0) + 1

        candidates = []
        for idx, (meal_type, item) in enumerate(day_items):
            if meal_type == "snack" or item[0] in removable_foods or counts.get(meal_type, 0) > 2:
                candidates.append((item[2], idx))

        if not candidates:
            break

        _, remove_idx = max(candidates)
        day_items.pop(remove_idx)


def make_day_items(current: date) -> list[tuple]:
    plan = MONTH_PLANS[current.month]
    over_target = is_over_target_day(current)
    desired_min, desired_max = plan["over_range"] if over_target else plan["under_range"]

    day_items = []
    day_items.extend(("breakfast", item) for item in random.sample(FOODS["breakfast"], 2))
    day_items.extend(("lunch", item) for item in random.sample(FOODS["lunch"], 2))
    day_items.extend(("dinner", item) for item in random.sample(FOODS["dinner"], 2))

    if over_target:
        day_items.append(("snack", random.choice(FOODS["snack"])))
        if current.weekday() >= 5 and random.random() < 0.5:
            day_items.append(("dinner", random.choice(WEEKEND_EXTRA)))
        else:
            day_items.append(("lunch", random.choice(CALORIE_ADJUSTERS)))
    elif current.month in {3, 4}:
        day_items.append(("snack", random.choice(FOODS["snack"])))
    elif random.random() < 0.45:
        day_items.append(("snack", random.choice(FOODS["snack"])))

    add_adjusters(day_items, desired_min, desired_max)
    trim_to_max(day_items, desired_max)
    add_adjusters(day_items, desired_min, desired_max)

    return day_items


def insert_meal_logs() -> None:
    print("Generating meal logs from 2026-03-01 to 2026-06-05...")
    rows = []
    current = date(2026, 3, 1)
    end = date(2026, 6, 5)

    while current <= end:
        for meal_type, item in make_day_items(current):
            rows.append(meal_row(current, meal_type, item))

        current += timedelta(days=1)

    print(f"Inserting {len(rows)} meal rows...")
    for i in range(0, len(rows), 50):
        sb.table("meal_logs").insert(rows[i:i + 50]).execute()
        print(f"  {min(i + 50, len(rows))}/{len(rows)}")


def print_summary() -> None:
    rows = []
    offset = 0
    while True:
        batch = (
            sb.table("meal_logs")
            .select("log_date,calories,protein_g")
            .eq("user_id", USER_ID)
            .range(offset, offset + 999)
            .execute()
            .data
        )
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    by_date = {}
    for row in rows:
        d = row["log_date"]
        by_date.setdefault(d, {"cal": 0, "protein": 0})
        by_date[d]["cal"] += row["calories"]
        by_date[d]["protein"] += row["protein_g"]

    avg_cal = sum(v["cal"] for v in by_date.values()) / len(by_date)
    avg_protein = sum(v["protein"] for v in by_date.values()) / len(by_date)
    print("\nDemo seed complete.")
    print(f"  user_id: {USER_ID}")
    print("  body story: 90.0kg -> 87.6kg -> 85.5kg")
    print("  skeletal muscle story: 43.2kg -> 43.0kg -> 42.8kg")
    print("  body fat story: 18.0% -> 15.9% -> 13.3%")
    print("  june upload suggestion: 83.5kg, skeletal muscle 42.7kg, body fat 10.3%")
    print(f"  logged days: {len(by_date)}")
    print(f"  average intake: {round(avg_cal)}kcal / protein {round(avg_protein)}g")
    for month in [3, 4, 5, 6]:
        month_rows = {d: v for d, v in by_date.items() if date.fromisoformat(d).month == month}
        if not month_rows:
            continue
        target = MONTH_PLANS[month]["target"]
        avg_month_cal = sum(v["cal"] for v in month_rows.values()) / len(month_rows)
        over_days = sum(1 for v in month_rows.values() if v["cal"] > target)
        print(
            f"  2026-{month:02d}: avg {round(avg_month_cal)}kcal, "
            f"over target {over_days}/{len(month_rows)} days"
        )
    print("  active target before June upload: 2600kcal / protein 190g")


if __name__ == "__main__":
    ensure_demo_user()
    reset_demo_data()
    insert_inbody_history()
    insert_strategy_history()
    insert_meal_logs()
    print_summary()
