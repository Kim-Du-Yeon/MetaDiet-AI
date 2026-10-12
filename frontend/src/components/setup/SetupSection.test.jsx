import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import SetupSection from './SetupSection';

test('visually identifies required and optional setup groups', () => {
  const { rerender } = render(
    <SetupSection title="신체 정보" required>
      <p>내용</p>
    </SetupSection>
  );

  expect(screen.getByRole('heading', { name: '신체 정보' })).toBeInTheDocument();
  expect(screen.getByText('필수')).toBeInTheDocument();

  rerender(
    <SetupSection title="장기 목표" optional>
      <p>내용</p>
    </SetupSection>
  );
  expect(screen.getByText('선택')).toBeInTheDocument();
});
