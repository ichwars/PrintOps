# Unified NumberField Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a PrintOps-owned numeric input with integrated vertical steppers and migrate every rendered numeric field without changing domain values, payloads, validation, or save behavior.

**Architecture:** A pure `numberFieldMath` module computes clamped, precision-safe step results. `NumberField` composes that behavior with the existing `FormField` and `TextField` visual conventions, keeps a real `input[type="number"]`, and emits the same raw-string callbacks consumers already use. Migration is divided by product area and guarded by source-audit tests plus existing integration tests.

**Tech Stack:** React 19, TypeScript 5.9, Tailwind CSS 4, lucide-react, react-i18next, Vitest 4, Testing Library, Vite 8.

## Global Constraints

- Use Variant A: a 34-pixel desktop segment with integrated vertical increment and decrement buttons.
- Keep the editable control as `input[type="number"]`; hide native WebKit and Firefox spinners only inside `NumberField`.
- Preserve existing values, callbacks, validation constraints, API payloads, defaults, and save timing.
- Direct typing emits the raw input string; no domain conversion occurs inside the primitive.
- Support `min`, `max`, decimal `step`, `step="any"`, empty values, disabled, read-only, helper text, and errors.
- Default stepping is `1`; clamp to supplied bounds and normalize decimal results to step precision.
- Empty increment starts at `min` when present, otherwise `0`; empty decrement starts at `max` when present, otherwise applies one decrement from `0`.
- Step buttons are `type="button"`, have translated accessible labels, and return focus to the input.
- Do not migrate range, color, file, chart-library `type="number"` props, or non-rendered field metadata.
- Do not add a dependency, formatted currency input, locale grouping, or press-and-hold acceleration.

## File Structure

- `frontend/src/components/ui/numberFieldMath.ts`: pure parsing, stepping, clamping, and decimal normalization.
- `frontend/src/components/ui/NumberField.tsx`: field markup, callbacks, refs, steppers, accessibility, and component-scoped spinner suppression.
- `frontend/src/components/ui/index.ts`: public component and prop exports.
- `frontend/src/i18n/locales/en.ts`, `frontend/src/i18n/locales/de.ts`: default stepper labels.
- `frontend/src/__tests__/components/ui/numberFieldMath.test.ts`: pure numeric behavior.
- `frontend/src/__tests__/components/ui/NumberField.test.tsx`: rendered interaction and accessibility contract.
- `frontend/src/__tests__/components/ui/NumberFieldMigration.test.ts`: source-level guard proving product surfaces no longer render native numeric fields directly.
- Existing page and component files retain domain conversion and persistence logic; only the rendered field primitive changes.

---

### Task 1: Precision-Safe Number Stepping

**Files:**
- Create: `frontend/src/components/ui/numberFieldMath.ts`
- Test: `frontend/src/__tests__/components/ui/numberFieldMath.test.ts`

**Interfaces:**
- Consumes: numeric strings or numbers from `NumberField` props.
- Produces: `stepNumberValue(options: StepNumberValueOptions): string` and `isNumberStepBoundary(options: NumberStepBoundaryOptions): boolean`.

- [ ] **Step 1: Write the failing math tests**

```ts
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
    expect(isNumberStepBoundary({ value: '', direction: 1, max: 5 })).toBe(false);
    expect(isNumberStepBoundary({ value: '1', direction: -1, min: 0 })).toBe(false);
  });
});
```

- [ ] **Step 2: Run the focused test and verify the red state**

Run from `frontend`:

```powershell
npm.cmd run test -- --run src/__tests__/components/ui/numberFieldMath.test.ts
```

Expected: FAIL because `components/ui/numberFieldMath` does not exist.

- [ ] **Step 3: Implement the pure stepping functions**

```ts
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

  if (parsed === undefined && direction === 1 && minimum !== undefined) return String(minimum);
  if (parsed === undefined && direction === -1 && maximum !== undefined) return String(maximum);

  const baseline = parsed ?? 0;
  const precision = Math.max(precisionOf(step), precisionOf(value));
  const factor = 10 ** precision;
  let next = (Math.round(baseline * factor) + direction * Math.round(amount * factor)) / factor;
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
```

- [ ] **Step 4: Run the focused test and verify the green state**

Run: `npm.cmd run test -- --run src/__tests__/components/ui/numberFieldMath.test.ts`

Expected: 5 tests PASS.

- [ ] **Step 5: Commit the numeric core**

