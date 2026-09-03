import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { api } from '../../api/client';
import { lexwareApi, type LexwareConnection, type LexwarePreview, type LexwareResource } from '../../api/client/lexware';
import { LexwareSettings } from '../../components/settings/LexwareSettings';
import { LexwareImportReview } from '../../components/settings/lexware/LexwareImportReview';
import { LexwareResources } from '../../components/settings/lexware/LexwareResources';
import i18n from '../../i18n';
import { server } from '../mocks/server';

const auth = vi.hoisted(() => ({ permissions: ['*'], loading: false }));
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ loading: auth.loading, hasPermission: (permission: string) => auth.permissions.includes('*') || auth.permissions.includes(permission) }) }));
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ showToast: vi.fn() }) }));

const profiles = [{ id: 7, name: 'Studio Berlin', is_active: true }, { id: 8, name: 'Studio Hamburg', is_active: true }];
const connection: LexwareConnection = { id: 3, business_profile_id: 7, organization_id: 'org-one', company_name: 'Source GmbH', enabled: true, connected: true,
  version: 1, sync_status: 'idle', last_success_at: '2026-08-31T08:00:00Z', last_attempt_at: '2026-08-31T08:00:00Z', last_error: null };
const resource: LexwareResource = { id: 12, external_id: 'contact-12', name: 'Source customer', number: 'LEX-12', archived: false, version_hash: 'a'.repeat(64), customer_id: null, article_id: null, payload: {}, updated_at: '2026-08-31T08:00:00Z' };
const preview: LexwarePreview = { resource_id: 12, version_hash: 'a'.repeat(64), local_version: null, customer_id: null, article_id: null,
  source: { identity: { display_name: 'Source customer' }, addresses: [{ kind: 'billing', street: 'Source street' }], contacts: [], tax_identifiers: [] },
  current: {}, changes: [{ field: 'identity', current: null, incoming: { display_name: 'Source customer' } }, { field: 'addresses', current: null, incoming: [] }], affected_profiles: [], warnings: [] };
let clients: QueryClient[] = [];

function mount(ui = <LexwareSettings />) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } });
  clients.push(client);
  return { ...render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>), client };
}

function choose(label: string, option: string) {
  fireEvent.click(screen.getByRole('combobox', { name: label }));
  fireEvent.click(screen.getByRole('option', { name: option }));
}

async function connectionAction(name: string) {
  fireEvent.click(await screen.findByRole('button', { name: 'Connection actions' }));
  fireEvent.click(screen.getByRole('menuitem', { name }));
}

function handlers(connections: LexwareConnection[] = [connection], resources = [resource]) {
  server.use(
    http.get('/api/v1/business-profiles/', () => HttpResponse.json(profiles)),
    http.get('/api/v1/business-profiles/options', () => HttpResponse.json(profiles)),
    http.get('/api/v1/lexware/connections', () => HttpResponse.json(connections)),
    http.get('/api/v1/lexware/connections/3/resources', () => HttpResponse.json(resources)),
    http.get('/api/v1/customers/', () => HttpResponse.json({ items: [{ id: 44, account_number: 'LOCAL-44', display_name: 'Local customer' }], total: 1, limit: 25, offset: 0 })),
    http.get('/api/v1/warehouse-articles', () => HttpResponse.json({ items: [{ id: 91, sku: 'LOCAL-91', name: 'Local article' }], total: 1, limit: 25, offset: 0 })),
    http.get('/api/v1/small-parts/settings/units', () => HttpResponse.json([{ code: 'pcs', label: 'Pieces', is_active: true, decimal_places: 0 }])),
    http.post('/api/v1/lexware/connections/3/preview', () => HttpResponse.json(preview)),
    http.post('/api/v1/lexware/connections/3/import', () => HttpResponse.json({ customer_id: 44, unchanged: false })),
  );
}

beforeEach(async () => { auth.permissions = ['*']; auth.loading = false; await i18n.changeLanguage('en'); handlers(); });
afterEach(async () => { clients.forEach((client) => client.clear()); clients = []; vi.useRealTimers(); vi.restoreAllMocks(); await i18n.changeLanguage('en'); });

