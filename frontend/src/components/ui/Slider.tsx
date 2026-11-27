import { forwardRef, type InputHTMLAttributes } from 'react';

export type SliderProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> & {
  variant?: 'default' | 'unstyled';
};

export const Slider = forwardRef<HTMLInputElement, SliderProps>(function Slider(
  { variant = 'default', className = '', ...props },
  ref,
) {
  const defaultStyle = 'h-2 w-full cursor-pointer appearance-none rounded-full bg-bambu-dark-tertiary accent-bambu-green outline-none focus-visible:ring-2 focus-visible:ring-bambu-green focus-visible:ring-offset-2 focus-visible:ring-offset-bambu-dark disabled:cursor-not-allowed disabled:opacity-50 [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:bg-bambu-green [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-bambu-green max-[768px]:[&::-moz-range-thumb]:h-6 max-[768px]:[&::-moz-range-thumb]:w-6 max-[768px]:[&::-webkit-slider-thumb]:h-6 max-[768px]:[&::-webkit-slider-thumb]:w-6';
  return (
    <input
      {...props}
      ref={ref}
      type="range"
      className={variant === 'unstyled' ? className : `${defaultStyle} ${className}`}
    />
  );
});
