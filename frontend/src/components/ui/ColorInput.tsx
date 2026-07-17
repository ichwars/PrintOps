import { forwardRef, type InputHTMLAttributes } from 'react';

export type ColorInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'type'>;

export const ColorInput = forwardRef<HTMLInputElement, ColorInputProps>(function ColorInput(
  { className = '', ...props },
  ref,
) {
  return (
    <input
      {...props}
      ref={ref}
      type="color"
      className={`h-[38px] w-12 cursor-pointer overflow-hidden rounded-lg border border-bambu-dark-tertiary bg-bambu-dark p-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-bambu-green disabled:cursor-not-allowed disabled:opacity-50 max-[768px]:h-11 max-[768px]:w-14 [&::-webkit-color-swatch-wrapper]:p-0 [&::-webkit-color-swatch]:rounded-md [&::-webkit-color-swatch]:border-0 ${className}`}
    />
  );
});
