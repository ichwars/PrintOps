import { forwardRef, type InputHTMLAttributes } from 'react';

export type FileInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'type'>;

export const FileInput = forwardRef<HTMLInputElement, FileInputProps>(function FileInput(
  { className = '', ...props },
  ref,
) {
  return (
    <input
      {...props}
      ref={ref}
      type="file"
      className={`text-sm text-bambu-gray file:mr-3 file:rounded-lg file:border-0 file:bg-bambu-dark-tertiary file:px-3 file:py-2 file:text-white hover:file:bg-bambu-green/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-bambu-green ${className}`}
    />
  );
});
