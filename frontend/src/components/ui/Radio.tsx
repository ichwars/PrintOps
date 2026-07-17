import { forwardRef, type InputHTMLAttributes } from 'react';

export type RadioProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'type'>;

export const Radio = forwardRef<HTMLInputElement, RadioProps>(function Radio(
  { className = '', disabled, ...props },
  ref,
) {
  return (
    <span
      className={`inline-flex min-h-[38px] items-center justify-center max-[768px]:min-h-11 ${
        disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'
      } ${className}`}
    >
      <input {...props} ref={ref} type="radio" disabled={disabled} className="peer sr-only" />
      <span
        data-testid="radio-visual"
        aria-hidden="true"
        className="flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full border border-bambu-dark-tertiary bg-bambu-dark leading-none transition-colors peer-focus-visible:ring-2 peer-focus-visible:ring-bambu-green peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-bambu-dark peer-checked:border-bambu-green peer-checked:[&>span]:opacity-100 max-[768px]:h-[22px] max-[768px]:w-[22px]"
      >
        <span className="h-2 w-2 rounded-full bg-bambu-green opacity-0 max-[768px]:h-2.5 max-[768px]:w-2.5" />
      </span>
    </span>
  );
});
