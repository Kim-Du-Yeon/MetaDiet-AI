"""
tools/analytics.py

역할: 누적 식단 데이터 분석 함수 모음
이게 GPT/기존 앱과의 핵심 차별점.
DB에 쌓인 데이터를 패턴으로 전환하는 로직.
"""
from datetime import date, timedelta
from app.db.supabase_client import get_supabase
from app.core.service_clock import service_today

sb = get_supabase()


async def get_yesterday_summary(user_id: str) -> dict:
    """
    어제 식단 요약 - 오늘 전략 조정의 근거
    초과했으면 오늘 얼마나 줄여야 하는지 계산
    """
    yesterday = (service_today() - timedelta(days=1)).isoformat()
    rows = sb.table("meal_logs").select(
        "calories, protein_g, carbs_g, fat_g"
    ).eq("user_id", user_id).eq("log_date", yesterday).execute().data

    if not rows:
        return {"has_data": False, "date": yesterday}

    total_cal = sum(r["calories"] for r in rows)
    total_protein = sum(r["protein_g"] for r in rows)

    strategy = sb.table("diet_strategies").select(
        "daily_calories, protein_g"
    ).eq("user_id", user_id).eq("is_active", True).limit(1).execute().data

    target_cal = strategy[0]["daily_calories"] if strategy else 2000
    target_protein = strategy[0]["protein_g"] if strategy else 130

    excess_cal = round(total_cal - target_cal, 1)
    protein_deficit = round(target_protein - total_protein, 1)

    return {
        "has_data": True,
        "date": yesterday,
        "total_calories": round(total_cal, 1),
        "total_protein": round(total_protein, 1),
        "target_calories": target_cal,
        "target_protein": target_protein,
        "excess_calories": excess_cal,        # 양수=초과, 음수=부족
        "protein_deficit": protein_deficit,    # 양수=부족
        "today_adjustment": round(-excess_cal * 0.5, 0),  # 초과분의 50%만 조정
    }


async def get_pattern_analysis(user_id: str, days: int = 30) -> dict:
    """
    최근 N일 식단 패턴 분석
    - 요일별 칼로리 패턴
    - 단백질 달성률
    - 목표 체중 도달 예상 기간
    """
    start = (service_today() - timedelta(days=days)).isoformat()
    rows = sb.table("meal_logs").select(
        "log_date, calories, protein_g, carbs_g, fat_g"
    ).eq("user_id", user_id).gte("log_date", start).execute().data

    if not rows:
        return {"has_data": False}

    strategy = sb.table("diet_strategies").select(
        "daily_calories, protein_g"
    ).eq("user_id", user_id).eq("is_active", True).limit(1).execute().data

    target_cal = strategy[0]["daily_calories"] if strategy else 2000
    target_protein = strategy[0]["protein_g"] if strategy else 130

    # 날짜별 집계
    by_date = {}
    for row in rows:
        d = row["log_date"]
        if d not in by_date:
            by_date[d] = {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0}
        by_date[d]["calories"] += row["calories"]
        by_date[d]["protein_g"] += row["protein_g"]

    logged_days = len(by_date)
    if logged_days == 0:
        return {"has_data": False}

    avg_cal = sum(v["calories"] for v in by_date.values()) / logged_days
    avg_protein = sum(v["protein_g"] for v in by_date.values()) / logged_days

    # 요일별 패턴 (0=월, 6=일)
    weekday_cal = {i: [] for i in range(7)}
    for d, v in by_date.items():
        weekday = date.fromisoformat(d).weekday()
        weekday_cal[weekday].append(v["calories"])

    weekday_avg = {}
    weekday_names = ["월", "화", "수", "목", "금", "토", "일"]
    for i, name in enumerate(weekday_names):
        if weekday_cal[i]:
            weekday_avg[name] = round(sum(weekday_cal[i]) / len(weekday_cal[i]), 0)

    # 주말 초과 패턴 감지
    weekend_avg = (weekday_avg.get("토", 0) + weekday_avg.get("일", 0)) / 2
    weekday_avg_val = sum(
        weekday_avg.get(d, 0) for d in ["월", "화", "수", "목", "금"]
    ) / 5 if any(weekday_avg.get(d) for d in ["월", "화", "수", "목", "금"]) else 0

    weekend_excess = round(weekend_avg - target_cal, 0) if weekend_avg > 0 else 0
    has_weekend_pattern = weekend_excess > 200

    # 달성률
    cal_achievement = round((avg_cal / target_cal) * 100, 1)
    protein_achievement = round((avg_protein / target_protein) * 100, 1)

    # 목표 체중 도달 예상
    # 7700kcal = 체지방 1kg
    daily_deficit = target_cal - avg_cal  # 음수면 초과
    inbody = sb.table("inbody_logs").select(
        "weight_kg, measured_date"
    ).eq("user_id", user_id).order("measured_date", desc=True).limit(2).execute().data

    weeks_delayed = 0
    if has_weekend_pattern and len(inbody) >= 1:
        weekly_excess = weekend_excess * 2  # 토+일
        weeks_delayed = round(weekly_excess * 4 / 7700, 1)  # 한달 기준

    return {
        "has_data": True,
        "period_days": logged_days,
        "avg_daily_calories": round(avg_cal, 1),
        "avg_daily_protein": round(avg_protein, 1),
        "target_calories": target_cal,
        "target_protein": target_protein,
        "cal_achievement_pct": cal_achievement,
        "protein_achievement_pct": protein_achievement,
        "weekday_pattern": weekday_avg,
        "has_weekend_excess_pattern": has_weekend_pattern,
        "weekend_avg_excess": weekend_excess,
        "weeks_delayed_by_weekend": weeks_delayed,
        "daily_deficit": round(daily_deficit, 1),
    }


