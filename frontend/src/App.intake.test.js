import {render, screen, fireEvent} from '@testing-library/react';
import '@testing-library/jest-dom';
import App from './App';
import {getSessionRestore} from './api/dietApi';
let mockSnapshot;
beforeEach(()=>{mockSnapshot=undefined; jest.clearAllMocks();});
jest.mock('./api/dietApi',()=>({setToken:jest.fn(),getSessionRestore:jest.fn()}));
jest.mock('./lib/supabaseClient',()=>({supabase:{auth:{
  getSession:()=>Promise.resolve({data:{session:{user:{id:'owner'},access_token:'test'}}}),
  onAuthStateChange:()=>({data:{subscription:{unsubscribe:()=>{}}}}),
}}}));
jest.mock('./components/Setup',()=>({onComplete})=><button onClick={onComplete}>시작</button>);
jest.mock('./components/chat/ChatInterface',()=>({messages})=><div>{messages.map(m=>m.content).join('\n')}</div>);
jest.mock('./components/calendar/CalendarView',()=>({onRecordsChanged,onRecordsChanging,onRecordsChangeFinished})=><button onClick={async()=>{
  const ticket=onRecordsChanging?.(); const snapshot=await mockSnapshot; await onRecordsChanged(snapshot,ticket); onRecordsChangeFinished?.();
}}>검증 기록 삭제</button>);
test('calendar mutation updates header from server and reconciles conversation without page reload',async()=>{
  getSessionRestore.mockResolvedValue({today_calories:436,target_calories:2000,
    messages:[{role:'assistant',content:'삭제된 섭취 기록입니다.'}]});
  render(<App/>);
  fireEvent.click(await screen.findByRole('button',{name:'시작'}));
  fireEvent.click(await screen.findByRole('button',{name:'📅 캘린더'}));
  fireEvent.click(screen.getByRole('button',{name:'검증 기록 삭제'}));
  await screen.findByText('436 / 2000 kcal');
  fireEvent.click(screen.getByRole('button',{name:'💬 채팅'}));
  expect(screen.getByText('삭제된 섭취 기록입니다.')).toBeInTheDocument();
});

const snapshot = calories => ({protocol:1,version:'a'.repeat(64),today_calories:calories,target_calories:2000,
  calendar:{date:'2026-10-19',meals:[]},calendar_month:{year_month:'2026-10',days:[]},
  messages:[{role:'assistant',content:'삭제된 섭취 기록입니다.'}]});
test('valid snapshot updates shared state with no session restore and ignores late older reply',async()=>{
  let first;
  mockSnapshot=new Promise(resolve=>{first=resolve;});
  render(<App/>);
  fireEvent.click(await screen.findByRole('button',{name:'시작'}));
  fireEvent.click(await screen.findByRole('button',{name:'📅 캘린더'}));
  fireEvent.click(screen.getByRole('button',{name:'검증 기록 삭제'}));
  mockSnapshot=Promise.resolve(snapshot(100));
  fireEvent.click(screen.getByRole('button',{name:'검증 기록 삭제'}));
  await screen.findByText('100 / 2000 kcal');
  first(snapshot(300));
  fireEvent.click(screen.getByRole('button',{name:'💬 채팅'}));
  expect(await screen.findByText('삭제된 섭취 기록입니다.')).toBeInTheDocument();
  expect(screen.getByText('100 / 2000 kcal')).toBeInTheDocument();
  expect(getSessionRestore).not.toHaveBeenCalled();
});