```powershell
git add frontend/src/components/ui/numberFieldMath.ts frontend/src/__tests__/components/ui/numberFieldMath.test.ts
git commit -m "feat(ui): add numeric step behavior"
```

---

### Task 2: Shared NumberField Primitive

**Files:**
- Create: `frontend/src/components/ui/NumberField.tsx`
- Modify: `frontend/src/components/ui/index.ts`
- Modify: `frontend/src/i18n/locales/en.ts`
- Modify: `frontend/src/i18n/locales/de.ts`
- Test: `frontend/src/__tests__/components/ui/NumberField.test.tsx`

**Interfaces:**
- Consumes: `stepNumberValue`, `isNumberStepBoundary`, `FormField`, `controlClass`, and standard numeric input props.
- Produces: `NumberField`, `NumberFieldProps`, raw `onValueChange(value: string)`, and compatible `onChange(event)` behavior.

- [ ] **Step 1: Write failing component tests**

Create tests covering the public contract:

```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { NumberField } from '../../../components/ui';

describe('NumberField', () => {
  it('links field copy and emits raw typed values through both callbacks', async () => {
    const onValueChange = vi.fn();
    const onChange = vi.fn();
    function ControlledField() {
      const [value, setValue] = useState('');
      return <NumberField label="Timeout" helperText="Seconds" error="Required" value={value} onValueChange={(next) => { setValue(next); onValueChange(next); }} onChange={onChange} />;
    }
    render(<ControlledField />);
    const input = screen.getByRole('spinbutton', { name: 'Timeout' });
    expect(input).toHaveAttribute('aria-invalid', 'true');
    await userEvent.setup().type(input, '2.5');
    expect(onValueChange).toHaveBeenLastCalledWith('2.5');
    expect(onChange).toHaveBeenCalled();
  });

  it('increments, decrements, clamps, and retains input focus', async () => {
    const onValueChange = vi.fn();
    const changedValues: string[] = [];
    const user = userEvent.setup();
    const { rerender } = render(<NumberField aria-label="Rate" value="0.2" step="0.1" max="0.3" onValueChange={onValueChange} onChange={(event) => changedValues.push(event.target.value)} />);
    const input = screen.getByRole('spinbutton', { name: 'Rate' });
    expect(input).toHaveAttribute('type', 'number');
    await user.click(screen.getByRole('button', { name: 'Increase value' }));
    expect(onValueChange).toHaveBeenLastCalledWith('0.3');
    expect(onValueChange).toHaveBeenCalledTimes(1);
    expect(changedValues).toEqual(['0.3']);
    expect(input).toHaveFocus();
    rerender(<NumberField aria-label="Rate" value="0.3" step="0.1" max="0.3" onValueChange={onValueChange} />);
    expect(screen.getByRole('button', { name: 'Increase value' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Decrease value' }));
    expect(onValueChange).toHaveBeenLastCalledWith('0.2');
  });

  it('never submits a surrounding form from either step button', async () => {
    const onSubmit = vi.fn((event: React.FormEvent) => event.preventDefault());
    render(<form onSubmit={onSubmit}><NumberField aria-label="Copies" value="1" onValueChange={() => {}} /></form>);
    await userEvent.setup().click(screen.getByRole('button', { name: 'Increase value' }));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('disables both controls for disabled and read-only fields', () => {
    const { rerender } = render(<NumberField aria-label="Copies" value="1" disabled />);
    expect(screen.getByRole('spinbutton', { name: 'Copies' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Increase value' })).toBeDisabled();
    rerender(<NumberField aria-label="Copies" value="1" readOnly />);
    expect(screen.getByRole('button', { name: 'Decrease value' })).toBeDisabled();
  });

  it('does not emit a value on mount and supports custom button labels', () => {
    const onValueChange = vi.fn();
    render(<NumberField aria-label="Copies" value="1" incrementLabel="More copies" decrementLabel="Fewer copies" onValueChange={onValueChange} />);
    expect(screen.getByRole('button', { name: 'More copies' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fewer copies' })).toBeInTheDocument();
    expect(onValueChange).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run the component test and verify the red state**

Run: `npm.cmd run test -- --run src/__tests__/components/ui/NumberField.test.tsx`

Expected: FAIL because `NumberField` is not exported.

- [ ] **Step 3: Add translated defaults and the public exports**

Add to both `common` locale objects:

```ts
// en.ts
increaseValue: 'Increase value',
decreaseValue: 'Decrease value',

