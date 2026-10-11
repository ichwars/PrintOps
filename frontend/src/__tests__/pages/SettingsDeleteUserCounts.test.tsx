import { cleanup, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, describe, expect, it } from 'vitest';
import { setAuthToken } from '../../api/client';
import i18n from '../../i18n';
import { SettingsPage } from '../../pages/SettingsPage';
import { server } from '../mocks/server';
import { render } from '../utils';

function useUserItems(count: number | { archives: number; queue_items: number; library_files: number }, canDelete = true) {
  const currentUser = {
    id: 1, username: 'operator', role: 'user', is_active: true, is_admin: false,
    groups: [], permissions: canDelete ? ['users:read', 'users:delete'] : ['users:read'],
    created_at: '2026-01-01T00:00:00Z',
  };
  const targetUser = { ...currentUser, id: 2, username: 'Artifact owner', permissions: [] };
  const deletions: URL[] = [];
  server.use(
    http.get('/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: true, requires_setup: false })),
    http.get('/api/v1/auth/me', () => HttpResponse.json(currentUser)),
    http.get('/api/v1/users/', () => HttpResponse.json([currentUser, targetUser])),
    http.get('/api/v1/users/2/items-count', () => HttpResponse.json(typeof count === 'number'
      ? { archives: count, queue_items: count, library_files: count }
      : count)),
    http.delete('/api/v1/users/2', ({ request }) => {
      deletions.push(new URL(request.url));
      return new HttpResponse(null, { status: 204 });
    }),
  );
  setAuthToken('test-token');
  window.history.replaceState({}, '', '/settings?tab=users-security&sub=users');
  return deletions;
}

afterEach(async () => {
  cleanup();
  setAuthToken(null);
  window.history.replaceState({}, '', '/');
  await i18n.changeLanguage('en');
});

describe('SettingsPage delete-user item counts', () => {
  it.each([
    { language: 'nl', count: 1, labels: ['1 archief', '1 wachtrij-item', '1 bibliotheekbestand'], action: 'Gebruiker verwijderen, items behouden (worden eigenaarloos)' },
    { language: 'nl', count: 2, labels: ['2 archieven', '2 wachtrij-items', '2 bibliotheekbestanden'], action: 'Gebruiker EN diens items verwijderen' },
    { language: 'de', count: 1, labels: ['1 Archiv', '1 Warteschlangeneintrag', '1 Bibliotheksdatei'], action: 'Benutzer löschen, Elemente behalten (werden herrenlos)' },
    { language: 'de', count: 2, labels: ['2 Archive', '2 Warteschlangeneinträge', '2 Bibliotheksdateien'], action: 'Benutzer UND dessen Elemente löschen' },
    { language: 'en', count: 1, labels: ['1 archive', '1 queue item', '1 library file'], action: 'Delete user, keep items (become ownerless)' },
    { language: 'en', count: 2, labels: ['2 archives', '2 queue items', '2 library files'], action: 'Delete user AND their items' },
  ])('renders complete $language count phrases for $count items and preserves deletion choice', async ({ language, count, labels, action }) => {
    const deletions = useUserItems(count);
    await i18n.changeLanguage(language);
    const user = userEvent.setup();
    render(<SettingsPage />);

    const owner = await screen.findByText('Artifact owner');
    await user.click(within(owner.closest('.py-3') as HTMLElement).getByRole('button'));
    const firstCount = await screen.findByText(labels[0], { selector: 'li' });
    expect(within(firstCount.parentElement!).getAllByRole('listitem').map(item => item.textContent)).toEqual(labels);
    expect(deletions).toHaveLength(0);

    await user.click(screen.getByRole('button', { name: action }));
    await waitFor(() => expect(deletions).toHaveLength(1));
    expect(deletions[0].pathname).toBe('/api/v1/users/2');
    expect(deletions[0].searchParams.get('delete_items')).toBe(String(count > 1));
  });

  it('keeps independent category quantities and omits zero-count categories', async () => {
    useUserItems({ archives: 0, queue_items: 1, library_files: 3 });
    await i18n.changeLanguage('nl');
    render(<SettingsPage />);
    const owner = await screen.findByText('Artifact owner');
    await userEvent.setup().click(within(owner.closest('.py-3') as HTMLElement).getByRole('button'));
    const queueCount = await screen.findByText('1 wachtrij-item', { selector: 'li' });
    expect(within(queueCount.parentElement!).getAllByRole('listitem').map(item => item.textContent)).toEqual([
      '1 wachtrij-item', '3 bibliotheekbestanden',
    ]);
  });

  it('keeps deletion unavailable without users:delete permission', async () => {
    useUserItems(2, false);
    await i18n.changeLanguage('nl');
    render(<SettingsPage />);
    const owner = await screen.findByText('Artifact owner');
    expect(within(owner.closest('.py-3') as HTMLElement).queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Gebruiker verwijderen' })).not.toBeInTheDocument();
  });
});
