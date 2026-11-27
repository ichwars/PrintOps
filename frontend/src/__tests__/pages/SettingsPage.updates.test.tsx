import { beforeEach, describe, expect, it } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { SettingsPage } from '../../pages/SettingsPage';
import { server } from '../mocks/server';
import { render } from '../utils';
import { mockSettings, resetSettingsPage, setSettingsTabUrl } from './settingsPageFixtures';

describe('SettingsPage update CTA per deployment shape', () => {
  beforeEach(resetSettingsPage);

  // The update card branches on the deployment shape returned by
  // /updates/check. Each branch is mutually exclusive — verify the right
  // one wins so HA addon users never see the docker-compose snippet
  // (which they can't run from inside an HA addon container) and Docker
  // users never see the in-app Install button (which would no-op).
  const renderWithUpdateCheck = async (
    checkBody: Record<string, unknown>,
  ) => {
    server.use(
      http.get('/api/v1/settings/', () =>
        HttpResponse.json({ ...mockSettings, check_updates: true }),
      ),
      http.get('/api/v1/updates/check', () => HttpResponse.json(checkBody)),
    );
    setSettingsTabUrl('operations');
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Updates', level: 1 })).toBeInTheDocument();
    });
  };

  it('shows the HA Supervisor message when running as an HA addon', async () => {
    await renderWithUpdateCheck({
      update_available: true,
      current_version: '0.2.4',
      latest_version: '0.2.5',
      release_name: '0.2.5',
      release_notes: '',
      release_url: 'https://example.invalid/r',
      published_at: '2099-01-01T00:00:00Z',
      is_docker: true,
      is_ha_addon: true,
      update_method: 'ha_addon',
    });

    await waitFor(() => {
      expect(
        screen.getByText(/Home Assistant Supervisor/i),
      ).toBeInTheDocument();
    }, { timeout: 5000 });
    // Docker hint must NOT render — HA branch wins.
    expect(screen.queryByText('docker compose pull && docker compose up -d')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /install update/i })).not.toBeInTheDocument();
  });

  it('shows the docker-compose snippet for Docker (non-HA) deployments', async () => {
    await renderWithUpdateCheck({
      update_available: true,
      current_version: '0.2.4',
      latest_version: '0.2.5',
      release_name: '0.2.5',
      release_notes: '',
      release_url: 'https://example.invalid/r',
      published_at: '2099-01-01T00:00:00Z',
      is_docker: true,
      is_ha_addon: false,
      update_method: 'docker',
    });

    await waitFor(() => {
      expect(screen.getByText('docker compose pull && docker compose up -d')).toBeInTheDocument();
    }, { timeout: 5000 });
    expect(screen.queryByText(/Home Assistant Supervisor/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /install update/i })).not.toBeInTheDocument();
  });

  it('shows the installer-download link for Windows installer installs', async () => {
    const downloadUrl =
      'https://github.com/ichwars/PrintOps/releases/download/v0.2.5/printops-0.2.5-windows-x64-setup.exe';
    await renderWithUpdateCheck({
      update_available: true,
      current_version: '0.2.4',
      latest_version: '0.2.5',
      release_name: '0.2.5',
      release_notes: '',
      release_url: 'https://github.com/ichwars/PrintOps/releases/tag/v0.2.5',
      published_at: '2099-01-01T00:00:00Z',
      is_docker: false,
      is_ha_addon: false,
      is_windows_installer: true,
      update_method: 'windows_installer',
      installer_download_url: downloadUrl,
    });

    const link = await screen.findByRole('link', { name: /download installer for v0\.2\.5/i }, { timeout: 5000 });
    expect(link).toHaveAttribute('href', downloadUrl);
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
    // The in-app update button must NOT render — the git-fetch path can't
    // work from an installer payload.
    expect(screen.queryByRole('button', { name: /install update/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/Home Assistant Supervisor/i)).not.toBeInTheDocument();
    expect(screen.queryByText('docker compose pull && docker compose up -d')).not.toBeInTheDocument();
  });
});
