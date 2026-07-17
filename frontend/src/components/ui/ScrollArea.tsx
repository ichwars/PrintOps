import { forwardRef, type HTMLAttributes } from 'react';

export type ScrollAreaProps = HTMLAttributes<HTMLDivElement> & {
  direction?: 'vertical' | 'horizontal' | 'both';
  scrollbar?: 'normal' | 'thin' | 'hidden';
  stableGutter?: boolean;
};

export const ScrollArea = forwardRef<HTMLDivElement, ScrollAreaProps>(function ScrollArea(
  {
    direction = 'vertical',
    scrollbar = 'normal',
    stableGutter = false,
    className = '',
    ...props
  },
  ref,
) {
  const directionClass = {
    vertical: 'overflow-x-hidden overflow-y-auto',
    horizontal: 'overflow-x-auto overflow-y-hidden',
    both: 'overflow-auto',
  }[direction];
  const scrollbarClass = {
    normal: 'scrollbar-default',
    thin: 'scrollbar-thin',
    hidden: 'scrollbar-hidden',
  }[scrollbar];

  return (
    <div
      {...props}
      ref={ref}
      className={`${directionClass} ${scrollbarClass} ${stableGutter ? 'scrollbar-gutter-stable' : ''} ${className}`}
    />
  );
});
