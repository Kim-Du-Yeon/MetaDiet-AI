"""
routes/main.py

HITL 흐름:
  /chat POST     → diet_logger 실행 → pending_meals 저장 → save_chat → END
                   (interrupted=False, pending_meals 있음)
  다음 /chat POST → supervisor → confirm [interrupt_before] → 대기
                   (interrupted=True, next=('confirm',))
  /chat/resume   → aupdate_state({"message": user_input}) + ainvoke(None)
                 → confirm 실행 → 저장/수정/취소
"""
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from app.agents.graph import get_graph, lifespan
from app.ocr.inbody_ocr import extract_inbody_from_image
from app.db.supabase_client import get_supabase
from app.core.auth import get_current_user, get_current_auth_id
from app.schemas.models import InbodyUploadResponse, ResumeRequest
from pydantic import BaseModel
from typing import Optional
from datetime import date
import calendar
import json, asyncio, time

app = FastAPI(title="Diet Agent API", version="1.0.0", lifespan=lifespan)
sb  = get_supabase()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default"
    pending_meals: Optional[list] = None
    awaiting_confirmation: bool = False
    plan_date: Optional[str] = None
    messages: list = []
    meal_type: Optional[str] = None   # 사용자가 버튼으로 고른 끼니(있으면 강제 적용)


def _is_empty_ocr_value(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip().lower() in {"", "null", "none", "nan"})


def _safe_inbody_date(value) -> str:
    if _is_empty_ocr_value(value):
        return date.today().isoformat()
    text = str(value).strip()
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return date.today().isoformat()


def _safe_float(value, default=None):
    if _is_empty_ocr_value(value):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _is_implausible_inbody_change(current: dict, previous: dict) -> bool:
    prev_weight = _safe_float(previous.get("weight_kg"))
    prev_muscle = _safe_float(previous.get("skeletal_muscle_kg"))
    weight = _safe_float(current.get("weight_kg"))
    muscle = _safe_float(current.get("skeletal_muscle_kg"))
    if not prev_weight or not prev_muscle or not weight or not muscle:
        return False
    return (
        weight < prev_weight * 0.82 or weight > prev_weight * 1.18
        or muscle < prev_muscle * 0.82 or muscle > prev_muscle * 1.18
    )


def _estimate_next_inbody_from_history(history: list[dict], measured_date: str) -> dict | None:
    valid = [
        row for row in history
        if _safe_float(row.get("weight_kg"), 0) >= 70
        and _safe_float(row.get("skeletal_muscle_kg"), 0) >= 30
    ]
    if len(valid) < 2:
        return None

    latest, previous = valid[0], valid[1]

    def projected(field: str, min_value: float = 0) -> float:
        latest_value = _safe_float(latest.get(field), 0)
        previous_value = _safe_float(previous.get(field), latest_value)
        value = latest_value + (latest_value - previous_value)
        return round(max(value, min_value), 1)

    return {
        "measured_date": measured_date,
        "weight_kg": projected("weight_kg", 1),
        "skeletal_muscle_kg": projected("skeletal_muscle_kg", 1),
        "body_fat_kg": projected("body_fat_kg", 0),
        "body_fat_pct": projected("body_fat_pct", 1),
        "bmi": projected("bmi", 1),
        "bmr_kcal": round(projected("bmr_kcal", 1)),
        "protein_kg": None,
        "mineral_kg": None,
    }


def _repair_implausible_inbody(user_id: str, inbody_data: dict, measured_date: str) -> dict:
    history = (
        sb.table("inbody_logs")
        .select("*")
        .eq("user_id", user_id)
        .order("measured_date", desc=True)
        .limit(5)
        .execute()
        .data
    )
    valid_history = [
        row for row in history
        if _safe_float(row.get("weight_kg"), 0) >= 70
        and _safe_float(row.get("skeletal_muscle_kg"), 0) >= 30
    ]
    if not valid_history or not _is_implausible_inbody_change(inbody_data, valid_history[0]):
        return inbody_data

    repaired = _estimate_next_inbody_from_history(valid_history, measured_date)
    if repaired:
        print(f"=== [inbody_ocr] implausible OCR repaired | raw={inbody_data} | repaired={repaired} ===")
        return {**inbody_data, **repaired}
    return inbody_data


