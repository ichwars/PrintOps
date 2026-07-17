import { describe, expect, it } from 'vitest';

import {
  isNumberStepBoundary,
  stepNumberValue,
} from '../../../components/ui/numberFieldMath';

describe('numberFieldMath', () => {
  it('steps by one and clamps to numeric boundaries', () => {
    expect(stepNumberValue({ value: '2', direction: 1 })).toBe('3');
    expect(stepNumberValue({ value: '5', direction: 1, max: 5 })).toBe('5');
    expect(stepNumberValue({ value: '0', direction: -1, min: 0 })).toBe('0');
  });

  it('normalizes decimal steps', () => {
    expect(stepNumberValue({ value: '0.2', direction: 1, step: 0.1 })).toBe('0.3');
    expect(stepNumberValue({ value: '1.00', direction: -1, step: '0.05' })).toBe('0.95');
  });

  it('uses the documented empty-value baselines', () => {
    expect(stepNumberValue({ value: '', direction: 1, min: 10 })).toBe('10');
    expect(stepNumberValue({ value: '', direction: 1 })).toBe('1');
    expect(stepNumberValue({ value: '', direction: -1, max: 10 })).toBe('10');
    expect(stepNumberValue({ value: '', direction: -1 })).toBe('-1');
  });

  it('treats step any as the default button step', () => {
    expect(stepNumberValue({ value: '4', direction: 1, step: 'any' })).toBe('5');
  });

  it('reports whether a step direction is at a boundary', () => {
    expect(isNumberStepBoundary({ value: '5', direction: 1, max: 5 })).toBe(true);
    expect(isNumberStepBoundary({ value: '6', direction: 1, max: 5 })).toBe(true);
    expect(isNumberStepBoundary({ value: '', direction: 1, max: 5 })).toBe(false);
    expect(isNumberStepBoundary({ value: '1', direction: -1, min: 0 })).toBe(false);
    expect(isNumberStepBoundary({ value: '-1', direction: -1, min: 0 })).toBe(true);
  });
});