describe('Lexware setup and connection controls', () => {
  it('does not request data without integration permissions', async () => {
    auth.permissions = ['customers:read'];
    const requests = vi.spyOn(lexwareApi, 'connections');
    mount();
    expect(screen.getByRole('alert')).toHaveTextContent('permission to manage accounting integrations');
    expect(requests).not.toHaveBeenCalled();
  });

  it('uses profile options for integration-only users and shows no customer or article data', async () => {
    auth.permissions = ['accounting_integrations:manage'];
    const options = vi.spyOn(api, 'getBusinessProfileOptions');
    const resources = vi.spyOn(lexwareApi, 'resources');
    mount();
    expect(await screen.findByText('You do not have permission to read customers or inventory.')).toBeInTheDocument();
    expect(options).toHaveBeenCalled();
    expect(resources).not.toHaveBeenCalled();
  });

  it('requires a test before save and invalidates the organization on key or profile edits', async () => {
    handlers([]);
    const saves: unknown[] = [];
    server.use(
      http.post('/api/v1/lexware/connections/test', () => HttpResponse.json({ organization_id: 'org-two', company_name: 'Verified GmbH' })),
      http.post('/api/v1/lexware/connections', async ({ request }) => { saves.push(await request.json()); return HttpResponse.json(connection); }),
    );
    const { client } = mount();
    fireEvent.click(await screen.findByRole('button', { name: 'Set up connection' }));
    await screen.findByRole('combobox', { name: 'Business profile' });
    choose('Business profile', 'Studio Berlin');
    fireEvent.change(screen.getByLabelText('Lexware API key'), { target: { value: 'fake-only-key' } });
    expect(screen.getByLabelText('Lexware API key')).toHaveAttribute('type', 'password');
    expect(screen.getByRole('button', { name: 'Save connection' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }));
    await screen.findByText('Lexware organization: Verified GmbH');
    expect(screen.getByRole('button', { name: 'Save connection' })).toBeEnabled();
    choose('Business profile', 'Studio Hamburg');
    expect(screen.queryByText('Lexware organization: Verified GmbH')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save connection' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }));
    await screen.findByText('Lexware organization: Verified GmbH');
    fireEvent.change(screen.getByLabelText('Lexware API key'), { target: { value: 'fake-changed-key' } });
    expect(screen.getByRole('button', { name: 'Save connection' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }));
    await screen.findByText('Lexware organization: Verified GmbH');
    fireEvent.click(screen.getByRole('button', { name: 'Save connection' }));
    await waitFor(() => expect(saves).toEqual([{ business_profile_id: 8, api_key: 'fake-changed-key', organization_id: 'org-two' }]));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(screen.queryByLabelText('Lexware API key')).not.toBeInTheDocument();
    expect(JSON.stringify(client.getMutationCache().getAll())).not.toContain('fake-changed-key');
    expect(document.body.textContent).not.toContain('fake-changed-key');
    expect(localStorage.setItem).not.toHaveBeenCalledWith(expect.anything(), expect.stringContaining('fake-changed-key'));
  });

  it('rejects a replacement key for a different organization without updating the connection', async () => {
    handlers([connection]);
    const updates = vi.spyOn(lexwareApi, 'update');
    server.use(http.post('/api/v1/lexware/connections/test', () => HttpResponse.json({ organization_id: 'different-org', company_name: 'Other company' })));
    mount();
    await connectionAction('Manage key');
    const card = screen.getByRole('dialog', { name: 'Manage key' });
    fireEvent.change(within(card).getByLabelText('Lexware API key'), { target: { value: 'fake-key' } });
    fireEvent.click(within(card).getByRole('button', { name: 'Test connection' }));
    expect(await within(card).findByRole('alert')).toHaveTextContent('different organization');
    expect(within(card).getByRole('button', { name: 'Save connection' })).toBeDisabled();
    expect(updates).not.toHaveBeenCalled();
  });

  it('localizes request errors without rendering a provider error containing a token', async () => {
    await i18n.changeLanguage('de'); handlers([]);
    server.use(http.post('/api/v1/lexware/connections/test', () => HttpResponse.json({ detail: 'upstream failure fake-secret' }, { status: 503 })));
    mount();
    fireEvent.click(await screen.findByRole('button', { name: 'Verbindung einrichten' }));
    await screen.findByRole('combobox', { name: 'Unternehmensprofil' });
    choose('Unternehmensprofil', 'Studio Berlin');
    fireEvent.change(screen.getByLabelText('Lexware-API-Schlüssel'), { target: { value: 'fake-secret' } });
    fireEvent.click(screen.getByRole('button', { name: 'Verbindung testen' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Lexware ist nicht erreichbar');
    expect(document.body.textContent).not.toContain('fake-secret');
  });

  it('pauses, resumes and disconnects while preserving the saved resource list', async () => {
    let state = { ...connection };
    const changes: unknown[] = [];
    server.use(
      http.get('/api/v1/lexware/connections', () => HttpResponse.json([state])),
      http.patch('/api/v1/lexware/connections/3', async ({ request }) => { const body = await request.json() as { enabled: boolean }; changes.push(body); state = { ...state, ...body }; return HttpResponse.json(state); }),
      http.delete('/api/v1/lexware/connections/3', () => { state = { ...state, connected: false, enabled: false, sync_status: 'disconnected' }; return new HttpResponse(null, { status: 204 }); }),
    );
    mount();
    await connectionAction('Pause sync');
    await screen.findByText('Paused');
    expect(screen.getByRole('button', { name: 'Refresh now' })).toBeDisabled();
    await connectionAction('Resume sync');
    await screen.findByText('Connected');
    expect(changes).toEqual([{ enabled: false }, { enabled: true }]);
    await connectionAction('Disconnect');
    const confirmation = await screen.findByRole('dialog', { name: 'Disconnect Lexware Office?' });
    expect(state.connected).toBe(true);
    fireEvent.click(within(confirmation).getByRole('button', { name: 'Disconnect', exact: true }));
    await screen.findByText('Disconnected');
    expect(screen.getByRole('button', { name: 'Refresh now' })).toBeDisabled();
    expect(screen.getByText('Source customer')).toBeInTheDocument();
  });

  it('polls local status every five seconds for enabled connections and stops when paused', async () => {
    vi.useFakeTimers();
    vi.spyOn(api, 'getBusinessProfiles').mockResolvedValue([]);
    let state = { ...connection, sync_status: 'running' };
    const requests = vi.spyOn(lexwareApi, 'connections').mockImplementation(async () => [state]);
    vi.spyOn(lexwareApi, 'resources').mockResolvedValue([]);
    mount();
    await act(async () => { await vi.advanceTimersByTimeAsync(10); });
    expect(requests).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(4900); });
    expect(requests).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(110); });
    expect(requests).toHaveBeenCalledTimes(2);
    state = { ...state, sync_status: 'success' };
    await act(async () => { await vi.advanceTimersByTimeAsync(5010); });
    expect(requests).toHaveBeenCalledTimes(3);
    state = { ...state, enabled: false, sync_status: 'paused' };
    await act(async () => { await vi.advanceTimersByTimeAsync(5010); });
    expect(requests).toHaveBeenCalledTimes(4);
    await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
    expect(requests).toHaveBeenCalledTimes(4);
  });

  it('queues a manual sync once and disables another refresh while queued', async () => {
    let state = { ...connection };
    let calls = 0;
    server.use(
      http.get('/api/v1/lexware/connections', () => HttpResponse.json([state])),
      http.post('/api/v1/lexware/connections/3/sync', () => { calls++; state = { ...state, sync_status: 'queued' }; return HttpResponse.json({ status: 'queued' }, { status: 202 }); }),
    );
    mount();
    fireEvent.click(await screen.findByRole('button', { name: 'Refresh now' }));
    await screen.findByText('Queued');
    fireEvent.click(screen.getByRole('button', { name: 'Refresh now' }));
    expect(screen.getByRole('button', { name: 'Refresh now' })).toBeDisabled();
    expect(calls).toBe(1);
  });

  it('retains a successfully loaded snapshot after a failed refresh instead of showing an empty list', async () => {
    const { client } = mount(<LexwareResources connection={connection} />);
    await screen.findByText('Source customer');
    server.use(http.get('/api/v1/lexware/connections/3/resources', () => HttpResponse.json({ detail: 'offline' }, { status: 503 })));
    await act(async () => { await client.invalidateQueries({ queryKey: ['lexware', 'resources'] }); });
    await screen.findByText('The last successful data remains visible. An incomplete sync does not mean the source is empty.');
    expect(screen.getByText('Source customer')).toBeInTheDocument();
    expect(screen.queryByText('No saved external records yet. Run a complete refresh to fetch data.')).not.toBeInTheDocument();
  });

  it('renders loading, empty and retryable list errors distinctly', async () => {
    const request = vi.spyOn(lexwareApi, 'connections').mockRejectedValue(new Error('unreachable'));
    const { client } = mount();
    expect(screen.getAllByRole('status').length).toBeGreaterThan(0);
    await screen.findByRole('alert');
    expect(screen.queryByText('No Lexware connections yet.')).not.toBeInTheDocument();
    request.mockResolvedValue([]);
    await act(async () => { await client.invalidateQueries({ queryKey: ['lexware', 'connections'] }); });
    await screen.findByText('No Lexware connections yet.');
  });
});

