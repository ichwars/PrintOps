import {
  autoUpdate,
  computePosition,
  flip,
  offset,
  shift,
  size,
  type Placement,
} from '@floating-ui/dom';
import { useEffect, useLayoutEffect, useRef, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';

export type FloatingLayerProps = {
  open: boolean;
  anchorRef: RefObject<HTMLElement | null>;
  children: ReactNode;
  onDismiss: () => void;
  returnFocus?: boolean;
  className?: string;
  placement?: Placement;
  matchAnchorWidth?: boolean;
};

export function FloatingLayer({
  open,
  anchorRef,
  children,
  onDismiss,
  returnFocus = true,
  className = '',
  placement = 'bottom-start',
  matchAnchorWidth = false,
}: FloatingLayerProps) {
  const layerRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    if (!open) return undefined;
    const anchor = anchorRef.current;
    const layer = layerRef.current;
    if (!anchor || !layer) return undefined;

    return autoUpdate(anchor, layer, () => {
      void computePosition(anchor, layer, {
        placement,
        strategy: 'fixed',
        middleware: [
          offset(6),
          flip({ padding: 8 }),
          shift({ padding: 8 }),
          size({
            padding: 8,
            apply({ availableHeight, rects, elements }) {
              Object.assign(elements.floating.style, {
                maxHeight: `${Math.max(120, availableHeight)}px`,
                minWidth: matchAnchorWidth ? `${rects.reference.width}px` : '',
              });
            },
          }),
        ],
      }).then(({ x, y }) => {
        Object.assign(layer.style, { left: `${x}px`, top: `${y}px` });
      });
    });
  }, [anchorRef, matchAnchorWidth, open, placement]);

  useEffect(() => {
    if (!open) return undefined;

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node | null;
      if (target && (anchorRef.current?.contains(target) || layerRef.current?.contains(target))) {
        return;
      }
      onDismiss();
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      onDismiss();
      if (returnFocus) anchorRef.current?.focus();
    };

    document.addEventListener('pointerdown', handlePointerDown, true);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown, true);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [anchorRef, onDismiss, open, returnFocus]);

  if (!open) return null;

  return createPortal(
    <div
      ref={layerRef}
      className={`fixed z-50 overflow-auto rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary shadow-xl ${className}`}
    >
      {children}
    </div>,
    document.body,
  );
}
