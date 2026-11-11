import { useEffect, useEffectEvent, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Camera, ImageUp, ScanLine } from 'lucide-react';
import { Button } from './Button';
import { FileInput, TextField } from './ui';

async function decodeFrame(canvas: HTMLCanvasElement, image: CanvasImageSource, width: number, height: number) {
  if (!width || !height) return null;
  const scale = Math.min(1, 1280 / Math.max(width, height));
  canvas.width = Math.max(1, Math.round(width * scale));
  canvas.height = Math.max(1, Math.round(height * scale));
  const context = canvas.getContext('2d', { willReadFrequently: true });
  if (!context) return null;
  context.drawImage(image, 0, 0, canvas.width, canvas.height);
  const pixels = context.getImageData(0, 0, canvas.width, canvas.height);
  const { default: readQR } = await import('jsqr');
  return readQR(pixels.data, pixels.width, pixels.height)?.data ?? null;
}

interface Props {
  onPayload: (payload: string) => void;
  disabled?: boolean;
}

export function QrSpoolScanner({ onPayload, disabled = false }: Props) {
  const { t } = useTranslation();
  const [camera, setCamera] = useState(false);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [error, setError] = useState('');
  const [manual, setManual] = useState('');
  const videoRef = useRef<HTMLVideoElement>(null);
  const photoRef = useRef<HTMLInputElement>(null);
  const decodeResult = useEffectEvent((payload: string) => onPayload(payload));
  const cameraError = useEffectEvent(() => {
    setError(t('inventory.qrAssign.cameraError'));
    setCamera(false);
  });

  useEffect(() => {
    if (!camera || disabled) return;
    let cancelled = false;
    let stream: MediaStream | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const video = videoRef.current;
    const canvas = document.createElement('canvas');

    async function scan() {
      if (!video || cancelled) return;
      try {
        const payload = await decodeFrame(canvas, video, video.videoWidth, video.videoHeight);
        if (cancelled) return;
        if (payload) {
          setCamera(false);
          decodeResult(payload);
        } else {
          timer = setTimeout(() => void scan(), 180);
        }
      } catch {
        if (!cancelled) cameraError();
      }
    }

    async function start() {
      try {
        if (!video || !navigator.mediaDevices?.getUserMedia) throw new Error('Camera unavailable');
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false });
        if (cancelled) {
          stream.getTracks().forEach(track => track.stop());
          return;
        }
        video.srcObject = stream;
        await video.play();
        void scan();
      } catch {
        if (!cancelled) cameraError();
      }
    }

    void start();
    return () => {
      cancelled = true;
      clearTimeout(timer);
      stream?.getTracks().forEach(track => track.stop());
      if (video) video.srcObject = null;
    };
  }, [camera, disabled]);

  async function scanPhoto(file: File) {
    setCamera(false);
    setError('');
    setPhotoBusy(true);
    const url = URL.createObjectURL(file);
    try {
      const image = new Image();
      image.src = url;
      await image.decode();
      const payload = await decodeFrame(document.createElement('canvas'), image, image.naturalWidth, image.naturalHeight);
      if (payload) onPayload(payload);
      else setError(t('inventory.qrAssign.noCode'));
    } catch {
      setError(t('inventory.qrAssign.noCode'));
    } finally {
      URL.revokeObjectURL(url);
      setPhotoBusy(false);
    }
  }

  return <div className="space-y-3">
    <div className="flex flex-wrap gap-2">
      <Button variant="secondary" disabled={disabled || photoBusy} onClick={() => {
        setError('');
        setCamera(previous => !previous);
      }}>
        <Camera className="h-4 w-4" />
        {t(camera ? 'inventory.qrAssign.stopCamera' : 'inventory.qrAssign.startCamera')}
      </Button>
      <Button variant="secondary" disabled={disabled || photoBusy} onClick={() => photoRef.current?.click()}>
        <ImageUp className="h-4 w-4" />
        {t('inventory.qrAssign.photo')}
      </Button>
      <FileInput ref={photoRef} className="hidden" accept="image/*" onChange={event => {
        const file = event.target.files?.[0];
        event.target.value = '';
        if (file) void scanPhoto(file);
      }} />
    </div>
    {camera && <video ref={videoRef} autoPlay muted playsInline className="max-h-56 w-full rounded bg-black" />}
    <div className="flex items-end gap-2">
      <div className="min-w-0 flex-1">
        <TextField label={t('inventory.qrAssign.pasteLabel')} value={manual} disabled={disabled || photoBusy}
          maxLength={2048} onChange={event => setManual(event.target.value)}
          onKeyDown={event => {
            if (event.key !== 'Enter' || !manual.trim()) return;
            event.preventDefault();
            setCamera(false);
            onPayload(manual.trim());
          }} />
      </div>
      <Button variant="secondary" disabled={disabled || photoBusy || !manual.trim()} onClick={() => {
        setCamera(false);
        onPayload(manual.trim());
      }}>
        <ScanLine className="h-4 w-4" />
        {t('inventory.qrAssign.read')}
      </Button>
    </div>
    {error && <p role="status" className="text-sm text-red-400">{error}</p>}
  </div>;
}
