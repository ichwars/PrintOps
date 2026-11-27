import { describe, expect, it } from 'vitest';
import { toastDuration } from '../../utils/toastDuration';

describe('toastDuration', () => {
  it('keeps brief informational confirmations at 3 seconds', () => {
    expect(toastDuration('Saved', 'info')).toBe(3000);
  });

  it('scales longer informational messages with reading time, capped at 10 seconds', () => {
    expect(toastDuration('x'.repeat(120), 'info')).toBe(7200);
    expect(toastDuration('x'.repeat(200), 'info')).toBe(10000);
  });

  it('keeps errors and warnings on their slower scale', () => {
    expect(toastDuration('Boom', 'error')).toBe(10000);
    expect(toastDuration('x'.repeat(600), 'warning')).toBe(30000);
  });
});
