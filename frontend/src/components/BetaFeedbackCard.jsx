import { useRef, useState } from "react";
import { submitBetaFeedback } from "../api/dietApi";

const categories = [
  ["general", "전반적인 의견"],
  ["answer_quality", "답변 품질"],
  ["evidence", "근거와 출처"],
  ["usability", "사용 편의성"],
  ["bug", "오류 신고"],
];

function defaultUuidFactory() {
  return window.crypto?.randomUUID?.()
    || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function BetaFeedbackCard({ uuidFactory = defaultUuidFactory }) {
  const [rating, setRating] = useState("");
  const [category, setCategory] = useState("general");
  const [comment, setComment] = useState("");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const submissionId = useRef(null);
  const inFlight = useRef(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (inFlight.current) return;
    if (!rating) {
      setMessage("만족도를 선택해주세요.");
      return;
    }
    if (!submissionId.current) submissionId.current = uuidFactory();
    inFlight.current = true;
    setSubmitting(true);
    setMessage("");
    try {
      await submitBetaFeedback({
        rating: Number(rating),
        category,
        comment: comment.trim() || null,
        client_submission_id: submissionId.current,
      });
      setRating("");
      setCategory("general");
      setComment("");
      submissionId.current = null;
      setMessage("피드백을 보내주셔서 감사합니다.");
    } catch {
      setMessage("피드백을 전송하지 못했습니다. 입력을 유지했으니 다시 시도해주세요.");
    } finally {
      inFlight.current = false;
      setSubmitting(false);
    }
  };

  return (
    <section className="settings-card feedback-card" aria-labelledby="beta-feedback-title">
      <p className="settings-eyebrow">BETA FEEDBACK</p>
      <h2 id="beta-feedback-title">베타 피드백</h2>
      <p>사용 경험을 알려주시면 다음 개선 순서를 정하는 데 활용합니다.</p>

      <form onSubmit={handleSubmit}>
        <fieldset className="feedback-rating">
          <legend>서비스 만족도</legend>
          <div className="feedback-rating-options">
            {[1, 2, 3, 4, 5].map((score) => (
              <label key={score}>
                <input
                  type="radio"
                  name="feedback-rating"
                  value={score}
                  checked={rating === String(score)}
                  onChange={(event) => setRating(event.target.value)}
                  disabled={submitting}
                />
                <span>{score}점</span>
              </label>
            ))}
          </div>
        </fieldset>

        <label className="settings-label" htmlFor="feedback-category">피드백 종류</label>
        <select
          id="feedback-category"
          className="settings-input"
          value={category}
          onChange={(event) => setCategory(event.target.value)}
          disabled={submitting}
        >
          {categories.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>

        <label className="settings-label" htmlFor="feedback-comment">의견 (선택)</label>
        <textarea
          id="feedback-comment"
          className="settings-input feedback-comment"
          value={comment}
          maxLength={1000}
          onChange={(event) => setComment(event.target.value)}
          disabled={submitting}
          rows={5}
        />
        <div className="feedback-meta">
          <span>대화·식사·인바디 기록은 자동으로 첨부되지 않습니다.</span>
          <span aria-live="polite">{comment.length} / 1000</span>
        </div>

        {message && <p className="feedback-status" role="status">{message}</p>}
        <button className="feedback-submit-button" type="submit" disabled={submitting}>
          {submitting ? "전송 중..." : "피드백 보내기"}
        </button>
      </form>
    </section>
  );
}
