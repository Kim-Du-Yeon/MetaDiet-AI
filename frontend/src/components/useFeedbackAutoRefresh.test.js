import {act, renderHook} from '@testing-library/react';
import useFeedbackAutoRefresh from './useFeedbackAutoRefresh';

beforeEach(()=>jest.useFakeTimers());
afterEach(()=>{jest.useRealTimers();jest.restoreAllMocks();});

test('hidden tab waits, returning refreshes once and in-flight requests never overlap',()=>{
  const refresh=jest.fn();
  const visibility=jest.spyOn(document,'visibilityState','get').mockReturnValue('hidden');
  const {rerender,unmount}=renderHook(({busy})=>useFeedbackAutoRefresh(true,busy,refresh),{initialProps:{busy:false}});
  act(()=>jest.advanceTimersByTime(60000));
  expect(refresh).not.toHaveBeenCalled();
  visibility.mockReturnValue('visible');
  act(()=>{document.dispatchEvent(new Event('visibilitychange'));window.dispatchEvent(new Event('focus'));});
  expect(refresh).toHaveBeenCalledTimes(1);
  rerender({busy:true});
  act(()=>jest.advanceTimersByTime(60000));
  expect(refresh).toHaveBeenCalledTimes(1);
  rerender({busy:false});
  act(()=>jest.advanceTimersByTime(30000));
  expect(refresh).toHaveBeenCalledTimes(2);
  unmount();
  act(()=>{jest.advanceTimersByTime(60000);window.dispatchEvent(new Event('focus'));});
  expect(refresh).toHaveBeenCalledTimes(2);
});

test('pausing or losing administrator access removes timers and focus refreshes',()=>{
  const refresh=jest.fn();
  const {rerender}=renderHook(({enabled})=>useFeedbackAutoRefresh(enabled,false,refresh),{initialProps:{enabled:true}});
  rerender({enabled:false});
  act(()=>{jest.advanceTimersByTime(60000);window.dispatchEvent(new Event('focus'));});
  expect(refresh).not.toHaveBeenCalled();
  rerender({enabled:true});
  act(()=>jest.advanceTimersByTime(30000));
  expect(refresh).toHaveBeenCalledTimes(1);
});
