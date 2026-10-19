import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import MealChoiceCards from './MealChoiceCards';

const selection = {id:'choice', items:[{index:2, query:'돼지바 아이스크림', quantity_g:70, generic_available:true}]};
test('asks through choices and opens fields only on manual entry', () => {
  const submit = jest.fn(); const cancel = jest.fn();
  render(<MealChoiceCards selection={selection} onResolve={submit} onCancel={cancel} />);
  expect(screen.queryByLabelText('열량 (kcal)')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', {name:'기입하기'}));
  expect(screen.getByLabelText('열량 (kcal)')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', {name:'제외하기'}));
  expect(screen.queryByLabelText('열량 (kcal)')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', {name:'남은 음식 확인하기'}));
  expect(submit).toHaveBeenCalledWith([{index:2,action:'exclude'}]);
  fireEvent.click(screen.getByRole('button', {name:'전체 취소'}));
  expect(cancel).toHaveBeenCalled();
});

test('excluding every food closes without sending an empty proposal', () => {
  const submit = jest.fn(); const cancel = jest.fn();
  render(<MealChoiceCards selection={{...selection, known_count:0}} onResolve={submit} onCancel={cancel} />);
  fireEvent.click(screen.getByRole('button', {name:'제외하기'}));
  expect(screen.getByText(/남은 음식이 없어요/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', {name:'기록 없이 닫기'}));
  expect(cancel).toHaveBeenCalledTimes(1);
  expect(submit).not.toHaveBeenCalled();
});

test('skip all unknown foods closes when there are no recognized foods', () => {
  const submit = jest.fn(); const cancel = jest.fn();
  render(<MealChoiceCards selection={{...selection, known_count:0}} onResolve={submit} onCancel={cancel} />);
  fireEvent.click(screen.getByRole('button', {name:'모두 제외하고 닫기'}));
  expect(cancel).toHaveBeenCalledTimes(1);
  expect(submit).not.toHaveBeenCalled();
});
test('generic is explicit and failure leaves retry/cancel available', () => {
  const submit = jest.fn();
  render(<MealChoiceCards selection={selection} onResolve={submit} onCancel={()=>{}} error="실패" />);
  fireEvent.click(screen.getByRole('button', {name:'일반 아이스크림 기준 사용'}));
  fireEvent.click(screen.getByRole('button', {name:'선택 적용'}));
  expect(submit).toHaveBeenCalledWith([{index:2,action:'generic'}]);
  expect(screen.getByRole('alert')).toHaveTextContent('실패');
});
