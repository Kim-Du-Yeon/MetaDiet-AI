import { useState } from 'react';
import FoodProductSearch from './FoodProductSearch';
import NutritionLabelForm from './NutritionLabelForm';

export default function ProductCorrection({ proposal, busy, onReplace, onEditingChange }) {
  const [open, setOpen] = useState(false);
  const [index, setIndex] = useState(0);
  const [mode, setMode] = useState(null);
  const meal = proposal.payload.meals[index];
  if (!meal) return null;
  const name = meal.nutrition_metadata?.portion?.display_name || meal.food_name;
  return <div className="proposal__product-tools">
    <button type="button" className="proposal__secondary" disabled={busy} aria-expanded={open}
      onClick={() => {setOpen(!open); setMode(null); onEditingChange(!open);}}>{open ? '제품 변경 닫기' : '정확한 제품으로 변경 (선택)'}</button>
    {open && <><p>일반 기준으로 그대로 기록해도 돼요. 변경할 음식만 선택하세요. 다른 음식과 날짜는 유지됩니다. 변경하지 않으려면 ‘제품 변경 닫기’를 누르세요.</p>
      <label>변경할 음식<select disabled={busy} value={index} onChange={e=>{setIndex(Number(e.target.value));setMode(null);}}>
        {proposal.payload.meals.map((item,i)=><option key={i} value={i}>{item.nutrition_metadata?.portion?.display_name || item.food_name}</option>)}
      </select></label>
      <div className="proposal__actions">
        <button className="proposal__secondary" type="button" disabled={busy} onClick={()=>setMode('label')}>제품 영양표 입력</button>
        <button className="proposal__secondary" type="button" disabled={busy} onClick={()=>setMode('search')}>제품을 정확히 입력</button>
      </div>
      {mode === 'search' && <FoodProductSearch key={`search-${index}`} disabled={busy} initialName={name} initialGrams={meal.quantity_g}
        onClose={()=>setMode(null)} onProduct={product=>onReplace(index,{food_id:product.food_id,amount:product.quantity_g,unit:'g'})} />}
      {mode === 'label' && <NutritionLabelForm key={`label-${index}`} disabled={busy} initialValues={{food_name:name,quantity_g:meal.quantity_g}}
        onClose={()=>setMode(null)} onLabel={label=>onReplace(index,{label,amount:label.quantity_g,unit:'g'})} />}
    </>}
  </div>;
}
