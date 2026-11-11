import { useCallback, type RefObject } from 'react';

/** Open a camera request after React attaches its image and close it on detach. */
export function useStreamImgRef(src: string | undefined, imgRef?: RefObject<HTMLImageElement | null>) {
  return useCallback((img: HTMLImageElement | null) => {
    if (!img) return;
    if (imgRef) imgRef.current = img;
    // Setting src while rendering would start requests even for discarded images.
    if (src) img.src = src;
    return () => {
      img.removeAttribute('src');
      if (imgRef?.current === img) imgRef.current = null;
    };
  }, [imgRef, src]);
}