// de.ts
increaseValue: 'Wert erhöhen',
decreaseValue: 'Wert verringern',
```

Add to `frontend/src/components/ui/index.ts`:

```ts
export { NumberField } from './NumberField';
export type { NumberFieldProps } from './NumberField';
```

- [ ] **Step 4: Implement the shared component**

Implement `NumberField.tsx` with this structure and callback contract:

```tsx
import { ChevronDown, ChevronUp } from 'lucide-react';
import {
  forwardRef,
  useImperativeHandle,
  useRef,
  type ChangeEventHandler,
  type InputHTMLAttributes,
  type ReactNode,
} from 'react';
import { useTranslation } from 'react-i18next';

import { FormField } from './FormField';
import { controlClass } from './TextField';
import { isNumberStepBoundary, stepNumberValue, type NumberStepDirection } from './numberFieldMath';

export type NumberFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'type' | 'value' | 'onChange' | 'size'> & {
  value?: string | number;
  onValueChange?: (value: string) => void;
  onChange?: ChangeEventHandler<HTMLInputElement>;
  label?: ReactNode;
  helperText?: ReactNode;
  error?: ReactNode;
  incrementLabel?: string;
  decrementLabel?: string;
};

export const NumberField = forwardRef<HTMLInputElement, NumberFieldProps>(function NumberField(
  { id, label, helperText, error, required, className = '', value, onValueChange, onChange, incrementLabel, decrementLabel, min, max, step, disabled, readOnly, ...props },
  forwardedRef,
) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  useImperativeHandle(forwardedRef, () => inputRef.current as HTMLInputElement);

  const emitStep = (direction: NumberStepDirection) => {
    const input = inputRef.current;
    if (!input || disabled || readOnly) return;
    const next = stepNumberValue({ value, direction, min, max, step });
    const prototypeSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
    prototypeSetter?.call(input, next);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.focus();
  };

  return (
    <FormField id={id} label={label} helperText={helperText} error={error} required={required}>
      {({ controlId, describedBy, invalid }) => (
        <div className="relative">
          <input
            {...props}
            ref={inputRef}
            id={controlId}
            type="number"
            value={value ?? ''}
            min={min}
            max={max}
            step={step}
            required={required}
            disabled={disabled}
            readOnly={readOnly}
            aria-describedby={describedBy}
            aria-invalid={invalid || undefined}
            className={`${controlClass} [appearance:textfield] pr-11 max-[768px]:pr-12 [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none ${className}`}
            onChange={(event) => {
              onValueChange?.(event.target.value);
              onChange?.(event);
            }}
          />
          <div className="absolute inset-y-px right-px grid w-[34px] grid-rows-2 overflow-hidden rounded-r-[7px] border-l border-bambu-dark-tertiary max-[768px]:w-10">
            <button type="button" aria-label={incrementLabel ?? t('common.increaseValue')} disabled={disabled || readOnly || isNumberStepBoundary({ value, direction: 1, min, max, step })} className="grid place-items-center border-b border-bambu-dark-tertiary text-bambu-gray hover:bg-bambu-green/15 hover:text-white disabled:cursor-not-allowed disabled:opacity-40" onMouseDown={(event) => event.preventDefault()} onClick={() => emitStep(1)}><ChevronUp aria-hidden="true" className="h-3 w-3" /></button>
            <button type="button" aria-label={decrementLabel ?? t('common.decreaseValue')} disabled={disabled || readOnly || isNumberStepBoundary({ value, direction: -1, min, max, step })} className="grid place-items-center text-bambu-gray hover:bg-bambu-green/15 hover:text-white disabled:cursor-not-allowed disabled:opacity-40" onMouseDown={(event) => event.preventDefault()} onClick={() => emitStep(-1)}><ChevronDown aria-hidden="true" className="h-3 w-3" /></button>
          </div>
        </div>
      )}
    </FormField>
  );
});
```

- [ ] **Step 5: Run component, math, and i18n checks**

Run:

```powershell
npm.cmd run test -- --run src/__tests__/components/ui/NumberField.test.tsx src/__tests__/components/ui/numberFieldMath.test.ts
npm.cmd run check:i18n
```

Expected: all focused tests PASS and i18n parity exits successfully.

- [ ] **Step 6: Commit the primitive**

```powershell
git add frontend/src/components/ui/NumberField.tsx frontend/src/components/ui/index.ts frontend/src/i18n/locales/en.ts frontend/src/i18n/locales/de.ts frontend/src/__tests__/components/ui/NumberField.test.tsx
git commit -m "feat(ui): add unified number field"
```

---

### Task 3: Settings and Administration Migration

**Files:**
- Create: `frontend/src/__tests__/components/ui/NumberFieldMigration.test.ts`
- Modify: `frontend/src/pages/CameraTokensPage.tsx`
- Modify: `frontend/src/pages/LibraryTrashPage.tsx`
- Modify: `frontend/src/pages/SettingsPage.tsx`
- Modify: `frontend/src/components/AddNotificationModal.tsx`
- Modify: `frontend/src/components/AddSmartPlugModal.tsx`
- Modify: `frontend/src/components/EmailSettings.tsx`
- Modify: `frontend/src/components/FailureDetectionSettings.tsx`
- Modify: `frontend/src/components/GitHubBackupSettings.tsx`
- Modify: `frontend/src/components/SmartPlugCard.tsx`
- Modify: `frontend/src/components/settings/BusinessProfileEditorModal.tsx`
- Modify: `frontend/src/components/settings/DeviceManagement.tsx`
- Test: `frontend/src/__tests__/components/AddNotificationModal.test.tsx`
- Test: `frontend/src/__tests__/components/DeviceManagement.test.tsx`
- Test: `frontend/src/__tests__/components/SmartPlugCard.test.tsx`
- Test: `frontend/src/__tests__/pages/CameraTokensPage.test.tsx`
- Test: `frontend/src/__tests__/pages/SettingsPage.test.tsx`

**Interfaces:**
- Consumes: `NumberField` and its raw string callbacks.
- Produces: settings and device surfaces with no direct rendered numeric input.

- [ ] **Step 1: Add a failing source contract for this file group**

```ts
import fs from 'node:fs';
import path from 'node:path';
import * as ts from 'typescript';
import { describe, expect, it } from 'vitest';

