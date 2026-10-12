import { fireEvent, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import ProductChoiceCards from './ProductChoiceCards';

test('chooses a product without displaying IDs and preserves the whole original meal', () => {
  const onSelect = jest.fn();
  render(<ProductChoiceCards selection={{ request: '오늘 쌀밥 450g과 라이스페이퍼 80g 기록만 해줘', items: [
    { query: '라이스페이퍼', quantity_g: 80, candidates: [
      { food_id: 'mfds:P1', name: '라이스 페이퍼', manufacturer: '회사', package_text: '300g', basis_g: 100 }
    ] }
  ] }} onSelect={onSelect} />);
  expect(screen.queryByText(/mfds:P1/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('radio', { name: /라이스 페이퍼/ }));
  fireEvent.click(screen.getByRole('button', { name: '선택한 제품으로 다시 검토' }));
  expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({
    request: expect.stringContaining('오늘 쌀밥 450g과 라이스페이퍼 80g 기록만 해줘'),
    display: '라이스 페이퍼 80g 제품을 선택했어요.'
  }));
  expect(onSelect.mock.calls[0][0].request).toContain('제품 선택: mfds:P1');
});
