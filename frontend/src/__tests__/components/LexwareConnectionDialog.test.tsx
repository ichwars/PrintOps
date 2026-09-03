import { useState } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { lexwareApi, type LexwareConnection, type LexwareOrganization } from '../../api/client/lexware';
import { LexwareConnectionCard } from '../../components/settings/lexware/LexwareConnectionCard';
import { LexwareConnectionDialog } from '../../components/settings/lexware/LexwareConnectionDialog';
import i18n from '../../i18n';

vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ showToast: vi.fn() }) }));

const profiles = [{ id: 7, name: 'Studio Berlin' }, { id: 8, name: 'Studio Hamburg' }];
const organization: LexwareOrganization = { organization_id: 'org-one', company_name: 'Source GmbH' };
const connection: LexwareConnection = {
  id: 3, business_profile_id: 7, ...organization, enabled: true, connected: true, version: 1,
  sync_status: 'idle', last_success_at: '2026-08-31T08:00:00Z', last_attempt_at: '2026-08-31T08:00:00Z', last_error: null,
};
const clients: QueryClient[] = [];

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

function Setup({ onSaved = async () => undefined }: { onSaved?: () => Promise<unknown> }) {
  const [open, setOpen] = useState(true);
  return <><button onClick={() => setOpen(true)}>Open setup</button>{open && <LexwareConnectionDialog profiles={profiles}
    onClose={() => setOpen(false)} onSaved={onSaved} />}</>;
}

function mount(ui = <Setup />) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  clients.push(client);
  return { ...render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>), client };
}

function chooseProfile(name = 'Studio Berlin') {
  fireEvent.click(screen.getByRole('combobox', { name: 'Business profile' }));
  fireEvent.click(screen.getByRole('option', { name }));
}

function enterKey() {
  chooseProfile();
  fireEvent.change(screen.getByLabelText('Lexware API key'), { target: { value: 'fake-only-key' } });
  fireEvent.click(screen.getByRole('button', { name: 'Test connection' }));
}

