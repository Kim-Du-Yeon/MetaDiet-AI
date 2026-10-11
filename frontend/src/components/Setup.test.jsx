import { render,screen,fireEvent,waitFor } from '@testing-library/react';
import Setup from './Setup';
import { decideProposal } from '../api/dietApi';
jest.mock('../api/dietApi',()=>({BASE_URL:'http://test',getToken:()=> 'token',
  decideProposal:jest.fn(async()=>({status:'confirmed'}))}));

test('initial strategy requires explicit confirmation before completion',async()=>{
  decideProposal.mockResolvedValue({status:'confirmed'});
  const done=jest.fn();
  global.fetch=jest.fn(async(url,options)=>({ok:true,json:async()=>options?.method==='POST'?({pending_proposal:{id:'p',version:1,kind:'strategy',status:'pending',payload:{daily_calories:2400,protein_g:120,carbs_g:330,fat_g:66.67,strategy_note:'유지 기준선',effective_date:'2026-10-10',evidence:[]}}}):{}}));
  render(<Setup onComplete={done}/>);
  await waitFor(()=>expect(screen.getByRole('button',{name:/전략/}).disabled).toBe(false));
  for(const [name,value] of [['나이','30'],['키','170'],['체중','70']])
    fireEvent.change(screen.getByLabelText(name),{target:{value}});
  fireEvent.change(screen.getByLabelText('활동 수준'),{target:{value:'low_active'}});
  fireEvent.click(screen.getByLabelText(/일반 성인 적용/));
  fireEvent.click(screen.getByRole('button',{name:/전략/}));
  await screen.findByRole('heading',{name:'초기 전략 제안'});
  expect(done).not.toHaveBeenCalled();
  expect(global.fetch.mock.calls[0][0]).toContain('/users/onboarding');
  fireEvent.click(screen.getByRole('button',{name:'이 내용 확정'}));
  await waitFor(()=>expect(done).toHaveBeenCalledTimes(1));
});

test('existing strategy skips onboarding after a returning user reconnects',async()=>{
  const done=jest.fn();
  global.fetch=jest.fn(async()=>({ok:true,json:async()=>({current_strategy:{daily_calories:1800,protein_g:90,carbs_g:250,fat_g:49,strategy_note:'기존 전략'}})}));
  render(<Setup onComplete={done}/>);
  await waitFor(()=>expect(done).toHaveBeenCalledTimes(1));
  expect(screen.queryByRole('button',{name:/시작하기/})).toBeNull();
});
