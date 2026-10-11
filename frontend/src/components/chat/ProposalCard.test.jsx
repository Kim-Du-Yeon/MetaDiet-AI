import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import ProposalCard from "./ProposalCard";

test("plan acceptance explicitly does not log intake", () => {
  const decide = jest.fn();
  render(<ProposalCard proposal={{ kind: "plan", version: 2, payload: { meals: [], log_date: "2026-10-09" } }} onDecision={decide} />);
  expect(screen.getByText(/실제 섭취량에는 반영되지 않습니다/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "이 내용 확정" }));
  expect(decide).toHaveBeenCalledWith("confirm");
});

test("editing OCR disables approval until a revised proposal is created", () => {
  const revise = jest.fn();
  render(<ProposalCard proposal={{ kind: "measurement", version: 1, payload: { measured_date: "2026-10-08", weight_kg: 56.1, skeletal_muscle_kg: 23, body_fat_kg: 12, body_fat_pct: 21.4 } }} onRevise={revise} />);
  fireEvent.change(screen.getByLabelText("체중 (kg)"), { target: { value: "57.1" } });
  expect(screen.getByRole("button", { name: "이 내용 확정" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "수정한 수치로 다시 제안" }));
  expect(revise).toHaveBeenCalledWith(expect.objectContaining({ weight_kg: 57.1 }));
});

test("strategy proposal exposes traceable evidence as source cards", () => {
  render(<ProposalCard proposal={{ kind: "strategy", version: 1, payload: {
    effective_date: "2026-10-11", daily_calories: 1800, protein_g: 100,
    carbs_g: 220, fat_g: 58, strategy_note: "검토된 감량 전략",
    evidence: [{ source: "KDRIs 2025", page: 42, edition: "2025", population: "성인" }],
  } }} onDecision={jest.fn()} />);

  expect(screen.getByRole("heading", { name: "참고 근거" })).toBeInTheDocument();
  expect(screen.getByText("KDRIs 2025")).toBeInTheDocument();
  expect(screen.getByText(/42쪽/)).toBeInTheDocument();
  expect(screen.getByText(/성인/)).toBeInTheDocument();
});
