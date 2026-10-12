import './ActivityLevelSection.css';

const ACTIVITY_LEVELS = [
  { value: 'sedentary', label: '비활동적', description: '대부분 앉아서 생활하고 이동이 적어요' },
  { value: 'low_active', label: '저활동적', description: '가벼운 걷기나 일상적인 이동이 있어요' },
  { value: 'active', label: '활동적', description: '걷기, 서 있는 업무 또는 규칙적인 운동을 해요' },
  { value: 'very_active', label: '매우 활동적', description: '육체 노동이나 고강도 운동을 자주 해요' },
];

export default function ActivityLevelSection({
  value,
  confirmed,
  onActivityChange,
  onConfirmationChange,
}) {
  return (
    <section className="activity-section" aria-labelledby="activity-level-title">
      <div className="activity-section__heading">
        <h3 id="activity-level-title">활동 수준</h3>
        <span>필수</span>
      </div>

      <div className="activity-section__intro">
        <p>평소 하루 활동량과 가장 가까운 항목을 골라주세요.</p>
        <small>운동뿐 아니라 출퇴근, 업무, 집안일까지 포함해 판단해요.</small>
      </div>

      <fieldset className="activity-options">
        <legend className="sr-only">활동 수준</legend>
        {ACTIVITY_LEVELS.map((level) => (
          <label
            className={`activity-option${value === level.value ? ' activity-option--selected' : ''}`}
            key={level.value}
          >
            <input
              type="radio"
              name="activity"
              value={level.value}
              checked={value === level.value}
              onChange={() => onActivityChange(level.value)}
            />
            <span className="activity-option__copy">
              <strong>{level.label}</strong>
              <small>{level.description}</small>
            </span>
            <span className="activity-option__marker" aria-hidden="true" />
          </label>
        ))}
      </fieldset>

      <div className="adult-eligibility">
        <p className="adult-eligibility__label">적용 대상 확인</p>
        <label className={`adult-confirmation${confirmed ? ' adult-confirmation--checked' : ''}`}>
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(event) => onConfirmationChange(event.target.checked)}
          />
          <span className="adult-confirmation__content">
            <strong>일반 성인 기준 적용에 동의해요</strong>
            <small>
              19~64세이며 임신·수유 중이 아니고, 질환별 영양관리나 섭식장애 등 별도 관리가 필요하지 않아요.
            </small>
          </span>
        </label>
      </div>
    </section>
  );
}
