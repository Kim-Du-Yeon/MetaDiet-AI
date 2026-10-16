import { reportRequestTiming } from './requestTiming';

test('emits only finite measured durations and correlation metadata', () => {
  const listener = jest.fn();
  const log = jest.spyOn(console, 'info').mockImplementation(() => {});
  window.addEventListener('metadiet:request-timing', listener);
  reportRequestTiming({requestId:'request', attemptId:'attempt'},'response_headers',performance.now());
  const row = listener.mock.calls[0][0].detail;
  expect(row.request_id).toBe('request');
  expect(row.elapsed_ms).toBeGreaterThanOrEqual(0);
  expect(Object.keys(row).sort()).toEqual(['attempt_id','elapsed_ms','request_id','stage','visibility']);
  window.removeEventListener('metadiet:request-timing', listener);
  log.mockRestore();
});
