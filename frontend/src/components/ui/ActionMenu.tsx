import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { MoreVertical } from 'lucide-react';
import { FloatingLayer } from './FloatingLayer';

interface ActionMenuProps {
  label: string;
  className?: string;
  children: (close: () => void) => ReactNode;
}

/** Anchored, flat action menu. Positioning/dismissal belong to FloatingLayer;
 * callers retain their action permissions and render role="menuitem" buttons. */
export function ActionMenu({ label, className = '', children }: ActionMenuProps) {
  const [open, setOpen] = useState(false);
  const anchorRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const initialFocus = useRef<'first' | 'last'>('first');
  const id = useId();

  const close = () => {
    setOpen(false);
    anchorRef.current?.focus({ preventScroll: true });
  };

  useEffect(() => {
    if (!open) return;
    const menu = menuRef.current;
    const buttons = menu?.querySelectorAll<HTMLButtonElement>('button[role="menuitem"]:not(:disabled)');
    const target = initialFocus.current === 'last' ? buttons?.[buttons.length - 1] : buttons?.[0];
    (target ?? menu)?.focus({ preventScroll: true });

    const dismissOnScroll = (event: Event) => {
      // FloatingLayer (the parent) owns overflow scrolling, not the menu div.
      if (!menu?.parentElement?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('scroll', dismissOnScroll, true);
    return () => document.removeEventListener('scroll', dismissOnScroll, true);
  }, [open]);

  return (
    <>
      <button
        ref={anchorRef}
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        className={className}
        onClick={(event) => {
          event.stopPropagation();
          initialFocus.current = 'first';
          setOpen(!open);
        }}
        onKeyDown={(event) => {
          if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
          event.preventDefault();
          event.stopPropagation();
          initialFocus.current = event.key === 'ArrowUp' ? 'last' : 'first';
          setOpen(true);
        }}
      >
        <MoreVertical className="w-4 h-4 text-bambu-gray" />
      </button>
      <FloatingLayer open={open} anchorRef={anchorRef} onDismiss={() => setOpen(false)}
        className="min-w-[160px] max-w-[min(280px,calc(100vw-16px))] py-1">
        <div ref={menuRef} id={id} role="menu" aria-label={label} tabIndex={-1}
          onClick={(event) => event.stopPropagation()}
          onKeyDown={(event) => {
            if (event.key === 'Escape' || event.key === 'Tab') {
              if (event.key === 'Escape') event.preventDefault();
              event.stopPropagation();
              // For Tab, restore the trigger first and let native navigation
              // continue from its place in the page, not from the body portal.
              close();
              return;
            }
            if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
            event.preventDefault();
            event.stopPropagation();
            const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('button[role="menuitem"]:not(:disabled)'));
            if (!buttons.length) return;
            const current = buttons.indexOf(document.activeElement as HTMLButtonElement);
            const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1
              : (current + (event.key === 'ArrowUp' ? -1 : 1) + buttons.length) % buttons.length;
            buttons[next].focus({ preventScroll: true });
            buttons[next].scrollIntoView?.({ block: 'nearest' });
          }}
        >
          {children(close)}
        </div>
      </FloatingLayer>
    </>
  );
}
