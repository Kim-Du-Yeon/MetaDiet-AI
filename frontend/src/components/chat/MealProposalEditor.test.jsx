import { fireEvent, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import ProposalCard from './ProposalCard';

test('approximate product basis is visible and pizza slice/whole units are editable', () => {
  render(<ProposalCard proposal={{ kind: 'intake', version: 1, payload: { log_date: '2026-10-13', meals: [
    { food_id: 'csv:pizza', food_name: '일반 피자', meal_type: 'lunch', quantity_g: 200,
      calories: 400, carbs_g: 40, protein_g: 20, fat_g: 10, source: 'csv', nutrition_metadata: {
        portion: { display_name: '도미노피자', amount: 2, unit: '조각', default_unit: '조각',
          unit_g: 100, representative: true, basis_note: '일반 피자 기준이며 브랜드 제품값이 아니에요.',
          unit_grams: { 조각: 100, 판: 800, 회분: 200 } } } },
  ] } }} onRevise={jest.fn()} onDecision={jest.fn()} />);
  expect(screen.getByText('일반 피자 기준이며 브랜드 제품값이 아니에요.')).toBeVisible();
  expect(screen.getByRole('option', { name: '판' })).toBeInTheDocument();
});

test('portion edit requires server recalculation and sends units without client nutrients', () => {
  const revise = jest.fn();
  render(<ProposalCard proposal={{ kind: 'intake', version: 1, payload: { log_date: '2026-10-13', meals: [
    { food_id: 'csv:test', food_name: '밥', meal_type: 'lunch', quantity_g: 200, calories: 300,
      protein_g: 5, carbs_g: 65, fat_g: 1, source: 'csv', nutrition_metadata: { portion: {
        amount: 1, unit: '공기', default_unit: '공기', unit_g: 200, defaulted: true } } },
  ] } }} onRevise={revise} onDecision={jest.fn()} />);
  expect(screen.getByText(/탄수화물 65g/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('1번 음식 분량'), { target: { value: '1.5' } });
  expect(screen.getByRole('button', { name: '이대로 기록' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: '수정한 분량 다시 계산' }));
  expect(revise).toHaveBeenCalledWith({ log_date: '2026-10-13', meal_type: 'lunch', items: [{ amount: 1.5, unit: '공기' }] });
  fireEvent.change(screen.getByLabelText('1번 음식 분량'), { target: { value: '1' } });
  expect(screen.getByRole('button', { name: '이대로 기록' })).toBeEnabled();
});


test('excluding all foods blocks saving and recalculation; undo restores the proposal', () => {
  render(<ProposalCard proposal={{kind:'intake',version:1,payload:{log_date:'2026-10-13',meals:[
    {food_id:'csv:test',food_name:'밥',meal_type:'lunch',quantity_g:200,calories:300,protein_g:5,carbs_g:65,fat_g:1,source:'csv'}
  ]}}} onRevise={jest.fn()} onDecision={jest.fn()} />);
  fireEvent.click(screen.getByRole('button',{name:'1번 음식 제외하기'}));
  expect(screen.getByRole('button',{name:'이대로 기록'})).toBeDisabled();
  expect(screen.getByRole('button',{name:'수정한 분량 다시 계산'})).toBeDisabled();
  expect(screen.getByText(/모두 제외하려면/)).toBeVisible();
  fireEvent.click(screen.getByRole('button',{name:'1번 음식 제외 취소'}));
  expect(screen.getByRole('button',{name:'이대로 기록'})).toBeEnabled();
});
