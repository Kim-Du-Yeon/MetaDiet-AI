import { useState, useEffect, useMemo, useRef } from "react";
import { supabase } from "./lib/supabaseClient";
import { setToken, getSessionRestore } from "./api/dietApi";
import Auth from "./components/Auth";
import ChatInterface from "./components/chat/ChatInterface";
import CalendarView from "./components/calendar/CalendarView";
import Dashboard from "./components/dashboard/Dashboard";
import Setup from "./components/Setup";
import Settings from "./components/Settings";
import { useConversationThread } from "./lib/useConversationThread";
import "./App.css";

const INITIAL_MESSAGES = [
  {
    role: "assistant",
    content: "안녕하세요! 오늘 드신 음식을 알려주시거나 식단 전략을 물어보세요 😊",
    agentUsed: null,
  },
];

export default function App() {
  const [session, setSession] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("chat");
  const [todayStats, setTodayStats] = useState(null);
  const [setupDone, setSetupDone] = useState(false);
  const [messages, setMessages] = useState(INITIAL_MESSAGES);
  const refreshSequence = useRef(0);

  const [threadId, setThreadId, threadReady] = useConversationThread(session?.user?.id);
  // 직전에 완료된 thread_id 보관 → 타임 트래블에서 이전 세션 조회용
  const [prevThreadId, setPrevThreadId] = useState(null);
  const [isInterrupted, setIsInterrupted] = useState(false);
  const ownerId = session?.user?.id || null;
  const latestOwner = useRef(ownerId);
  latestOwner.current = ownerId;
  const chatSetters = useMemo(() => {
    const owned = setter => value => {
      if (latestOwner.current === ownerId) setter(value);
    };
    return { messages: owned(setMessages), stats: owned(setTodayStats),
      previousThread: owned(setPrevThreadId), interrupted: owned(setIsInterrupted) };
  }, [ownerId]);

  const refreshIntake = async () => {
    const sequence = ++refreshSequence.current;
    const restored = await getSessionRestore(threadId);
    if (latestOwner.current !== ownerId || sequence !== refreshSequence.current) return;
    if (restored.today_calories === undefined || restored.target_calories === undefined) {
      throw new Error('기록은 변경됐지만 오늘 섭취량을 갱신하지 못했습니다. 다시 확인해주세요.');
    }
    setTodayStats({calories:restored.today_calories,target:restored.target_calories});
    if (restored.messages?.length) setMessages(restored.messages.map(message => ({
      role:message.role, content:message.content, agentUsed:message.agent_used || null, streaming:false,
    })));
  };

  useEffect(() => {
    setMessages(INITIAL_MESSAGES);
    setPrevThreadId(null);
    setIsInterrupted(false);
    setTodayStats(null);
    setSetupDone(false);
  }, [session?.user?.id]);

  const handleAccountDeleted = () => {
    setToken(null);
    setSession(null);
    setSetupDone(false);
    setMessages(INITIAL_MESSAGES);
    setTodayStats(null);
    setActiveTab("chat");
  };

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      setToken(session?.access_token ?? null);
      setAuthLoading(false);
    });
    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
      setToken(session?.access_token ?? null);
    });
    const handleAuthExpired = async () => {
      setToken(null);
      await supabase.auth.signOut();
      setSession(null);
    };
    window.addEventListener("metadiet:auth-expired", handleAuthExpired);
    return () => {
      listener.subscription.unsubscribe();
      window.removeEventListener("metadiet:auth-expired", handleAuthExpired);
    };
  }, []);

  if (authLoading || (session && !threadReady)) {
    return <main className="app-loading" role="status" aria-live="polite">
      <span className="app-loading__eyebrow">MetaDiet AI</span>
      <strong>안전하게 세션을 확인하는 중입니다.</strong>
    </main>;
  }
  if (!session) {
    return <Auth />;
  }
  if (!setupDone) {
    return <Setup onComplete={() => setSetupDone(true)} />;
  }

  return (
    <div className="app">
      {todayStats && (
        <div className="stats-bar">
          <span>오늘</span>
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{
                width: `${Math.min(
                  (todayStats.calories / todayStats.target) * 100,
                  100
                )}%`,
              }}
            />
          </div>
          <span>
            {Math.round(todayStats.calories)} / {Math.round(todayStats.target)} kcal
          </span>
        </div>
      )}

      <div className="tab-bar">
        <button
          className={activeTab === "chat" ? "tab active" : "tab"}
          onClick={() => setActiveTab("chat")}
        >
          💬 채팅
        </button>
        <button
          className={activeTab === "calendar" ? "tab active" : "tab"}
          onClick={() => setActiveTab("calendar")}
        >
          📅 캘린더
        </button>
        <button
          className={activeTab === "dashboard" ? "tab active" : "tab"}
          onClick={() => setActiveTab("dashboard")}
        >
          📊 대시보드
        </button>
        <button
          className={activeTab === "settings" ? "tab active" : "tab"}
          onClick={() => setActiveTab("settings")}
        >
          ⚙️ 설정
        </button>
      </div>

      <div className="content">
        {activeTab === "chat" && (
          <ChatInterface
            onStatsUpdate={chatSetters.stats}
            messages={messages}
            setMessages={chatSetters.messages}
            threadId={threadId}
            setThreadId={setThreadId}
            prevThreadId={prevThreadId}
            setPrevThreadId={chatSetters.previousThread}
            isInterrupted={isInterrupted}
            setIsInterrupted={chatSetters.interrupted}
          />
        )}
        {activeTab === "calendar" && <CalendarView onRecordsChanged={refreshIntake} />}
        {activeTab === "dashboard" && <Dashboard />}
        {activeTab === "settings" && (
          <Settings session={session} onDeleted={handleAccountDeleted} />
        )}
      </div>
    </div>
  );
}
