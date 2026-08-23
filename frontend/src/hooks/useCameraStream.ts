import { useEffect, useRef, useState, useCallback } from 'react';
import { getStreamToken } from '../api/client';

// go2rtc's own reference player (www/video-rtc.js) tries these, in order,
// via MediaSource.isTypeSupported() and sends whichever match as the `value`
// of the MSE handshake. Bambu cameras are video-only (no mic), so this list
// only needs video codecs — go2rtc negotiates down to whichever the printer's
// H.264 stream actually is.
const CANDIDATE_CODECS = [
  'avc1.640029', // H.264 High 4.1
  'avc1.64002A', // H.264 High 4.2
  'avc1.640033', // H.264 High 5.1
  'avc1.4D4029', // H.264 Main 4.1 (some P1/A1-adjacent firmware)
  'hvc1.1.6.L153.B0', // H.265 main 5.1
];

export type CameraStreamStatus = 'idle' | 'connecting' | 'playing' | 'error' | 'unsupported';

interface UseCameraStreamOptions {
  printerId: number;
  enabled: boolean;
  onError?: () => void;
  onPlaying?: () => void;
}

interface UseCameraStreamResult {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  status: CameraStreamStatus;
  reconnect: () => void;
}

/**
 * MSE (fMP4-over-WebSocket) camera player, speaking go2rtc's own protocol
 * directly against PrintOps's `/camera/mse` proxy — see
 * backend/app/api/routes/camera.py::camera_mse_stream for the wire format
 * (JSON handshake, then binary fMP4 fragments) and why it's proxied rather
 * than pointed at go2rtc.
 *
 * This is the primary player; callers should fall back to the existing
 * MJPEG `<img>` path when `status` settles on 'unsupported' or 'error' —
 * see EmbeddedCameraViewer.tsx. Kept intentionally minimal (no WebRTC/HLS
 * negotiation, no audio) since Bambu cameras are video-only and this is
 * meant to sit behind an existing, working fallback rather than replace it
 * outright.
 */
export function useCameraStream({ printerId, enabled, onError, onPlaying }: UseCameraStreamOptions): UseCameraStreamResult {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [status, setStatus] = useState<CameraStreamStatus>('idle');
  const wsRef = useRef<WebSocket | null>(null);
  const mediaSourceRef = useRef<MediaSource | null>(null);
  const generationRef = useRef(0);
  const [retryKey, setRetryKey] = useState(0);

  const reconnect = useCallback(() => setRetryKey((k) => k + 1), []);

  useEffect(() => {
    if (!enabled) {
      setStatus('idle');
      return;
    }

    if (!('MediaSource' in window)) {
      setStatus('unsupported');
      onError?.();
      return;
    }

    const generation = ++generationRef.current;
    const video = videoRef.current;
    if (!video) {
      setStatus('error');
      return;
    }

    setStatus('connecting');

    const ms = new MediaSource();
    mediaSourceRef.current = ms;
    const objectUrl = URL.createObjectURL(ms);
    video.src = objectUrl;

    let sourceBuffer: SourceBuffer | null = null;
    // Chunks that arrive while the SourceBuffer is mid-append get queued
    // here and flushed on 'updateend' — appendBuffer() throws if called
    // while updating=true, and network frames don't wait for us.
    const pending: ArrayBuffer[] = [];

    const flushPending = () => {
      if (!sourceBuffer || sourceBuffer.updating || pending.length === 0) return;
      const chunk = pending.shift();
      if (chunk) {
        try {
          sourceBuffer.appendBuffer(chunk);
        } catch {
          // SourceBuffer in an unusable state (e.g. video element torn
          // down mid-append) — let the outer error handling take over.
        }
      }
    };

    const token = getStreamToken();
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const tokenParam = token ? `?token=${encodeURIComponent(token)}` : '';
    const ws = new WebSocket(`${proto}//${window.location.host}/api/v1/printers/${printerId}/camera/mse${tokenParam}`);
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    const supportedCodecs = CANDIDATE_CODECS.filter((c) =>
      MediaSource.isTypeSupported(`video/mp4; codecs="${c}"`)
    ).join();

    ws.onopen = () => {
      if (generationRef.current !== generation) return;
      // MediaSource might already be open by the time the socket connects;
      // if not, sourceopen (below) sends the handshake instead.
      if (ms.readyState === 'open') {
        ws.send(JSON.stringify({ type: 'mse', value: supportedCodecs }));
      }
    };

    ms.addEventListener('sourceopen', () => {
      if (generationRef.current !== generation) return;
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'mse', value: supportedCodecs }));
      }
    });

    ws.onmessage = (ev) => {
      if (generationRef.current !== generation) return;

      if (typeof ev.data === 'string') {
        let msg: { type?: string; value?: string };
        try {
          msg = JSON.parse(ev.data);
        } catch {
          return;
        }
        if (msg.type === 'mse' && msg.value) {
          try {
            sourceBuffer = ms.addSourceBuffer(msg.value);
            sourceBuffer.mode = 'segments';
            sourceBuffer.addEventListener('updateend', () => {
              flushPending();
              // Trim the buffered window so memory doesn't grow unbounded
              // on a live stream that's never seeked backward.
              if (sourceBuffer && !sourceBuffer.updating && sourceBuffer.buffered.length) {
                const end = sourceBuffer.buffered.end(sourceBuffer.buffered.length - 1);
                const start = sourceBuffer.buffered.start(0);
                if (end - start > 10) {
                  try {
                    sourceBuffer.remove(start, end - 5);
                  } catch {
                    // Ignore — not fatal, just means the buffer keeps growing.
                  }
                }
              }
            });
            video.play().catch(() => {
              // Autoplay can be blocked before user interaction; the
              // viewer's own play button (if any) / user gesture recovers
              // this. Not a stream error.
            });
            setStatus('playing');
            onPlaying?.();
          } catch {
            setStatus('error');
            onError?.();
          }
        } else if (msg.type === 'error') {
          setStatus('error');
          onError?.();
        }
        return;
      }

      // Binary frame: an fMP4 init segment or media fragment.
      const chunk = ev.data as ArrayBuffer;
      if (!sourceBuffer) {
        // Handshake reply hasn't landed yet (shouldn't normally happen —
        // go2rtc replies before sending data) — drop rather than crash.
        return;
      }
      if (sourceBuffer.updating || pending.length > 0) {
        pending.push(chunk);
      } else {
        try {
          sourceBuffer.appendBuffer(chunk);
        } catch {
          pending.push(chunk);
        }
      }
    };

    ws.onerror = () => {
      if (generationRef.current !== generation) return;
      setStatus('error');
      onError?.();
    };

    ws.onclose = () => {
      // A deliberate close (unmount, reconnect(), dep change) bumps
      // generationRef in the cleanup below *before* the browser fires this
      // event, so reaching here means the socket dropped unexpectedly.
      if (generationRef.current !== generation) return;
      setStatus('error');
      onError?.();
    };

    return () => {
      generationRef.current += 1;
      try {
        ws.close();
      } catch {
        // Already closed.
      }
      wsRef.current = null;
      if (ms.readyState === 'open') {
        try {
          ms.endOfStream();
        } catch {
          // MediaSource already detached from the video element.
        }
      }
      mediaSourceRef.current = null;
      URL.revokeObjectURL(objectUrl);
      if (video) {
        video.removeAttribute('src');
        video.load();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [printerId, enabled, retryKey]);

  return { videoRef, status, reconnect };
}
