import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import AnswerContent from './AnswerContent';

test('completed answer renders headings and emphasis without raw HTML or images', () => {
  const { container } = render(<AnswerContent content={'### 점심 추천\n\n**밥**과 채소\n\n<img src="https://example.com/private"/>\n\n![tracking](https://example.com/pixel)\n\n[위험](javascript:alert(1))'} />);
  expect(screen.getByRole('heading', { name: '점심 추천' })).toBeInTheDocument();
  expect(container.querySelector('strong')).toHaveTextContent('밥');
  expect(container.querySelector('img')).toBeNull();
  expect(container.innerHTML).not.toContain('javascript:');
});

test('unfinished answer is plain text until completion', () => {
  const { container } = render(<AnswerContent content={'**아직 미완성'} streaming />);
  expect(container).toHaveTextContent('**아직 미완성');
  expect(container.querySelector('strong')).toBeNull();
});
