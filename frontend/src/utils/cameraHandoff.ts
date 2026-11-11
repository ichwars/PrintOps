const OPEN = 'printops:camera-overlay-open';
const REPLY = 'printops:camera-overlay-reply';
const WAIT_MS = 2000;

type OverlayRequest = { type: typeof OPEN; nonce: string; printerId: number; account: string; deadline: number };

export function requestCameraOverlay(printerId: number, account: string): Promise<boolean> {
  const opener = window.opener as Window | null;
  if (!opener || opener.closed) return Promise.resolve(false);
  const nonce = Math.random().toString(36).slice(2);
  const origin = window.location.origin;
  return new Promise((resolve) => {
    const finish = (accepted: boolean) => {
      window.clearTimeout(timeout);
      window.removeEventListener('message', receive);
      resolve(accepted);
    };
    const receive = (event: MessageEvent) => {
      if (event.origin === origin && event.source === opener && event.data?.type === REPLY && event.data.nonce === nonce) {
        finish(event.data.accepted === true);
      }
    };
    const timeout = window.setTimeout(() => finish(false), WAIT_MS);
    window.addEventListener('message', receive);
    try {
      opener.postMessage({
        type: OPEN, nonce, printerId, account, deadline: Date.now() + WAIT_MS - 200,
      } satisfies OverlayRequest, origin);
    } catch {
      finish(false);
    }
  });
}

export function listenForCameraOverlay(
  account: string,
  open: (id: number, stillCurrent: () => boolean) => Promise<boolean>,
): () => void {
  const origin = window.location.origin;
  let listening = true;
  const receive = async (event: MessageEvent<Partial<OverlayRequest>>) => {
    const request = event.data;
    const source = event.source as Window | null;
    if (
      event.origin !== origin || !source || source === window || request?.type !== OPEN || request.account !== account
      || typeof request.nonce !== 'string' || typeof request.printerId !== 'number'
      || !Number.isSafeInteger(request.printerId) || request.printerId <= 0 || typeof request.deadline !== 'number'
    ) return;
    const deadline = request.deadline;
    if (!(Date.now() <= deadline && deadline <= Date.now() + WAIT_MS)) return;
    const accepted = await open(request.printerId, () => listening && Date.now() <= deadline);
    if (listening) source.postMessage({ type: REPLY, nonce: request.nonce, accepted }, origin);
  };
  window.addEventListener('message', receive);
  return () => {
    listening = false;
    window.removeEventListener('message', receive);
  };
}
