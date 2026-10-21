import '@testing-library/jest-dom';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import PromptControl from './PromptControl';
import {adminPromptRequest} from '../api/dietApi';
jest.mock('../api/dietApi',()=>({adminPromptRequest:jest.fn()}));
test('shows actual commits and disabled user A/B, refreshes without prompt bodies',async()=>{
 adminPromptRequest.mockResolvedValue({prompt_release:'v1',prompt_source:'signed',prompt_commit_ids:{'team.base':'abcdef'},remote_enabled:true,ab_enabled:false});
 render(<PromptControl/>);
 expect(await screen.findByText('v1')).toBeInTheDocument();
 expect(screen.getByText(/실제 사용자 A\/B: 중지/)).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'검증된 릴리스 다시 가져오기'}));
 await waitFor(()=>expect(adminPromptRequest).toHaveBeenLastCalledWith(true));
 expect(screen.getByText('abcdef')).toBeInTheDocument();
});
test('nonadministrator does not see release controls',async()=>{
 adminPromptRequest.mockResolvedValue(null);const {container}=render(<PromptControl/>);
 await waitFor(()=>expect(container).toBeEmptyDOMElement());
});
