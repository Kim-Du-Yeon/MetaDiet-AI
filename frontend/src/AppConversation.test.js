import {fireEvent,render,screen} from '@testing-library/react';
import '@testing-library/jest-dom';
import App from './App';
import {supabase} from './lib/supabaseClient';

jest.mock('./lib/supabaseClient',()=>({supabase:{auth:{getSession:jest.fn(),
  onAuthStateChange:jest.fn(()=>({data:{subscription:{unsubscribe:jest.fn()}}})),signOut:jest.fn()}}}));
jest.mock('./api/dietApi',()=>({setToken:jest.fn()}));
jest.mock('./components/Setup',()=>function Setup({onComplete}){return <button onClick={onComplete}>complete setup</button>});
let mockChatProps;
jest.mock('./components/chat/ChatInterface',()=>function Chat(props){
  mockChatProps=props;
  const {threadId,setThreadId}=props;
  return <><p>active thread: {threadId}</p><button onClick={()=>setThreadId('server-rotated-thread')}>rotate thread</button></>
});

beforeEach(()=>{
  sessionStorage.clear();
  supabase.auth.onAuthStateChange.mockReturnValue({data:{subscription:{unsubscribe:jest.fn()}}});
  supabase.auth.getSession.mockResolvedValue({data:{session:{access_token:'test',user:{id:'account-a'}}}});
});

async function openChat(){fireEvent.click(await screen.findByText('complete setup'));return screen.findByText(/^active thread:/);}

test('App restores the same account thread before mounting chat after reload',async()=>{
  const first=render(<App/>);await openChat();
  fireEvent.click(screen.getByText('rotate thread'));
  expect(screen.getByText('active thread: server-rotated-thread')).toBeInTheDocument();
  first.unmount();render(<App/>);await openChat();
  expect(screen.getByText('active thread: server-rotated-thread')).toBeInTheDocument();
});

test('App does not restore another account conversation pointer',async()=>{
  const first=render(<App/>);await openChat();fireEvent.click(screen.getByText('rotate thread'));first.unmount();
  supabase.auth.getSession.mockResolvedValue({data:{session:{access_token:'other',user:{id:'account-b'}}}});
  render(<App/>);await openChat();
  expect(screen.queryByText('active thread: server-rotated-thread')).not.toBeInTheDocument();
});

test('late previous-account chat callbacks cannot repopulate the current account UI',async()=>{
  const first=render(<App/>);await openChat();
  const previous=mockChatProps;
  const listener=supabase.auth.onAuthStateChange.mock.calls[0][0];
  const {act}=require('@testing-library/react');
  act(()=>listener('SIGNED_IN',{access_token:'other',user:{id:'account-b'}}));
  await openChat();
  act(()=>{
    previous.setMessages([{role:'assistant',content:'previous account private answer'}]);
    previous.onStatsUpdate({calories:99999,target:1});
    previous.setIsInterrupted(true);
    previous.setPrevThreadId('previous-private-thread');
  });
  expect(mockChatProps.messages.some(m=>m.content==='previous account private answer')).toBe(false);
  expect(mockChatProps.isInterrupted).toBe(false);
  expect(mockChatProps.prevThreadId).toBe(null);
  first.unmount();
});
