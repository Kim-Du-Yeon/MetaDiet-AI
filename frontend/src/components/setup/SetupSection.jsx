import './SetupSection.css';

export default function SetupSection({ title, description, required = false, optional = false, children }) {
  const headingId = `setup-section-${title.replace(/\s/g, '-')}`;
  return (
    <section className="setup-section" aria-labelledby={headingId}>
      <header className="setup-section__header">
        <div>
          <h3 id={headingId}>{title}</h3>
          {description && <p>{description}</p>}
        </div>
        {required && <span className="setup-section__badge setup-section__badge--required">필수</span>}
        {optional && <span className="setup-section__badge">선택</span>}
      </header>
      <div className="setup-section__body">{children}</div>
    </section>
  );
}
