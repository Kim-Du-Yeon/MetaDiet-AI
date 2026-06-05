import { useState, useRef, useEffect } from "react";
import { sendChatMessage, uploadImage, resumeChat, getChatHistory, rollbackToCheckpoint, nutritionLookup } from "../../api/dietApi";

const USER_ID = "17691249-f22f-4447-a6e4-fca7a8e57cc8";

const AGENT_LABELS = {
  diet_logger: "🍽️ 식단 기록",
  strategy:    "💡 전략 추천",
  inbody:      "📊 인바디 분석",
  reporter:    "📋 주간 리포트",
  meal_plan:   "📋 식단 계획",
  confirm:     "✅ 식단 확정",
  edit:        "✏️ 식단 수정",
};

const MEAL_OPTIONS = [
  { key: "breakfast", label: "🌅 아침" },
  { key: "lunch",     label: "☀️ 점심" },
  { key: "dinner",    label: "🌙 저녁" },
  { key: "snack",     label: "🍎 간식" },
];

const STEP_LABELS = {
  diet_logger: "🍽️ 식단 파싱",
  confirm:     "✅ 확정/수정",
  strategy:    "💡 전략 조언",
  meal_plan:   "📋 식단 계획",
  validator:   "🔍 검증",
  inbody:      "📊 인바디",
  reporter:    "📋 리포트",
  edit:        "✏️ 수정",
};

const EMPTY_PENDING_STATE = { pending_meals: null, awaiting_confirmation: false, plan_date: null };
const FOOD_REJECTION_RE = /(아니|ㅇ\s*아니|아니야|아니요|아뇨|노|no|ㄴㄴ|틀렸|틀렸어|잘못|잘못봤|잘못 봤|이거\s*(?:ㅇ\s*)?아니|그거\s*(?:ㅇ\s*)?아니)/i;

