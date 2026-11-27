import { useLayoutEffect, useRef, type RefObject } from 'react';

function findViewport(footer: HTMLElement) {
  const content = footer.previousElementSibling;
  if (!(content instanceof HTMLElement)) return null;
  const viewport = content.classList.contains('warehouse-table-scroll') ? content.firstElementChild : content;
  if (!(viewport instanceof HTMLElement)) return null;
  const hasRows = viewport.hasAttribute('data-table-list') ||
    Array.from(viewport.children).some(child => child instanceof HTMLTableElement);
  return hasRows ? viewport : null;
}

export function usePaginatedTableViewport(offset: number, pageSize: number, viewportRef?: RefObject<HTMLDivElement | null>) {
  const footerRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const footer = footerRef.current;
    const container = footer?.parentElement;
    if (!footer || !container) return;

    let viewport: HTMLElement | null = null;
    let addedTabStop = false;

    const releaseViewport = () => {
      if (!viewport) return;
      viewport.removeAttribute('data-paginated-table-viewport');
      if (addedTabStop) viewport.removeAttribute('tabindex');
      addedTabStop = false;
    };

    const updateViewport = () => {
      const nextViewport = viewportRef ? viewportRef.current : findViewport(footer);
      if (viewport !== nextViewport) {
        releaseViewport();
        viewport = nextViewport;
        watchSize.disconnect();
        if (viewport) {
          viewport.setAttribute('data-paginated-table-viewport', '');
          watchSize.observe(viewport);
        }
      }
      if (!viewport) return;

      const scrollable = viewport.scrollHeight > viewport.clientHeight;
      if (scrollable && !viewport.hasAttribute('tabindex')) {
        viewport.tabIndex = 0;
        addedTabStop = true;
      } else if (!scrollable && addedTabStop && viewport !== document.activeElement) {
        viewport.removeAttribute('tabindex');
        addedTabStop = false;
      }
    };

    const watchSize = new ResizeObserver(updateViewport);
    // A table can be swapped for a card view while the same footer stays mounted.
    const watchContent = new MutationObserver(updateViewport);
    watchContent.observe(container, { childList: true, subtree: true });
    updateViewport();

    return () => {
      releaseViewport();
      watchSize.disconnect();
      watchContent.disconnect();
    };
  }, [viewportRef]);

  useLayoutEffect(() => {
    const footer = footerRef.current;
    const viewport = viewportRef ? viewportRef.current : footer && findViewport(footer);
    if (viewport) viewport.scrollTop = 0;
  }, [offset, pageSize, viewportRef]);

  return footerRef;
}
