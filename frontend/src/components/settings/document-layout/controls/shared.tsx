import type { ReactNode } from 'react';
import { RotateCcw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { LayoutRulePatch, LayoutRuleSources } from '../../../../api/documentLayouts';
import { ColorInput, NumberField as UiNumberField, Select as UiSelect, Switch, TextField as UiTextField } from '../../../ui';

export interface LayoutSectionProps<T extends object> {
  value: T;
  sources: LayoutRuleSources<T>;
  overrides: LayoutRulePatch<T>;
  readOnly: boolean;
  onChange: <K extends keyof T>(key: K, value: T[K]) => void;
  onReset: <K extends keyof T>(key: K) => void;
}

type FieldControlKind = 'boolean' | 'number' | 'text' | 'select';

interface FieldShellProps {
  label: string;
  controlKind: FieldControlKind;
  help?: string;
  unit?: string;
  source: string;
  overridden: boolean;
  readOnly: boolean;
  onReset: () => void;
  children: ReactNode;
}

export function FieldShell({ label, controlKind, help, unit, source, overridden, readOnly, onReset, children }: FieldShellProps) {
  const { t } = useTranslation();
  const hintKeys: Record<FieldControlKind, string> = {
    boolean: 'settings.documentLayout.inheritance.booleanHint',
    number: 'settings.documentLayout.inheritance.numberHint',
    text: 'settings.documentLayout.inheritance.textHint',
    select: 'settings.documentLayout.inheritance.selectHint',
  };
  const defaultHints: Record<FieldControlKind, string> = {
    boolean: 'Shows or hides “{{field}}” in the generated PDF.',
    number: 'Sets the value for “{{field}}” in the generated PDF.',
    text: 'Sets the text or value for “{{field}}” in the generated PDF.',
    select: 'Selects how “{{field}}” is displayed in the generated PDF.',
  };
  const fieldHelp = help ?? t(hintKeys[controlKind], {
    field: label,
    defaultValue: defaultHints[controlKind],
  });
  return <div data-layout-field className="group relative flex h-full flex-col rounded-lg border border-bambu-dark-tertiary bg-bambu-dark p-3">
    <div className="mb-2 min-w-0">
      <p className="block min-h-5 text-sm font-medium text-white">{label}{unit ? <span className="ml-1 text-xs font-normal text-bambu-gray">({unit})</span> : null}</p>
      <p data-layout-help className="mt-0.5 min-h-10 w-full text-xs leading-4 text-bambu-gray">{fieldHelp}</p>
    </div>
    <div className="absolute right-1 top-1 flex items-center gap-1">
      <span className={[
        'pointer-events-none rounded-full px-2 py-0.5 text-[10px] opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100',
        overridden ? 'bg-bambu-green/20 text-bambu-green' : 'bg-bambu-dark-secondary text-bambu-gray',
      ].join(' ')}>
        {overridden ? t('settings.documentLayout.inheritance.override', 'Override') : source}
      </span>
      {overridden && !readOnly ? <button type="button" className="flex h-8 w-8 items-center justify-center rounded text-bambu-gray hover:bg-bambu-dark-secondary hover:text-white" aria-label={t('settings.documentLayout.actions.removeOverride', 'Remove override')} title={t('settings.documentLayout.actions.removeOverride', 'Remove override')} onClick={onReset}><RotateCcw className="h-3.5 w-3.5" aria-hidden="true" /></button> : null}
    </div>
    <div className="mt-auto">{children}</div>
  </div>;
}

function sourceLabel(level: string): string {
  const labels: Record<string, string> = { system: 'System', profile: 'Profile', document_type: 'Document type', language: 'Language' };
  return labels[level] ?? level;
}

function hasOverride<T extends object, K extends keyof T>(patch: LayoutRulePatch<T>, key: K): boolean {
  return patch[key] !== undefined && patch[key] !== null;
}

function fieldValue<T extends object, K extends keyof T>(value: T, patch: LayoutRulePatch<T>, key: K): T[K] {
  const override = patch[key];
  return override === undefined || override === null ? value[key] : override;
}

interface BooleanFieldProps<T extends object, K extends keyof T> { field: K; label: string; help?: string; props: LayoutSectionProps<T>; }
export function BooleanField<T extends object, K extends keyof T>({ field, label, help, props }: BooleanFieldProps<T, K>) {
  const current = Boolean(fieldValue(props.value, props.overrides, field));
  const overridden = hasOverride(props.overrides, field);
  return <FieldShell label={label} controlKind="boolean" help={help} source={sourceLabel(props.sources[field].level)} overridden={overridden} readOnly={props.readOnly} onReset={() => props.onReset(field)}>
    <Switch checked={current} ariaLabel={label} disabled={props.readOnly} onCheckedChange={(checked) => props.onChange(field, checked as T[K])} />
  </FieldShell>;
}

interface NumberFieldProps<T extends object, K extends keyof T> { field: K; label: string; unit?: string; help?: string; min?: number; max?: number; step?: number; props: LayoutSectionProps<T>; }
export function NumberField<T extends object, K extends keyof T>({ field, label, unit, help, min, max, step = 1, props }: NumberFieldProps<T, K>) {
  const current = Number(fieldValue(props.value, props.overrides, field));
  const overridden = hasOverride(props.overrides, field);
  return <FieldShell label={label} controlKind="number" unit={unit} help={help} source={sourceLabel(props.sources[field].level)} overridden={overridden} readOnly={props.readOnly} onReset={() => props.onReset(field)}>
    <UiNumberField aria-label={label} value={Number.isFinite(current) ? current : 0} min={min} max={max} step={step} suffix={unit} disabled={props.readOnly} onValueChange={(value) => {
      const numericValue = Number(value);
      if (!Number.isFinite(numericValue)) return;
      if (min !== undefined && numericValue < min) return;
      if (max !== undefined && numericValue > max) return;
      props.onChange(field, numericValue as T[K]);
    }} />
  </FieldShell>;
}

interface TextFieldProps<T extends object, K extends keyof T> { field: K; label: string; help?: string; type?: 'text' | 'color'; props: LayoutSectionProps<T>; }
export function TextField<T extends object, K extends keyof T>({ field, label, help, type = 'text', props }: TextFieldProps<T, K>) {
  const current = String(fieldValue(props.value, props.overrides, field));
  const overridden = hasOverride(props.overrides, field);
  return <FieldShell label={label} controlKind="text" help={help} source={sourceLabel(props.sources[field].level)} overridden={overridden} readOnly={props.readOnly} onReset={() => props.onReset(field)}>
    {type === 'color'
      ? <div className="flex items-center gap-3"><ColorInput aria-label={label} value={current} disabled={props.readOnly} onChange={(event) => props.onChange(field, event.target.value as T[K])} /><span className="font-mono text-xs text-bambu-gray">{current}</span></div>
      : <UiTextField aria-label={label} value={current} disabled={props.readOnly} onValueChange={(value) => props.onChange(field, value as T[K])} />}
  </FieldShell>;
}

interface SelectFieldProps<T extends object, K extends keyof T> { field: K; label: string; help?: string; options: Array<{ value: string; label: string }>; props: LayoutSectionProps<T>; }
export function SelectField<T extends object, K extends keyof T>({ field, label, help, options, props }: SelectFieldProps<T, K>) {
  const current = String(fieldValue(props.value, props.overrides, field));
  const overridden = hasOverride(props.overrides, field);
  return <FieldShell label={label} controlKind="select" help={help} source={sourceLabel(props.sources[field].level)} overridden={overridden} readOnly={props.readOnly} onReset={() => props.onReset(field)}>
    <UiSelect ariaLabel={label} value={current} options={options} disabled={props.readOnly} onValueChange={(value) => props.onChange(field, value as T[K])} />
  </FieldShell>;
}