export default function ChatInterface({
  onStatsUpdate, messages, setMessages,
  threadId, setThreadId,
  prevThreadId, setPrevThreadId,
  isInterrupted, setIsInterrupted,
}) {
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [pendingState, setPendingState] = useState({ pending_meals: null, awaiting_confirmation: false, plan_date: null });
  const [isRolledBack, setIsRolledBack] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [checkpoints, setCheckpoints] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [foodEntry, setFoodEntry] = useState(null);   // 음식 카드: { foods, grams, mealType }
  const bottomRef = useRef(null);
  const fileInputRef = useRef(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const handleToken = (token) => {
    setMessages((prev) => {
      const updated = [...prev];
      const last = updated[updated.length - 1];
      updated[updated.length - 1] = { ...last, content: last.content + token };
      return updated;
    });
  };

  const handleDone = (meta) => {
    setMessages((prev) => {
      const updated = [...prev];
      updated[updated.length - 1] = { ...updated[updated.length - 1], streaming: false, agentUsed: meta.agent_used };
      return updated;
    });
    setPendingState({ pending_meals: meta.pending_meals || null, awaiting_confirmation: meta.awaiting_confirmation || false, plan_date: meta.plan_date || null });

    // 새 thread_id 발급 시 이전 thread 보관
    if (meta.thread_id && meta.thread_id !== threadId) {
      setPrevThreadId(threadId);   // 현재 → 이전으로
      setThreadId(meta.thread_id); // 새 thread로 전환
    }
    if (meta.prev_thread_id) setPrevThreadId(meta.prev_thread_id);

    setIsInterrupted(meta.interrupted || false);
    if (meta.today_calories !== undefined && onStatsUpdate) {
      onStatsUpdate({ calories: meta.today_calories, target: meta.target_calories });
    }
    setIsLoading(false);
  };

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;
    const userMsg = input.trim();
    const activeFoodEntry = foodEntry;
    const isFoodRejection = activeFoodEntry && FOOD_REJECTION_RE.test(userMsg);
    setInput("");
    if (isFoodRejection) {
      setFoodEntry(null);
      setPendingState(EMPTY_PENDING_STATE);
      setIsInterrupted(false);
      setIsRolledBack(false);
      setMessages((prev) => [...prev,
        { role: "user", content: userMsg },
        {
          role: "assistant",
          content: "알겠어요. 사진 인식 결과는 취소할게요.\n직접 음식명과 양을 입력하거나, 사진을 다시 올려주세요.",
          agentUsed: null,
          streaming: false,
        },
      ]);
      return;
    }
    setFoodEntry(null);   // 직접 타이핑하면 음식 카드는 닫음
    setIsLoading(true);
    const newUserMessage = { role: "user", content: userMsg };
    setMessages((prev) => [...prev, newUserMessage, { role: "assistant", content: "", agentUsed: null, streaming: true }]);
    try {
      const contextMessages = [...messages, newUserMessage];
      const shouldResume = !isRolledBack && (isInterrupted || pendingState.pending_meals);
      if (shouldResume) {
        setIsInterrupted(false); setIsRolledBack(false);
        await resumeChat(USER_ID, threadId, userMsg, handleToken, handleDone);
      } else {
        setIsRolledBack(false);
        await sendChatMessage(USER_ID, userMsg, handleToken, handleDone, pendingState, contextMessages, threadId);
      }
    } catch (e) {
      console.error(e);
      setMessages((prev) => [...prev.slice(0, -1), { role: "assistant", content: "오류가 발생했습니다.", agentUsed: null }]);
      setIsLoading(false);
    }
  };

  // ── 타임 트래블 ──────────────────────────────────────────────────
  const loadHistory = async () => {
    setHistoryLoading(true);
    try {
      // 현재 thread + 이전 thread 체크포인트 합산
      const targets = [threadId, prevThreadId].filter(Boolean);
      const allCps = [];
      for (const tid of targets) {
        const data = await getChatHistory(USER_ID, tid);
        if (data.checkpoints?.length) {
          allCps.push(...data.checkpoints.map(cp => ({ ...cp, _tid: tid })));
        }
      }
      // step 내림차순 정렬, agent 없는 것 제외
      allCps.sort((a, b) => b.step - a.step);
      setCheckpoints(allCps.filter(cp => cp.step >= 0 && cp.agent_used));
    } catch (e) { console.error(e); }
    setHistoryLoading(false);
  };

  const handleShowHistory = async () => {
    const next = !showHistory;
    setShowHistory(next);
    if (next) await loadHistory();
  };

  const handleRollback = async (cp) => {
    if (!window.confirm(`step ${cp.step} — "${cp.message}" 시점으로 롤백하시겠습니까?\n(DB 데이터는 유지됩니다)`)) return;
    try {
      const result = await rollbackToCheckpoint(USER_ID, cp._tid, cp.checkpoint_id);
      if (result.success) {
        setIsRolledBack(true);
        setIsInterrupted(false);
        setThreadId(cp._tid); // 롤백한 thread로 전환
        setPendingState({ pending_meals: result.rolled_back_to.pending_meals || null, awaiting_confirmation: !!result.rolled_back_to.pending_meals, plan_date: null });
        if (result.rolled_back_to.response) {
          setMessages((prev) => [...prev, {
            role: "assistant",
            content: `⏪ **롤백 완료** (step ${cp.step})\n\n${result.rolled_back_to.response}`,
            agentUsed: result.rolled_back_to.agent_used, streaming: false,
          }]);
        }
        setShowHistory(false);
      }
    } catch (e) { alert("롤백 실패: " + e.message); }
  };

  // 영양성분만 조회 (기록 X) — g 미입력은 100g 기준
  const submitNutritionInfo = async () => {
    if (!foodEntry || isLoading) return;
    const foods = foodEntry.foods.map((f) => ({ name: f, quantity_g: Number(foodEntry.grams[f]) || 100 }));
    setFoodEntry(null);
    setIsLoading(true);
    setMessages((prev) => [...prev,
      { role: "user", content: "📷 이 음식들 영양성분이 궁금해요" },
      { role: "assistant", content: "영양성분 조회 중...", agentUsed: null, streaming: true }]);
    try {
      const { results } = await nutritionLookup(foods);
      const lines = results.map((r) => r.found_in_db
        ? `• ${r.food_name} ${r.quantity_g}g → ${Math.round(r.calories)}kcal | 탄 ${Math.round(r.carbs_g)}g | 단 ${Math.round(r.protein_g)}g | 지 ${Math.round(r.fat_g)}g`
        : `• ${r.food_name} ${r.quantity_g}g → DB 미등록(추정 불가)`);
      const total = results.filter(r => r.found_in_db).reduce((a, r) => a + (r.calories || 0), 0);
      const body = `ℹ️ **영양성분** (기록되지 않음)\n\n${lines.join("\n")}\n\n합계: 약 ${Math.round(total)}kcal\n\n기록하시려면 사진을 다시 올리거나 "${foods[0]?.name} ${foods[0]?.quantity_g}g"처럼 입력해주세요.`;
      setMessages((prev) => { const u=[...prev]; u[u.length-1] = { role:"assistant", content: body, agentUsed:null, streaming:false }; return u; });
    } catch {
      setMessages((prev) => [...prev.slice(0,-1), { role:"assistant", content:"영양성분 조회에 실패했습니다.", agentUsed:null }]);
    }
    setIsLoading(false);
  };

  // 음식 카드 제출 → "연어롤 300g, 닭가슴살 100g" + 선택 끼니(meal_type)로 기록
  const submitFoodEntry = async () => {
    if (!foodEntry || !foodEntry.mealType || isLoading) return;
    const parts = foodEntry.foods
      .filter((f) => foodEntry.grams[f] && Number(foodEntry.grams[f]) > 0)
      .map((f) => `${f} ${foodEntry.grams[f]}g`);
    if (parts.length === 0) { alert("최소 한 음식의 g을 입력해주세요."); return; }
    const text = parts.join(", ");
    const mealType = foodEntry.mealType;
    setFoodEntry(null);
    setIsLoading(true);
    const newUserMessage = { role: "user", content: text };
    setMessages((prev) => [...prev, newUserMessage, { role: "assistant", content: "", agentUsed: null, streaming: true }]);
    try {
      await sendChatMessage(USER_ID, text, handleToken, handleDone, pendingState, [...messages, newUserMessage], threadId, mealType);
    } catch (e) {
      setMessages((prev) => [...prev.slice(0, -1), { role: "assistant", content: "오류가 발생했습니다.", agentUsed: null }]);
      setIsLoading(false);
    }
  };

  // 통합 이미지 업로드: 서버(Agent)가 인바디/음식을 판단 → 분기 처리
  const handleImageUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    e.target.value = "";   // 같은 파일 재선택 허용
    setFoodEntry(null);
    setPendingState(EMPTY_PENDING_STATE);
    setIsInterrupted(false);
    setIsRolledBack(false);
    setIsLoading(true);
    setMessages((prev) => [...prev,
      { role: "user", content: "📷 사진을 업로드했습니다." },
      { role: "assistant", content: "사진 분석 중...", agentUsed: null, streaming: true }]);
    try {
      const result = await uploadImage(USER_ID, file);
      if (result.type === "inbody") {
        setMessages((prev) => { const u=[...prev]; u[u.length-1] = { role:"assistant",
          content:`✅ 인바디 분석 완료!\n체중: ${result.weight_kg}kg | 골격근: ${result.skeletal_muscle_kg}kg | 체지방률: ${result.body_fat_pct}%\n\n${result.strategy_note}`,
          agentUsed:"inbody", streaming:false }; return u; });
      } else if (result.type === "food") {
        setMessages((prev) => { const u=[...prev]; u[u.length-1] = { role:"assistant",
          content: result.message, agentUsed:"diet_logger", streaming:false }; return u; });
        // 끼니·양을 사용자가 버튼/입력으로 직접 고르도록 음식 카드 표시(LLM 추측 방지)
        if (result.foods?.length) {
          setFoodEntry({
            foods: result.foods,
            grams: Object.fromEntries(result.foods.map(f => [f, ""])),
            mealType: null,
            mode: null,   // 사용자가 '기록' / '영양성분만' 중 선택
          });
        }
      } else {
        setMessages((prev) => { const u=[...prev]; u[u.length-1] = { role:"assistant",
          content: result.message || "사진을 인식하지 못했어요. 다시 시도해주세요.", agentUsed:null, streaming:false }; return u; });
      }
    } catch {
      setMessages((prev) => [...prev.slice(0,-1), { role:"assistant", content:"사진 분석에 실패했습니다.", agentUsed:null }]);
    }
    setIsLoading(false);
  };

  return (
    <div style={styles.container}>
      {isInterrupted && <div style={styles.interruptBanner}>⏸️ 식단 확인 대기 중 — 확정, 수정, 또는 취소를 입력해주세요</div>}
      {isRolledBack   && <div style={styles.rollbackBanner}>⏪ 롤백된 상태 — 이전 시점에서 계속 진행 중입니다</div>}

      <div style={styles.messages}>
        {messages.map((msg, i) => (
          <div key={i} style={{ display:"flex", justifyContent: msg.role==="user"?"flex-end":"flex-start", marginBottom:12 }}>
            <div style={msg.role==="user" ? styles.userBubble : styles.aiBubble}>
              <p style={{ margin:0, whiteSpace:"pre-wrap", lineHeight:1.6 }}>{msg.content}</p>
              {msg.streaming && <span style={styles.cursor}>▊</span>}
              {msg.agentUsed && !msg.streaming && <p style={styles.agentLabel}>{AGENT_LABELS[msg.agentUsed] || msg.agentUsed}</p>}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {showHistory && (
        <div style={styles.historyPanel}>
          <div style={styles.historyHeader}>
            <span>⏱️ 타임 트래블</span>
            <button onClick={() => setShowHistory(false)} style={styles.closeBtn}>✕</button>
          </div>
          {historyLoading ? <p style={{ padding:12, color:"#999" }}>로딩 중...</p>
          : checkpoints.length === 0 ? <p style={{ padding:12, color:"#999" }}>체크포인트가 없습니다.</p>
          : (
            <div style={styles.checkpointList}>
              {checkpoints.map((cp) => (
                <div key={cp.checkpoint_id} style={styles.checkpointItem}>
                  <div style={styles.checkpointInfo}>
                    <span style={styles.stepBadge}>step {cp.step}</span>
                    <span style={styles.agentBadge}>{STEP_LABELS[cp.agent_used] || cp.agent_used}</span>
                    <span style={styles.messagePreview}>{cp.message ? `"${cp.message.slice(0,20)}${cp.message.length>20?"...":""}"` : ""}</span>
                  </div>
                  {cp.response_preview && <p style={styles.responsePreview}>{cp.response_preview.slice(0,60)}...</p>}
                  {cp.has_pending && (
                    <button onClick={() => handleRollback(cp)} style={styles.rollbackBtn}>⏪ 이 시점으로 롤백</button>
                  )}
                  {!cp.has_pending && cp.next && cp.next.length > 0 && (
                    <span style={{fontSize:"11px",color:"#bbb"}}>※ 실행 중 상태 (롤백 불가)</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {foodEntry && (
        <div style={styles.foodCard}>
          <div style={styles.foodCardTitle}>📷 인식된 음식 — 무엇을 할까요?</div>

          {/* 1) 의도 선택: 기록 vs 영양성분만 */}
          <div style={styles.mealBtnRow}>
            <button onClick={() => setFoodEntry((fe) => ({ ...fe, mode: "log" }))}
              style={{ ...styles.mealBtn, ...(foodEntry.mode === "log" ? styles.mealBtnActive : {}) }}>📝 식단 기록</button>
            <button onClick={() => setFoodEntry((fe) => ({ ...fe, mode: "info" }))}
              style={{ ...styles.mealBtn, ...(foodEntry.mode === "info" ? styles.mealBtnActive : {}) }}>ℹ️ 영양성분만</button>
          </div>

          {/* 2) 기록 모드: 끼니 선택 */}
          {foodEntry.mode === "log" && (
            <div style={styles.mealBtnRow}>
              {MEAL_OPTIONS.map((o) => (
                <button key={o.key}
                  onClick={() => setFoodEntry((fe) => ({ ...fe, mealType: o.key }))}
                  style={{ ...styles.mealBtn, ...(foodEntry.mealType === o.key ? styles.mealBtnActive : {}) }}>
                  {o.label}
                </button>
              ))}
            </div>
          )}

          {/* 3) 양(g) 입력 (모드 선택 후) */}
          {foodEntry.mode && (
            <>
              <div style={styles.foodList}>
                {foodEntry.foods.map((f) => (
                  <div key={f} style={styles.foodRow}>
                    <span style={styles.foodName}>{f}</span>
                    <input type="number" min="0" placeholder={foodEntry.mode === "info" ? "100" : "0"}
                      value={foodEntry.grams[f] || ""}
                      onChange={(e) => setFoodEntry((fe) => ({ ...fe, grams: { ...fe.grams, [f]: e.target.value } }))}
                      style={styles.gramInput} />
                    <span style={styles.gramUnit}>g</span>
                  </div>
                ))}
              </div>
              <div style={styles.foodCardActions}>
                {foodEntry.mode === "log" ? (
                  <button onClick={submitFoodEntry} disabled={!foodEntry.mealType}
                    style={{ ...styles.foodSubmitBtn, ...(foodEntry.mealType ? {} : styles.foodSubmitDisabled) }}>
                    {foodEntry.mealType ? "기록하기" : "끼니를 선택하세요"}
                  </button>
                ) : (
                  <button onClick={submitNutritionInfo} style={styles.foodSubmitBtn}>영양성분 보기</button>
                )}
                <button onClick={() => setFoodEntry(null)} style={styles.foodCancelBtn}>취소</button>
              </div>
            </>
          )}

          {/* 모드 미선택 시 취소만 */}
          {!foodEntry.mode && (
            <div style={styles.foodCardActions}>
              <button onClick={() => setFoodEntry(null)} style={styles.foodCancelBtn}>아니에요 / 취소</button>
            </div>
          )}
        </div>
      )}

      <div style={styles.inputArea}>
        <button onClick={() => fileInputRef.current?.click()} style={styles.iconBtn} disabled={isLoading} title="사진 업로드 (음식·인바디 자동 인식)">📷</button>
        <input ref={fileInputRef} type="file" accept="image/*" style={{ display:"none" }} onChange={handleImageUpload} />
        <button onClick={handleShowHistory} style={styles.iconBtn} title="타임 트래블">⏱️</button>
        <input
          type="text" value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key==="Enter" && sendMessage()}
          placeholder={isInterrupted ? "확정 / 수정 / 취소 입력..." : "오늘 뭐 드셨어요?"}
          style={{ ...styles.input, borderColor: isInterrupted?"#4CAF50": isRolledBack?"#FF9800":"#ddd" }}
          disabled={isLoading}
        />
        <button onClick={sendMessage} disabled={isLoading||!input.trim()} style={styles.sendBtn}>
          {isInterrupted ? "확인" : "전송"}
        </button>
      </div>
    </div>
  );
}

const styles = {
  container:       { display:"flex", flexDirection:"column", height:"100%", backgroundColor:"#f8f9fa" },
  interruptBanner: { backgroundColor:"#e8f5e9", color:"#2e7d32", padding:"8px 16px", fontSize:"13px", fontWeight:"500", borderBottom:"1px solid #c8e6c9", textAlign:"center" },
  rollbackBanner:  { backgroundColor:"#fff3e0", color:"#e65100", padding:"8px 16px", fontSize:"13px", fontWeight:"500", borderBottom:"1px solid #ffe0b2", textAlign:"center" },
  messages:        { flex:1, overflowY:"auto", padding:"20px" },
  userBubble:      { backgroundColor:"#4CAF50", color:"white", padding:"10px 16px", borderRadius:"18px 18px 4px 18px", maxWidth:"70%" },
  aiBubble:        { backgroundColor:"white", color:"#333", padding:"10px 16px", borderRadius:"18px 18px 18px 4px", maxWidth:"70%", border:"1px solid #e0e0e0" },
  agentLabel:      { margin:"6px 0 0", fontSize:"11px", color:"#999" },
  cursor:          { display:"inline-block", animation:"blink 1s infinite" },
  inputArea:       { display:"flex", padding:"12px", backgroundColor:"white", borderTop:"1px solid #e0e0e0", gap:"8px", alignItems:"center" },
  iconBtn:         { fontSize:"20px", background:"none", border:"none", cursor:"pointer", padding:"4px" },
  input:           { flex:1, padding:"10px 16px", borderRadius:"24px", border:"1px solid #ddd", outline:"none", fontSize:"14px", transition:"border-color 0.2s" },
  sendBtn:         { padding:"10px 20px", backgroundColor:"#4CAF50", color:"white", border:"none", borderRadius:"24px", cursor:"pointer", fontSize:"14px" },
  historyPanel:    { backgroundColor:"white", borderTop:"1px solid #e0e0e0", maxHeight:"280px", overflowY:"auto" },
  historyHeader:   { display:"flex", justifyContent:"space-between", alignItems:"center", padding:"10px 16px", borderBottom:"1px solid #eee", fontWeight:"600", fontSize:"13px" },
  closeBtn:        { background:"none", border:"none", cursor:"pointer", fontSize:"16px", color:"#999" },
  checkpointList:  { padding:"8px" },
  checkpointItem:  { padding:"8px 12px", marginBottom:"6px", borderRadius:"8px", backgroundColor:"#f9f9f9", border:"1px solid #eee" },
  checkpointInfo:  { display:"flex", gap:"8px", alignItems:"center", marginBottom:"4px" },
  stepBadge:       { backgroundColor:"#e3f2fd", color:"#1565c0", padding:"2px 8px", borderRadius:"12px", fontSize:"11px", fontWeight:"600" },
  agentBadge:      { backgroundColor:"#f3e5f5", color:"#6a1b9a", padding:"2px 8px", borderRadius:"12px", fontSize:"11px" },
  messagePreview:  { fontSize:"12px", color:"#666" },
  responsePreview: { margin:"2px 0 6px", fontSize:"11px", color:"#999", lineHeight:1.4 },
  rollbackBtn:     { fontSize:"11px", padding:"4px 10px", backgroundColor:"#FF9800", color:"white", border:"none", borderRadius:"12px", cursor:"pointer" },
  foodCard:        { backgroundColor:"#fffdf5", borderTop:"1px solid #ffe0b2", padding:"12px 16px" },
  foodCardTitle:   { fontSize:"13px", fontWeight:"600", color:"#e65100", marginBottom:"10px" },
  mealBtnRow:      { display:"flex", gap:"6px", marginBottom:"12px", flexWrap:"wrap" },
  mealBtn:         { flex:1, minWidth:"64px", padding:"8px 6px", fontSize:"13px", border:"1px solid #ddd", borderRadius:"10px", background:"white", cursor:"pointer" },
  mealBtnActive:   { backgroundColor:"#4CAF50", color:"white", borderColor:"#4CAF50", fontWeight:"600" },
  foodList:        { maxHeight:"160px", overflowY:"auto" },
  foodRow:         { display:"flex", alignItems:"center", gap:"8px", marginBottom:"6px" },
  foodName:        { flex:1, fontSize:"13px", color:"#333" },
  gramInput:       { width:"70px", padding:"6px 8px", border:"1px solid #ddd", borderRadius:"8px", fontSize:"13px", textAlign:"right", outline:"none" },
  gramUnit:        { fontSize:"12px", color:"#999", width:"14px" },
  foodCardActions: { display:"flex", gap:"8px", marginTop:"10px" },
  foodSubmitBtn:   { flex:1, padding:"9px", backgroundColor:"#4CAF50", color:"white", border:"none", borderRadius:"10px", cursor:"pointer", fontSize:"14px", fontWeight:"500" },
  foodSubmitDisabled: { backgroundColor:"#c8c8c8", cursor:"not-allowed" },
  foodCancelBtn:   { padding:"9px 16px", backgroundColor:"#f0f0f0", color:"#666", border:"none", borderRadius:"10px", cursor:"pointer", fontSize:"14px" },
};
