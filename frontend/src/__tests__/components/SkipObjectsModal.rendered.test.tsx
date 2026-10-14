import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SkipObjectsModal } from '../../components/SkipObjectsModal';
import { server } from '../mocks/server';

const auth = vi.hoisted(() => ({ canControl: true }));
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ hasPermission: (permission: string) => permission === 'printers:control' && auth.canControl }),
}));
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ showToast: vi.fn() }) }));

const part = (id: number, name: string, skipped = false) => ({ id, name, x: null, y: null, skipped });
let objects = [part(100, 'Part A'), part(200, 'Part B'), part(300, 'Part C')];
let layer = 2;
let requests: unknown[];
let client: QueryClient;

function response() {
  return { objects, total: objects.length, skipped_count: objects.filter((o) => o.skipped).length,
    is_printing: true, bbox_all: null };
}

async function openModal() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  render(<QueryClientProvider client={client}>
    <SkipObjectsModal printerId={7} isOpen onClose={vi.fn()} />
  </QueryClientProvider>);
  await screen.findByRole('button', { name: /Part A/ });
  await waitFor(() => expect(screen.queryByText('Unavailable')).not.toBeInTheDocument());
}

function clickPlate(id: 100 | 200) {
  fireEvent.click(screen.getAllByLabelText('Select objects you want to skip from the current print')[0], { clientX: id === 100 ? 50 : 150, clientY: 100 });
}

async function refetchObjects() {
  await act(async () => { await client.invalidateQueries({ queryKey: ['printableObjects', 7] }); });
  await waitFor(() => {
    if (objects.some((object) => object.id === 100)) {
      expect(screen.getByRole('button', { name: /Part A/ })).toBeDisabled();
    } else {
      expect(screen.queryByRole('button', { name: /Part A/ })).not.toBeInTheDocument();
    }
  });
}

function confirmButton() {
  return within(screen.getByRole('dialog')).getByRole('button', { name: 'Skip Selected' });
}

beforeEach(() => {
  auth.canControl = true;
  objects = [part(100, 'Part A'), part(200, 'Part B'), part(300, 'Part C')];
  layer = 2;
  requests = [];
  server.use(
    http.get('*/api/v1/printers/7/status', () => HttpResponse.json({ layer_num: layer, cover_url: '/plate.png' })),
    http.get('*/api/v1/printers/7/print/objects', () => HttpResponse.json(response())),
    http.post('*/api/v1/printers/7/print/skip-objects', async ({ request }) => {
      requests.push(await request.json());
      return HttpResponse.json({ success: true, message: 'Objects skipped', skipped_objects: requests.at(-1) });
    }),
  );
  // jsdom cannot decode images or draw canvases. Keep production picking and
  // coordinate mapping real; only supply a two-pixel RGB mask at the browser boundary.
  vi.stubGlobal('Image', class {
    naturalWidth = 2;
    naturalHeight = 1;
    onload: (() => void) | null = null;
    set src(_value: string) { queueMicrotask(() => this.onload?.()); }
  });
  vi.spyOn(HTMLCanvasElement.prototype, 'getBoundingClientRect').mockReturnValue({
    left: 0, top: 0, width: 200, height: 200, right: 200, bottom: 200, x: 0, y: 0, toJSON: () => ({}),
  });
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => ({
    drawImage: vi.fn(), putImageData: vi.fn(),
    getImageData: () => ({ width: 2, height: 1, data: new Uint8ClampedArray([100, 0, 0, 255, 200, 0, 0, 255]) }),
    createImageData: (width: number, height: number) => ({ width, height, data: new Uint8ClampedArray(width * height * 4) }),
  }) as unknown as CanvasRenderingContext2D);
});

afterEach(() => { client?.clear(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('SkipObjectsModal rendered selection', () => {
  it('picks from the plate and sends only the confirmed object through the API', async () => {
    await openModal();
    clickPlate(100);
    fireEvent.click(screen.getByRole('button', { name: 'Skip Selected' }));
    expect(screen.getByRole('dialog')).toHaveTextContent('Are you sure you want to skip "Part A"?');
    expect(requests).toEqual([]);
    fireEvent.click(confirmButton());
    await waitFor(() => expect(requests).toEqual([[100]]));
  });

  it.each(['skipped', 'removed'] as const)('removes a %s object from the selection after refetch', async (change) => {
    await openModal();
    clickPlate(100);
    objects = change === 'skipped' ? [part(100, 'Part A', true), part(200, 'Part B')] : [part(200, 'Part B')];
    await refetchObjects();
    expect(screen.getByRole('button', { name: 'Skip Selected' })).toBeDisabled();
    expect(screen.getByText('No objects selected')).toBeInTheDocument();
    expect(requests).toEqual([]);
  });

  it('keeps active selections but excludes stale IDs while confirmation is open', async () => {
    await openModal();
    clickPlate(100);
    clickPlate(200);
    fireEvent.click(screen.getByRole('button', { name: 'Skip Selected' }));
    objects = [part(100, 'Part A', true), part(200, 'Part B'), part(300, 'Part C')];
    await refetchObjects();
    expect(screen.getByRole('dialog')).toHaveTextContent('Are you sure you want to skip "Part B"?');
    fireEvent.click(confirmButton());
    await waitFor(() => expect(requests).toEqual([[200]]));
  });

  it('blocks an open confirmation when no selected object remains active', async () => {
    await openModal();
    clickPlate(100);
    fireEvent.click(screen.getByRole('button', { name: 'Skip Selected' }));
    objects = [part(100, 'Part A', true), part(200, 'Part B')];
    await refetchObjects();
    expect(confirmButton()).toBeDisabled();
    fireEvent.click(confirmButton());
    expect(requests).toEqual([]);
  });

  it.each([0, 1])('blocks submitting selected objects at layer %i', async (blockedLayer) => {
    layer = blockedLayer;
    await openModal();
    clickPlate(100);
    expect(screen.getByRole('button', { name: 'Skip Selected' })).toBeDisabled();
    expect(requests).toEqual([]);
  });

  it('blocks submitting selected objects without printer control permission', async () => {
    auth.canControl = false;
    await openModal();
    clickPlate(100);
    expect(screen.getByRole('button', { name: 'Skip Selected' })).toBeDisabled();
    expect(requests).toEqual([]);
  });
});
