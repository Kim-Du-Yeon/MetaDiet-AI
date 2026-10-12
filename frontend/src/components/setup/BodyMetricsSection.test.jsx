import { fireEvent, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import BodyMetricsSection from './BodyMetricsSection';

test('groups required body measurements and reports field changes', () => {
  const onChange = jest.fn();
  render(
    <BodyMetricsSection
      values={{ age: '', height_cm: '', weight_kg: '' }}
      onChange={onChange}
    />
  );

  expect(screen.getByText('필수')).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('키'), { target: { value: '181' } });
  expect(onChange).toHaveBeenCalledWith('height_cm', '181');
});