const groups = {
  settings: [
    'pages/CameraTokensPage.tsx', 'pages/LibraryTrashPage.tsx', 'pages/SettingsPage.tsx',
    'components/AddNotificationModal.tsx', 'components/AddSmartPlugModal.tsx',
    'components/EmailSettings.tsx', 'components/FailureDetectionSettings.tsx',
    'components/GitHubBackupSettings.tsx', 'components/SmartPlugCard.tsx',
    'components/settings/BusinessProfileEditorModal.tsx', 'components/settings/DeviceManagement.tsx',
  ],
};

const sourceRoot = path.resolve(process.cwd(), 'src');

function directNumericFields(file: string, source: string): string[] {
  const sourceFile = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const matches: string[] = [];

  function visit(node: ts.Node): void {
    if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
      const tagName = node.tagName.getText(sourceFile);
      if (tagName === 'input' || tagName === 'TextField') {
        const typeAttribute = node.attributes.properties.find(
          (property): property is ts.JsxAttribute => ts.isJsxAttribute(property) && property.name.getText(sourceFile) === 'type',
        );
        if (typeAttribute?.initializer && ts.isStringLiteral(typeAttribute.initializer) && typeAttribute.initializer.text === 'number') {
          const { line } = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
          matches.push(`${file}:${line + 1}`);
        }
      }
    }
    ts.forEachChild(node, visit);
  }

  visit(sourceFile);
  return matches;
}

describe('NumberField migration', () => {
  it.each(Object.entries(groups))('%s uses NumberField for rendered numeric inputs', (_group, files) => {
    for (const file of files) {
      const source = fs.readFileSync(path.join(sourceRoot, file), 'utf8');
      expect(directNumericFields(file, source), file).toEqual([]);
    }
  });
});
```

Also assert the two dynamic renderers choose `NumberField` when metadata says `number`:

```ts
expect(fs.readFileSync(path.join(sourceRoot, 'components/AddNotificationModal.tsx'), 'utf8'))
  .toMatch(/field\.type === 'number'[\s\S]*?<NumberField/);
```

Run: `npm.cmd run test -- --run src/__tests__/components/ui/NumberFieldMigration.test.ts`

Expected: FAIL and name the unmigrated settings files.

- [ ] **Step 2: Replace each rendered numeric field while retaining domain callbacks**

For every listed file, import `NumberField`, replace `TextField type="number"` or `input type="number"` with `NumberField`, remove the `type` prop, and leave `value`, `min`, `max`, `step`, labels, classes, and callback bodies unchanged:

```tsx
// Before
<TextField type="number" min={0} value={draft.watts} onValueChange={(value) => setDraft({ ...draft, watts: Number(value) })} />

