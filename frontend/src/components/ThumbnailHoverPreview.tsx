import { useEffect, useState, type MouseEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

const EDGE = 8;
const SIZE = 256;

export function ThumbnailHoverPreview({ src, children, className }: {
  src: string | null;
  children: ReactNode;
  className?: string;
}) {
  const [position, setPosition] = useState<{ left: number; top: number; size: number } | null>(null);

  function show(event: MouseEvent<HTMLDivElement>) {
    if (!src || !window.matchMedia('(hover: hover) and (pointer: fine)').matches) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const size = Math.min(SIZE, window.innerWidth - 2 * EDGE, window.innerHeight - 2 * EDGE);
    if (size <= 0) return;
    const right = rect.right + EDGE;
    const left = right + size + EDGE <= window.innerWidth ? right : Math.max(EDGE, rect.left - size - EDGE);
    const top = Math.max(EDGE, Math.min(rect.top, window.innerHeight - size - EDGE));
    setPosition({ left, top, size });
  }

  useEffect(() => {
    if (!position) return;
    const hide = () => setPosition(null);
    window.addEventListener('scroll', hide, true);
    window.addEventListener('resize', hide);
    return () => {
      window.removeEventListener('scroll', hide, true);
      window.removeEventListener('resize', hide);
    };
  }, [position]);

  return <div className={className} onMouseEnter={show} onMouseLeave={() => setPosition(null)}>
    {children}
    {position && src && createPortal(<img src={src} alt="" aria-hidden="true" data-testid="thumbnail-hover-preview"
      className="pointer-events-none fixed z-[60] rounded-lg border border-bambu-dark-tertiary bg-bambu-dark object-contain shadow-xl"
      style={{ left: position.left, top: position.top, width: position.size, height: position.size }} />,
    document.body)}
  </div>;
}