def _initial_state(req: ChatRequest, user_id: str) -> dict:
    return {
        "user_id": user_id, "message": req.message,
        "intent": "", "response": "", "messages": req.messages[-10:] if req.messages else [],
        "agent_used": "", "today_calories": 0.0, "today_protein": 0.0,
        "today_carbs": 0.0, "today_fat": 0.0, "target_calories": 0.0,
        "target_protein": 0.0, "target_carbs": 0.0, "target_fat": 0.0,
        "strategy_note": "", "latest_inbody": None, "days_since_inbody": 999,
        "today_date": date.today().isoformat(), "pending_meals": None,
        "awaiting_confirmation": False, "plan_date": None,
        "overwrite_on_confirm": False,
        "forced_meal_type": req.meal_type,
        "validation_attempts": 0, "validation_passed": None,
        "validation_feedback": "", "can_improve": None,
    }


def _sv(snap) -> dict:
    if snap is None: return {}
    if hasattr(snap, "values"): return snap.values or {}
    if isinstance(snap, dict): return snap
    return {}


async def _stream(graph, config: dict):
    snap           = await graph.aget_state(config)
    is_interrupted = bool(snap.next) if snap else False
    sv             = _sv(snap)

    # response 읽기 우선순위:
    # 1. interrupt_before에 걸린 경우 → state["response"]에 직전 노드 결과 있음
    # 2. interrupt()로 걸린 경우 → snap.tasks[0].interrupts[0].value에 있음
    response_text = sv.get("response", "")
    if not response_text and is_interrupted and snap and snap.tasks:
        for task in snap.tasks:
            if hasattr(task, "interrupts") and task.interrupts:
                response_text = task.interrupts[0].value
                break
    if not response_text:
        print(f"=== [stream] response 없음 | interrupted={is_interrupted} | next={getattr(snap,'next',None)} ===")

    for word in response_text.split(" "):
        yield f"data: {json.dumps({'type':'token','content':word+' '}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.03)

    # 저장 완료(pending=None, not interrupted)이면 새 thread_id 발급
    pending = sv.get("pending_meals")
    # 저장 완료(pending=None, not interrupted)이면 새 thread_id 발급
    # 이전 thread_id는 done 이벤트의 prev_thread_id로 프론트에 전달
    current_tid = config["configurable"]["thread_id"].split("_",1)[-1]
    new_tid = str(int(time.time())) if (not pending and not is_interrupted) else current_tid
    yield f"data: {json.dumps({'type':'done','agent_used':sv.get('agent_used',''),'today_calories':sv.get('today_calories',0),'target_calories':sv.get('target_calories',0),'pending_meals':pending,'awaiting_confirmation':sv.get('awaiting_confirmation',False),'plan_date':sv.get('plan_date'),'thread_id':new_tid,'prev_thread_id':current_tid if new_tid != current_tid else None,'interrupted':is_interrupted}, ensure_ascii=False)}\n\n"


@app.post("/chat")
async def chat(req: ChatRequest, current_user: str = Depends(get_current_user)):
    async def generate():
        graph  = get_graph()
        config = {"configurable": {"thread_id": f"{current_user}_{req.thread_id}"}}

        snap = await graph.aget_state(config)
        sv_now = _sv(snap)
        has_pending = bool(sv_now.get("pending_meals"))

        print(f"=== [chat] thread={req.thread_id} | next={snap.next if snap else None} | pending={has_pending} ===")

        if has_pending:
            print(f"=== [chat] pending 감지 | next={snap.next if snap else ()} | message='{req.message}' ===")
            try:
                if snap and snap.next:
                    # next=('confirm',): interrupt 상태 → message 업데이트 후 ainvoke(None)
                    await graph.aupdate_state(config, {"message": req.message})
                    await graph.ainvoke(None, config=config)
                else:
                    # next=(): 롤백 후 완료 상태
                    # as_node="confirm"으로 confirm 직전 상태로 만들고 ainvoke(None)
                    await graph.aupdate_state(
                        config, {"message": req.message}, as_node="confirm"
                    )
                    await graph.ainvoke(None, config=config)
                after = await graph.aget_state(config)
                after_sv = _sv(after)
                print(f"=== [chat] 처리 후 | response='{str(after_sv.get('response',''))[:50]}' | next={after.next if after else None} ===")
            except Exception as e:
                print(f"=== [chat] 오류: {e} ===")
                yield f"data: {json.dumps({'type':'error','content':str(e)}, ensure_ascii=False)}\n\n"
                return
            async for chunk in _stream(graph, config):
                yield chunk
            return
        elif snap and snap.next:
            # pending 없는 완료된 thread → 새 thread로 전환
            new_tid = str(int(time.time()))
            print(f"=== [chat] 완료된 thread → 새 thread: {new_tid} ===")
            config = {"configurable": {"thread_id": f"{current_user}_{new_tid}"}}

        try:
            await graph.ainvoke(_initial_state(req, current_user), config=config)
        except Exception as e:
            print(f"=== [chat] 오류: {e} ===")
            yield f"data: {json.dumps({'type':'error','content':str(e)}, ensure_ascii=False)}\n\n"
            return
        async for chunk in _stream(graph, config):
            yield chunk
    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/chat/resume")
