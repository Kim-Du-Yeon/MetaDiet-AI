import {act,renderHook} from '@testing-library/react';
import {useConversationThread} from './useConversationThread';

beforeEach(()=>sessionStorage.clear());

test('keeps a server-returned conversation across reload/remount',()=>{
  const first=renderHook(()=>useConversationThread('account-a'));
  act(()=>first.result.current[1]('server-thread-123'));
  first.unmount();
  const restored=renderHook(()=>useConversationThread('account-a'));
  expect(restored.result.current[0]).toBe('server-thread-123');
  expect(restored.result.current[2]).toBe(true);
});

test('isolates accounts and rejects a late callback from the previous account',()=>{
  const hook=renderHook(({id})=>useConversationThread(id),{initialProps:{id:'account-a'}});
  const oldSetter=hook.result.current[1];
  act(()=>oldSetter('account-a-thread'));
  hook.rerender({id:'account-b'});
  expect(hook.result.current[0]).not.toBe('account-a-thread');
  act(()=>oldSetter('late-account-a-thread'));
  expect(hook.result.current[0]).not.toBe('late-account-a-thread');
  hook.rerender({id:'account-a'});
  expect(hook.result.current[0]).toBe('account-a-thread');
});

test('invalid persisted values and unavailable storage cannot break rendering',()=>{
  sessionStorage.setItem('metadiet:conversation:account-a','not/a/thread');
  const hook=renderHook(()=>useConversationThread('account-a'));
  expect(hook.result.current[0]).toMatch(/^chat_/);
  const spy=jest.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new Error('blocked');});
  act(()=>hook.result.current[1]('valid-thread'));
  expect(hook.result.current[0]).toBe('valid-thread');
  spy.mockRestore();
});

test('keeps the active day thread even when a reload happens on another day',()=>{
  jest.useFakeTimers().setSystemTime(new Date('2026-10-15T10:00:00Z'));
  const first=renderHook(()=>useConversationThread('account-a'));
  expect(first.result.current[0]).toBe('chat_2026-10-15');
  first.unmount();
  jest.setSystemTime(new Date('2026-10-16T10:00:00Z'));
  const restored=renderHook(()=>useConversationThread('account-a'));
  expect(restored.result.current[0]).toBe('chat_2026-10-15');
  jest.useRealTimers();
});
