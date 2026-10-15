import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import '@testing-library/jest-dom';
import FeedbackHistory from './FeedbackHistory';
import {getAdminFeedbackHistory} from '../api/dietApi';
jest.mock('../api/dietApi',()=>({getAdminFeedbackHistory:jest.fn()}));
const event=version=>({id:String(version),version,before_status:'received',after_status:'resolved',before_note:'',after_note:'',created_at:'2026-10-15T00:00:00Z'});

test('reopening history starts from newest page without duplicate older entries',async()=>{
  getAdminFeedbackHistory.mockImplementation(async(id,cursor)=>cursor?{items:[event(2)],has_more:false}:{items:[event(3)],has_more:true,next_before_version:3});
  render(<FeedbackHistory feedbackId="fixture" version={3}/>);
  fireEvent.click(screen.getByRole('button',{name:'변경 이력 보기'}));
  fireEvent.click(await screen.findByRole('button',{name:'이전 이력 더 보기'}));
  await screen.findByText('버전 2');
  fireEvent.click(screen.getByRole('button',{name:'변경 이력 접기'}));
  fireEvent.click(screen.getByRole('button',{name:'변경 이력 보기'}));
  await waitFor(()=>expect(getAdminFeedbackHistory).toHaveBeenLastCalledWith('fixture',null));
  expect(screen.queryByText('버전 2')).not.toBeInTheDocument();
  expect(screen.getAllByText('버전 3')).toHaveLength(1);
});


test('late history response cannot replace a newly selected feedback',async()=>{
  let finish;
  getAdminFeedbackHistory.mockImplementation(id=>id==='old'?new Promise(resolve=>{finish=resolve;}):Promise.resolve({items:[event(7)],has_more:false}));
  const {rerender}=render(<FeedbackHistory feedbackId="old" version={3}/>);
  fireEvent.click(screen.getByRole('button',{name:'변경 이력 보기'}));
  rerender(<FeedbackHistory feedbackId="new" version={7}/>);
  await screen.findByText('버전 7');
  const {act}=require('@testing-library/react');
  await act(async()=>finish({items:[event(3)],has_more:false}));
  expect(screen.queryByText('버전 3')).not.toBeInTheDocument();
});

test('history request failure has a retry path',async()=>{
  getAdminFeedbackHistory.mockRejectedValueOnce(new Error('이력 조회 실패')).mockResolvedValue({items:[],has_more:false});
  render(<FeedbackHistory feedbackId="fixture" version={1}/>);
  fireEvent.click(screen.getByRole('button',{name:'변경 이력 보기'}));
  fireEvent.click(await screen.findByRole('button',{name:'이력 다시 시도'}));
  await screen.findByText('아직 변경 이력이 없습니다.');
});
