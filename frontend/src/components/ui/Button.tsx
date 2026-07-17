import { LoaderCircle } from 'lucide-react';
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
  children: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = 'primary',
    size = 'md',
    loading = false,
    disabled,
    className = '',
    children,
    ...props
  },
  ref,
) {
  const baseStyles =
    'inline-flex items-center justify-center font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-bambu-dark disabled:opacity-50 disabled:cursor-not-allowed';

  const variants = {
    primary: 'bg-bambu-green hover:bg-bambu-green-light text-white focus:ring-bambu-green',
    secondary:
      'bg-bambu-dark-tertiary hover:bg-bambu-gray-dark text-white focus:ring-bambu-gray',
    danger: 'bg-red-600 hover:bg-red-700 text-white focus:ring-red-500',
    ghost:
      'bg-transparent hover:bg-bambu-dark-tertiary text-bambu-gray-light hover:text-white',
  };

  const sizes = {
    sm: 'h-[34px] px-3 py-1.5 text-sm gap-1.5 max-[768px]:min-h-11',
    md: 'h-[38px] px-4 py-2 text-sm gap-2 max-[768px]:min-h-11',
    lg: 'min-h-11 px-6 py-3 text-base gap-2 max-[768px]:min-h-12',
  };

  return (
    <button
      {...props}
      ref={ref}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`${baseStyles} ${variants[variant]} ${sizes[size]} ${className}`}
    >
      {loading ? <LoaderCircle aria-hidden="true" className="h-4 w-4 animate-spin" /> : null}
      {children}
    </button>
  );
});
