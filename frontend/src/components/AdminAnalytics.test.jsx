import { render, screen, waitFor } from "@testing-library/react";
import AdminAnalytics from "./AdminAnalytics";
import { getAdminAnalytics } from "../api/dietApi";

jest.mock("../api/dietApi", () => ({ getAdminAnalytics: jest.fn() }));

test("renders privacy-safe product and agent metrics for an administrator", async () => {
  getAdminAnalytics.mockResolvedValue({
    active_users: { daily: 3, weekly: 9 },
    funnel: { onboarding_rate: 0.8, first_meal_rate: 0.5 },
    agent: { success_rate: 0.9, latency_p95_ms: 2400 },
  });
  render(<AdminAnalytics />);
  expect(await screen.findByRole("heading", { name: "제품 운영 지표" })).toBeTruthy();
  expect(screen.getByText("90%")).toBeTruthy();
  expect(screen.getByText("2.4초")).toBeTruthy();
  expect(screen.getByText(/대화 내용과 건강 수치는 수집하지 않고/)).toBeTruthy();
});

test("renders nothing when the API denies administrator access", async () => {
  getAdminAnalytics.mockResolvedValue(null);
  const { container } = render(<AdminAnalytics />);
  await waitFor(() => expect(getAdminAnalytics).toHaveBeenCalled());
  expect(container.innerHTML).toBe("");
});
