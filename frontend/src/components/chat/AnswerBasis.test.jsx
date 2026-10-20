import {render, screen, fireEvent} from '@testing-library/react';
import '@testing-library/jest-dom';
import AnswerBasis from './AnswerBasis';

test('shows record snapshot and only explicit citations, blocking unsafe URLs', () => {
  render(<AnswerBasis basis={{records:{date:'2026-10-19',meals:[{food_name:'밥',quantity_g:200,meal_type:'lunch'}],
    totals:{calories:300,protein_g:5,carbs_g:60,fat_g:1}},targets:{protein_g:100},
    documents:[{source:'지침',page:'3',source_url:'javascript:alert(1)',excerpt:'근거 문장'}],notice:'조회 당시 기록'}}/>);
  fireEvent.click(screen.getByRole('button', {name:'내 기록·계산 근거 보기'}));
  expect(screen.getByText('점심 · 밥 200g')).toBeVisible();
  expect(screen.getByText('100 g')).toBeVisible();
  expect(screen.queryByRole('link')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', {name:'출처 보기 · 1개'}));
  fireEvent.click(screen.getByText('인용 내용 보기'));
  expect(screen.getByText('근거 문장')).toBeVisible();
});

test('missing provenance does not invent sources', () => {
  const {container} = render(<AnswerBasis />);
  expect(container).toBeEmptyDOMElement();
});


test('source list is collapsed, numbered, and links to the original safely', () => {
  render(<AnswerBasis basis={{documents:[{source:'공식 지침',page:'12',source_url:'https://example.org/guide',excerpt:'관련 내용'}]}} />);
  const sources = screen.getByRole('button', {name:'출처 보기 · 1개'});
  expect(sources).toHaveAttribute('aria-expanded', 'false');
  expect(screen.queryByRole('link', {name:'원문 보기 ↗'})).not.toBeInTheDocument();
  fireEvent.click(sources);
  expect(sources).toHaveAttribute('aria-expanded', 'true');
  expect(screen.getByText('[근거 1] 공식 지침')).toBeVisible();
  expect(screen.getByRole('link', {name:'원문 보기 ↗'})).toHaveAttribute('rel', 'noopener noreferrer');
  expect(screen.getByText('관련 내용')).not.toBeVisible();
  fireEvent.click(screen.getByText('인용 내용 보기'));
  expect(screen.getByText('관련 내용')).toBeVisible();
  fireEvent.click(sources);
  expect(screen.getByText('관련 내용')).not.toBeVisible();
});

test('zero sources explains absence rather than fabricating a citation', () => {
  render(<AnswerBasis basis={{documents:[],limitation:'이번 답변에서는 문서 검색을 수행하지 않았어요.'}} />);
  expect(screen.getByText(/이번 답변에서는 문서 검색을 수행하지 않았어요/)).toBeVisible();
  expect(screen.queryByRole('button',{name:'출처 보기 · 0개'})).not.toBeInTheDocument();
  expect(screen.queryByRole('link')).not.toBeInTheDocument();
});

test.each([
  ['not_searched','문서 검색 안 함'],
  ['insufficient_evidence','관련 근거 미확보'],
  ['search_unavailable','근거 검색 오류'],
  ['retrieved_not_cited','검색 완료 · 인용 없음'],
])('shows %s without opening a panel', (status,label) => {
  render(<AnswerBasis basis={{documents:[],search:{status},limitation:'상태 상세 안내'}} />);
  expect(screen.getByText(label)).toBeVisible();
  expect(screen.getByText('상태 상세 안내')).toBeVisible();
  expect(screen.queryByRole('button',{name:/출처 보기/})).not.toBeInTheDocument();
});
