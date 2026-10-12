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
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from app.agents.graph import get_graph, lifespan
from app.ocr.inbody_ocr import extract_inbody_from_image
from app.db.supabase_client import get_supabase
from app.core.auth import (
    AuthContext,
    get_active_auth_id,
    get_current_user,
    get_current_auth_id,
    get_current_admin,
    get_recent_auth_context,
)
from app.schemas.models import InbodyUploadResponse, ResumeRequest
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, Literal
from uuid import uuid4, UUID
from app.schemas.proposals import (ProposalDecision, MeasurementProposal, MeasurementRevision,
                                   WeightProposal, WeightRevision)
from app.db.proposals import ProposalRepository, ProposalConflict
from app.db.feedback import FeedbackInput, FeedbackRepository, FeedbackStorageUnavailable
from app.db.analytics import ProductAnalyticsUnavailable, ProductEventInput, ProductEventRepository
from app.db.thread_lock import serialized_stream, conversation_lock
from app.agents.execution_stream import (
    ExecutionEventJournal, find_journal, get_or_create_journal, progress_for_runtime_event,
    reset_event_sink, set_event_sink,
)
from datetime import date
from app.core.service_clock import service_today
from app.core.cors import allowed_origins
import calendar
import hashlib
import json, asyncio, time, logging

logger = logging.getLogger(__name__)

app = FastAPI(title="Diet Agent API", version="1.0.0", lifespan=lifespan)
sb  = get_supabase()

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)


def _trace_thread_id(user_id: str, thread_id: str) -> str:
    """Stable pseudonymous trace grouping; never send the internal user UUID."""
    digest = hashlib.sha256(f"{user_id}:{thread_id}".encode("utf-8")).hexdigest()
    return f"thread-{digest[:24]}"


class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default"
    pending_meals: Optional[list] = None
    awaiting_confirmation: bool = False
    plan_date: Optional[str] = None
    messages: list = []
    meal_type: Optional[str] = None   # 사용자가 버튼으로 고른 끼니(있으면 강제 적용)
    requested_action: Optional[Literal["record_only", "meal_plan", "goal", "evidence", "weekly_review"]] = None
    tool_policy: Optional[list[Literal["read_profile", "read_intake", "read_measurements", "assess_goal_progress", "search_foods",
        "nutrition_lookup", "search_evidence", "propose_meal", "propose_strategy", "read_recent_intake", "propose_meal_change"]]] = None
    stream_run_id: Optional[str] = None
    after_seq: int = 0


class AccountDeleteRequest(BaseModel):
    confirmation: Literal["DELETE"]


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rating: int = Field(ge=1, le=5, strict=True)
    category: Literal["general", "answer_quality", "evidence", "usability", "bug"]
    comment: str | None = Field(default=None, max_length=1000)
    client_submission_id: UUID

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class FeedbackResponse(BaseModel):
    id: str
    status: Literal["stored"] = "stored"
    created: bool


class ProductEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_name: Literal[
        "signup_completed", "onboarding_started", "onboarding_completed",
        "chat_sent", "chat_completed", "meal_proposed", "meal_confirmed",
        "measurement_confirmed", "feedback_submitted", "error_shown",
    ]
    status: Literal["success", "failed", "cancelled"]
    client_event_id: UUID
    session_id: UUID
    duration_ms: int | None = Field(default=None, ge=0, le=600_000)
    trace_id: str | None = Field(default=None, max_length=128)
    properties: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @field_validator("properties")
    @classmethod
    def reject_sensitive_properties(cls, value: dict) -> dict:
        allowed = {
            "source": {"web"}, "channel": {"text", "food_photo"},
            "surface": {"chat", "setup", "dashboard", "settings"},
            "category": {"general", "answer_quality", "evidence", "usability", "bug"},
            "route": {"diet_logger", "meal_plan", "strategy", "inbody", "reporter",
                      "confirm", "edit", "goal_manager", "off_topic"},
        }
        if any(key not in allowed or not isinstance(item, str) or item not in allowed[key]
               for key, item in value.items()):
            raise ValueError("민감 정보나 허용되지 않은 속성은 분석 이벤트에 저장할 수 없습니다.")
        return value


class ProductEventResponse(BaseModel):
    id: str
    created: bool


def _is_empty_ocr_value(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip().lower() in {"", "null", "none", "nan"})


