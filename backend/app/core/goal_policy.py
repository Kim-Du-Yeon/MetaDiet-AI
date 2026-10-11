"""Deterministic goal adjustment policy backed by reviewed source passages."""
from datetime import date
import math
from app.core.service_clock import service_today

POLICY_VERSION = "goal-applicability-v2"
DIET_SOURCE = {
    "status": "reviewed_for_general_adult_weight_loss",
    "source": "guideline2022_vol8.pdf",
    "document_sha256": "d28c3ef8b06beba0c659cb7dc096db6b521190baa4f8b430ebb5cce4284d0147",
    "source_url": "https://general.kosso.or.kr/html/user/core/view/reaction/main/kosso/inc/data/guideline2022_vol8.pdf",
    "year": 2022, "pdf_page": 6, "printed_pages": "10-11",
    "population": "overweight_or_obese_adult",
    "reviewed_deficit_kcal": [500, 1000], "service_deficit_kcal": 500,
    "minimum_energy_floor_rule": "1200 kcal if weight <113 kg; 1500 kcal if weight >=113 kg",
    "minimum_energy_floor_pdf_page": 8,
    "very_low_calorie_boundary_kcal": 800,
    "newer_scope_check": {
        "source": "2024 Clinical Practice Guidelines by KSSO",
        "doi": "10.7570/jomes25042",
        "scope": "diagnosis_and_pharmacologic_treatment",
        "conclusion": "does_not_supersede_2022_diet_therapy_section",
    },
    "limitation": "일반 성인 자가확인 범위의 보수적 제안이며 임상 처방이나 의료 감독을 대체하지 않음.",
}
BULK_SOURCE = {
    "status": "population_and_protocol_review_required",
    "source_url": "https://doi.org/10.1186/s40798-023-00651-y", "year": 2023,
    "population": "resistance-trained participants",
    "limitation": "완료자 17명의 8주 연구이므로 일반 성인 전체의 증량 공식으로 적용하지 않음.",
}
SOURCE_REVIEWS = {"diet": DIET_SOURCE, "bulk": BULK_SOURCE}


