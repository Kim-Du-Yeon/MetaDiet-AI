const nutrients = [['탄수화물', 'carbs_g'], ['단백질', 'protein_g'], ['지방', 'fat_g']];

export default function MealNutritionFacts({ meal }) {
  return <dl className="meal-nutrition" aria-label={`${meal.nutrition_metadata?.portion?.display_name || meal.food_name} 영양정보`}>
    <div className="meal-nutrition__energy"><dt>열량</dt><dd>{meal.calories}<small>kcal</small></dd></div>
    {nutrients.map(([label, key]) => <div key={key} aria-label={`${label} ${meal[key]}g`}>
      <dt>{label}</dt><dd>{meal[key]}<small>g</small></dd>
    </div>)}
  </dl>;
}
