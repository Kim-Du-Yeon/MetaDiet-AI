import { useState, useEffect } from "react";
import { supabase } from "./lib/supabaseClient";
import { setToken } from "./api/dietApi";
import Auth from "./components/Auth";
import ChatInterface from "./components/chat/ChatInterface";
import CalendarView from "./components/calendar/CalendarView";
import Dashboard from "./components/dashboard/Dashboard";
import Setup from "./components/Setup";
import Settings from "./components/Settings";
import "./App.css";

const INITIAL_MESSAGES = [
  {
    role: "assistant",
    content: "안녕하세요! 오늘 드신 음식을 알려주시거나 식단 전략을 물어보세요 😊",
    agentUsed: null,
  },
];

function generateThreadId() {
  const today = new Date().toISOString().split("T")[0];
  return `chat_${today}`;
}

export default function App() {
  const [session, setSession] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("chat");
  const [todayStats, setTodayStats] = useState(null);
  const [setupDone, setSetupDone] = useState(false);
  const [messages, setMessages] = useState(INITIAL_MESSAGES);

  const [threadId, setThreadId] = useState(generateThreadId);
  // 직전에 완료된 thread_id 보관 → 타임 트래블에서 이전 세션 조회용
  const [prevThreadId, setPrevThreadId] = useState(null);
  const [isInterrupted, setIsInterrupted] = useState(false);

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
    return () => listener.subscription.unsubscribe();
  }, []);

  if (authLoading) {
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
            onStatsUpdate={setTodayStats}
            messages={messages}
            setMessages={setMessages}
            threadId={threadId}
            setThreadId={setThreadId}
            prevThreadId={prevThreadId}
            setPrevThreadId={setPrevThreadId}
            isInterrupted={isInterrupted}
            setIsInterrupted={setIsInterrupted}
          />
        )}
        {activeTab === "calendar" && <CalendarView />}
        {activeTab === "dashboard" && <Dashboard />}
        {activeTab === "settings" && (
          <Settings session={session} onDeleted={handleAccountDeleted} />
        )}
      </div>
    </div>
  );
}