// After
<NumberField min={0} value={draft.watts} onValueChange={(value) => setDraft({ ...draft, watts: Number(value) })} />
```

For `AddNotificationModal`, preserve nonnumeric provider fields with an explicit branch:

```tsx
field.type === 'number' ? (
  <NumberField
    value={config[field.key] || ''}
    onValueChange={(value) => {
      setConfig({ ...config, [field.key]: value });
      setTestResult(null);
    }}
    placeholder={field.placeholder}
    className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white focus:border-bambu-green focus:outline-none"
  />
) : (
  <TextField
    type={field.type}
    value={config[field.key] || ''}
    onChange={(event) => {
      setConfig({ ...config, [field.key]: event.target.value });
      setTestResult(null);
    }}
    placeholder={field.placeholder}
    className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white focus:border-bambu-green focus:outline-none"
  />
)
```

- [ ] **Step 3: Run the migration contract and affected integration tests**

Run:

```powershell
npm.cmd run test -- --run src/__tests__/components/ui/NumberFieldMigration.test.ts src/__tests__/components/AddNotificationModal.test.tsx src/__tests__/components/DeviceManagement.test.tsx src/__tests__/components/SmartPlugCard.test.tsx src/__tests__/pages/CameraTokensPage.test.tsx src/__tests__/pages/SettingsPage.test.tsx
```

Expected: all listed suites PASS; payload and settings-save assertions remain unchanged.

- [ ] **Step 4: Commit the settings migration**

```powershell
git add frontend/src/pages/CameraTokensPage.tsx frontend/src/pages/LibraryTrashPage.tsx frontend/src/pages/SettingsPage.tsx frontend/src/components/AddNotificationModal.tsx frontend/src/components/AddSmartPlugModal.tsx frontend/src/components/EmailSettings.tsx frontend/src/components/FailureDetectionSettings.tsx frontend/src/components/GitHubBackupSettings.tsx frontend/src/components/SmartPlugCard.tsx frontend/src/components/settings/BusinessProfileEditorModal.tsx frontend/src/components/settings/DeviceManagement.tsx frontend/src/__tests__/components/ui/NumberFieldMigration.test.ts
git commit -m "refactor(settings): use unified number fields"
```

---

### Task 4: Printer, Project, and Print Workflow Migration

**Files:**
- Modify: `frontend/src/__tests__/components/ui/NumberFieldMigration.test.ts`
- Modify: `frontend/src/pages/MaintenancePage.tsx`
- Modify: `frontend/src/pages/PrintersPage.tsx`
- Modify: `frontend/src/pages/ProjectsPage.tsx`
- Modify: `frontend/src/pages/ProjectDetailPage.tsx`
- Modify: `frontend/src/pages/spoolbuddy/SpoolBuddyWriteTagPage.tsx`
- Modify: `frontend/src/components/PreheatFilamentTargetsEditor.tsx`
- Modify: `frontend/src/components/PrintModal/index.tsx`
- Modify: `frontend/src/components/PrintModal/PrintOptions.tsx`
- Modify: `frontend/src/components/PrintModal/ScheduleOptions.tsx`
- Modify: `frontend/src/components/RunWithPipelineModal.tsx`
- Test: `frontend/src/__tests__/components/PrintModal.test.tsx`
- Test: `frontend/src/__tests__/pages/MaintenancePage.test.tsx`
- Test: `frontend/src/__tests__/pages/PrintersPage.test.tsx`
- Test: `frontend/src/__tests__/pages/ProjectDetailPage.test.tsx`
- Test: `frontend/src/__tests__/pages/ProjectsPage.test.tsx`
- Test: `frontend/src/__tests__/pages/SpoolBuddyWriteTagPage.test.tsx`

**Interfaces:**
- Consumes: `NumberField` with standard input attributes.
- Produces: printer, project, scheduling, and print-option flows with unchanged numeric conversion.

- [ ] **Step 1: Extend the source contract and verify it fails**

Add this group to `groups`:

```ts
printerAndProjects: [
  'pages/MaintenancePage.tsx', 'pages/PrintersPage.tsx', 'pages/ProjectsPage.tsx',
  'pages/ProjectDetailPage.tsx', 'pages/spoolbuddy/SpoolBuddyWriteTagPage.tsx',
  'components/PreheatFilamentTargetsEditor.tsx', 'components/PrintModal/index.tsx',
  'components/PrintModal/PrintOptions.tsx', 'components/PrintModal/ScheduleOptions.tsx',
  'components/RunWithPipelineModal.tsx',
],
```

Run: `npm.cmd run test -- --run src/__tests__/components/ui/NumberFieldMigration.test.ts`

Expected: FAIL for the new group while the settings group stays green.

- [ ] **Step 2: Migrate the listed fields mechanically**

Import `NumberField`; replace only `<input type="number" ... />` and `<TextField type="number" ... />` with `<NumberField ... />`. Preserve conversions such as `Number(event.target.value)`, nullable-string handling, bounds, steps, disabled states, and existing CSS classes. Use `onValueChange` only when it removes event plumbing without changing the callback body:

```tsx
<NumberField
  min={0}
  step={0.1}
  value={targetTemperature}
  onValueChange={(value) => setTargetTemperature(Number(value))}
  className={existingClassName}