async def get_inbody_diet_correlation(user_id: str) -> dict:
    """
    인바디 변화와 식단 패턴의 상관관계 분석
    "근육이 줄었는데 그 기간 단백질 달성률이 낮았다" 같은 연결
    """
    inbody_rows = sb.table("inbody_logs").select("*").eq(
        "user_id", user_id
    ).order("measured_date", desc=False).execute().data

    if len(inbody_rows) < 2:
        return {"has_data": False, "reason": "인바디 기록 2회 이상 필요"}

    latest = inbody_rows[-1]
    previous = inbody_rows[-2]

    # 두 인바디 사이 기간의 식단 분석
    start_date = previous["measured_date"]
    end_date = latest["measured_date"]

    meal_rows = sb.table("meal_logs").select(
        "calories, protein_g"
    ).eq("user_id", user_id).gte(
        "log_date", start_date
    ).lte("log_date", end_date).execute().data

    strategy = sb.table("diet_strategies").select(
        "protein_g"
    ).eq("user_id", user_id).eq("is_active", True).limit(1).execute().data
    target_protein = strategy[0]["protein_g"] if strategy else 130

    by_date = {}
    for row in meal_rows:
        pass

    period_days = (date.fromisoformat(end_date) - date.fromisoformat(start_date)).days or 1
    avg_protein = sum(r["protein_g"] for r in meal_rows) / period_days if meal_rows else 0
    protein_achievement = round((avg_protein / target_protein) * 100, 1)

    muscle_change = round(latest["skeletal_muscle_kg"] - previous["skeletal_muscle_kg"], 2)
    fat_change = round(latest["body_fat_kg"] - previous["body_fat_kg"], 2)
    weight_change = round(latest["weight_kg"] - previous["weight_kg"], 2)

    muscle_lost = muscle_change < -0.2
    fat_reduced = fat_change < 0

    return {
        "has_data": True,
        "period": f"{start_date} ~ {end_date}",
        "weight_change": weight_change,
        "muscle_change": muscle_change,
        "fat_change": fat_change,
        "avg_protein_in_period": round(avg_protein, 1),
        "protein_achievement_pct": protein_achievement,
        "muscle_lost": muscle_lost,
        "fat_reduced": fat_reduced,
        "insight": _generate_insight(muscle_change, fat_change, protein_achievement),
    }


def _generate_insight(muscle_change: float, fat_change: float, protein_pct: float) -> str:
    if muscle_change < -0.2 and protein_pct < 80:
        return f"근육이 {abs(muscle_change)}kg 감소했고 그 기간 단백질 달성률이 {protein_pct}%였습니다. 단백질 섭취 부족이 근손실의 원인일 수 있습니다."
    elif muscle_change >= 0 and fat_change < 0:
        return f"근육은 유지·증가하면서 체지방이 {abs(fat_change)}kg 감소했습니다. 이상적인 변화입니다."
    elif fat_change > 0:
        return f"체지방이 {fat_change}kg 증가했습니다. 칼로리 초과가 지속된 결과입니다."
    else:
        return "체성분 변화가 미미합니다. 식단 일관성을 높이면 더 빠른 변화를 볼 수 있습니다."
    
async def get_missing_meal_alert(user_id: str) -> dict:
    """
    오늘 누락된 끼니 감지 + 이번달 누락 횟수 집계
    """
    from datetime import datetime
    now = datetime.now()
    hour = now.hour
    today_value = service_today()
    today = today_value.isoformat()

    # 오늘 기록된 끼니
    rows = sb.table("meal_logs").select("meal_type").eq(
        "user_id", user_id).eq("log_date", today).execute().data
    logged_types = set(r["meal_type"] for r in rows)

    # 시간대별 누락 감지
    missing = []
    if hour >= 14 and "breakfast" not in logged_types:
        missing.append("아침")
    if hour >= 18 and "lunch" not in logged_types:
        missing.append("점심")

    # 이번달 누락 횟수
    month_start_value = today_value.replace(day=1)
    month_start = month_start_value.isoformat()
    all_days = (today_value - month_start_value).days + 1

    month_rows = sb.table("meal_logs").select(
        "log_date, meal_type"
    ).eq("user_id", user_id).gte("log_date", month_start).execute().data

    logged_by_date = {}
    for row in month_rows:
        d = row["log_date"]
        if d not in logged_by_date:
            logged_by_date[d] = set()
        logged_by_date[d].add(row["meal_type"])

    # 누락 횟수: 하루에 아침/점심/저녁 중 하나라도 없으면 누락 1회
    missing_days = 0
    for i in range(all_days):
        check_date = (month_start_value + timedelta(days=i)).isoformat()
        if check_date > today:
            break
        day_logs = logged_by_date.get(check_date, set())
        if len(day_logs) < 2:  # 2끼 미만이면 누락
            missing_days += 1

    return {
        "missing_today": missing,
        "has_missing_today": len(missing) > 0,
        "missing_days_this_month": missing_days,
        "total_days_this_month": all_days,
        "missing_rate": round((missing_days / all_days) * 100, 1) if all_days > 0 else 0,
    }
