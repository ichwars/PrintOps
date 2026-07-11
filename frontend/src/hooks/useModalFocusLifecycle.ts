import { useLayoutEffect, useRef, type KeyboardEvent, type RefObject } from 'react';

const focusableSelector = [
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  'a[href]',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

interface Options {
  canClose?: boolean;
  initialFocusRef?: RefObject<HTMLElement | null>;
  onClose: () => void;
}

export function useModalFocusLifecycle<T extends HTMLElement>({ onClose, canClose = true, initialFocusRef }: Options) {
  const dialogRef = useRef<T>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  useLayoutEffect(() => {
    triggerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const initial = initialFocusRef?.current ?? dialogRef.current?.querySelector<HTMLElement>(focusableSelector) ?? dialogRef.current;
    initial?.focus();

    return () => {
      if (triggerRef.current?.isConnected) triggerRef.current.focus();
    };
  }, [initialFocusRef]);

  const onKeyDown = (event: KeyboardEvent<T>) => {
    if (event.key === 'Escape') {
      event.stopPropagation();
      event.preventDefault();
      if (canClose) onClose();
      return;
    }
    if (event.key !== 'Tab') return;

    const controls = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>(focusableSelector) ?? [])
      .filter((control) => !control.matches(':disabled'));
    if (controls.length === 0) {
      event.preventDefault();
      dialogRef.current?.focus();
      return;
    }
    const first = controls[0];
    const last = controls[controls.length - 1];
    const activeControl = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (!activeControl || !controls.includes(activeControl)) {
      event.preventDefault();
      (event.shiftKey ? last : first).focus();
    } else if (event.shiftKey && activeControl === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && activeControl === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return { dialogRef, onKeyDown };
}
