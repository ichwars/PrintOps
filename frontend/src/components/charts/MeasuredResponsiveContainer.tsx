import { cloneElement, useEffect, useRef, useState, type CSSProperties, type ReactElement } from 'react';

type MeasuredResponsiveContainerProps = {
  width: number | string;
  height: number | string;
  minWidth?: number;
  minHeight?: number;
  className?: string;
  style?: CSSProperties;
  children: ReactElement;
};

export function MeasuredResponsiveContainer({
  width,
  height,
  minWidth = 0,
  minHeight = 0,
  className,
  style,
  children,
}: MeasuredResponsiveContainerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [measuredSize, setMeasuredSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return undefined;
    const hasResizeObserver = typeof ResizeObserver !== 'undefined';
    const isLayoutlessDom = typeof navigator !== 'undefined' && /jsdom/i.test(navigator.userAgent);

    const updateSize = () => {
      const rect = element.getBoundingClientRect();
      const nextSize = {
        width: Math.floor(rect.width) || (hasResizeObserver && !isLayoutlessDom ? 0 : (typeof width === 'number' ? width : 1)),
        height: Math.floor(rect.height) || (hasResizeObserver && !isLayoutlessDom ? 0 : (typeof height === 'number' ? height : 1)),
      };
      setMeasuredSize((currentSize) => (
        currentSize.width === nextSize.width && currentSize.height === nextSize.height
          ? currentSize
          : nextSize
      ));
    };

    updateSize();
    const resizeObserver = hasResizeObserver ? new ResizeObserver(updateSize) : null;
    resizeObserver?.observe(element);
    window.addEventListener('resize', updateSize);

    return () => {
      resizeObserver?.disconnect();
      window.removeEventListener('resize', updateSize);
    };
  }, [height, width]);

  return (
    <div ref={containerRef} className={className} style={{ width, height, minWidth, minHeight, ...style }}>
      {measuredSize.width > 0 && measuredSize.height > 0
        ? cloneElement(children, measuredSize)
        : null}
    </div>
  );
}
