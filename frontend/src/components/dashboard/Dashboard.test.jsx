import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import Dashboard from "./Dashboard";
import * as api from "../../api/dietApi";

jest.mock("../../api/dietApi");
jest.mock("recharts", () => ({
  LineChart: ({ children }) => <div>{children}</div>, Line: () => null,
  XAxis: () => null, YAxis: () => null, CartesianGrid: () => null,
  Tooltip: () => null, Legend: () => null,
  ResponsiveContainer: ({ children }) => <div>{children}</div>,
}));

beforeEach(() => {
  api.getDashboardSummary.mockResolvedValue({
    latest_weight: { measured_date: "2026-10-12", weight_kg: 70, source: "onboarding" },
    latest_body_composition: null,
    weight_history: [{ measured_date: "2026-10-12", weight_kg: 70, source: "onboarding" }],
    body_composition_history: [],
  });
  api.getCurrentStrategy.mockResolvedValue({});
  api.getCalendar.mockResolvedValue({ total: {} });
  api.getCaloriesHistory.mockResolvedValue({ days: [] });
});

test("가입 체중은 표시하고 없는 체성분은 미입력으로 표시한다", async () => {
  render(<Dashboard />);
  expect(await screen.findByText("70")).toBeInTheDocument();
  expect(screen.getAllByText("미입력")).toHaveLength(2);
});

test("체중만 기록해도 확인 제안을 거친다", async () => {
  api.proposeWeight.mockResolvedValue({ id: "p1", version: 1, kind: "weight", payload: {
    kind: "weight", measured_date: "2026-10-12", weight_kg: 69.5, source: "manual",
  }});
  render(<Dashboard />);
  await screen.findByText("70");
  fireEvent.click(screen.getByRole("button", { name: "측정 기록하기" }));
  fireEvent.click(screen.getByRole("button", { name: "체중만 기록" }));
  fireEvent.change(screen.getByLabelText("체중 (kg)"), { target: { value: "69.5" } });
  fireEvent.click(screen.getByRole("button", { name: "확인 내용 만들기" }));
  await waitFor(() => expect(api.proposeWeight).toHaveBeenCalled());
  expect(await screen.findByText("체중 기록 확인")).toBeInTheDocument();
  expect(api.decideProposal).not.toHaveBeenCalled();
});
