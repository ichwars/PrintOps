import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { server } from '../mocks/server';
import { SettingsPage } from '../../pages/SettingsPage';
import { setAuthToken } from '../../api/client';
import { CreateUserAdvancedAuthModal } from '../../components/CreateUserAdvancedAuthModal';
import type { Printer } from '../../api/client';

const viewer = { id: 2, username: 'scopedviewer', role: 'user', is_active: true, is_admin: false, groups: [], allowed_printer_ids: [] };
const printer = { id: 7, name: 'Studio printer' } as Printer;
beforeEach(() => {
  window.history.replaceState({}, '', '/settings?tab=users-security');
  localStorage.clear();
  setAuthToken('fixture-session');
  Element.prototype.scrollIntoView = vi.fn();
  server.use(
    http.get('/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: true, requires_setup: false })),
    http.get('/api/v1/auth/me', () => HttpResponse.json({ id: 1, username: 'admin', role: 'admin', is_admin: true, is_active: true, permissions: [] })),
    http.get('/api/v1/users/', () => HttpResponse.json([viewer])),
    http.get('/api/v1/printers/', () => HttpResponse.json([printer])),
  );
});

async function editViewer() {
  render(<SettingsPage />);
  const label = await screen.findByText('scopedviewer');
  const row = label.parentElement!.parentElement!;
  fireEvent.click(within(row).getAllByRole('button')[0]);
  return screen.findByRole('button', { name: 'Save Changes' });
}

describe('explicit printer scope in user forms', () => {
  it('renders and saves an existing deny-all scope without granting every printer', async () => {
    let saved: unknown;
    server.use(http.patch('/api/v1/users/2', async ({ request }) => {
      saved = await request.json();
      return HttpResponse.json(viewer);
    }));
    const save = await editViewer();
    expect(screen.getByRole('checkbox', { name: 'All printers' })).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Studio printer' })).not.toBeChecked();
    fireEvent.click(save);
    await waitFor(() => expect(saved).toMatchObject({ allowed_printer_ids: [] }));
  });
  it('removing the final selected printer keeps deny-all until All printers is explicitly chosen', async () => {
    let saved: unknown;
    server.use(
      http.get('/api/v1/users/', () => HttpResponse.json([{ ...viewer, allowed_printer_ids: [7] }])),
      http.patch('/api/v1/users/2', async ({ request }) => { saved = await request.json(); return HttpResponse.json(viewer); }),
    );
    const save = await editViewer();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Studio printer' }));
    expect(screen.getByRole('checkbox', { name: 'All printers' })).not.toBeChecked();
    fireEvent.click(save);
    await waitFor(() => expect(saved).toMatchObject({ allowed_printer_ids: [] }));
  });
  it('saves unrestricted access only after an explicit All printers choice', async () => {
    let saved: unknown;
    server.use(http.patch('/api/v1/users/2', async ({ request }) => { saved = await request.json(); return HttpResponse.json({ ...viewer, allowed_printer_ids: null }); }));
    const save = await editViewer();
    fireEvent.click(screen.getByRole('checkbox', { name: 'All printers' }));
    fireEvent.click(save);
    await waitFor(() => expect(saved).toMatchObject({ allowed_printer_ids: null }));
  });
  it('advanced create form distinguishes deny-all from an explicit All printers choice', () => {
    const setFormData = vi.fn();
    render(<CreateUserAdvancedAuthModal formData={{ username: 'newviewer', email: 'new@example.test', group_ids: [], confirmPassword: '', allowed_printer_ids: [] }} setFormData={setFormData} groups={[]} printers={[printer]} onClose={() => {}} onCreate={() => {}} isCreating={false} isCreateButtonDisabled={false} />);
    const all = screen.getByRole('checkbox', { name: 'All printers' });
    expect(all).not.toBeChecked();
    fireEvent.click(all);
    expect(setFormData).toHaveBeenCalledWith(expect.objectContaining({ allowed_printer_ids: undefined }));
  });
});
