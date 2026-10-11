import { useEffect, useRef, useState } from "react";
import "./LegalNotices.css";

const notices = {
  privacy: {
    title: "개인정보처리방침",
    body: <>
      <p className="legal-effective">시행일: 2026년 10월 11일 · 제한 베타</p>
      <h3>처리하는 정보와 목적</h3>
      <p>이메일과 인증 식별자, 신체·목표·활동 정보, 식사·인바디 기록, 대화와 확인 대기 제안을 계정 인증, 개인화된 식단 코칭, 화면 상태 복원과 안전한 기록 처리를 위해 사용합니다.</p>
      <h3>외부 서비스</h3>
      <p>Supabase는 인증과 데이터베이스, Google Gemini는 생성·이미지 분석·임베딩, Pinecone은 영양 근거 문서 검색, LangSmith는 입력·출력 원문 노출을 제한한 실행 추적, Render는 서비스 호스팅에 사용됩니다.</p>
      <h3>저장과 삭제</h3>
      <p>설정의 <strong>계정 삭제</strong>를 실행하면 앱의 식사·인바디·전략·대화 기록과 인증 계정 삭제를 요청합니다. 외부 사업자의 백업과 운영 로그는 각 사업자의 보존 정책에 따라 일정 기간 남을 수 있습니다.</p>
      <p>베타 기간의 정확한 운영 보존 기간은 확정 전이며, 확정 시 이 안내를 갱신합니다.</p>
    </>,
  },
  beta: {
    title: "베타 이용 안내",
    body: <>
      <p className="legal-effective">시행일: 2026년 10월 11일 · 무료 베타</p>
      <h3>서비스 범위</h3>
      <p>MetaDiet AI는 일반 성인의 체중 관리를 돕는 기록·정보 서비스입니다. 의료 진단, 치료, 처방 또는 응급 대응을 제공하지 않습니다.</p>
      <h3>사용자 확인</h3>
      <p>AI의 음식·중량·영양 추정과 권고는 틀릴 수 있습니다. 저장이나 전략 변경 전에 표시된 수치와 근거를 확인하고, 임신·수유·질환·섭식장애 등 전문 관리가 필요한 경우 의료 전문가와 상담해주세요.</p>
      <h3>베타 제한</h3>
      <p>무료 호스팅은 일정 시간 사용하지 않으면 첫 응답이 늦어질 수 있으며 가용성을 보장하지 않습니다. 오류 제보는 GitHub Issues를 이용하되, 건강정보·이메일·API 키 같은 민감정보는 공개 이슈에 남기지 마세요.</p>
      <a href="https://github.com/Kim-Du-Yeon/MetaDiet-AI/issues" target="_blank" rel="noreferrer">민감정보를 제외하고 오류 제보하기</a>
    </>,
  },
};

export default function LegalNotices({ compact = false }) {
  const [active, setActive] = useState(null);
  const closeButtonRef = useRef(null);
  const notice = active ? notices[active] : null;

  useEffect(() => {
    if (!notice) return undefined;
    closeButtonRef.current?.focus();
    const handleKeyDown = (event) => {
      if (event.key === "Escape") setActive(null);
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [notice]);

  return <>
    <nav className={`legal-links${compact ? " legal-links--compact" : ""}`} aria-label="서비스 정책">
      <button type="button" onClick={() => setActive("privacy")}>개인정보처리방침</button>
      <span aria-hidden="true">·</span>
      <button type="button" onClick={() => setActive("beta")}>베타 이용 안내</button>
    </nav>
    {notice && <div className="legal-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) setActive(null);
    }}>
      <section className="legal-dialog" role="dialog" aria-modal="true" aria-labelledby="legal-title">
        <header>
          <div><span>METADIET AI</span><h2 id="legal-title">{notice.title}</h2></div>
          <button ref={closeButtonRef} type="button" aria-label="안내 닫기" onClick={() => setActive(null)}>×</button>
        </header>
        <div className="legal-body">{notice.body}</div>
      </section>
    </div>}
  </>;
}
