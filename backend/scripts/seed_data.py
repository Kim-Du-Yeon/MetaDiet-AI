"""
scripts/seed_data.py
3달치 가상 식단 + 인바디 데이터 생성
실행: python scripts/seed_data.py
"""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from datetime import date, timedelta
import random
from app.db.supabase_client import get_supabase

sb = get_supabase()
USER_ID = "17691249-f22f-4447-a6e4-fca7a8e57cc8"

# 기존 데이터 삭제 (깔끔하게 시작)
print("기존 데이터 삭제 중...")
sb.table("meal_logs").delete().eq("user_id", USER_ID).execute()
sb.table("inbody_logs").delete().eq("user_id", USER_ID).execute()
sb.table("diet_strategies").delete().eq("user_id", USER_ID).execute()

# ── 초기 전략 설정 ──────────────────────────────────
# 여성, 20세, 170cm, 65kg, 다이어트
# 해리스-베네딕트: 447.593 + (9.247*65) + (3.098*170) - (4.330*20) = 1586 kcal
bmr = 1586
daily_calories = round(bmr * 1.4 - 400)   # 1820kcal
protein_g = round(65 * 2.0)               # 130g
carbs_g = round((daily_calories * 0.5) / 4)
fat_g = round((daily_calories * 0.25) / 9)

print(f"초기 전략: {daily_calories}kcal / 단백질 {protein_g}g")

sb.table("diet_strategies").insert({
    "user_id": USER_ID,
    "daily_calories": daily_calories,
    "protein_g": protein_g,
    "carbs_g": carbs_g,
    "fat_g": fat_g,
    "strategy_note": f"체중 감량 목표: 기초대사량 {bmr}kcal 기준 하루 {daily_calories}kcal",
    "triggered_by": "initial",
    "is_active": False,
}).execute()

# ── 인바디 데이터 3회 ────────────────────────────────
inbody_data = [
    # 3월 1일: 시작 (65kg)
    {
        "user_id": USER_ID,
        "measured_date": "2026-03-01",
        "weight_kg": 65.0,
        "skeletal_muscle_kg": 24.5,
        "body_fat_kg": 18.2,
        "body_fat_pct": 28.0,
        "bmi": 22.5,
        "bmr_kcal": 1586,
    },
    # 4월 1일: 1달 후 (63.2kg, 근육 유지, 체지방 감소)
    {
        "user_id": USER_ID,
        "measured_date": "2026-04-01",
        "weight_kg": 63.2,
        "skeletal_muscle_kg": 24.4,
        "body_fat_kg": 16.5,
        "body_fat_pct": 26.1,
        "bmi": 21.9,
        "bmr_kcal": 1562,
    },
    # 5월 1일: 2달 후 (61.8kg, 근육 소폭 감소 - 단백질 부족 영향)
    {
        "user_id": USER_ID,
        "measured_date": "2026-05-01",
        "weight_kg": 61.8,
        "skeletal_muscle_kg": 24.1,
        "body_fat_kg": 15.2,
        "body_fat_pct": 24.6,
        "bmi": 21.4,
        "bmr_kcal": 1545,
    },
]

print("인바디 데이터 삽입 중...")
for ib in inbody_data:
    sb.table("inbody_logs").insert(ib).execute()

# ── 전략 재설정 (인바디마다) ─────────────────────────
strategies = [
    # 4월 전략 (3월 인바디 기준)
    {
        "user_id": USER_ID,
        "daily_calories": 1770,
        "protein_g": 126,
        "carbs_g": 221,
        "fat_g": 49,
        "strategy_note": "1달간 1.8kg 감량. 근육 유지되어 전략 소폭 강화. 칼로리 50kcal 추가 감소.",
        "triggered_by": "inbody_update",
        "is_active": False,
    },
    # 5월 전략 (4월 인바디 기준 - 근손실 감지)
    {
        "user_id": USER_ID,
        "daily_calories": 1820,
        "protein_g": 140,
        "carbs_g": 228,
        "fat_g": 51,
        "strategy_note": "골격근 0.3kg 감소 감지. 단백질을 130g→140g으로 증가. 칼로리는 소폭 상향하여 근손실 방지.",
        "triggered_by": "inbody_update",
        "is_active": True,
    },
]

for s in strategies:
    sb.table("diet_strategies").insert(s).execute()