describe('Lexware explicit imports', () => {
  it('opens a preview dialog without losing list filters, selection or return focus', async () => {
    mount(<LexwareResources connection={connection} />);
    const select = await screen.findByRole('checkbox', { name: 'Select: Source customer' });
    const search = screen.getByRole('searchbox', { name: 'Search external data' });
    fireEvent.change(search, { target: { value: 'Source' } });
    fireEvent.click(select);
    const trigger = screen.getByRole('button', { name: 'Review import: Source customer' });
    trigger.focus();
    fireEvent.click(trigger);
    const dialog = await screen.findByRole('dialog', { name: 'Import preview' });
    expect(within(dialog).getByText('Choose the fields you want to import into PrintOps.')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Customers' })).toContainElement(select);
    expect(search).toHaveValue('Source');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Close preview' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(select).toBeChecked();
    expect(search).toHaveValue('Source');
    expect(trigger).toHaveFocus();
  });

  it('blocks Escape, backdrop and cancel until a pending import finishes', async () => {
    let finish!: () => void;
    const pending = new Promise<{ customer_id: number; unchanged: boolean }>((resolve) => {
      finish = () => resolve({ customer_id: 44, unchanged: false });
    });
    const request = vi.spyOn(lexwareApi, 'import').mockReturnValue(pending);
    const close = vi.fn();
    const imported = vi.fn();
    mount(<LexwareImportReview connection={connection} kind="contacts" resources={[resource]} onClose={close} onImported={imported} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Import selected fields' }));
    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    const dialog = screen.getByRole('dialog', { name: 'Import preview' });
    expect(within(dialog).getByRole('button', { name: 'Close preview' })).toBeDisabled();
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toBeDisabled();
    fireEvent.keyDown(dialog, { key: 'Escape' });
    fireEvent.pointerDown(dialog.parentElement!);
    expect(close).not.toHaveBeenCalled();
    await act(async () => { finish(); await pending; });
    await waitFor(() => expect(imported).toHaveBeenCalledOnce());
  });

  it('selects only visible new customers and never archived or linked rows', async () => {
    handlers([connection], [resource,
      { ...resource, id: 13, name: 'Hidden by filter' },
      { ...resource, id: 14, name: 'Source archived', archived: true },
      { ...resource, id: 15, name: 'Source linked', customer_id: 44 },
    ]);
    mount(<LexwareResources connection={connection} />);
    await screen.findByRole('checkbox', { name: 'Select: Source customer' });
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search external data' }), { target: { value: 'Source' } });
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select new customers on this page' }));
    expect(screen.getByRole('checkbox', { name: 'Select: Source customer' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Select: Source archived' })).toBeDisabled();
    expect(screen.getByRole('checkbox', { name: 'Select: Source linked' })).toBeDisabled();
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search external data' }), { target: { value: '' } });
    expect(screen.getByRole('checkbox', { name: 'Select: Hidden by filter' })).not.toBeChecked();
    expect(screen.getByRole('button', { name: 'Review selected new customers (1)' })).toBeEnabled();
  });

  it.each([false, true])('adopts the customer number with explicit consent for existing=%s', async (existing) => {
    let imported: unknown;
    server.use(
      http.post('/api/v1/lexware/connections/3/preview', () => HttpResponse.json({
        ...preview, customer_id: existing ? 44 : null, local_version: existing ? 5 : null,
        source: { ...preview.source, customer_number: 'LEX-12' },
        current: existing ? { customer_number: 'LOCAL-44' } : {},
        changes: [...preview.changes, { field: 'customer_number', current: existing ? 'LOCAL-44' : null, incoming: 'LEX-12' }],
      })),
      http.post('/api/v1/lexware/connections/3/import', async ({ request }) => {
        imported = await request.json(); return HttpResponse.json({ customer_id: 44, unchanged: false });
      }),
    );
    mount(<LexwareImportReview connection={connection} kind="contacts" resources={[{ ...resource, customer_id: existing ? 44 : null }]} onClose={vi.fn()} onImported={vi.fn()} />);
    const number = await screen.findByRole('checkbox', { name: 'Customer number' });
    if (existing) {
      expect(number).not.toBeChecked();
      expect(screen.getByText('LOCAL-44')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Import selected fields' })).toBeDisabled();
      fireEvent.click(number);
    } else {
      expect(number).toBeChecked();
    }
    fireEvent.click(screen.getByRole('button', { name: 'Import selected fields' }));
    await waitFor(() => expect(imported).toMatchObject({
      fields: existing ? ['customer_number'] : ['identity', 'addresses', 'customer_number'],
      local_version: existing ? 5 : null,
    }));
  });

  it('explains a duplicate customer number without exposing the raw error', async () => {
    await i18n.changeLanguage('de');
    server.use(http.post('/api/v1/lexware/connections/3/import', () => HttpResponse.json({
      detail: { code: 'customer_number_conflict', message: 'raw-sensitive-provider-error' },
    }, { status: 409 })));
    mount(<LexwareImportReview connection={connection} kind="contacts" resources={[resource]} onClose={vi.fn()} onImported={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Ausgewählte Felder importieren' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Diese Kundennummer ist im Unternehmensprofil bereits vergeben.');
    expect(document.body.textContent).not.toContain('raw-sensitive-provider-error');
  });

  it('shows source/current and shared profiles, then submits only the chosen field with reviewed versions', async () => {
    let target: unknown;
    let imported: unknown;
    server.use(
      http.post('/api/v1/lexware/connections/3/preview', async ({ request }) => {
        target = await request.json();
        return HttpResponse.json({ ...preview, customer_id: 44, local_version: 9, current: { identity: { display_name: 'Local customer' } }, affected_profiles: [{ id: 7, name: 'Studio Berlin' }, { id: 8, name: 'Studio Hamburg' }] });
      }),
      http.post('/api/v1/lexware/connections/3/import', async ({ request }) => { imported = await request.json(); return HttpResponse.json({ customer_id: 44, unchanged: false }); }),
    );
    const done = vi.fn();
    mount(<LexwareImportReview connection={connection} kind="contacts" resources={[{ ...resource, customer_id: 44 }]} onClose={vi.fn()} onImported={done} />);
    await screen.findByText('Original source: Lexware');
    expect(screen.getByText('Current local data: PrintOps')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Studio BerlinStudio Hamburg');
    expect(screen.getByRole('button', { name: 'Import selected fields' })).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Name and identity' }));
    fireEvent.click(screen.getByRole('button', { name: 'Import selected fields' }));
    await waitFor(() => expect(done).toHaveBeenCalled());
    expect(target).toEqual({ resource_id: 12, customer_id: 44 });
    expect(imported).toEqual({ resource_id: 12, version_hash: 'a'.repeat(64), local_version: 9, customer_id: 44, fields: ['identity'] });
  });

  it('uses a profile-scoped paginated customer lookup and requires a new preview after target selection', async () => {
    const lookups: URLSearchParams[] = [];
    const previews: unknown[] = [];
    server.use(
      http.get('/api/v1/customers/', ({ request }) => { lookups.push(new URL(request.url).searchParams); return HttpResponse.json({ items: [{ id: 44, account_number: 'LOCAL-44', display_name: 'Local customer' }], total: 26, limit: 25, offset: 0 }); }),
      http.post('/api/v1/lexware/connections/3/preview', async ({ request }) => { const body = await request.json() as { customer_id: number | null }; previews.push(body); return HttpResponse.json({ ...preview, customer_id: body.customer_id, local_version: body.customer_id ? 6 : null }); }),
    );
    mount(<LexwareImportReview connection={connection} kind="contacts" resources={[resource]} onClose={vi.fn()} onImported={vi.fn()} />);
    await screen.findByRole('checkbox', { name: 'Name and identity' });
    await waitFor(() => expect(lookups).toHaveLength(1));
    choose('Local target', 'LOCAL-44 — Local customer');
    await waitFor(() => expect(previews).toContainEqual({ resource_id: 12, customer_id: 44 }));
    await waitFor(() => expect(screen.getByRole('checkbox', { name: 'Name and identity' })).not.toBeChecked());
    expect(lookups[0].get('business_profile_id')).toBe('7');
    fireEvent.change(screen.getByLabelText('Search local targets'), { target: { value: 'Local' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search local targets' }));
    await waitFor(() => expect(lookups.at(-1)?.get('search')).toBe('Local'));
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    await waitFor(() => expect(lookups.at(-1)?.get('offset')).toBe('25'));
  });

  it('blocks a stale preview after conflict until it is explicitly refreshed', async () => {
    let previews = 0;
    const imports: unknown[] = [];
    server.use(
      http.post('/api/v1/lexware/connections/3/preview', () => HttpResponse.json({ ...preview, version_hash: (++previews === 1 ? 'a' : 'b').repeat(64) })),
      http.post('/api/v1/lexware/connections/3/import', async ({ request }) => { imports.push(await request.json()); return imports.length === 1 ? HttpResponse.json({ detail: 'changed' }, { status: 409 }) : HttpResponse.json({ customer_id: 44, unchanged: false }); }),
    );
    mount(<LexwareImportReview connection={connection} kind="contacts" resources={[resource]} onClose={vi.fn()} onImported={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Import selected fields' }));
    await screen.findByText('The source or local record changed. Refresh the preview and review it again.');
    expect(screen.getByRole('button', { name: 'Import selected fields' })).toBeDisabled();
    expect(previews).toBe(1);
    fireEvent.click(screen.getByRole('button', { name: 'Refresh preview' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Import selected fields' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Import selected fields' }));
    await waitFor(() => expect(imports).toHaveLength(2));
    expect(imports[1]).toMatchObject({ version_hash: 'b'.repeat(64), local_version: null });
  });

  it('reviews selected new customers together and does not retry completed records after a partial failure', async () => {
    const second = { ...resource, id: 13, name: 'Second customer', external_id: 'contact-13' };
    handlers([connection], [resource, second, { ...resource, id: 14, name: 'Archived customer', archived: true }]);
    const imported: number[] = [];
    let fail = true;
    server.use(
      http.post('/api/v1/lexware/connections/3/preview', async ({ request }) => { const body = await request.json() as { resource_id: number }; return HttpResponse.json({ ...preview, resource_id: body.resource_id }); }),
      http.post('/api/v1/lexware/connections/3/import', async ({ request }) => { const body = await request.json() as { resource_id: number }; imported.push(body.resource_id); if (body.resource_id === 13 && fail) { fail = false; return HttpResponse.json({ detail: 'failure' }, { status: 503 }); } return HttpResponse.json({ customer_id: body.resource_id, unchanged: false }); }),
    );
    mount(<LexwareResources connection={connection} />);
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Select: Source customer' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select: Second customer' }));
    expect(screen.getByRole('checkbox', { name: 'Select: Archived customer' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: /Review selected new customers/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Import selected fields' }));
    await screen.findByText('Some records were imported before an error. Completed records will not be imported again.');
    fireEvent.click(screen.getByRole('button', { name: 'Import selected fields' }));
    await waitFor(() => expect(imported).toEqual([12, 13, 13]));
  });

  it('requires explicit article kind, unit and stock source and never sends the sale price as a cost', async () => {
    const articlePreview = { ...preview, source: { name: 'Consulting', sale_price: '123.4567', tax_rate: '19', unit_name: 'unknown external unit', external_type: 'SERVICE' },
      changes: [{ field: 'name', current: null, incoming: 'Consulting' }, { field: 'sale_price', current: null, incoming: '123.4567' }] };
    let body: unknown;
    server.use(
      http.post('/api/v1/lexware/connections/3/preview', () => HttpResponse.json(articlePreview)),
      http.post('/api/v1/lexware/connections/3/import', async ({ request }) => { body = await request.json(); return HttpResponse.json({ article_id: 91, unchanged: false }); }),
    );
    mount(<LexwareImportReview connection={connection} kind="articles" resources={[resource]} onClose={vi.fn()} onImported={vi.fn()} />);
    await screen.findByText('123.4567');
    expect(screen.getByRole('button', { name: 'Import selected fields' })).toBeDisabled();
    fireEvent.change(screen.getByRole('textbox', { name: 'Local article number' }), { target: { value: 'SERVICE-01' } });
    choose('Article kind', 'Service');
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Confirmed local unit' })).toBeEnabled());
    choose('Confirmed local unit', 'Pieces (pcs)');
    expect(screen.getByRole('combobox', { name: 'Stock source' })).toHaveTextContent('No inventory (service)');
    fireEvent.click(screen.getByRole('button', { name: 'Import selected fields' }));
    await waitFor(() => expect(body).toMatchObject({ article_id: null, local_version: null, fields: ['name', 'sale_price'], article_options: { sku: 'SERVICE-01', kind: 'service', unit_code: 'pcs', stock_source: 'none', small_part_id: null } }));
    expect(JSON.stringify(body)).not.toContain('unit_cost');
  });

  it('allows preview but not customer import without customer-manage permission', async () => {
    auth.permissions = ['accounting_integrations:manage', 'customers:read'];
    mount(<LexwareImportReview connection={connection} kind="contacts" resources={[resource]} onClose={vi.fn()} onImported={vi.fn()} />);
    await screen.findByText('You do not have permission to import into this local target.');
    expect(screen.getByRole('button', { name: 'Import selected fields' })).toBeDisabled();
  });

  it('requires a matching material unit and resets the selection when the unit changes', async () => {
    server.use(
      http.post('/api/v1/lexware/connections/3/preview', () => HttpResponse.json({ ...preview, source: { name: 'Product', unit_name: 'piece', external_type: 'PRODUCT' }, changes: [{ field: 'name', current: null, incoming: 'Product' }] })),
      http.get('/api/v1/small-parts/settings/units', () => HttpResponse.json([
        { code: 'pcs', label: 'Pieces', is_active: true }, { code: 'kg', label: 'Kilograms', is_active: true },
      ])),
      http.get('/api/v1/small-parts', () => HttpResponse.json({ items: [
        { id: 21, sku: 'MAT-PCS', name: 'Piece material', unit_code: 'pcs' },
        { id: 22, sku: 'MAT-KG', name: 'Mass material', unit_code: 'kg' },
      ], total: 2, limit: 25, offset: 0 })),
    );
    mount(<LexwareImportReview connection={connection} kind="articles" resources={[resource]} onClose={vi.fn()} onImported={vi.fn()} />);
    fireEvent.change(await screen.findByRole('textbox', { name: 'Local article number' }), { target: { value: 'ARTICLE-1' } });
    choose('Article kind', 'Merchandise');
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Confirmed local unit' })).toBeEnabled());
    choose('Confirmed local unit', 'Pieces (pcs)');
    choose('Stock source', 'Existing material inventory');
    expect(screen.getByRole('button', { name: 'Import selected fields' })).toBeDisabled();
    fireEvent.click(screen.getByRole('combobox', { name: 'Existing material' }));
    expect(await screen.findByRole('option', { name: 'MAT-KG — Mass material (kg)' })).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(screen.getByRole('option', { name: 'MAT-PCS — Piece material (pcs)' }));
    expect(screen.getByRole('button', { name: 'Import selected fields' })).toBeEnabled();
    choose('Confirmed local unit', 'Kilograms (kg)');
    expect(screen.getByRole('combobox', { name: 'Existing material' })).toHaveTextContent('Select…');
    expect(screen.getByRole('button', { name: 'Import selected fields' })).toBeDisabled();
  });

  it('renders normalized German address labels and treats external markup as plain text', async () => {
    await i18n.changeLanguage('de');
    server.use(http.post('/api/v1/lexware/connections/3/preview', () => HttpResponse.json({ ...preview,
      source: { identity: { display_name: '<img src=x onerror=alert(1)>' }, addresses: [{ kind: 'billing', street: 'Hauptstraße 1' }, { kind: 'delivery', street: 'Lieferstraße 2' }] },
    })));
    mount(<LexwareImportReview connection={connection} kind="contacts" resources={[resource]} onClose={vi.fn()} onImported={vi.fn()} />);
    await screen.findByText('Rechnungsadresse');
    expect(screen.getByText('Lieferadresse')).toBeInTheDocument();
    const identityDetails = screen.getByText('Anzeigename').closest('details')!;
    expect(identityDetails).not.toHaveAttribute('open');
    fireEvent.click(identityDetails.querySelector('summary')!);
    expect(screen.getByText('Anzeigename')).toBeVisible();
    expect(screen.getAllByText('<img src=x onerror=alert(1)>')).toHaveLength(2);
    expect(screen.getByRole('dialog', { name: 'Übernahmevorschau' }).querySelector('img')).toBeNull();
  });

  it('uses the warehouse client for existing article targets and sends only chosen fields', async () => {
    auth.permissions = ['accounting_integrations:manage', 'inventory:read', 'inventory:update'];
    let body: unknown;
    const done = vi.fn();
    server.use(
      http.post('/api/v1/lexware/connections/3/preview', async ({ request }) => {
        const target = await request.json() as { article_id: number | null };
        return HttpResponse.json({ ...preview, article_id: target.article_id, local_version: target.article_id ? 3 : null,
          source: { name: 'Product', sale_price: '42.75', external_type: 'PRODUCT', unit_name: 'piece' }, current: target.article_id ? { name: 'Local article', sale_price: '30.25', unit_code: 'pcs', kind: 'trade', stock_source: 'own' } : {},
          changes: [{ field: 'name', current: 'Local article', incoming: 'Product' }, { field: 'sale_price', current: '30.25', incoming: '42.75' }] });
      }),
      http.post('/api/v1/lexware/connections/3/import', async ({ request }) => { body = await request.json(); return HttpResponse.json({ article_id: 91, unchanged: false }); }),
    );
    mount(<LexwareImportReview connection={connection} kind="articles" resources={[resource]} onClose={vi.fn()} onImported={done} />);
    await screen.findByText('You do not have permission to import into this local target.');
    choose('Local target', 'LOCAL-91 — Local article');
    await screen.findByText('30.25');
    expect(screen.queryByRole('textbox', { name: 'Local article number' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Link without changing fields' })).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: 'I confirm that one Lexware unit corresponds to one local unit.' }));
    expect(screen.getByRole('button', { name: 'Link without changing fields' })).toBeEnabled();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Sale price' }));
    fireEvent.click(screen.getByRole('button', { name: 'Import selected fields' }));
    await waitFor(() => expect(done).toHaveBeenCalled());
    expect(body).toEqual({ resource_id: 12, article_id: 91, version_hash: 'a'.repeat(64), local_version: 3, fields: ['sale_price'], confirmed_unit_code: 'pcs' });
  });

  it('requires fresh explicit unit confirmation for existing article imports and submits the reviewed unit and version', async () => {
    let version = 3;
    let body: unknown;
    const done = vi.fn();
    server.use(
      http.post('/api/v1/lexware/connections/3/preview', () => HttpResponse.json({ ...preview, article_id: 91, local_version: version,
        source: { name: 'Product', sale_price: '42.75', external_type: 'PRODUCT', unit_name: 'kg' },
        current: { name: 'Local article', sale_price: '30.25', unit_code: 'pcs', kind: 'trade', stock_source: 'own' },
        changes: [{ field: 'sale_price', current: '30.25', incoming: '42.75' }] })),
      http.post('/api/v1/lexware/connections/3/import', async ({ request }) => { body = await request.json(); return HttpResponse.json({ article_id: 91, unchanged: false }); }),
    );
    mount(<LexwareImportReview connection={connection} kind="articles" resources={[{ ...resource, article_id: 91 }]} onClose={vi.fn()} onImported={done} />);
    const label = 'I confirm that one Lexware unit corresponds to one local unit.';
    expect(await screen.findByRole('checkbox', { name: label })).not.toBeChecked();
    expect(screen.getByText('Lexware unit').nextElementSibling).toHaveTextContent('kg');
    expect(screen.getByText('Current local unit').nextElementSibling).toHaveTextContent('pcs');
    expect(screen.getByText(/Import uses a 1:1 basis/)).toHaveTextContent('No conversion is performed and the local unit is not changed.');
    fireEvent.click(screen.getByRole('checkbox', { name: 'Sale price' }));
    const button = screen.getByRole('button', { name: 'Import selected fields' });
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(body).toBeUndefined();
    fireEvent.click(screen.getByRole('checkbox', { name: label }));
    expect(button).toBeEnabled();
    version = 4;
    fireEvent.click(screen.getByRole('button', { name: 'Refresh preview' }));
    expect(await screen.findByRole('checkbox', { name: label })).not.toBeChecked();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Sale price' }));
    expect(screen.getByRole('button', { name: 'Import selected fields' })).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: label }));
    fireEvent.click(screen.getByRole('button', { name: 'Import selected fields' }));
    await waitFor(() => expect(done).toHaveBeenCalled());
    expect(body).toEqual({ resource_id: 12, article_id: 91, version_hash: 'a'.repeat(64), local_version: 4, fields: ['sale_price'], confirmed_unit_code: 'pcs' });
  });

  it('can link matching local records without overwriting any fields', async () => {
    let body: unknown;
    server.use(
      http.post('/api/v1/lexware/connections/3/preview', async ({ request }) => {
        const target = await request.json() as { customer_id: number | null };
        return HttpResponse.json({ ...preview, customer_id: target.customer_id, local_version: target.customer_id ? 6 : null, changes: target.customer_id ? [] : preview.changes });
      }),
      http.post('/api/v1/lexware/connections/3/import', async ({ request }) => { body = await request.json(); return HttpResponse.json({ customer_id: 44, unchanged: false }); }),
    );
    const done = vi.fn();
    mount(<LexwareImportReview connection={connection} kind="contacts" resources={[resource]} onClose={vi.fn()} onImported={done} />);
    await screen.findByRole('checkbox', { name: 'Name and identity' });
    choose('Local target', 'LOCAL-44 — Local customer');
    fireEvent.click(await screen.findByRole('button', { name: 'Link without changing fields' }));
    await waitFor(() => expect(done).toHaveBeenCalled());
    expect(body).toMatchObject({ customer_id: 44, local_version: 6, fields: [] });
  });

  it('does not import archived or disconnected snapshots', async () => {
    mount(<LexwareImportReview connection={{ ...connection, connected: false }} kind="contacts" resources={[{ ...resource, archived: true }]} onClose={vi.fn()} onImported={vi.fn()} />);
    await screen.findByText('Archived Lexware records cannot be imported.');
    expect(screen.getByText('Reconnect Lexware before importing saved data.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Import selected fields' })).toBeDisabled();
  });
});