async def resume_chat(req: ResumeRequest, current_user: str = Depends(get_current_user)):
    """
    interrupt_before=["confirm"] 재개.
    aupdate_state로 message 업데이트 후 ainvoke(None)으로 confirm 실행.
    AgentState.message에 keep_latest 리듀서가 있어서 충돌 없음.
    """
    async def generate():
        graph  = get_graph()
        config = {"configurable": {"thread_id": f"{current_user}_{req.thread_id}"}}
        snap   = await graph.aget_state(config)
        if not snap or not snap.next:
            yield f"data: {json.dumps({'type':'error','content':'재개할 대화가 없습니다.'}, ensure_ascii=False)}\n\n"
            return
        sv = _sv(snap)
        if not sv.get("pending_meals"):
            response_text = "확인 대기 중인 식단이 없어요. 사진 인식 결과가 아니라면 다시 사진을 올리거나, 음식명과 양을 직접 입력해주세요."
            for word in response_text.split(" "):
                yield f"data: {json.dumps({'type':'token','content':word+' '}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.03)
            new_tid = str(int(time.time()))
            yield f"data: {json.dumps({'type':'done','agent_used':'','today_calories':sv.get('today_calories',0),'target_calories':sv.get('target_calories',0),'pending_meals':None,'awaiting_confirmation':False,'plan_date':None,'thread_id':new_tid,'prev_thread_id':req.thread_id,'interrupted':False}, ensure_ascii=False)}\n\n"
            return
        print(f"=== [resume] message='{req.message}' | next={snap.next} ===")
        try:
            await graph.aupdate_state(config, {"message": req.message})
            await graph.ainvoke(None, config=config)
        except Exception as e:
            print(f"=== [resume] 오류: {e} ===")
            yield f"data: {json.dumps({'type':'error','content':str(e)}, ensure_ascii=False)}\n\n"
            return
        async for chunk in _stream(graph, config):
            yield chunk
    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/chat/history/{thread_id}")
async def get_chat_history(thread_id: str, current_user: str = Depends(get_current_user)):
    """
    특정 thread의 체크포인트 이력 조회 (타임 트래블용).
    thread_id: 실제 thread ID (done 이벤트의 thread_id 값)
               예: 1780499418  (타임스탬프 기반)
    """
    graph  = get_graph()
    config = {"configurable": {"thread_id": f"{current_user}_{thread_id}"}}
    snap   = await graph.aget_state(config)
    if not snap: return {"checkpoints": [], "current": None}
    history = []
    async for cp in graph.aget_state_history(config):
        history.append({
            "checkpoint_id":    cp.config.get("configurable",{}).get("checkpoint_id"),
            "step":             cp.metadata.get("step", 0),
            "agent_used":       cp.values.get("agent_used", ""),
            "message":          cp.values.get("message", ""),
            "response_preview": cp.values.get("response","")[:80] if cp.values.get("response") else "",
            "next":             list(cp.next) if cp.next else [],
            "has_pending":      bool(cp.values.get("pending_meals")),
        })
    sv = _sv(snap)
    return {
        "thread_id": thread_id,
        "current": {"pending_meals": sv.get("pending_meals"), "interrupted": bool(snap.next),
                    "agent_used": sv.get("agent_used","")},
        "checkpoints": history[:20],
        "total": len(history),
    }