/>
```

- [ ] **Step 3: Run product-area tests**

Run:

```powershell
npm.cmd run test -- --run src/__tests__/components/ui/NumberFieldMigration.test.ts src/__tests__/components/PrintModal.test.tsx src/__tests__/pages/MaintenancePage.test.tsx src/__tests__/pages/PrintersPage.test.tsx src/__tests__/pages/ProjectDetailPage.test.tsx src/__tests__/pages/ProjectsPage.test.tsx src/__tests__/pages/SpoolBuddyWriteTagPage.test.tsx
```

Expected: all listed suites PASS.

- [ ] **Step 4: Commit the workflow migration**

```powershell
git add frontend/src/__tests__/components/ui/NumberFieldMigration.test.ts frontend/src/pages/MaintenancePage.tsx frontend/src/pages/PrintersPage.tsx frontend/src/pages/ProjectsPage.tsx frontend/src/pages/ProjectDetailPage.tsx frontend/src/pages/spoolbuddy/SpoolBuddyWriteTagPage.tsx frontend/src/components/PreheatFilamentTargetsEditor.tsx frontend/src/components/PrintModal/index.tsx frontend/src/components/PrintModal/PrintOptions.tsx frontend/src/components/PrintModal/ScheduleOptions.tsx frontend/src/components/RunWithPipelineModal.tsx
git commit -m "refactor(printing): use unified number fields"
```

---

### Task 5: Inventory, Catalog, and History Migration

**Files:**
- Modify: `frontend/src/__tests__/components/ui/NumberFieldMigration.test.ts`
- Modify: `frontend/src/components/AMSHistoryModal.tsx`
- Modify: `frontend/src/components/BulkEditSpoolsModal.tsx`
- Modify: `frontend/src/components/CameraWall.tsx`
- Modify: `frontend/src/components/EditArchiveModal.tsx`
- Modify: `frontend/src/components/ForecastPanel.tsx`
- Modify: `frontend/src/components/HeaterHistoryModal.tsx`
- Modify: `frontend/src/components/PurgeArchivesModal.tsx`
- Modify: `frontend/src/components/PurgeOldFilesModal.tsx`
- Modify: `frontend/src/components/SpoolCatalogSettings.tsx`
- Modify: `frontend/src/components/spool-form/AdditionalSection.tsx`
- Modify: `frontend/src/components/spool-form/FilamentSection.tsx`
- Test: `frontend/src/__tests__/components/EditArchiveModal.test.tsx`
- Test: `frontend/src/__tests__/components/ForecastPanelPermissions.test.tsx`
- Test: `frontend/src/__tests__/components/PurgeOldFilesModal.test.tsx`
- Test: `frontend/src/__tests__/components/SpoolCatalogSettings.test.tsx`
- Test: `frontend/src/__tests__/components/SpoolFormModal.test.tsx`

**Interfaces:**
- Consumes: `NumberField`, including its internal real spinbutton.
- Produces: inventory and history surfaces with shared visual steppers and unchanged values.

- [ ] **Step 1: Extend the source contract and verify it fails**

```ts
inventoryAndHistory: [
  'components/AMSHistoryModal.tsx', 'components/BulkEditSpoolsModal.tsx',
  'components/CameraWall.tsx', 'components/EditArchiveModal.tsx',
  'components/ForecastPanel.tsx', 'components/HeaterHistoryModal.tsx',
  'components/PurgeArchivesModal.tsx', 'components/PurgeOldFilesModal.tsx',
  'components/SpoolCatalogSettings.tsx', 'components/spool-form/AdditionalSection.tsx',
  'components/spool-form/FilamentSection.tsx',
],
```

Add the dynamic renderer assertion:

```ts
expect(fs.readFileSync(path.join(sourceRoot, 'components/BulkEditSpoolsModal.tsx'), 'utf8'))
  .toMatch(/f\.type === 'number'[\s\S]*?<NumberField/);
