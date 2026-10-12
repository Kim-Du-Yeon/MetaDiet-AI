import "./ProcessTrace.css";

export default function ProcessTrace({ steps = [], running = false }) {
  if (!steps.length) return null;
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
