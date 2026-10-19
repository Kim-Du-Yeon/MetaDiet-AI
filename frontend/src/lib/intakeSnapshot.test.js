import {validIntakeSnapshot} from './intakeSnapshot';
test('incomplete snapshot cannot replace server-confirmed intake',()=>{
  expect(validIntakeSnapshot({protocol:1,version:'a'.repeat(64),today_calories:NaN})).toBeFalsy();
  expect(validIntakeSnapshot({protocol:1,version:'old',today_calories:0})).toBeFalsy();
});
