import {render, screen, fireEvent, waitFor} from '@testing-library/react';
import '@testing-library/jest-dom';
import CalendarView from './CalendarView';
import {getCalendar, getCalendarMonth, updateMeal, deleteMeal} from '../../api/dietApi';
jest.mock('../../api/dietApi',()=>({getCalendar:jest.fn(),getCalendarMonth:jest.fn(),updateMeal:jest.fn(),deleteMeal:jest.fn()}));
beforeEach(()=>{
  jest.clearAllMocks();
  getCalendar.mockResolvedValue({total:{calories:15},meals:[{id:'test',food_name:'검증용 밥',quantity_g:10,calories:15,meal_type:'lunch'}]});
  getCalendarMonth.mockResolvedValue({days:[]});
  jest.spyOn(window,'confirm').mockReturnValue(true);
});
afterEach(()=>jest.restoreAllMocks());
test('versioned mutation response supplies calendar and parent without follow-up reads',async()=>{
  const refresh=jest.fn();
  const begin=jest.fn(()=>7);
  const sync={protocol:1,version:'a'.repeat(64),today_calories:0,target_calories:2000,
    calendar:{date:'2026-10-19',meals:[],total:{calories:0}},
    calendar_month:{year_month:'2026-10',days:[]},messages:[]};
  deleteMeal.mockResolvedValue({success:true,sync});
  render(<CalendarView onRecordsChanged={refresh} onRecordsChanging={begin} threadId="test-thread"/>);
  await screen.findByText('검증용 밥');
  fireEvent.click(screen.getByTitle('삭제'));
  await waitFor(()=>expect(refresh).toHaveBeenCalledWith(sync,7));
  expect(getCalendar).toHaveBeenCalledTimes(1);
  expect(getCalendarMonth).toHaveBeenCalledTimes(1);
  expect(deleteMeal.mock.calls[0][1].threadId).toBe('test-thread');
});
test('successful deletion and edit notify shared intake refresh; failed deletion does not',async()=>{
  const refresh=jest.fn();
  deleteMeal.mockResolvedValue({success:true});
  updateMeal.mockResolvedValue({success:true});
  render(<CalendarView onRecordsChanged={refresh}/>);
  await screen.findByText('검증용 밥');
  fireEvent.click(await screen.findByTitle('삭제'));
  await waitFor(()=>expect(refresh).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByTitle('수정'));
  fireEvent.change(screen.getByRole('spinbutton'),{target:{value:'20'}});
  fireEvent.click(screen.getByRole('button',{name:'저장'}));
  await waitFor(()=>expect(refresh).toHaveBeenCalledTimes(2));
  deleteMeal.mockRejectedValue(new Error('network'));
  jest.spyOn(window,'alert').mockImplementation(()=>{});
  fireEvent.click(screen.getByTitle('삭제'));
  await waitFor(()=>expect(window.alert).toHaveBeenCalled());
  expect(refresh).toHaveBeenCalledTimes(2);
});
