import { fireEvent, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import CoachingReview from './CoachingReview';

test('shows no input for evidence failures alone', () => {
  render(<CoachingReview details={{reason:'search_unavailable',optional_input:null}} onProvide={jest.fn()} />);
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
});

test('asks through buttons; skip and cancel never submit', () => {
  const onProvide=jest.fn();
  render(<CoachingReview details={{optional_input:'measurements'}} onProvide={onProvide} />);
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'입력',exact:true}));
  expect(screen.getByRole('textbox')).toBeVisible();
  expect(screen.getByRole('button',{name:'확인 요청'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'취소',exact:true}));
  fireEvent.click(screen.getByRole('button',{name:'건너뛰기'}));
  expect(screen.getByRole('status')).toHaveTextContent('기록은 변경되지');
  expect(onProvide).not.toHaveBeenCalled();
});

test('explicit input is submitted once and busy prevents another action', () => {
  const onProvide=jest.fn();
  const details={optional_input:'measurements'};
  const {rerender}=render(<CoachingReview details={details} onProvide={onProvide} />);
  fireEvent.click(screen.getByRole('button',{name:'입력',exact:true}));
  fireEvent.change(screen.getByRole('textbox'),{target:{value:'2026-10-16 체중 80kg'}});
  fireEvent.click(screen.getByRole('button',{name:'확인 요청'}));
  expect(onProvide).toHaveBeenCalledWith('2026-10-16 체중 80kg');
  rerender(<CoachingReview details={details} onProvide={onProvide} busy />);
  expect(screen.getByRole('button',{name:'확인 요청'})).toBeDisabled();
});
