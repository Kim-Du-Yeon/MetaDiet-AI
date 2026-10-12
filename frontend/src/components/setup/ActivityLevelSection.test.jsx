import { fireEvent, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import ActivityLevelSection from './ActivityLevelSection';

test('selects an activity level from descriptive cards', () => {
  const onActivityChange = jest.fn();

  render(
    <ActivityLevelSection
      value=""
      confirmed={false}
      onActivityChange={onActivityChange}
      onConfirmationChange={jest.fn()}
    />
  );

  fireEvent.click(screen.getByRole('radio', { name: /저활동적/ }));

  expect(onActivityChange).toHaveBeenCalledWith('low_active');
  expect(screen.getByText('평소 하루 활동량과 가장 가까운 항목을 골라주세요.')).toBeInTheDocument();
  expect(screen.getByText(/운동뿐 아니라 출퇴근, 업무, 집안일까지 포함/)).toBeInTheDocument();
});

test('shows the selected state and changes the general adult confirmation', () => {
  const onConfirmationChange = jest.fn();

  render(
    <ActivityLevelSection
      value="active"
      confirmed={false}
      onActivityChange={jest.fn()}
      onConfirmationChange={onConfirmationChange}
    />
  );

  expect(screen.getByRole('radio', { name: /^활동적/ })).toBeChecked();
  fireEvent.click(screen.getByRole('checkbox', { name: /일반 성인 기준 적용/ }));
  expect(onConfirmationChange).toHaveBeenCalledWith(true);
});
