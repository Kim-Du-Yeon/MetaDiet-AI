import {render, screen, fireEvent} from '@testing-library/react';
import '@testing-library/jest-dom';
import App from './App';
import {getSessionRestore} from './api/dietApi';
jest.mock('./api/dietApi',()=>({setToken:jest.fn(),getSessionRestore:jest.fn()}));
jest.mock('./lib/supabaseClient',()=>({supabase:{auth:{
  getSession:()=>Promise.resolve({data:{session:{user:{id:'owner'},access_token:'test'}}}),
  onAuthStateChange:()=>({data:{subscription:{unsubscribe:()=>{}}}}),
}}}));
jest.mock('./components/Setup',()=>({onComplete})=><button onClick={onComplete}>시작</button>);
jest.mock('./components/chat/ChatInterface',()=>({messages})=><div>{messages.map(m=>m.content).join('\n')}</div>);
jest.mock('./components/calendar/CalendarView',()=>({onRecordsChanged})=><button onClick={onRecordsChanged}>검증 기록 삭제</button>);
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