def finite_number(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite positive number")
    return float(value)


def _deferred(code, message, kcal):
    return {"status": "adjustment_deferred", "reason_code": code, "message": message,
            "target_calories": kcal, "applied_adjustment_kcal": 0}


def assess_goal(profile: dict, maintenance_kcal: float) -> dict:
    kcal = finite_number(maintenance_kcal, "maintenance_kcal")
    goal = profile.get("goal") or "maintain"
    if goal not in ("diet", "bulk", "maintain"):
        raise ValueError("지원하지 않는 목표입니다.")
    weight = finite_number(profile.get("weight_kg"), "weight_kg")
    target = profile.get("target_weight_kg")
    change = None
    if target is not None:
        target = finite_number(target, "target_weight_kg")
        change = target - weight
        if ((goal == "diet" and change >= 0) or (goal == "bulk" and change <= 0)
                or (goal == "maintain" and change != 0)):
            raise ValueError("목표 종류와 목표 체중 방향이 맞지 않습니다.")
    deadline = profile.get("target_date")
    if deadline is not None:
        try:
            if type(deadline) is str:
                deadline = date.fromisoformat(deadline)
            if type(deadline) is not date or deadline <= service_today():
                raise ValueError()
        except (TypeError, ValueError):
            raise ValueError("목표일은 오늘 이후의 유효한 날짜여야 합니다.") from None
    days = (deadline - service_today()).days if deadline else None
    common = {
        "policy_version": POLICY_VERSION, "goal": goal,
        "target_weight_kg": target, "target_date": deadline.isoformat() if deadline else None,
        "target_change_kg": change, "days_to_target": days,
        "requested_weekly_change_kg": change * 7 / days if change is not None and days else None,
        "requested_rate_is_recommendation": False,
        "source_review": SOURCE_REVIEWS.get(goal),
        "missing_inputs": [key for key in ("target_weight_kg", "target_date")
                           if goal != "maintain" and profile.get(key) is None],
    }
    if goal == "maintain":
        return {**common, "status": "maintenance_ready",
                "reason_code": "maintenance_formula_reviewed",
                "message": "유지 에너지 계산식에 따른 기준선을 제안합니다.",
                "target_calories": kcal, "applied_adjustment_kcal": 0}
    if goal == "bulk":
        return {**common, **_deferred("bulk_applicability_unverified",
            "증량 연구의 운동 경험·프로그램 적용대상이 제한적이어서 유지 기준선만 제안합니다.", kcal)}
    if common["missing_inputs"]:
        return {**common, **_deferred("weight_loss_goal_incomplete",
            "목표 체중과 목표일을 모두 입력해야 감량 조정안을 제안할 수 있습니다.", kcal)}
    height_m = finite_number(profile.get("height_cm"), "height_cm") / 100
    bmi = weight / height_m ** 2
    floor = 1500 if weight >= 113 else 1200
    detail = {**common, "bmi": bmi, "minimum_energy_floor_kcal": floor,
              "selected_deficit_kcal": DIET_SOURCE["service_deficit_kcal"]}
    if bmi < 23:
        return {**detail, **_deferred("weight_loss_population_not_applicable",
            "현재 BMI는 이 과체중·비만 성인 감량 정책의 적용 범위가 아니므로 자동 조정을 보류합니다.", kcal)}
    target_kcal = kcal - DIET_SOURCE["service_deficit_kcal"]
    if target_kcal < floor:
        return {**detail, **_deferred("minimum_energy_floor_blocks_reviewed_deficit",
            "검토된 500 kcal 감량을 적용하면 서비스 최소 열량 기준보다 낮아져 자동 조정을 보류합니다.", kcal)}
    return {**detail, "status": "adjustment_ready",
            "reason_code": "reviewed_adult_weight_loss_policy",
            "message": "개인화가 필요한 500~1,000 kcal 범위 중 보수적인 500 kcal 감량안을 제안합니다. 확정 전에는 적용되지 않습니다.",
            "target_calories": target_kcal, "applied_adjustment_kcal": -500}


def assess_weight_trend(measurements: list[dict]) -> dict:
    """Apply the reviewed 1-month 2.5% checkpoint without inventing a new deficit."""
    valid = []
    for item in measurements:
        try:
            measured = date.fromisoformat(str(item["measured_date"]))
            weight = finite_number(item["weight_kg"], "weight_kg")
            valid.append((measured, weight))
        except (KeyError, TypeError, ValueError):
            continue
    valid = sorted(set(valid))
    latest = valid[-1] if valid else None
    candidates = [(day, weight) for day, weight in valid[:-1]
                  if 28 <= (latest[0] - day).days <= 42] if latest else []
    if not candidates:
        return {"status": "insufficient_data", "automatic_calorie_adjustment_kcal": 0,
                "requires_human_confirmation": False,
                "message": "28~42일 간격의 확정 체중 기록이 필요합니다."}
    baseline = max(candidates, key=lambda value: value[0])
    days = (latest[0] - baseline[0]).days
    loss_pct = (baseline[1] - latest[1]) / baseline[1] * 100
    source = {"source": "guideline2022_vol8.pdf", "pdf_page": 8,
              "document_sha256": DIET_SOURCE["document_sha256"],
              "reviewed_threshold": "within one month, 2.5% weight loss",
              "action": "consider strengthening comprehensive lifestyle intervention"}
    if loss_pct < 2.5:
        return {"status": "lifestyle_review_recommended", "days": days,
                "weight_loss_pct": loss_pct, "automatic_calorie_adjustment_kcal": 0,
                "requires_human_confirmation": True, "source_review": source,
                "message": "생활습관 중재 강화 검토 대상입니다. 기록 완전성·실행 가능성·의학적 상태를 먼저 확인하며 칼로리를 자동으로 더 줄이지 않습니다."}
    return {"status": "continue_current_strategy", "days": days,
            "weight_loss_pct": loss_pct, "automatic_calorie_adjustment_kcal": 0,
            "requires_human_confirmation": False, "source_review": source,
            "message": "현재 전략을 유지하고 추세를 계속 확인합니다."}
