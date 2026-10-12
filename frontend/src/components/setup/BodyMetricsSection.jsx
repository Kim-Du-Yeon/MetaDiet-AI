import SetupSection from './SetupSection';
import './BodyMetricsSection.css';

const BODY_FIELDS = [
  { key: 'age', label: '나이', unit: '세', placeholder: '25' },
  { key: 'height_cm', label: '키', unit: 'cm', placeholder: '175' },
  { key: 'weight_kg', label: '체중', unit: 'kg', placeholder: '70' },
];

export default function BodyMetricsSection({ values, onChange }) {
  return (
    <SetupSection title="신체 정보" description="현재 상태를 기준으로 하루 권장량을 계산해요." required>
      <div className="body-metrics-grid">
        {BODY_FIELDS.map((field) => (
          <div className="body-metric-field" key={field.key}>
            <label htmlFor={`setup-${field.key}`}>{field.label}</label>
            <div className="body-metric-field__control">
              <input
                id={`setup-${field.key}`}
                type="number"
                value={values[field.key]}
                onChange={(event) => onChange(field.key, event.target.value)}
                placeholder={field.placeholder}
              />
              <span>{field.unit}</span>
            </div>
          </div>
        ))}
      </div>
    </SetupSection>
  );
}
