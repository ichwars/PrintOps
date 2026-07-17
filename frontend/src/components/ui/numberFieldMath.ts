export type NumberStepDirection = 1 | -1;

export type StepNumberValueOptions = {
  value: string | number | undefined;
  direction: NumberStepDirection;
  min?: string | number;
  max?: string | number;
  step?: string | number;
};

export type NumberStepBoundaryOptions = StepNumberValueOptions;

function finiteNumber(value: string | number | undefined): number | undefined {
  if (value === '' || value === undefined) return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function precisionOf(value: string | number | undefined): number {
  if (value === undefined || value === '' || value === 'any') return 0;
  const text = String(value).toLowerCase();
  if (text.includes('e-')) return Number(text.split('e-')[1]) || 0;
  return text.includes('.') ? text.split('.')[1].length : 0;
}

export function stepNumberValue({
  value,
  direction,
  min,
  max,
  step,
}: StepNumberValueOptions): string {
  const parsed = finiteNumber(value);
  const minimum = finiteNumber(min);
  const maximum = finiteNumber(max);
  const parsedStep = step === 'any' ? 1 : finiteNumber(step);
  const amount = parsedStep !== undefined && parsedStep > 0 ? parsedStep : 1;

  if (parsed === undefined && direction === 1 && minimum !== undefined) {
    return String(minimum);
  }
  if (parsed === undefined && direction === -1 && maximum !== undefined) {
    return String(maximum);
  }

  const baseline = parsed ?? 0;
  const precision = Math.max(precisionOf(step), precisionOf(value));
  const factor = 10 ** precision;
  let next =
    (Math.round(baseline * factor) + direction * Math.round(amount * factor)) / factor;
  if (minimum !== undefined) next = Math.max(next, minimum);
  if (maximum !== undefined) next = Math.min(next, maximum);
  return String(next);
}

export function isNumberStepBoundary(options: NumberStepBoundaryOptions): boolean {
  const current = finiteNumber(options.value);
  if (current === undefined) return false;
  const boundary = finiteNumber(options.direction === 1 ? options.max : options.min);
  if (boundary === undefined) return false;
  return options.direction === 1 ? current >= boundary : current <= boundary;
}
