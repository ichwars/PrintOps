/** Dismiss popups on new outside scrolling, not a queued notification from
 * the focus/scroll that brought their opener into view before they opened. */
export function listenForOutsideScroll(
  container: HTMLElement,
  anchor: HTMLElement | null,
  onOutsideScroll: () => void,
) {
  const position = (target: EventTarget): [number, number] | null => {
    if (target === document) return [window.scrollX, window.scrollY];
    if (target instanceof HTMLElement) return [target.scrollLeft, target.scrollTop];
    return null;
  };
  const initial = new Map<EventTarget, [number, number]>();
  initial.set(document, [window.scrollX, window.scrollY]);
  for (let element = anchor; element; element = element.parentElement) {
    initial.set(element, [element.scrollLeft, element.scrollTop]);
  }
  const handleScroll = (event: Event) => {
    const target = event.target;
    if (!target || container.contains(target as Node)) return;
    const before = initial.get(target);
    const after = position(target);
    if (before && after && before[0] === after[0] && before[1] === after[1]) return;
    onOutsideScroll();
  };
  document.addEventListener('scroll', handleScroll, true);
  return () => document.removeEventListener('scroll', handleScroll, true);
}
