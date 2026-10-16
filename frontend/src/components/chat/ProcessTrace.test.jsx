import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import ProcessTrace from "./ProcessTrace";

test('shows an immediate honest waiting state before the first server event', () => {
  const {rerender} = render(<ProcessTrace running steps={[]} />);
  expect(screen.getByRole('status')).toHaveTextContent('서버 응답을 기다리는 중');
  expect(screen.queryByText('요청 의도 분석 중')).not.toBeInTheDocument();
  rerender(<ProcessTrace running steps={[{phase:'checkpoint_restore',label:'저장된 대화 상태를 확인 중입니다.'}]} />);
  expect(screen.queryByText(/서버 응답을 기다리는 중/)).not.toBeInTheDocument();
  expect(screen.getByText('저장된 대화 상태를 확인 중입니다.')).toBeInTheDocument();
  rerender(<ProcessTrace running={false} steps={[]} />);
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});

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

test("numbers streamed steps by their displayed order", () => {
  const { container } = render(<ProcessTrace running steps={[
    { phase: "intent", label: "요청 의도 분석 중" },
    { phase: "delegation", label: "식사 전문 Agent에 위임 중" },
    { phase: "records", label: "사용자 정보 확인 중" },
    { phase: "records", label: "오늘 섭취 기록 확인 중" },
  ]} />);

  expect([...container.querySelectorAll(".process-trace__index")].map((node) => node.textContent))
    .toEqual(["01", "02", "03", "04"]);
});


test('coaching after a verified read shows one concise live status', () => {
  render(<ProcessTrace running steps={[{phase:'intent',label:'요청 의도 분석 중'},
    {phase:'coaching_context',label:'확인한 기록을 바탕으로 답변 준비 중'}]} />);
  expect(screen.getByRole('status')).toHaveTextContent('확인한 기록을 바탕으로 답변 준비 중');
  expect(screen.queryByText('요청 의도 분석 중')).not.toBeInTheDocument();
});
