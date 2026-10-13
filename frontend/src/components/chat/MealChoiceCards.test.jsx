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
  fireEvent.click(screen.getByRole('button', {name:'선택 적용'}));
  expect(submit).toHaveBeenCalledWith([{index:2,action:'exclude'}]);
  fireEvent.click(screen.getByRole('button', {name:'전체 취소'}));
  expect(cancel).toHaveBeenCalled();
});
test('generic is explicit and failure leaves retry/cancel available', () => {
  const submit = jest.fn();
  render(<MealChoiceCards selection={selection} onResolve={submit} onCancel={()=>{}} error="실패" />);
  fireEvent.click(screen.getByRole('button', {name:'일반 아이스크림 기준 사용'}));
  fireEvent.click(screen.getByRole('button', {name:'선택 적용'}));
  expect(submit).toHaveBeenCalledWith([{index:2,action:'generic'}]);
  expect(screen.getByRole('alert')).toHaveTextContent('실패');
});
