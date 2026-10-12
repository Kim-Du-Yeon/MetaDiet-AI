import { fireEvent, render, screen } from '@testing-library/react';
import FoodProductSearch from './FoodProductSearch';
import { nutritionLookup } from '../../api/dietApi';
jest.mock('../../api/dietApi', () => ({ nutritionLookup: jest.fn() }));

test('selection names today explicitly and does not send or confirm a record', async () => {
  nutritionLookup.mockResolvedValue({ results: [{ status: 'ambiguous', candidates: [
    { food_id: 'mfds:P1', name: '제품', manufacturer: '회사', basis_g: 100 }
  ] }] });
  const onSelect = jest.fn();
  render(<FoodProductSearch onSelect={onSelect} onClose={() => {}} />);
  fireEvent.change(screen.getByLabelText('제품명'), { target: { value: '제품' } });
  fireEvent.change(screen.getByLabelText('먹은 양 (g)'), { target: { value: '10' } });
  fireEvent.click(screen.getByRole('button', { name: '제품 검색' }));
  fireEvent.click(await screen.findByRole('button', { name: '이 제품 선택' }));
  expect(onSelect).toHaveBeenCalledWith('제품 선택: mfds:P1 / 제품 10g 오늘 먹었어. 기록만 해줘.');
});