```

Run the migration test and expect the new group to FAIL.

- [ ] **Step 2: Migrate literal fields and branch the bulk renderer**

Apply the same literal-field replacement contract from Task 4. In `BulkEditSpoolsModal`, keep color and text behavior and select the shared numeric component explicitly:

```tsx
if (f.type === 'number') {
  return (
    <NumberField
      disabled={isPending}
      value={value}
      onValueChange={(next) => setField(f.id, next)}
      min={f.min}
      max={f.max}
      step={f.step}
      className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white placeholder-bambu-gray/50 focus:border-bambu-green focus:outline-none"
    />
  );
}

return <input type="text" disabled={isPending} value={value} onChange={(event) => setField(f.id, event.target.value)} className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white placeholder-bambu-gray/50 focus:border-bambu-green focus:outline-none" />;
```

- [ ] **Step 3: Run inventory and history tests**

Run:

```powershell
npm.cmd run test -- --run src/__tests__/components/ui/NumberFieldMigration.test.ts src/__tests__/components/EditArchiveModal.test.tsx src/__tests__/components/ForecastPanelPermissions.test.tsx src/__tests__/components/PurgeOldFilesModal.test.tsx src/__tests__/components/SpoolCatalogSettings.test.tsx src/__tests__/components/SpoolFormModal.test.tsx
```

Expected: all listed suites PASS. Existing `input[type="number"]` queries in `SpoolFormModal.test.tsx` still pass because `NumberField` retains the native input type internally.

- [ ] **Step 4: Commit the inventory migration**

```powershell
git add frontend/src/__tests__/components/ui/NumberFieldMigration.test.ts frontend/src/components/AMSHistoryModal.tsx frontend/src/components/BulkEditSpoolsModal.tsx frontend/src/components/CameraWall.tsx frontend/src/components/EditArchiveModal.tsx frontend/src/components/ForecastPanel.tsx frontend/src/components/HeaterHistoryModal.tsx frontend/src/components/PurgeArchivesModal.tsx frontend/src/components/PurgeOldFilesModal.tsx frontend/src/components/SpoolCatalogSettings.tsx frontend/src/components/spool-form/AdditionalSection.tsx frontend/src/components/spool-form/FilamentSection.tsx
git commit -m "refactor(inventory): use unified number fields"
```

---

### Task 6: Orders and Calculation Migration

**Files:**
- Modify: `frontend/src/__tests__/components/ui/NumberFieldMigration.test.ts`
- Modify: `frontend/src/components/orders/CalculationWorkspace.tsx`
- Modify: `frontend/src/components/orders/CustomerEditorModal.tsx`
- Modify: `frontend/src/components/orders/calculation/CalculationSettings.tsx`
- Modify: `frontend/src/components/orders/calculation/CommercialOverridesEditor.tsx`
- Modify: `frontend/src/components/orders/calculation/DeviceAssignmentEditor.tsx`
- Modify: `frontend/src/components/orders/calculation/LaborEditor.tsx`
- Modify: `frontend/src/components/orders/calculation/MaterialsEditor.tsx`
- Modify: `frontend/src/components/orders/calculation/RequestEditor.tsx`
- Test: `frontend/src/__tests__/components/CalculationEditors.test.tsx`
- Test: `frontend/src/__tests__/components/CalculationWorkspace.test.tsx`
- Test: `frontend/src/__tests__/pages/OrdersCustomersPage.test.tsx`

**Interfaces:**
- Consumes: `NumberField` raw-string callback behavior.
- Produces: order/customer payloads with the same string-versus-number conversions as before.

- [ ] **Step 1: Extend the source contract and verify it fails**

```ts
orders: [
  'components/orders/CalculationWorkspace.tsx', 'components/orders/CustomerEditorModal.tsx',
  'components/orders/calculation/CalculationSettings.tsx',
  'components/orders/calculation/CommercialOverridesEditor.tsx',
  'components/orders/calculation/DeviceAssignmentEditor.tsx',
  'components/orders/calculation/LaborEditor.tsx',
  'components/orders/calculation/MaterialsEditor.tsx',
  'components/orders/calculation/RequestEditor.tsx',
],
```

Run the migration test and expect only the new group to FAIL.

- [ ] **Step 2: Migrate order fields without altering data types**

Preserve each existing conversion at the consumer boundary:

```tsx
<NumberField value={line.quantity} min="0.001" step="1" onValueChange={(value) => updateLine({ quantity: value })} />
<NumberField value={account.payment_term_days ?? 0} min="0" onValueChange={(value) => patchAccount(index, { payment_term_days: Number(value) })} />
<NumberField value={line.unit_price ?? ''} min="0" step="0.01" onValueChange={(value) => updateLine({ unit_price: value || null })} />
```

For mapped fields in `CalculationWorkspace`, keep the current key-dependent conversion:

```tsx
<NumberField
  min="0"
  step={key.includes('hours') ? '0.01' : '1'}
  value={String(op[key])}
  onValueChange={(value) => changeVariant(selectedIndex, (variant) => ({
    ...variant,
    operations: variant.operations.map((item, itemIndex) => itemIndex === index
      ? { ...item, [key]: key.includes('grams') || key.includes('hours') ? value : Number(value) }
      : item),
  }))}
  className={inputClass}
