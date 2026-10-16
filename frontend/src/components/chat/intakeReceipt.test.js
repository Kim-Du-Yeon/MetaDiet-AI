import { intakeReceipt } from './intakeReceipt';

test('receipt summarizes only final meals with revised grams and total', () => {
  const text = intakeReceipt({payload: {log_date: '2026-10-16', meals: [
    {food_name: '계란 후라이', quantity_g: 200, calories: 400, meal_type: 'breakfast'},
    {food_name: '돼지고기 볶음', quantity_g: 300, calories: 601.4, meal_type: 'breakfast',
      nutrition_metadata: {portion: {display_name: '제육볶음'}, excluded_foods: ['밥']}}
  ]}});
  expect(text).toContain('2026-10-16 · 아침');
  expect(text).toContain('제육볶음 · 300g · 601 kcal');
  expect(text).toContain('계란 후라이 · 200g · 400 kcal');
  expect(text).toContain('합계 1001 kcal');
  expect(text).not.toContain('밥');
});
