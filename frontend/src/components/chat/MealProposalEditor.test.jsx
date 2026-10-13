import { fireEvent, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import ProposalCard from './ProposalCard';

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