/>
```

- [ ] **Step 3: Run calculation and customer tests**

Run:

```powershell
npm.cmd run test -- --run src/__tests__/components/ui/NumberFieldMigration.test.ts src/__tests__/components/CalculationEditors.test.tsx src/__tests__/components/CalculationWorkspace.test.tsx src/__tests__/pages/OrdersCustomersPage.test.tsx
```

Expected: all listed suites PASS and existing payload assertions retain their original value types.

- [ ] **Step 4: Commit the order migration**

```powershell
git add frontend/src/__tests__/components/ui/NumberFieldMigration.test.ts frontend/src/components/orders/CalculationWorkspace.tsx frontend/src/components/orders/CustomerEditorModal.tsx frontend/src/components/orders/calculation/CalculationSettings.tsx frontend/src/components/orders/calculation/CommercialOverridesEditor.tsx frontend/src/components/orders/calculation/DeviceAssignmentEditor.tsx frontend/src/components/orders/calculation/LaborEditor.tsx frontend/src/components/orders/calculation/MaterialsEditor.tsx frontend/src/components/orders/calculation/RequestEditor.tsx
git commit -m "refactor(orders): use unified number fields"
```

---

### Task 7: Full Audit, Build, and Browser QA

**Files:**
- Verify exclusion: `frontend/src/pages/StatsPage.tsx` keeps Recharts `<XAxis type="number" />`.
- Verify primitive: `frontend/src/components/ui/NumberField.tsx` is the only source file containing a rendered `input type="number"`.

**Interfaces:**
- Consumes: all completed NumberField work.
- Produces: repository-wide evidence that the migration is complete and visually sound.

- [ ] **Step 1: Run the final scoped source audit**

Run from the repository root:

```powershell
rg -n --glob '*.tsx' 'type="number"' frontend/src
rg -n --glob '*.tsx' '<TextField[^>]*type="number"' frontend/src
```

Expected: the first command reports only `NumberField.tsx`, the intentional Recharts `StatsPage.tsx` occurrence, and test selectors; the second command reports no product-source matches. Confirm `AddNotificationModal` and `BulkEditSpoolsModal` use explicit `NumberField` branches for numeric metadata.

- [ ] **Step 2: Run all automated verification**

Run from `frontend`:

```powershell
npm.cmd run test:run
npm.cmd run lint
npm.cmd run build
```

Expected: the complete Vitest suite and i18n parity pass, ESLint exits successfully, TypeScript compiles, and Vite produces the production bundle.

- [ ] **Step 3: Perform browser QA at the primary workflow**

Open `http://127.0.0.1:8000/settings?tab=printers-production` and verify:

1. A printer cost number field shows integrated vertical arrows and no native browser spinner.
2. Direct typing saves the same value as before.
3. Increment and decrement respect step and bounds, do not submit the form, and leave the input focused.
4. Disabled and read-only examples disable both step buttons.
5. Dark and light themes use PrintOps colors with visible focus, hover, active, invalid, and disabled states.
6. At desktop and mobile widths, fields do not clip, overlap labels, or break settings grids.
7. Sample inventory, printer workflow, and order-calculation number fields behave identically.
8. Arrow Up and Arrow Down still step the focused native numeric input.
9. The console has no relevant errors and no development overlay is visible.

- [ ] **Step 4: Confirm the implementation worktree is clean**

Run:

```powershell
git status --short
```

Expected: no output. If a verification defect is found, return to its owning task, repair it, rerun that task's focused checks, commit the repair with that task's exact file list, and then repeat Task 7 from Step 1.