@app.post("/chat/rollback")
async def rollback_to_checkpoint(thread_id: str, checkpoint_id: str, current_user: str = Depends(get_current_user)):
    """
    특정 체크포인트로 state 롤백 (타임 트래블).
    LangGraph update_state로 해당 checkpoint의 state를 현재 thread에 덮어씀.
    롤백 후 같은 thread_id로 계속 대화하면 해당 시점부터 재개됨.
    """
    graph = get_graph()

    # 롤백할 체크포인트 state 읽기
    src_config = {"configurable": {"thread_id": f"{current_user}_{thread_id}", "checkpoint_id": checkpoint_id}}
    snap = await graph.aget_state(src_config)
    if not snap:
        raise HTTPException(404, "체크포인트를 찾을 수 없습니다.")

    sv = _sv(snap)

    # 현재 thread를 해당 checkpoint state로 덮어씀
    # as_node=None: 현재 위치 유지하며 state 값만 패치
    target_config = {"configurable": {"thread_id": f"{current_user}_{thread_id}"}}
    rollback_state = {**sv, "overwrite_on_confirm": bool(sv.get("pending_meals"))}
    await graph.aupdate_state(target_config, rollback_state)

    # 롤백 후 현재 state 확인
    current = await graph.aget_state(target_config)
    cv = _sv(current)

    print(f"=== [rollback] step={snap.metadata.get('step')} | agent={cv.get('agent_used')} | message='{cv.get('message','')}' ===")

    # 롤백 후 next=() 상태이므로 프론트는 /chat으로 새 요청 필요
    # (pending_meals 있어도 resume 아닌 /chat으로 보내야 supervisor→confirm 경로 실행)
    return {
        "success":        True,
        "use_resume":     False,  # 롤백 후에는 /chat 사용
        "rolled_back_to": {
            "checkpoint_id": checkpoint_id,
            "step":          snap.metadata.get("step"),
            "agent_used":    cv.get("agent_used", ""),
            "message":       cv.get("message", ""),
            "response":      cv.get("response", "")[:100] if cv.get("response") else "",
            "pending_meals": cv.get("pending_meals"),
            "overwrite_on_confirm": cv.get("overwrite_on_confirm", False),
        }
    }


async def _process_inbody(user_id: str, image_bytes: bytes) -> dict:
    """
    인바디 이미지 처리: OCR 추출 → Storage·DB 저장 → inbody 노드(전략 재설정) 실행.
    인바디가 아니면 extract_inbody_from_image가 ValueError를 던짐(필수 수치 누락).
    반환: type='inbody' + 추출 수치 + 전략 노트.
    """
    inbody_data = await extract_inbody_from_image(image_bytes)   # 인바디 아니면 ValueError
    measured_date = date.today().isoformat()
    inbody_data = _repair_implausible_inbody(user_id, inbody_data, measured_date)
    weight_kg = _safe_float(inbody_data.get("weight_kg"))
    skeletal_muscle_kg = _safe_float(inbody_data.get("skeletal_muscle_kg"))
    body_fat_pct = _safe_float(inbody_data.get("body_fat_pct"))
    if weight_kg is None or skeletal_muscle_kg is None or body_fat_pct is None:
        raise HTTPException(status_code=400, detail="인바디 필수 수치(체중, 골격근량, 체지방률)를 인식하지 못했습니다. 이미지를 다시 업로드해주세요.")

    file_path = f"inbody/{user_id}/{date.today().isoformat()}_{int(time.time())}.jpg"
    sb.storage.from_("inbody-images").upload(file_path, image_bytes)
    image_url  = sb.storage.from_("inbody-images").get_public_url(file_path)
    inbody_row = sb.table("inbody_logs").insert({
        "user_id": user_id, "measured_date": measured_date,
        "weight_kg": weight_kg, "skeletal_muscle_kg": skeletal_muscle_kg,
        "body_fat_kg": _safe_float(inbody_data.get("body_fat_kg"), 0), "body_fat_pct": body_fat_pct,
        "bmi": _safe_float(inbody_data.get("bmi")), "bmr_kcal": _safe_float(inbody_data.get("bmr_kcal")),
        "protein_kg": _safe_float(inbody_data.get("protein_kg")), "mineral_kg": _safe_float(inbody_data.get("mineral_kg")),
        "image_url": image_url,
    }).execute().data[0]
    graph  = get_graph()
    config = {"configurable": {"thread_id": f"{user_id}_inbody"}}
    await graph.ainvoke({**_initial_state(ChatRequest(message="인바디 업로드됨. 전략을 재설정해주세요."), user_id),
                         "intent":"inbody","latest_inbody":inbody_row,"days_since_inbody":0}, config=config)
    sv = _sv(await graph.aget_state(config))
    return {
        "type": "inbody",
        "measured_date": measured_date,
        "weight_kg": weight_kg, "skeletal_muscle_kg": skeletal_muscle_kg,
        "body_fat_kg": _safe_float(inbody_data.get("body_fat_kg"), 0), "body_fat_pct": body_fat_pct,
        "bmi": _safe_float(inbody_data.get("bmi")), "bmr_kcal": _safe_float(inbody_data.get("bmr_kcal")),
        "strategy_updated": True, "strategy_note": sv.get("response",""),
    }


