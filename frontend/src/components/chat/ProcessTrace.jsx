import "./ProcessTrace.css";
import { useEffect, useRef } from 'react';
import { reportRequestTiming } from '../../api/requestTiming';

export default function ProcessTrace({ steps = [], running = false }) {
  const measured = useRef(new Set());
  const first = steps.find(step => step.requestId);
  const server = steps.find(step => step.requestId && !step.local);
  useEffect(() => {
    if (!running) return;
    const handles = [];
    for (const [step, stage] of [[first, 'local_paint_opportunity'], [server, 'server_progress_paint_opportunity']]) {
      if (!step || measured.current.has(`${step.requestId}:${stage}`)) continue;
      const key = `${step.requestId}:${stage}`;
      handles.push(requestAnimationFrame(() => {
        handles.push(requestAnimationFrame(() => {
          if (measured.current.has(key)) return;
          measured.current.add(key);
          reportRequestTiming({requestId:step.requestId, attemptId:step.attemptId}, stage, step.requestStartedAt);
        }));
      }));
    }
    return () => handles.forEach(cancelAnimationFrame);
  }, [first, server, running]);
  if (!steps.length) return running ? <section className="process-trace is-running" aria-label="답변 준비 과정"><div className="process-trace__status" role="status">상담 요청을 처리하고 있어요. 서버 응답을 기다리는 중입니다.</div></section> : null;
  if (running && steps[steps.length - 1]?.phase === "coaching_context") return <section className="process-trace is-running" aria-label="답변 준비 과정"><div className="process-trace__status" role="status">{steps[steps.length - 1].label}</div></section>;
  const content = <ol className="process-trace__list">{steps.map((step, index) => {
    const active = running && index === steps.length - 1;
    return <li className={`process-trace__step${active ? " is-active" : ""}`} key={`${step.phase}-${step.label}-${index}`}>
      <span className="process-trace__index" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
      <span aria-current={active ? "step" : undefined}>{step.label}</span>
    </li>;
  })}</ol>;
  if (running) return <section className="process-trace is-running" aria-label="답변 준비 과정">
    <div className="process-trace__status" role="status">{steps.length}단계 진행 중</div>{content}
  </section>;
  return <details className="process-trace"><summary>검토 과정 {steps.length}단계</summary>{content}</details>;
}
