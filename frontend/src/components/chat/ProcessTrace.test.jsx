import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import ProcessTrace from "./ProcessTrace";

test("shows only real streamed execution steps and marks the active step", () => {
  render(<ProcessTrace running steps={[
    { phase: "intent", label: "요청 의도 분석 중" },
    { phase: "evidence", label: "근거 자료 검색 중" },
  ]} />);

  expect(screen.getByText("요청 의도 분석 중")).toBeInTheDocument();
  expect(screen.getByText("근거 자료 검색 중")).toHaveAttribute("aria-current", "step");
  expect(screen.getByRole("status")).toHaveTextContent("2단계 진행 중");
});

test("completed trace has a concise expandable summary", () => {
  render(<ProcessTrace steps={[
    { phase: "intent", label: "요청 의도 분석" },
    { phase: "validation", label: "식단 제안 검토" },
  ]} />);

  expect(screen.getByText("검토 과정 2단계")).toBeInTheDocument();
  expect(screen.getByText("식단 제안 검토")).toBeInTheDocument();
});