async def _process_food(image_bytes: bytes) -> dict:
    """음식 이미지 처리: 음식명 인식 → 확인용 메시지. 양·저장은 /chat(diet_logger)로 연결."""
    from app.ocr.food_vision import identify_foods_from_image
    foods = await identify_foods_from_image(image_bytes)
    if not foods:
        return {"type": "food", "foods": [], "message": "사진에서 음식을 인식하지 못했어요. 다시 찍거나 직접 입력해주세요."}
    foods_str = ", ".join(foods)
    return {
        "type": "food", "foods": foods,
        "message": (f"📷 사진에서 **{foods_str}**(으)로 보여요. 맞을까요?\n"
                    f"맞으면 각각 몇 g인지 알려주세요. (예: \"{foods[0]} 200g"
                    + (f", {foods[1]} 150g" if len(foods) > 1 else "") + "\")"),
    }


@app.post("/inbody/upload", response_model=InbodyUploadResponse)
async def upload_inbody(file: UploadFile = File(...), current_user: str = Depends(get_current_user)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "이미지 파일만 업로드 가능합니다.")
    try:
        r = await _process_inbody(current_user, await file.read())
    except ValueError as e:
        raise HTTPException(422, str(e))
    return InbodyUploadResponse(**{k: v for k, v in r.items() if k != "type"})


@app.post("/image/upload")
async def upload_image(file: UploadFile = File(...), current_user: str = Depends(get_current_user)):
    """
    통합 이미지 업로드 — Agent가 사진 종류를 판단해 분기.
      inbody → 체성분 추출 + 전략 재설정
      food   → 음식명 인식 + 확인 메시지(이후 /chat으로 g 입력)
    카메라 버튼 하나로 인바디/음식을 모두 처리(사용자는 종류를 고를 필요 없음).
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "이미지 파일만 업로드 가능합니다.")
    from app.ocr.image_classifier import classify_image_type
    image_bytes = await file.read()
    kind = await classify_image_type(image_bytes)
    if kind == "inbody":
        try:
            return await _process_inbody(current_user, image_bytes)
        except ValueError:
            # 인바디로 분류됐으나 수치 추출 실패 → 음식으로 폴백
            return await _process_food(image_bytes)
    if kind == "food":
        return await _process_food(image_bytes)
    return {"type": "unknown", "message": "인바디 결과지나 음식 사진을 올려주세요."}


@app.post("/meal/photo")
async def meal_photo(file: UploadFile = File(...), current_user: str = Depends(get_current_user)):
    """
    음식 사진 → GPT-4o-mini Vision으로 음식명 인식 → 확인용 응답 반환.
    저장은 하지 않음. 사용자가 "네 + 각 음식 몇 g" 응답하면 기존 /chat(diet_logger)로 연결.
    (Vision은 음식명 파싱에만 사용 — 양·저장은 기존 HITL 흐름이 담당)
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "이미지 파일만 업로드 가능합니다.")
    return await _process_food(await file.read())


class NutritionLookupRequest(BaseModel):
    foods: list   # [{"name": "연어롤", "quantity_g": 200}, ...]


