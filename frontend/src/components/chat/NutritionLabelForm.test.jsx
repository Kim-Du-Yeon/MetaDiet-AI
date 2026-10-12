import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import NutritionLabelForm from "./NutritionLabelForm";
import { proposeNutritionLabel } from "../../api/dietApi";
jest.mock("../../api/dietApi", () => ({ proposeNutritionLabel: jest.fn() }));

test("manual label submits a proposal, never confirms it automatically", async () => {
  Object.defineProperty(window, "crypto", { configurable: true, value: { randomUUID: () => "00000000-0000-4000-8000-000000000001" } });
  const pending = { id: "p", kind: "intake", status: "pending" };
  proposeNutritionLabel.mockResolvedValue(pending);
  const onProposal = jest.fn();
  render(<NutritionLabelForm threadId="t" onProposal={onProposal} onClose={jest.fn()} />);
  fireEvent.change(screen.getByLabelText("제품명 (필수)"), { target: { value: "제품" } });
  ["영양표 기준량 (g)", "먹은 양 (g)", "열량 (kcal)", "단백질 (g)", "탄수화물 (g)", "지방 (g)"].forEach(label => {
    fireEvent.change(screen.getByLabelText(`${label} (필수)`), { target: { value: "10" } });
  });
  fireEvent.change(screen.getByLabelText("섭취일 (필수)"), { target: { value: "2026-10-12" } });
  fireEvent.submit(screen.getByRole("form", { name: "제품 영양표 입력" }));
  await waitFor(() => expect(onProposal).toHaveBeenCalledWith(pending));
  expect(proposeNutritionLabel).toHaveBeenCalledWith(expect.objectContaining({ thread_id: "t", basis_g: 10, quantity_g: 10 }));
});
