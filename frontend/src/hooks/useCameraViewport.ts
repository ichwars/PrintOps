import { useLayoutEffect, useState, type RefObject } from 'react';

/** Layout bounds for a camera rotated by a quarter turn. */
export function useCameraViewport(ref: RefObject<HTMLElement | null>, rotation: number, visible = true) {
  const sideways = visible && Math.abs(rotation % 180) === 90;
  const [bounds, setBounds] = useState<{ width: number; height: number }>();
  useLayoutEffect(() => {
    const viewport = ref.current;
    if (!sideways || !viewport) return;

    const measure = () => {
      const { clientHeight: width, clientWidth: height } = viewport;
      if (width && height) {
        setBounds(previous => previous?.width === width && previous.height === height ? previous : { width, height });
      }
    };
    measure();
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', measure);
      return () => window.removeEventListener('resize', measure);
    }
    const observer = new ResizeObserver(measure);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, [ref, sideways]);

  return sideways ? bounds : undefined;
}