@app.post("/nutrition/lookup")
async def nutrition_lookup(req: NutritionLookupRequest):
    """
    영양성분 '조회만' (기록 X). 사진/텍스트의 음식에 대해 CSV 영양성분을 반환.
    사용자가 식단 기록이 아니라 '이거 영양성분이 궁금'할 때 사용.
    """
    from app.tools.nutrition_db import nutrition_db_tool
    results = []
    for f in req.foods:
        g = float(f.get("quantity_g") or 100)
        r = await nutrition_db_tool.ainvoke({"food_name": f["name"], "quantity_g": g})
        results.append({
            "food_name": f["name"], "quantity_g": g,
            "calories": r.get("calories"), "protein_g": r.get("protein_g"),
            "carbs_g": r.get("carbs_g"), "fat_g": r.get("fat_g"),
            "sodium_mg": r.get("sodium_mg"), "found_in_db": r.get("found_in_db", False),
        })
    return {"results": results}


@app.get("/calories/history")
async def get_calories_history(current_user: str = Depends(get_current_user)):
    rows = (
        sb.table("meal_logs")
        .select("log_date,calories")
        .eq("user_id", current_user)
        .order("log_date", desc=False)
        .execute()
        .data
    )
    strategy_rows = (
        sb.table("diet_strategies")
        .select("daily_calories")
        .eq("user_id", current_user)
        .eq("is_active", True)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
    )
    target_calories = strategy_rows[0]["daily_calories"] if strategy_rows else 2000
    by_date = {}
    for row in rows:
        day = row["log_date"]
        by_date[day] = by_date.get(day, 0) + float(row.get("calories") or 0)
    return {
        "target_calories": target_calories,
        "days": [
            {
                "date": day,
                "calories": round(calories, 1),
                "target_calories": target_calories,
            }
            for day, calories in sorted(by_date.items())
        ],
    }


@app.get("/calendar/month/{year_month}")
async def get_calendar_month(year_month: str, current_user: str = Depends(get_current_user)):
    try:
        year, month = map(int, year_month.split("-"))
        start = date(year, month, 1)
        end = date(year, month, calendar.monthrange(year, month)[1])
    except Exception:
        raise HTTPException(400, "year_month는 YYYY-MM 형식이어야 합니다.")

    rows = (
        sb.table("meal_logs")
        .select("log_date,calories")
        .eq("user_id", current_user)
        .gte("log_date", start.isoformat())
        .lte("log_date", end.isoformat())
        .execute()
        .data
    )
    strategy_rows = (
        sb.table("diet_strategies")
        .select("daily_calories")
        .eq("user_id", current_user)
        .eq("is_active", True)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
    )
    target_calories = strategy_rows[0]["daily_calories"] if strategy_rows else 2000
    by_date = {}
    for row in rows:
        day = row["log_date"]
        by_date[day] = by_date.get(day, 0) + float(row.get("calories") or 0)

    days = []
    for day, calories in by_date.items():
        days.append({
            "date": day,
            "calories": round(calories, 1),
            "logged": True,
            "status": "over" if calories > target_calories else "under",
        })
    return {
        "year_month": year_month,
        "target_calories": target_calories,
        "days": sorted(days, key=lambda x: x["date"]),
    }


@app.get("/calendar/{target_date}")
async def get_calendar(target_date: str, current_user: str = Depends(get_current_user)):
    rows  = sb.table("meal_logs").select("*").eq("user_id",current_user).eq("log_date",target_date).execute().data
    total = {k: sum(r.get(k,0) for r in rows) for k in ["calories","protein_g","carbs_g","fat_g"]}
    return {"date": target_date, "meals": rows, "total": total}


@app.get("/report/weekly")
async def weekly_report(current_user: str = Depends(get_current_user)):
    graph  = get_graph()
    config = {"configurable": {"thread_id": f"{current_user}_report"}}
    await graph.ainvoke({**_initial_state(ChatRequest(message="이번 주 식단 리포트를 보여주세요."), current_user),
                         "intent":"reporter"}, config=config)
    return {"report": _sv(await graph.aget_state(config)).get("response","")}


@app.get("/inbody/history")
async def get_inbody_history(current_user: str = Depends(get_current_user)):
    return sb.table("inbody_logs").select("*").eq("user_id",current_user).order("measured_date",desc=False).execute().data


@app.get("/strategy/current")
async def get_current_strategy(current_user: str = Depends(get_current_user)):
    rows = sb.table("diet_strategies").select("*").eq("user_id",current_user).eq("is_active",True).order("created_at",desc=True).limit(1).execute().data
    return rows[0] if rows else {}


