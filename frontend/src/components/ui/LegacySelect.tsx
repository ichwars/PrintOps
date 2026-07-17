import {
  Children,
  Fragment,
  isValidElement,
  type ChangeEvent,
  type ChangeEventHandler,
  type ReactNode,
  type SelectHTMLAttributes,
} from 'react';

import { Select, type SelectOption } from './Select';

type LegacySelectProps = Omit<
  SelectHTMLAttributes<HTMLSelectElement>,
  'children' | 'defaultValue' | 'multiple' | 'onChange' | 'size' | 'value'
> & {
  value?: string | number;
  onChange?: ChangeEventHandler<HTMLSelectElement>;
  children: ReactNode;
  label?: ReactNode;
};

type OptionProps = {
  value?: string | number;
  disabled?: boolean;
  children?: ReactNode;
};

type OptionGroupProps = {
  label?: string;
  children?: ReactNode;
};

const optionValue = (children: ReactNode) =>
  Children.toArray(children)
    .filter((child) => typeof child === 'string' || typeof child === 'number')
    .join('');

function collectOptions(children: ReactNode, group?: string): SelectOption<string>[] {
  return Children.toArray(children).flatMap((child): SelectOption<string>[] => {
    if (!isValidElement(child)) return [];
    if (child.type === Fragment) {
      return collectOptions((child.props as { children?: ReactNode }).children, group);
    }
    if (child.type === 'optgroup') {
      const props = child.props as OptionGroupProps;
      return collectOptions(props.children, props.label);
    }
    if (child.type !== 'option') return [];
    const props = child.props as OptionProps;
    const value = props.value ?? optionValue(props.children);
    return [{
      value: String(value),
      label: props.children,
      disabled: props.disabled,
      group,
    }];
  });
}

export function LegacySelect({
  value,
  onChange,
  children,
  label,
  disabled,
  required,
  className = '',
  id,
  'aria-label': ariaLabel,
}: LegacySelectProps) {
  const options = collectOptions(children);

  const emitChange = (nextValue: string) => {
    const target = { value: nextValue } as HTMLSelectElement;
    onChange?.({ target, currentTarget: target } as ChangeEvent<HTMLSelectElement>);
  };

  return (
    <Select
      id={id}
      label={label}
      ariaLabel={ariaLabel}
      value={String(value ?? '')}
      options={options}
      disabled={disabled}
      required={required}
      controlClassName={className}
      onValueChange={emitChange}
    />
  );
}
