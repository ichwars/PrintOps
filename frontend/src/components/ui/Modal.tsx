import { X } from 'lucide-react';
import {
  useEffect,
  useId,
  useRef,
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
} from 'react';
import { createPortal } from 'react-dom';

import { IconButton } from './IconButton';
import { ScrollArea } from './ScrollArea';

export type ModalProps = {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  closeOnBackdrop?: boolean;
  closeDisabled?: boolean;
  closeLabel?: string;
  initialFocusRef?: RefObject<HTMLElement | null>;
  className?: string;
};

const FOCUSABLE_SELECTOR = [
  'button:not([disabled])',
  'a[href]',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

const focusableElements = (container: HTMLElement) =>
  Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (element) => element.getAttribute('aria-hidden') !== 'true' && !element.matches(':disabled'),
  );

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  closeOnBackdrop = true,
  closeDisabled = false,
  closeLabel = 'Close',
  initialFocusRef,
  className = '',
}: ModalProps) {
  const generatedId = useId().replace(/:/g, '');
  const titleId = `modal-${generatedId}-title`;
  const descriptionId = description ? `modal-${generatedId}-description` : undefined;
  const dialogRef = useRef<HTMLDivElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return undefined;
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const dialog = dialogRef.current;
    if (dialog) {
      const focusable = focusableElements(dialog);
      const target =
        initialFocusRef?.current ??
        focusable.find((element) => !element.hasAttribute('data-modal-close')) ??
        focusable[0] ??
        dialog;
      target.focus();
    }

    return () => {
      document.body.style.overflow = previousOverflow;
      previouslyFocused.current?.focus();
    };
  }, [initialFocusRef, open]);

  if (!open) return null;

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      onClose();
      return;
    }
    if (event.key !== 'Tab' || !dialogRef.current) return;

    const focusable = focusableElements(dialogRef.current);
    if (!focusable.length) {
      event.preventDefault();
      dialogRef.current.focus();
      return;
    }
    const current = document.activeElement as HTMLElement;
    const currentIndex = focusable.indexOf(current);
    const nextIndex = event.shiftKey
      ? currentIndex <= 0
        ? focusable.length - 1
        : currentIndex - 1
      : currentIndex < 0 || currentIndex === focusable.length - 1
        ? 0
        : currentIndex + 1;
    event.preventDefault();
    focusable[nextIndex].focus();
  };

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onPointerDown={(event) => {
        if (closeOnBackdrop && event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        tabIndex={-1}
        className={`flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary shadow-2xl ${className}`}
        onKeyDown={handleKeyDown}
      >
        <div className="flex shrink-0 items-start justify-between gap-4 border-b border-bambu-dark-tertiary px-6 py-4">
          <div className="min-w-0">
            <h2 id={titleId} className="text-lg font-semibold text-white">
              {title}
            </h2>
            {description ? (
              <p id={descriptionId} className="mt-1 text-sm text-bambu-gray">
                {description}
              </p>
            ) : null}
          </div>
          <IconButton
            data-modal-close
            label={closeLabel}
            icon={X}
            size="sm"
            disabled={closeDisabled}
            onClick={onClose}
          />
        </div>
        <ScrollArea className="min-h-0 flex-1 p-6" scrollbar="thin">
          {children}
        </ScrollArea>
      </div>
    </div>,
    document.body,
  );
}