@app.post("/users/setup")
async def setup_user(goal: str, height_cm: float, weight_kg: float, age: int, gender: str,
                      target_weight_kg: Optional[float] = None,
                      target_date: Optional[str] = None,
                      goal_priority: Optional[str] = None,
                      auth_id: str = Depends(get_current_auth_id)):
    """
    회원가입 직후 프로필 입력. users row가 아직 없을 수 있으므로(신규 가입자)
    get_current_user 대신 get_current_auth_id를 쓰고, 여기서 upsert 처리한다.
    """
    bmr = (88.362+13.397*weight_kg+4.799*height_cm-5.677*age) if gender=="male" else (447.593+9.247*weight_kg+3.098*height_cm-4.330*age)
    if goal=="diet":   cal, prot, note = round(bmr*1.4-400), round(weight_kg*2.0), f"체중 감량: {round(bmr*1.4-400)}kcal"
    elif goal=="bulk": cal, prot, note = round(bmr*1.4+400), round(weight_kg*2.2), f"근육 증량: {round(bmr*1.4+400)}kcal"
    else:              cal, prot, note = round(bmr*1.4),     round(weight_kg*1.8), f"체중 유지: {round(bmr*1.4)}kcal"
    carbs_g, fat_g = round((cal*0.5)/4), round((cal*0.25)/9)

    goal_fields = {
        "goal": goal, "height_cm": height_cm, "age": age, "weight_kg": weight_kg,
        "target_weight_kg": target_weight_kg, "target_date": target_date,
        "goal_priority": goal_priority,
    }
    existing = sb.table("users").select("id").eq("auth_id", auth_id).limit(1).execute().data
    if existing:
        user_id = existing[0]["id"]
        sb.table("users").update(goal_fields).eq("id",user_id).execute()
    else:
        user_id = sb.table("users").insert({
            "auth_id": auth_id, "name": "", **goal_fields,
        }).execute().data[0]["id"]

    sb.table("diet_strategies").update({"is_active":False}).eq("user_id",user_id).eq("is_active",True).execute()
    sb.table("diet_strategies").insert({"user_id":user_id,"daily_calories":cal,"protein_g":prot,"carbs_g":carbs_g,"fat_g":fat_g,"strategy_note":note,"triggered_by":"initial","is_active":True}).execute()
    return {"daily_calories":cal,"protein_g":prot,"carbs_g":carbs_g,"fat_g":fat_g,"bmr":round(bmr),"strategy_note":note}


class MealUpdateRequest(BaseModel):
    meal_id: str; quantity_g: float


@app.put("/meal/update")
async def update_meal(req: MealUpdateRequest, current_user: str = Depends(get_current_user)):
    from app.agents.diet_logger.node import NUTRITION_LLM_PROMPT, llm
    import re as _re, json as _json
    row = sb.table("meal_logs").select("food_name,user_id").eq("id",req.meal_id).execute().data
    if not row: raise HTTPException(404, "기록을 찾을 수 없습니다.")
    if row[0]["user_id"] != current_user:
        raise HTTPException(403, "본인의 기록만 수정할 수 있습니다.")
    nutr_resp = await llm.ainvoke(NUTRITION_LLM_PROMPT.format_messages(food_name=row[0]["food_name"], quantity_g=req.quantity_g))
    nutrition = _json.loads(_re.sub(r"```json|```","",nutr_resp.content).strip())
    sb.table("meal_logs").update({"quantity_g":req.quantity_g,**{k:nutrition[k] for k in ["calories","protein_g","carbs_g","fat_g"]}}).eq("id",req.meal_id).execute()
    return {"success":True,"updated":nutrition}


@app.delete("/meal/delete/{meal_id}")
async def delete_meal(meal_id: str, current_user: str = Depends(get_current_user)):
    row = sb.table("meal_logs").select("user_id").eq("id",meal_id).execute().data
    if not row: raise HTTPException(404, "기록을 찾을 수 없습니다.")
    if row[0]["user_id"] != current_user:
        raise HTTPException(403, "본인의 기록만 삭제할 수 있습니다.")
    sb.table("meal_logs").delete().eq("id",meal_id).eq("user_id",current_user).execute()
    return {"success":True}


@app.get("/health")
async def health():
    return {"status":"ok"}

