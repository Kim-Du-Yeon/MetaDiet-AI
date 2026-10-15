import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import '@testing-library/jest-dom';
import AdminFeedback from './AdminFeedback';
import {getAdminFeedback, getAdminFeedbackDetail, updateAdminFeedback, getAdminFeedbackAssignees, getAdminFeedbackHistory} from '../api/dietApi';
jest.mock('../api/dietApi',()=>({getAdminFeedback:jest.fn(),getAdminFeedbackDetail:jest.fn(),updateAdminFeedback:jest.fn(),getAdminFeedbackAssignees:jest.fn(),getAdminFeedbackHistory:jest.fn()}));
const row={id:'one',rating:4,category:'bug',preview:'button issue',status:'received',version:1,created_at:'2026-10-15T01:00:00Z',updated_at:'2026-10-15T01:00:00Z'};
beforeEach(()=>{jest.resetAllMocks();getAdminFeedbackAssignees.mockResolvedValue({items:[{id:'admin',email:'admin@example.invalid'}]});getAdminFeedbackHistory.mockResolvedValue({items:[],has_more:false});});
test('non-administrators see no feedback content',async()=>{
  getAdminFeedback.mockResolvedValue(null);
  const {container}=render(<AdminFeedback/>);
  await waitFor(()=>expect(getAdminFeedback).toHaveBeenCalled());
  await waitFor(()=>expect(container.innerHTML).toBe(''));
});
test('filters paginate, details render as text and failed updates preserve edits',async()=>{
  getAdminFeedback.mockResolvedValue({items:[row],has_more:true});
  getAdminFeedbackDetail.mockResolvedValue({...row,comment:'<script>unsafe</script>',admin_note:''});
  updateAdminFeedback.mockRejectedValueOnce(new Error('다른 관리자가 변경했습니다.')).mockResolvedValueOnce({...row,status:'resolved',version:2,comment:'safe',admin_note:'verified'});
  render(<AdminFeedback/>);
  fireEvent.click(await screen.findByRole('button',{name:/button issue/}));
  await screen.findByText('<script>unsafe</script>');
  expect(document.querySelector('script')).toBeNull();
  fireEvent.change(screen.getByLabelText('처리 상태'),{target:{value:'resolved'}});
  fireEvent.change(screen.getByLabelText('관리자 메모'),{target:{value:'verified'}});
  fireEvent.click(screen.getByRole('button',{name:'처리 내용 저장'}));
  await screen.findByText('다른 관리자가 변경했습니다.');
  expect(screen.getByLabelText('관리자 메모')).toHaveValue('verified');
  fireEvent.click(screen.getByRole('button',{name:'처리 내용 저장'}));
  await screen.findByText('저장했습니다.');
  expect(updateAdminFeedback).toHaveBeenLastCalledWith('one',{version:1,status:'resolved',admin_note:'verified'});
  fireEvent.change(screen.getByLabelText('피드백 상태 필터'),{target:{value:'resolved'}});
  await waitFor(()=>expect(getAdminFeedback).toHaveBeenLastCalledWith({status:'resolved',category:'',offset:0}));
  fireEvent.click(screen.getByRole('button',{name:'다음 페이지'}));
  await waitFor(()=>expect(getAdminFeedback).toHaveBeenLastCalledWith({status:'resolved',category:'',offset:20}));
});
test('list failure can be retried and empty feedback is explicit',async()=>{
  getAdminFeedback.mockRejectedValueOnce(new Error('조회 실패')).mockResolvedValue({items:[],has_more:false});
  render(<AdminFeedback/>);
  await screen.findByText('조회 실패');
  fireEvent.click(screen.getByRole('button',{name:'목록 새로고침'}));
  await screen.findByText('조건에 맞는 피드백이 없습니다.');
});

test('late save from previous selection never replaces the newly opened feedback',async()=>{
  const second={...row,id:'two',preview:'second feedback'};
  getAdminFeedback.mockResolvedValue({items:[row,second],has_more:false});
  getAdminFeedbackDetail.mockImplementation(async id=>({...row,id,comment:id==='one'?'first opinion':'second opinion',admin_note:''}));
  let finish;
  updateAdminFeedback.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
  render(<AdminFeedback/>);
  fireEvent.click(await screen.findByRole('button',{name:/button issue/}));
  await screen.findByText('first opinion');
  expect(screen.getByRole('button',{name:/button issue/})).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'처리 내용 저장'}));
  fireEvent.click(screen.getByRole('button',{name:/second feedback/}));
  await screen.findByText('second opinion');
  const {act}=require('@testing-library/react');
  await act(async()=>finish({...row,comment:'late first opinion',admin_note:'',version:2}));
  expect(screen.getByText('second opinion')).toBeVisible();
  expect(screen.queryByText('late first opinion')).not.toBeInTheDocument();
});


test('assigns and unassigns with server identities and renders history as plain text',async()=>{
  getAdminFeedback.mockResolvedValue({items:[row],has_more:false});
  getAdminFeedbackDetail.mockResolvedValue({...row,comment:'fixture',admin_note:'',assignee_id:null});
  updateAdminFeedback.mockResolvedValue({...row,comment:'fixture',admin_note:'',assignee_id:'admin',version:2});
  getAdminFeedbackHistory.mockResolvedValue({items:[{id:'event',version:2,actor_email:'admin@example.invalid',before_status:'received',after_status:'resolved',before_note:'',after_note:'<b>plain</b>',before_assignee_id:null,after_assignee_id:'admin',after_assignee_email:'admin@example.invalid',created_at:row.created_at}],has_more:false});
  render(<AdminFeedback/>);
  fireEvent.click(await screen.findByRole('button',{name:/button issue/}));
  const select=await screen.findByLabelText('담당자');
  await screen.findByRole('option',{name:'admin@example.invalid'});
  fireEvent.change(select,{target:{value:'admin'}});
  fireEvent.click(screen.getByRole('button',{name:'처리 내용 저장'}));
  await screen.findByText('저장했습니다.');
  expect(updateAdminFeedback).toHaveBeenLastCalledWith('one',{version:1,status:'received',admin_note:'',assignee_id:'admin'});
  fireEvent.change(select,{target:{value:''}});
  fireEvent.click(screen.getByRole('button',{name:'처리 내용 저장'}));
  await waitFor(()=>expect(updateAdminFeedback).toHaveBeenLastCalledWith('one',{version:2,status:'received',admin_note:'',assignee_id:null}));
  fireEvent.click(screen.getByRole('button',{name:'변경 이력 보기'}));
  await screen.findByText('<b>plain</b>');
  expect(screen.getByText('<b>plain</b>').querySelector('b')).toBeNull();
});
