const mealTypes = { breakfast: '아침', lunch: '점심', dinner: '저녁', snack: '간식' };

// Use the confirmed proposal, which already excludes removed foods and includes revisions.
export function intakeReceipt(proposal) {
  const payload = proposal.payload || {};
  const meals = payload.meals || [];
  const types = [...new Set(meals.map(meal => mealTypes[meal.meal_type]).filter(Boolean))];
  const lines = meals.map(meal => {
    const name = meal.nutrition_metadata?.portion?.display_name || meal.food_name;
    return `- ${name} · ${meal.quantity_g}g · ${Math.round(meal.calories)} kcal`;
  });
  return ['섭취 기록을 저장했습니다.', [payload.log_date, types.join('·')].filter(Boolean).join(' · '),
    lines.join('\n'), meals.length ? `합계 ${Math.round(meals.reduce((sum, meal) => sum + meal.calories, 0))} kcal` : '']
    .filter(Boolean).join('\n\n');
}