def _safe_inbody_date(value) -> str:
    if _is_empty_ocr_value(value):
        return service_today().isoformat()
    text = str(value).strip()
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return service_today().isoformat()


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
        print("=== [inbody_ocr] implausible OCR repaired | values_redacted ===")
        return {**inbody_data, **repaired}
    return inbody_data


def _initial_state(req: ChatRequest, user_id: str, run_id: str | None = None) -> dict:
    return {
        "thread_id": req.thread_id, "run_id": run_id or str(uuid4()),
        "requested_action": req.requested_action, "tool_policy": req.tool_policy,
        "pending_proposal": None, "proposal_decision": None, "proposal_result": None,
        "execution_usage": {}, "execution_status": "running", "execution_error": None, "agent_events": [],
        "user_id": user_id, "message": req.message,
        "intent": "", "response": "", "messages": req.messages[-10:] if req.messages else [],
        "agent_used": "", "today_calories": 0.0, "today_protein": 0.0,
        "today_carbs": 0.0, "today_fat": 0.0, "target_calories": 0.0,
        "target_protein": 0.0, "target_carbs": 0.0, "target_fat": 0.0,
        "strategy_note": "", "latest_inbody": None, "days_since_inbody": 999,
        "today_date": service_today().isoformat(), "pending_meals": None,
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


def _sse(event: dict) -> str:
    return f"id: {event.get('seq', '')}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


async def _invoke_with_progress(graph, graph_input, config: dict, journal: ExecutionEventJournal):
    async def sink(kind: str, payload: dict):
        progress = progress_for_runtime_event(kind, **payload)
        if progress:
            previous = journal.events[-1] if journal.events else None
            if not previous or (previous.get("phase"), previous.get("tool"), previous.get("agent")) != (
                    progress.get("phase"), progress.get("tool"), progress.get("agent")):
                await journal.publish("progress", progress)

    token = set_event_sink(sink)
    try:
        await graph.ainvoke(graph_input, config=config)
        await graph.aupdate_state(config, {"execution_status": "completed", "execution_error": None})
    except Exception:
        try:
            await graph.aupdate_state(config, {"execution_status": "failed", "execution_error": "execution_failed"})
        finally:
            await journal.publish("failed", {"content": "대화 실행에 실패했습니다. 잠시 후 다시 시도해주세요."})
        raise
    finally:
        reset_event_sink(token)
        await journal.finish()


async def _run_and_stream(graph, graph_input, config: dict, run_id: str, after_seq: int = 0):
    scope = config.get("configurable", {}).get("thread_id", "")
    journal, created = get_or_create_journal(run_id, scope)
    if created:
        journal.task = asyncio.create_task(_invoke_with_progress(graph, graph_input, config, journal))
    task = journal.task
    try:
        async for event in journal.subscribe(after_seq=after_seq):
            yield _sse(event)
        if task is not None:
            await task
    except asyncio.CancelledError:
        # The execution owns its DB idempotency key and must finish even if the browser disconnects.
        if task is not None:
            await asyncio.shield(task)
        raise
    finally:
        # GeneratorExit (client disconnect) must not cancel an in-flight proposal/idempotency transaction.
        if task is not None and not task.done():
            await asyncio.shield(task)


async def _replay_progress(config: dict, run_id: str, after_seq: int = 0):
    scope = config.get("configurable", {}).get("thread_id", "")
    journal = find_journal(run_id, scope)
    if journal is None:
        return
    async for event in journal.subscribe(after_seq=after_seq):
        yield _sse(event)


async def _follow_or_resume_run(graph, config: dict, run_id: str, after_seq: int = 0):
    """Follow a local run, or resume its durable LangGraph checkpoint on a new Pod."""
    scope = config.get("configurable", {}).get("thread_id", "")
    journal = find_journal(run_id, scope)
    if journal is not None:
        async for event in journal.subscribe(after_seq=after_seq):
            yield _sse(event)
        return
    async for chunk in _run_and_stream(graph, None, config, run_id, after_seq):
        yield chunk


async def _stream(graph, config: dict, run_id: str, after_seq: int = 0):
    snap           = await graph.aget_state(config)
    is_interrupted = bool(snap.next) if snap else False
    sv             = _sv(snap)
    if sv.get("execution_status") == "failed":
        if after_seq < 100000:
            yield _sse({"type": "failed", "content": "대화 실행에 실패했습니다. 잠시 후 다시 시도해주세요.",
                        "run_id": run_id, "seq": 100000})
        return

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

    for index, word in enumerate(response_text.split(" "), start=1001):
        if index <= after_seq:
            continue
        yield _sse({"type": "answer_delta", "content": word + " ", "run_id": run_id, "seq": index})
        await asyncio.sleep(0.03)

    # 저장 완료(pending=None, not interrupted)이면 새 thread_id 발급
    pending = sv.get("pending_meals")
    # 저장 완료(pending=None, not interrupted)이면 새 thread_id 발급
    # 이전 thread_id는 done 이벤트의 prev_thread_id로 프론트에 전달
    current_tid = config["configurable"]["thread_id"].split("_",1)[-1]
    new_tid = current_tid
    stats = await _public_stats(sv.get("user_id"))
    if after_seq < 100000:
        yield _sse({'type':'completed','agent_used':sv.get('agent_used',''),**stats,'pending_meals':pending,
            'pending_proposal':sv.get('pending_proposal'),'run_id':run_id,'seq':100000,
            'execution_usage':sv.get('execution_usage'),'awaiting_confirmation':sv.get('awaiting_confirmation',False),
            'plan_date':sv.get('plan_date'),'thread_id':new_tid,'prev_thread_id':None,'interrupted':is_interrupted})


async def _public_stats(user_id):
    if not user_id:
        return {}
    def read():
        meals = sb.table("meal_logs").select("calories").eq("user_id", user_id).eq("log_date", service_today().isoformat()).execute().data
        strategy = sb.table("diet_strategies").select("daily_calories").eq("user_id", user_id).eq("is_active", True).limit(1).execute().data
        return {"today_calories": sum(float(m["calories"]) for m in meals), "target_calories": strategy[0]["daily_calories"]} if strategy else {}
    try:
        return await asyncio.to_thread(read)
    except Exception:
        return {}  # Unavailable is not zero; retain the UI's last known values.


@app.post("/chat")
async def chat(req: ChatRequest, current_user: str = Depends(get_current_user)):
    async def generate():
        graph  = get_graph()
        stream_run_id = req.stream_run_id or str(uuid4())
        tid    = f"{current_user}_{req.thread_id}"
        config = {"configurable": {"thread_id": tid},
                  "metadata": {"thread_id": _trace_thread_id(current_user, req.thread_id),
                               "stream_run_id": stream_run_id}}

        snap = await graph.aget_state(config)
        sv_now = _sv(snap)
        if req.stream_run_id and sv_now.get("run_id") == stream_run_id:
            progress_stream = (_follow_or_resume_run(graph, config, stream_run_id, req.after_seq)
                               if sv_now.get("execution_status") == "running"
                               else _replay_progress(config, stream_run_id, req.after_seq))
            async for chunk in progress_stream:
                yield chunk
            async for chunk in _stream(graph, config, stream_run_id, req.after_seq):
                yield chunk
            return
        has_pending = bool(sv_now.get("pending_proposal") or sv_now.get("pending_meals"))

        print(f"=== [chat] thread={req.thread_id} | next={snap.next if snap else None} | pending={has_pending} ===")

        if has_pending:
            print(f"=== [chat] pending 감지 | next={snap.next if snap else ()} | message_redacted ===")
            try:
                if snap and snap.next:
                    # next=('confirm',): interrupt 상태 → message 업데이트 후 ainvoke(None)
                    await graph.aupdate_state(config, {"message": req.message, "run_id": stream_run_id,
                                                       "execution_status": "running"})
                    async for chunk in _run_and_stream(graph, None, config, stream_run_id, req.after_seq):
                        yield chunk
                else:
                    # next=(): 롤백 후 완료 상태
                    # as_node="confirm"으로 confirm 직전 상태로 만들고 ainvoke(None)
                    await graph.aupdate_state(
                        config, {"message": req.message, "proposal_decision": None, "run_id": stream_run_id,
                                 "execution_status": "running"}, as_node="supervisor"
                    )
                    async for chunk in _run_and_stream(graph, None, config, stream_run_id, req.after_seq):
                        yield chunk
                after = await graph.aget_state(config)
                after_sv = _sv(after)
                print(f"=== [chat] 처리 후 | response_redacted | next={after.next if after else None} ===")
            except Exception as e:
                print(f"=== [chat] 오류 유형: {type(e).__name__} ===")
                yield f"data: {json.dumps({'type':'error','content':'요청 처리 중 오류가 발생했습니다.'}, ensure_ascii=False)}\n\n"
                return
            async for chunk in _stream(graph, config, stream_run_id, req.after_seq):
                yield chunk
            return
        elif snap and snap.next:
            # pending 없는 완료된 thread → 새 thread로 전환
            new_tid = str(int(time.time()))
            print(f"=== [chat] 완료된 thread → 새 thread: {new_tid} ===")
            config = {"configurable": {"thread_id": f"{current_user}_{new_tid}"},
                      "metadata": {"thread_id": _trace_thread_id(current_user, new_tid),
                                   "stream_run_id": stream_run_id}}

        try:
            async for chunk in _run_and_stream(
                    graph, _initial_state(req, current_user, stream_run_id), config, stream_run_id, req.after_seq):
                yield chunk
        except Exception as e:
            print(f"=== [chat] 오류 유형: {type(e).__name__} ===")
            yield f"data: {json.dumps({'type':'error','content':'요청 처리 중 오류가 발생했습니다.'}, ensure_ascii=False)}\n\n"
            return
        async for chunk in _stream(graph, config, stream_run_id, req.after_seq):
            yield chunk
    return StreamingResponse(serialized_stream(generate, current_user, req.thread_id), media_type="text/event-stream")


@app.post("/chat/resume")
async def resume_chat(req: ResumeRequest, current_user: str = Depends(get_current_user)):
    """
    interrupt_before=["confirm"] 재개.
    aupdate_state로 message 업데이트 후 ainvoke(None)으로 confirm 실행.
    AgentState.message에 keep_latest 리듀서가 있어서 충돌 없음.
    """
    async def generate():
        graph  = get_graph()
        stream_run_id = req.stream_run_id or str(uuid4())
        tid    = f"{current_user}_{req.thread_id}"
        config = {"configurable": {"thread_id": tid},
                  "metadata": {"thread_id": _trace_thread_id(current_user, req.thread_id),
                               "stream_run_id": stream_run_id}}
        snap   = await graph.aget_state(config)
        existing = _sv(snap)
        if req.stream_run_id and existing.get("run_id") == stream_run_id:
            progress_stream = (_follow_or_resume_run(graph, config, stream_run_id, req.after_seq)
                               if existing.get("execution_status") == "running"
                               else _replay_progress(config, stream_run_id, req.after_seq))
            async for chunk in progress_stream:
                yield chunk
            async for chunk in _stream(graph, config, stream_run_id, req.after_seq):
                yield chunk
            return
        if not snap or not snap.next:
            yield f"data: {json.dumps({'type':'error','content':'재개할 대화가 없습니다.'}, ensure_ascii=False)}\n\n"
            return
        sv = _sv(snap)
        if not (sv.get("pending_proposal") or sv.get("pending_meals")):
            response_text = "확인 대기 중인 식단이 없어요. 사진 인식 결과가 아니라면 다시 사진을 올리거나, 음식명과 양을 직접 입력해주세요."
            for index, word in enumerate(response_text.split(" "), start=1001):
                if index <= req.after_seq:
                    continue
                yield _sse({"type": "answer_delta", "content": word + " ",
                            "run_id": stream_run_id, "seq": index})
                await asyncio.sleep(0.03)
            new_tid = str(int(time.time()))
            if req.after_seq < 100000:
                yield _sse({'type':'completed','agent_used':'','today_calories':sv.get('today_calories',0),
                    'target_calories':sv.get('target_calories',0),'pending_meals':None,
                    'awaiting_confirmation':False,'plan_date':None,'thread_id':new_tid,
                    'prev_thread_id':req.thread_id,'interrupted':False,
                    'run_id':stream_run_id,'seq':100000})
            return
        print(f"=== [resume] message_redacted | next={snap.next} ===")
        try:
            decision = req.decision.model_dump(mode="json") if req.decision else None
            await graph.aupdate_state(config, {"message": req.message, "proposal_decision": decision,
                                                "run_id": stream_run_id, "execution_status": "running"})
            async for chunk in _run_and_stream(graph, None, config, stream_run_id, req.after_seq):
                yield chunk
        except Exception as e:
            print(f"=== [resume] 오류 유형: {type(e).__name__} ===")
            yield f"data: {json.dumps({'type':'error','content':'요청 처리 중 오류가 발생했습니다.'}, ensure_ascii=False)}\n\n"
            return
        async for chunk in _stream(graph, config, stream_run_id, req.after_seq):
            yield chunk
    return StreamingResponse(serialized_stream(generate, current_user, req.thread_id), media_type="text/event-stream")


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


@app.get("/session/restore/{thread_id}")
async def restore_session(thread_id: str, current_user: str = Depends(get_current_user)):
    """Restore persisted UI state without invoking the graph or any model/tool."""
    graph = get_graph()
    config = {"configurable": {"thread_id": f"{current_user}_{thread_id}"}}
    snap = await graph.aget_state(config)
    sv = _sv(snap)

    proposal = None
    pending = sv.get("pending_proposal")
    if pending and pending.get("id"):
        try:
            candidate = await ProposalRepository().get(current_user, pending["id"])
            if candidate.get("status") == "pending":
                proposal = candidate
        except (ProposalConflict, KeyError, TypeError):
            proposal = None

    def read_messages():
        rows = (sb.table("chat_history")
                .select("role,content,agent_type,created_at")
                .eq("user_id", current_user)
                .eq("thread_id", thread_id)
                .order("created_at", desc=True)
                .order("role", desc=False)
                .limit(20).execute().data)
        return list(reversed([{
            "role": row.get("role"),
            "content": str(row.get("content", ""))[:12000],
            "agent_used": row.get("agent_type"),
        } for row in rows if row.get("role") in {"user", "assistant"} and row.get("content")]))

    try:
        messages = await asyncio.to_thread(read_messages)
    except Exception:
        messages = []
    stats = await _public_stats(current_user)
    active_pending = proposal is not None
    return {
        "thread_id": thread_id,
        "messages": messages,
        "pending_proposal": proposal,
        "pending_state": {
            "pending_meals": sv.get("pending_meals") if active_pending else None,
            "awaiting_confirmation": bool(sv.get("awaiting_confirmation")) if active_pending else False,
            "plan_date": sv.get("plan_date") if active_pending else None,
        },
        "interrupted": bool(snap and snap.next and active_pending),
        **stats,
    }


@app.post("/chat/rollback")
async def rollback_to_checkpoint(thread_id: str, checkpoint_id: str, current_user: str = Depends(get_current_user)):
    async with conversation_lock(current_user, thread_id):
        return await _rollback_to_checkpoint(thread_id, checkpoint_id, current_user)


async def _rollback_to_checkpoint(thread_id: str, checkpoint_id: str, current_user: str):
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
    if sv.get("pending_proposal"):
        proposal = await ProposalRepository().get(current_user, sv["pending_proposal"]["id"])
        if proposal["status"] != "pending":
            sv = {**sv, "pending_proposal": None, "pending_meals": None, "awaiting_confirmation": False}
    present = _sv(await graph.aget_state(target_config))
    counters = ("model_calls", "tool_calls", "elapsed_seconds", "validation_attempts", "replans")
    sv = {**sv, "execution_usage": {key: max((sv.get("execution_usage") or {}).get(key, 0),
        (present.get("execution_usage") or {}).get(key, 0)) for key in counters}}
    rollback_state = {**sv, "overwrite_on_confirm": bool(sv.get("pending_meals"))}
    await graph.aupdate_state(target_config, rollback_state)

    # 롤백 후 현재 state 확인
    current = await graph.aget_state(target_config)
    cv = _sv(current)

    print(f"=== [rollback] step={snap.metadata.get('step')} | agent={cv.get('agent_used')} | message_redacted ===")

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
    measured_date = inbody_data.get("measured_date")
    if not measured_date:
        raise HTTPException(422, "측정일을 인식하지 못했습니다. 날짜를 확인해 다시 입력해주세요.")
    weight_kg = _safe_float(inbody_data.get("weight_kg"))
    skeletal_muscle_kg = _safe_float(inbody_data.get("skeletal_muscle_kg"))
    body_fat_pct = _safe_float(inbody_data.get("body_fat_pct"))
    if weight_kg is None or skeletal_muscle_kg is None or body_fat_pct is None:
        raise HTTPException(status_code=400, detail="인바디 필수 수치(체중, 골격근량, 체지방률)를 인식하지 못했습니다. 이미지를 다시 업로드해주세요.")

    payload = MeasurementProposal(**{
        "measured_date": measured_date,
        "weight_kg": weight_kg, "skeletal_muscle_kg": skeletal_muscle_kg,
        "body_fat_kg": _safe_float(inbody_data.get("body_fat_kg")), "body_fat_pct": body_fat_pct,
        "bmi": _safe_float(inbody_data.get("bmi")), "bmr_kcal": _safe_float(inbody_data.get("bmr_kcal")),
        "protein_kg": _safe_float(inbody_data.get("protein_kg")), "mineral_kg": _safe_float(inbody_data.get("mineral_kg")),
    }).model_dump(mode="json")
    proposal = await ProposalRepository().create(user_id, "inbody-upload", payload, str(uuid4()))
    return {
        "type": "inbody",
        "measured_date": measured_date,
        "weight_kg": weight_kg, "skeletal_muscle_kg": skeletal_muscle_kg,
        "body_fat_kg": _safe_float(inbody_data.get("body_fat_kg"), 0), "body_fat_pct": body_fat_pct,
        "bmi": _safe_float(inbody_data.get("bmi")), "bmr_kcal": _safe_float(inbody_data.get("bmr_kcal")),
        "strategy_updated": False, "strategy_note": "측정일과 수치를 확인해주세요. 확인 전에는 측정값이나 전략을 저장하지 않습니다.",
        "proposal": proposal,
    }


@app.get("/proposals/{proposal_id}")
async def get_proposal(proposal_id: UUID, current_user: str = Depends(get_current_user)):
    try:
        return await ProposalRepository().get(current_user, str(proposal_id))
    except ProposalConflict as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/proposals/decision")
async def decide_proposal(req: ProposalDecision, current_user: str = Depends(get_current_user)):
    try:
        return await ProposalRepository().resolve(current_user, str(req.proposal_id), req.version, req.action)
    except ProposalConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@app.put("/proposals/{proposal_id}/measurement")
async def revise_measurement(proposal_id: UUID, req: MeasurementRevision, current_user: str = Depends(get_current_user)):
    repository = ProposalRepository()
    try:
        old = await repository.get(current_user, str(proposal_id))
        if old["kind"] != "measurement":
            raise ProposalConflict("인바디 측정 제안만 수정할 수 있습니다.")
        return await repository.create(current_user, old["thread_id"], req.payload.model_dump(mode="json"),
            str(uuid4()), replaces=(str(proposal_id), req.version))
    except ProposalConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@app.put("/proposals/{proposal_id}/weight")
async def revise_weight(proposal_id: UUID, req: WeightRevision, current_user: str = Depends(get_current_user)):
    repository = ProposalRepository()
    try:
        old = await repository.get(current_user, str(proposal_id))
        if old["kind"] != "weight":
            raise ProposalConflict("체중 기록 제안만 수정할 수 있습니다.")
        return await repository.create(current_user, old["thread_id"], req.payload.model_dump(mode="json"),
            str(uuid4()), replaces=(str(proposal_id), req.version))
    except ProposalConflict as exc:
        raise HTTPException(409, str(exc)) from exc


class WeightEntryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    measured_date: date
    weight_kg: float = Field(gt=0, le=500)


class MeasurementEntryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    measured_date: date
    weight_kg: float = Field(gt=0, le=500)
    skeletal_muscle_kg: float = Field(gt=0, le=250)
    body_fat_pct: float = Field(ge=0, le=100)


@app.post("/measurements/weight")
async def propose_weight(req: WeightEntryRequest, current_user: str = Depends(get_current_user)):
    payload = WeightProposal(**req.model_dump(), source="manual").model_dump(mode="json")
    return await ProposalRepository().create(current_user, "dashboard-weight", payload, str(uuid4()))


@app.post("/measurements/body-composition")
async def propose_body_composition(req: MeasurementEntryRequest, current_user: str = Depends(get_current_user)):
    body_fat_kg = round(req.weight_kg * req.body_fat_pct / 100, 2)
    payload = MeasurementProposal(**req.model_dump(), body_fat_kg=body_fat_kg).model_dump(mode="json")
    return await ProposalRepository().create(current_user, "dashboard-measurement", payload, str(uuid4()))


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


@app.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    req: FeedbackRequest,
    response: Response,
    current_user: str = Depends(get_current_user),
):
    """Store privacy-minimal beta feedback without tracing its comment body."""
    submission = FeedbackInput(
        rating=req.rating,
        category=req.category,
        comment=req.comment,
        client_submission_id=req.client_submission_id,
    )
    try:
        row, created = await FeedbackRepository().create(current_user, submission)
    except FeedbackStorageUnavailable as exc:
        logger.error(
            "feedback_storage_unavailable",
            extra={"error_type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="피드백 저장 서비스를 잠시 사용할 수 없습니다.",
        ) from None
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    logger.info(
        "feedback_stored",
        extra={
            "feedback_id": row["id"],
            "category": req.category,
            "rating": req.rating,
            "created": created,
        },
    )
    return FeedbackResponse(id=row["id"], created=created)


@app.post("/analytics/events", response_model=ProductEventResponse)
async def record_product_event(
    req: ProductEventRequest,
    response: Response,
    current_user: str = Depends(get_current_user),
):
    try:
        row, created = await ProductEventRepository().record(
            current_user, ProductEventInput(**req.model_dump())
        )
    except ProductAnalyticsUnavailable as exc:
        logger.error("product_event_storage_unavailable", extra={"error_type": type(exc).__name__})
        raise HTTPException(status_code=503, detail="사용 현황 기록 서비스를 잠시 사용할 수 없습니다.") from None
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return ProductEventResponse(id=row["id"], created=created)


@app.get("/admin/analytics/overview")
async def admin_analytics_overview(days: int = 7, _admin: str = Depends(get_current_admin)):
    if days not in {1, 7, 30, 90}:
        raise HTTPException(status_code=422, detail="조회 기간은 1, 7, 30, 90일만 지원합니다.")
    try:
        return await ProductEventRepository().overview(days=days)
    except ProductAnalyticsUnavailable as exc:
        logger.error("product_analytics_unavailable", extra={"error_type": type(exc).__name__})
        raise HTTPException(status_code=503, detail="제품 분석 지표를 불러올 수 없습니다.") from None


@app.delete("/users/me")
async def delete_account(req: AccountDeleteRequest,
                         auth: AuthContext = Depends(get_recent_auth_context)):
    """Irreversibly delete app data and the authenticated Supabase identity."""
    from app.db.account_deletion import (
        AccountDeletionPartialFailure,
        AccountDeletionService,
        InvalidAuthSession,
    )

    try:
        return await AccountDeletionService().delete(auth.auth_id, auth.session_id)
    except InvalidAuthSession as exc:
        raise HTTPException(status_code=401, detail={
            "code": "recent_authentication_required",
            "message": "세션이 만료되었습니다. 다시 로그인해주세요.",
            "retryable": True,
        }) from exc
    except AccountDeletionPartialFailure as exc:
        raise HTTPException(status_code=503, detail={
            "code": "auth_deletion_pending",
            "message": "서비스 데이터는 삭제됐지만 인증 계정 삭제를 재시도해야 합니다.",
            "retryable": True,
        }) from exc
    except (ConnectionError, TimeoutError) as exc:
        raise HTTPException(status_code=503, detail={
            "code": "account_deletion_unavailable",
            "message": "계정 삭제를 완료하지 못했습니다. 잠시 후 다시 시도해주세요.",
            "retryable": True,
        }) from exc


@app.get("/report/weekly")
async def weekly_report(current_user: str = Depends(get_current_user)):
    graph  = get_graph()
    config = {"configurable": {"thread_id": f"{current_user}_report"},
              "metadata": {"thread_id": _trace_thread_id(current_user, "report")}}
    readonly = ["read_profile", "read_intake", "read_recent_intake", "read_measurements",
                "assess_goal_progress", "search_evidence"]
    async with conversation_lock(current_user, "report"):
        await graph.ainvoke(_initial_state(ChatRequest(message="이번 주 식단 리포트를 보여주세요.",
                                                       requested_action="weekly_review",
                                                       tool_policy=readonly), current_user), config=config)
    state = _sv(await graph.aget_state(config))
    return {"report": state.get("response", ""), "pending_proposal": state.get("pending_proposal"),
            "awaiting_confirmation": state.get("awaiting_confirmation", False)}


@app.get("/inbody/history")
async def get_inbody_history(current_user: str = Depends(get_current_user)):
    return sb.table("inbody_logs").select("*").eq("user_id",current_user).order("measured_date",desc=False).execute().data


@app.get("/dashboard/summary")
async def get_dashboard_summary(current_user: str = Depends(get_current_user)):
    profile_rows = sb.table("users").select("weight_kg,created_at").eq("id", current_user).limit(1).execute().data
    profile = profile_rows[0] if profile_rows else {}
    composition = sb.table("inbody_logs").select("*").eq("user_id", current_user).order("measured_date", desc=False).execute().data
    try:
        weights = sb.table("weight_logs").select("*").eq("user_id", current_user).order("measured_date", desc=False).execute().data
    except Exception:
        weights = []
    if not weights and profile.get("weight_kg") is not None:
        created = str(profile.get("created_at") or service_today().isoformat())[:10]
        weights = [{"measured_date": created, "weight_kg": profile["weight_kg"], "source": "onboarding"}]

    priority = {"onboarding": 0, "manual": 1, "inbody": 2}
    by_date = {}
    for row in weights:
        key = str(row["measured_date"])
        if key not in by_date or priority.get(row.get("source"), -1) >= priority.get(by_date[key].get("source"), -1):
            by_date[key] = row
    weight_history = [by_date[key] for key in sorted(by_date)]
    return {
        "latest_weight": weight_history[-1] if weight_history else None,
        "latest_body_composition": composition[-1] if composition else None,
        "weight_history": weight_history,
        "body_composition_history": composition,
    }


@app.get("/strategy/current")
async def get_current_strategy(current_user: str = Depends(get_current_user)):
    rows = sb.table("diet_strategies").select("*").eq("user_id",current_user).eq("is_active",True).order("created_at",desc=True).limit(1).execute().data
    return rows[0] if rows else {}


from app.core.energy_policy import EnergyInputs, estimate_maintenance
from app.core.onboarding import OnboardingRequest


@app.post('/users/onboarding')
async def complete_onboarding(req: OnboardingRequest, auth_id: str = Depends(get_active_auth_id)):
    from app.core.onboarding import save_onboarding
    try:
        return await save_onboarding(req,auth_id)
    except (ValueError,ProposalConflict) as exc:
        raise HTTPException(status_code=422,detail=str(exc)) from exc


@app.get('/users/onboarding')
async def get_onboarding(auth_id: str = Depends(get_active_auth_id)):
    from app.core.onboarding import onboarding_status
    return await onboarding_status(auth_id)


@app.post("/users/energy-preview")
async def preview_energy(req: EnergyInputs, auth_id: str = Depends(get_active_auth_id)):
    """Authenticated, read-only estimate. No profile or strategy is modified."""
    try:
        return estimate_maintenance(req)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/users/setup")
async def setup_user(goal: str, height_cm: float, weight_kg: float, age: int, gender: str,
                      target_weight_kg: Optional[float] = None,
                      target_date: Optional[str] = None,
                      goal_priority: Optional[str] = None,
                      region: str = "KR",
                      auth_id: str = Depends(get_active_auth_id)):
    """
    레거시 조회 호환 경로. 프로필·초기 전략 저장은 /users/onboarding에서 처리한다.
    """
    existing = sb.table("users").select("id").eq("auth_id", auth_id).limit(1).execute().data
    if existing:
        user_id = existing[0]["id"]
        # Repeated onboarding must not replace a confirmed strategy outside HITL.
        current = sb.table("diet_strategies").select("*").eq("user_id",user_id).eq("is_active",True).order("created_at",desc=True).limit(1).execute().data
        if current:
            return {**current[0], "strategy_change_requires_confirmation": True,
                    "message": "기존 전략을 유지합니다. 프로필 변경은 /users/onboarding에서 확인해주세요."}
        raise HTTPException(status_code=409, detail="현재 전략이 없습니다. 검토된 초기 계획 설정이 필요합니다.")
    else:
        raise HTTPException(status_code=409,detail="활동 수준과 적용대상을 확인하는 /users/onboarding을 사용해주세요.")


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