# ── 식단 데이터 3달치 ────────────────────────────────
# 음식 메뉴 풀
WEEKDAY_MEALS = {
    "breakfast": [
        ("brown rice", 90, 130, 3, 28, 1),
        ("oatmeal", 80, 140, 5, 25, 3),
        ("whole wheat bread", 60, 160, 6, 30, 2),
        ("egg", 100, 155, 13, 1, 11),
        ("banana", 120, 107, 1, 27, 0),
        ("greek yogurt", 150, 130, 15, 10, 3),
    ],
    "lunch": [
        ("chicken breast", 200, 330, 62, 0, 7),
        ("salmon", 150, 280, 39, 0, 14),
        ("tofu", 200, 160, 17, 4, 9),
        ("tuna", 150, 220, 40, 0, 5),
        ("brown rice", 150, 218, 5, 46, 2),
        ("mixed salad", 200, 80, 3, 12, 3),
        ("sweet potato", 150, 173, 3, 40, 0),
    ],
    "dinner": [
        ("chicken breast", 150, 248, 46, 0, 5),
        ("broccoli", 200, 68, 6, 12, 1),
        ("brown rice", 100, 145, 3, 31, 1),
        ("salmon", 120, 224, 31, 0, 11),
        ("tofu soup", 300, 180, 15, 8, 9),
        ("mixed vegetables", 200, 80, 4, 14, 1),
    ],
    "snack": [
        ("apple", 150, 78, 0, 21, 0),
        ("protein shake", 300, 150, 25, 8, 3),
        ("almond", 30, 174, 6, 6, 15),
        ("boiled egg", 50, 78, 6, 0, 5),
    ],
}

WEEKEND_EXTRA = [
    ("pizza", 400, 1000, 38, 120, 36),
    ("fried chicken", 400, 980, 58, 62, 52),
    ("pasta", 350, 650, 22, 90, 18),
    ("burger", 300, 750, 35, 70, 32),
    ("sushi", 350, 580, 28, 80, 12),
    ("ramen", 500, 720, 25, 95, 22),
]

print("식단 데이터 생성 중...")

start_date = date(2026, 3, 1)
end_date = date(2026, 5, 28)

meal_batch = []
current = start_date

while current <= end_date:
    weekday = current.weekday()  # 0=월, 6=일
    is_weekend = weekday >= 5

    # 주중: 목표의 80~90% (단백질 부족 패턴)
    # 주말: 토요일 저녁 외식으로 초과

    # 아침
    b_items = random.sample(WEEKDAY_MEALS["breakfast"], 2)
    for item in b_items:
        meal_batch.append({
            "user_id": USER_ID,
            "log_date": current.isoformat(),
            "meal_type": "breakfast",
            "food_name": item[0],
            "quantity_g": item[1],
            "calories": item[2],
            "protein_g": item[3],
            "carbs_g": item[4],
            "fat_g": item[5],
        })

    # 점심
    l_items = random.sample(WEEKDAY_MEALS["lunch"], 3)
    for item in l_items:
        meal_batch.append({
            "user_id": USER_ID,
            "log_date": current.isoformat(),
            "meal_type": "lunch",
            "food_name": item[0],
            "quantity_g": item[1],
            "calories": item[2],
            "protein_g": item[3],
            "carbs_g": item[4],
            "fat_g": item[5],
        })

    # 저녁
    if weekday == 5:  # 토요일 외식
        extra = random.choice(WEEKEND_EXTRA)
        meal_batch.append({
            "user_id": USER_ID,
            "log_date": current.isoformat(),
            "meal_type": "dinner",
            "food_name": extra[0],
            "quantity_g": extra[1],
            "calories": extra[2],
            "protein_g": extra[3],
            "carbs_g": extra[4],
            "fat_g": extra[5],
        })
    else:
        d_items = random.sample(WEEKDAY_MEALS["dinner"], 2)
        for item in d_items:
            meal_batch.append({
                "user_id": USER_ID,
                "log_date": current.isoformat(),
                "meal_type": "dinner",
                "food_name": item[0],
                "quantity_g": item[1],
                "calories": item[2],
                "protein_g": item[3],
                "carbs_g": item[4],
                "fat_g": item[5],
            })

    # 간식 (주중만)
    if not is_weekend:
        snack = random.choice(WEEKDAY_MEALS["snack"])
        meal_batch.append({
            "user_id": USER_ID,
            "log_date": current.isoformat(),
            "meal_type": "snack",
            "food_name": snack[0],
            "quantity_g": snack[1],
            "calories": snack[2],
            "protein_g": snack[3],
            "carbs_g": snack[4],
            "fat_g": snack[5],
        })

    current += timedelta(days=1)

# 배치 삽입 (50개씩)
total = len(meal_batch)
print(f"총 {total}개 식단 기록 삽입 중...")
for i in range(0, total, 50):
    batch = meal_batch[i:i+50]
    sb.table("meal_logs").insert(batch).execute()
    print(f"  {min(i+50, total)}/{total}")

print("\n✅ 시드 데이터 삽입 완료!")
print(f"  기간: {start_date} ~ {end_date}")
print(f"  식단 기록: {total}개")
print(f"  인바디: 3회")
print(f"  전략: 3회 (초기 + 인바디 업데이트 2회)")