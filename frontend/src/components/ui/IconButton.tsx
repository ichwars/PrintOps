import { forwardRef, type ButtonHTMLAttributes } from 'react';
import type { LucideIcon } from 'lucide-react';

export type IconButtonProps = Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  'children' | 'aria-label'
> & {
  label: string;
  icon: LucideIcon;
  pressed?: boolean;
  size?: 'sm' | 'md' | 'lg';
};

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, icon: Icon, pressed, size = 'md', className = '', type = 'button', ...props },
  ref,
) {
  const sizes = {
    sm: 'h-[34px] w-[34px] max-[768px]:h-11 max-[768px]:w-11 [&_svg]:h-4 [&_svg]:w-4',
    md: 'h-[38px] w-[38px] max-[768px]:h-11 max-[768px]:w-11 [&_svg]:h-4 [&_svg]:w-4',
    lg: 'h-11 w-11 max-[768px]:h-12 max-[768px]:w-12 [&_svg]:h-5 [&_svg]:w-5',
  };

  return (
    <button
      {...props}
      ref={ref}
      type={type}
      aria-label={label}
      aria-pressed={pressed}
      className={`inline-flex shrink-0 items-center justify-center rounded-lg text-bambu-gray-light transition-colors hover:bg-bambu-dark-tertiary hover:text-white focus:outline-none focus:ring-2 focus:ring-bambu-green disabled:cursor-not-allowed disabled:opacity-50 ${sizes[size]} ${className}`}
    >
      <Icon aria-hidden="true" />
    </button>
  );
});