function tryClosingBusyDialog() {
  const dialog = screen.getByRole('dialog');
  expect(screen.getByRole('button', { name: 'Close connection setup' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Close connection setup' }));
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  fireEvent.keyDown(dialog, { key: 'Escape' });
  fireEvent.pointerDown(dialog.parentElement!);
  expect(screen.getByRole('dialog')).toBeInTheDocument();
}

beforeEach(async () => { await i18n.changeLanguage('en'); });
afterEach(async () => {
  clients.splice(0).forEach((client) => client.clear());
  vi.restoreAllMocks();
  await i18n.changeLanguage('en');
});

describe('Lexware connection dialog', () => {
  it('blocks every close path while testing, and requires a new test after key or profile changes', async () => {
    const request = deferred<LexwareOrganization>();
    const test = vi.spyOn(lexwareApi, 'test').mockReturnValue(request.promise);
    mount();
    expect(screen.getByRole('button', { name: 'Save connection' })).toBeDisabled();
    enterKey();
    expect(screen.getByLabelText('Lexware API key')).toHaveAttribute('type', 'password');
    tryClosingBusyDialog();
    expect(test).toHaveBeenCalledExactlyOnceWith('fake-only-key');
    await act(async () => request.resolve(organization));
    expect(screen.getByRole('button', { name: 'Save connection' })).toBeEnabled();
    fireEvent.change(screen.getByLabelText('Lexware API key'), { target: { value: 'fake-next-key' } });
    expect(screen.queryByText('Organization verified')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save connection' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }));
    await screen.findByText('Organization verified');
    chooseProfile('Studio Hamburg');
    expect(screen.queryByText('Organization verified')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save connection' })).toBeDisabled();
  });

  it('stays open through save and invalidation, then closes without caching the key', async () => {
    const saved = deferred<LexwareConnection>();
    const refreshed = deferred<void>();
    vi.spyOn(lexwareApi, 'test').mockResolvedValue(organization);
    const create = vi.spyOn(lexwareApi, 'create').mockReturnValue(saved.promise);
    const onSaved = vi.fn(() => refreshed.promise);
    const { client } = mount(<Setup onSaved={onSaved} />);
    enterKey();
    await screen.findByText('Organization verified');
    fireEvent.click(screen.getByRole('button', { name: 'Save connection' }));
    tryClosingBusyDialog();
    fireEvent.submit(screen.getByLabelText('Lexware API key').closest('form')!);
    expect(create).toHaveBeenCalledExactlyOnceWith({ business_profile_id: 7, api_key: 'fake-only-key', organization_id: 'org-one' });
    await act(async () => saved.resolve(connection));
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText('Lexware API key')).toHaveValue('');
    tryClosingBusyDialog();
    expect(JSON.stringify(client.getMutationCache().getAll())).not.toContain('fake-only-key');
    expect(JSON.stringify(client.getQueryCache().getAll())).not.toContain('fake-only-key');
    expect(localStorage.setItem).not.toHaveBeenCalledWith(expect.anything(), expect.stringContaining('fake-only-key'));
    await act(async () => refreshed.resolve());
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('keeps the dialog open if post-save invalidation fails and clears the secret', async () => {
    vi.spyOn(lexwareApi, 'test').mockResolvedValue(organization);
    vi.spyOn(lexwareApi, 'create').mockResolvedValue(connection);
    mount(<Setup onSaved={async () => { throw new Error('invalidation fake-only-key'); }} />);
    enterKey();
    await screen.findByText('Organization verified');
    fireEvent.click(screen.getByRole('button', { name: 'Save connection' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The connection was saved, but the view could not be refreshed.');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByLabelText('Lexware API key')).toHaveValue('');
    expect(screen.queryByText('Organization verified')).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain('fake-only-key');
    expect(screen.getByRole('button', { name: 'Save connection' })).toBeDisabled();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('rejects a replacement key for a different organization', async () => {
    vi.spyOn(lexwareApi, 'test').mockResolvedValue({ organization_id: 'org-other', company_name: 'Other company' });
    const update = vi.spyOn(lexwareApi, 'update');
    mount(<LexwareConnectionDialog profiles={profiles} connection={connection} onClose={vi.fn()} onSaved={async () => undefined} />);
    expect(screen.getByRole('combobox', { name: 'Business profile' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Lexware API key'), { target: { value: 'fake-only-key' } });
    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('different organization');
    expect(screen.getByRole('button', { name: 'Save connection' })).toBeDisabled();
    expect(update).not.toHaveBeenCalled();
  });

  it('reconnects only after validating the replacement key against the saved organization', async () => {
    vi.spyOn(lexwareApi, 'test').mockResolvedValue(organization);
    const update = vi.spyOn(lexwareApi, 'update').mockResolvedValue(connection);
    const onClose = vi.fn();
    mount(<LexwareConnectionDialog profiles={profiles} connection={{ ...connection, connected: false, enabled: false }}
      onClose={onClose} onSaved={async () => undefined} />);
    fireEvent.change(screen.getByLabelText('Lexware API key'), { target: { value: 'fake-only-key' } });
    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }));
    await screen.findByText('Organization verified');
    fireEvent.click(screen.getByRole('button', { name: 'Save connection' }));
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(update).toHaveBeenCalledExactlyOnceWith(3, { api_key: 'fake-only-key', enabled: true });
  });

  it('discards the typed key and organization check when the dialog unmounts', async () => {
    vi.spyOn(lexwareApi, 'test').mockResolvedValue(organization);
    mount();
    enterKey();
    await screen.findByText('Organization verified');
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    fireEvent.click(screen.getByRole('button', { name: 'Open setup' }));
    expect(screen.getByLabelText('Lexware API key')).toHaveValue('');
    expect(screen.queryByText('Organization verified')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save connection' })).toBeDisabled();
  });
});

describe('Lexware connection banner overflow', () => {
  it('supports arrow keys, Escape, outside dismissal and restores focus after managing the key', async () => {
    const user = userEvent.setup();
    mount(<LexwareConnectionCard connection={connection} profileName="Studio Berlin" />);
    const trigger = screen.getByRole('button', { name: 'Connection actions' });
    expect(screen.queryByLabelText('Lexware API key')).not.toBeInTheDocument();
    trigger.focus();
    await user.keyboard('{ArrowDown}');
    expect(screen.getByRole('menuitem', { name: 'Manage key' })).toHaveFocus();
    await user.keyboard('{ArrowDown}');
    expect(screen.getByRole('menuitem', { name: 'Pause sync' })).toHaveFocus();
    await user.keyboard('{End}');
    expect(screen.getByRole('menuitem', { name: 'Disconnect' })).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    await user.click(trigger);
    await user.click(screen.getByRole('menuitem', { name: 'Manage key' }));
    expect(screen.getByRole('dialog', { name: 'Manage key' })).toBeInTheDocument();
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(trigger).toHaveFocus();
    await user.keyboard('{ArrowUp}');
    expect(screen.getByRole('menuitem', { name: 'Disconnect' })).toHaveFocus();
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('dismisses the menu on Tab and exposes pause, resume and disconnect through real actions', async () => {
    const user = userEvent.setup();
    const update = vi.spyOn(lexwareApi, 'update').mockResolvedValue(connection);
    const disconnect = vi.spyOn(lexwareApi, 'disconnect').mockResolvedValue(undefined);
    const { rerender, client } = mount(<LexwareConnectionCard connection={connection} profileName="Studio Berlin" />);
    const trigger = screen.getByRole('button', { name: 'Connection actions' });
    await user.click(trigger);
    await user.keyboard('{Tab}');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    await user.click(trigger);
    await user.click(screen.getByRole('menuitem', { name: 'Pause sync' }));
    await waitFor(() => expect(update).toHaveBeenCalledWith(3, { enabled: false }));
    await waitFor(() => expect(trigger).toBeEnabled());
    rerender(<QueryClientProvider client={client}><LexwareConnectionCard connection={{ ...connection, enabled: false }} profileName="Studio Berlin" /></QueryClientProvider>);
    expect(screen.getByRole('button', { name: 'Refresh now' })).toBeDisabled();
    await user.click(trigger);
    await user.click(screen.getByRole('menuitem', { name: 'Resume sync' }));
    await waitFor(() => expect(update).toHaveBeenCalledWith(3, { enabled: true }));
    await waitFor(() => expect(trigger).toBeEnabled());
    await user.click(trigger);
    await user.click(screen.getByRole('menuitem', { name: 'Disconnect' }));
    await waitFor(() => expect(disconnect).toHaveBeenCalledExactlyOnceWith(3));
  });

  it('keeps refresh unavailable while queued and localizes the banner and key dialog in German', async () => {
    await i18n.changeLanguage('de');
    mount(<LexwareConnectionCard connection={{ ...connection, sync_status: 'queued' }} profileName="Studio Berlin" />);
    expect(screen.getByRole('status')).toHaveTextContent('Eingereiht');
    expect(screen.getByRole('button', { name: 'Jetzt aktualisieren' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Verbindungsaktionen' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Schlüssel verwalten' }));
    expect(screen.getByRole('dialog', { name: 'Schlüssel verwalten' })).toBeInTheDocument();
    expect(screen.getByLabelText('Lexware-API-Schlüssel')).toHaveValue('');
    expect(screen.getByRole('button', { name: 'Verbindung speichern' })).toBeDisabled();
  });
});
