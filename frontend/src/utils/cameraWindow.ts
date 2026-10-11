import type { CameraViewPreference } from '../hooks/useCameraViewPreference';

export function openCameraWindow(printerId: number, mode: CameraViewPreference) {
  const state = { width: 640, height: 400, left: undefined as number | undefined, top: undefined as number | undefined };
  try {
    const saved = JSON.parse(localStorage.getItem('cameraWindowState') ?? 'null');
    if (saved && typeof saved === 'object') {
      if (Number.isFinite(saved.width) && saved.width > 0) state.width = saved.width;
      if (Number.isFinite(saved.height) && saved.height > 0) state.height = saved.height;
      if (Number.isFinite(saved.left)) state.left = saved.left;
      if (Number.isFinite(saved.top)) state.top = saved.top;
    }
  } catch { /* Use the default popup size when storage is unavailable or malformed. */ }
  const features = [
    `width=${state.width}`,
    `height=${state.height}`,
    state.left !== undefined ? `left=${state.left}` : '',
    state.top !== undefined ? `top=${state.top}` : '',
    // Same-origin popup needs opener so the browser copies sessionStorage
    // (auth token) into the new window.
    'menubar=no,toolbar=no,location=no,status=no',
  ].filter(Boolean).join(',');
  window.open(`/camera/${printerId}?view=${mode}`, `camera-${printerId}`, features);
}
