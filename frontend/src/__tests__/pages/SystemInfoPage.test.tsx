/**
 * Tests for the SystemInfoPage component.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { render } from '../utils';
import { SystemInfoPage } from '../../pages/SystemInfoPage';
import { api, bugReportApi } from '../../api/client';

// Mock the API client
vi.mock('../../api/client', () => ({
  api: {
    getSystemInfo: vi.fn(),
    getSettings: vi.fn().mockResolvedValue({}),
    getLibraryStats: vi.fn().mockResolvedValue({ total_size_bytes: 0, total_files: 0, total_folders: 0 }),
    getPrinters: vi.fn().mockResolvedValue([]),
    getSystemHealth: vi.fn().mockResolvedValue({
      findings: [],
      scanned_entries: 0,
      log_available: true,
      summary: { total: 0, layer8: 0, environment: 0, bug: 0 },
    }),
    updateSettings: vi.fn().mockResolvedValue({}),
  },
  bugReportApi: {
    getStatus: vi.fn().mockResolvedValue({
      repository: 'ichwars/PrintOps',
      relay_configured: false,
      issue_url: 'https://github.com/ichwars/PrintOps/issues/new/choose',
    }),
  },
  supportApi: {
    getDebugLoggingState: vi.fn().mockResolvedValue({ enabled: false, enabled_at: null, duration_seconds: null }),
    setDebugLogging: vi.fn().mockResolvedValue({ enabled: true, enabled_at: new Date().toISOString(), duration_seconds: 0 }),
    downloadSupportBundle: vi.fn().mockResolvedValue(undefined),
  },
}));

// Mock system info response
const mockSystemInfo = {
  app: {
    version: '0.1.5b',
    base_dir: '/opt/printops',
    archive_dir: '/opt/printops/archives',
  },
  database: {
    engine: 'SQLite',
    version: 'SQLite 3.45.1',
    archives: 150,
    archives_completed: 140,
    archives_failed: 8,
    archives_printing: 2,
    printers: 3,
    filaments: 25,
    projects: 5,
    smart_plugs: 2,
    total_print_time_seconds: 360000,
    total_print_time_formatted: '100h',
    total_filament_grams: 5000,
    total_filament_kg: 5.0,
  },
  printers: {
    total: 3,
    connected: 2,
    connected_list: [
      { id: 1, name: 'X1C-01', state: 'IDLE', model: 'X1C' },
      { id: 2, name: 'P1S-01', state: 'RUNNING', model: 'P1S' },
    ],
  },
  storage: {
    archive_size_bytes: 1073741824,
    archive_size_formatted: '1.0 GB',
    database_size_bytes: 10485760,
    database_size_formatted: '10.0 MB',
    disk_total_bytes: 107374182400,
    disk_total_formatted: '100.0 GB',
    disk_used_bytes: 53687091200,
    disk_used_formatted: '50.0 GB',
    disk_free_bytes: 53687091200,
    disk_free_formatted: '50.0 GB',
    disk_percent_used: 50.0,
  },
  system: {
    platform: 'Linux',
    platform_release: '5.15.0',
    platform_version: '#1 SMP',
    architecture: 'x86_64',
    hostname: 'printops-server',
    python_version: '3.11.0',
    uptime_seconds: 86400,
    uptime_formatted: '1d',
    boot_time: '2024-12-11T00:00:00',
  },
  memory: {
    total_bytes: 17179869184,
    total_formatted: '16.0 GB',
    available_bytes: 8589934592,
    available_formatted: '8.0 GB',
    used_bytes: 8589934592,
    used_formatted: '8.0 GB',
    percent_used: 50.0,
  },
  cpu: {
    count: 4,
    count_logical: 8,
    percent: 25.0,
  },
};

describe('SystemInfoPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (bugReportApi.getStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      repository: 'ichwars/PrintOps',
      relay_configured: false,
      issue_url: 'https://github.com/ichwars/PrintOps/issues/new/choose',
    });
  });

  it('renders loading state initially', async () => {
    // Make the API call never resolve to test loading state
    (api.getSystemInfo as ReturnType<typeof vi.fn>).mockImplementation(
      () => new Promise(() => {})
    );

    render(<SystemInfoPage />);

    // Should show loading spinner
    expect(document.querySelector('.animate-spin')).toBeInTheDocument();
  });

  it('renders system info when data loads', async () => {
    (api.getSystemInfo as ReturnType<typeof vi.fn>).mockResolvedValue(mockSystemInfo);

    render(<SystemInfoPage />);

    await waitFor(() => {
      expect(screen.getByText('System Information')).toBeInTheDocument();
    });

    // Check for version
    expect(screen.getByText('v0.1.5b')).toBeInTheDocument();
  });

  it('displays application section', async () => {
    (api.getSystemInfo as ReturnType<typeof vi.fn>).mockResolvedValue(mockSystemInfo);

    render(<SystemInfoPage />);

    await waitFor(() => {
      expect(screen.getByText('Application')).toBeInTheDocument();
    });

    expect(screen.getByText('v0.1.5b')).toBeInTheDocument();
    expect(screen.getByText('printops-server')).toBeInTheDocument();
    expect(screen.getByText('1d')).toBeInTheDocument();
  });

  it('displays database statistics', async () => {
    (api.getSystemInfo as ReturnType<typeof vi.fn>).mockResolvedValue(mockSystemInfo);

    render(<SystemInfoPage />);

    await waitFor(() => {
      expect(screen.getByText('Database')).toBeInTheDocument();
    });

    // Check archive counts
    expect(screen.getByText('150')).toBeInTheDocument(); // Total archives
    expect(screen.getByText('140')).toBeInTheDocument(); // Completed
    expect(screen.getByText('8')).toBeInTheDocument(); // Failed
  });

  it('displays connected printers', async () => {
    (api.getSystemInfo as ReturnType<typeof vi.fn>).mockResolvedValue(mockSystemInfo);

    render(<SystemInfoPage />);

    await waitFor(() => {
      expect(screen.getByText('Connected Printers')).toBeInTheDocument();
    });

    // Check connected printer names
    expect(screen.getByText('X1C-01')).toBeInTheDocument();
    expect(screen.getByText('P1S-01')).toBeInTheDocument();

    // Check printer states
    expect(screen.getByText('IDLE')).toBeInTheDocument();
    expect(screen.getByText('RUNNING')).toBeInTheDocument();
  });

  it('displays storage information', async () => {
    (api.getSystemInfo as ReturnType<typeof vi.fn>).mockResolvedValue(mockSystemInfo);

    render(<SystemInfoPage />);

    await waitFor(() => {
      expect(screen.getByText('Storage')).toBeInTheDocument();
    });

    expect(screen.getByText('1.0 GB')).toBeInTheDocument(); // Archive size
    expect(screen.getByText('10.0 MB')).toBeInTheDocument(); // Database size
  });

  it('displays memory usage', async () => {
    (api.getSystemInfo as ReturnType<typeof vi.fn>).mockResolvedValue(mockSystemInfo);

    render(<SystemInfoPage />);

    await waitFor(() => {
      expect(screen.getByText('Memory')).toBeInTheDocument();
    });

    expect(screen.getByText('8.0 GB available')).toBeInTheDocument();
  });

  it('displays CPU information', async () => {
    (api.getSystemInfo as ReturnType<typeof vi.fn>).mockResolvedValue(mockSystemInfo);

    render(<SystemInfoPage />);

    await waitFor(() => {
      expect(screen.getByText('CPU')).toBeInTheDocument();
    });

    expect(screen.getByText('4')).toBeInTheDocument(); // CPU cores
    expect(screen.getByText('25%')).toBeInTheDocument(); // CPU usage
  });

  it('displays system details', async () => {
    (api.getSystemInfo as ReturnType<typeof vi.fn>).mockResolvedValue(mockSystemInfo);

    render(<SystemInfoPage />);

    await waitFor(() => {
      expect(screen.getByText('System Details')).toBeInTheDocument();
    });

    expect(screen.getByText('Linux')).toBeInTheDocument();
    expect(screen.getByText('x86_64')).toBeInTheDocument();
    expect(screen.getByText('3.11.0')).toBeInTheDocument(); // Python version
  });

  it('shows error state when data fails to load', async () => {
    (api.getSystemInfo as ReturnType<typeof vi.fn>).mockResolvedValue(null);

    render(<SystemInfoPage />);

    await waitFor(() => {
      expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
    });
  });

  it('shows no printers message when none connected', async () => {
    const noConnectedPrinters = {
      ...mockSystemInfo,
      printers: {
        total: 3,
        connected: 0,
        connected_list: [],
      },
    };

    (api.getSystemInfo as ReturnType<typeof vi.fn>).mockResolvedValue(noConnectedPrinters);

    render(<SystemInfoPage />);

    await waitFor(() => {
      expect(screen.getByText(/no printers connected/i)).toBeInTheDocument();
    });
  });

  it('has refresh button', async () => {
    (api.getSystemInfo as ReturnType<typeof vi.fn>).mockResolvedValue(mockSystemInfo);

    render(<SystemInfoPage />);

    await waitFor(() => {
      expect(screen.getByText('Refresh')).toBeInTheDocument();
    });
  });

  it('applies warning color for high disk usage', async () => {
    const highDiskUsage = {
      ...mockSystemInfo,
      storage: {
        ...mockSystemInfo.storage,
        disk_percent_used: 80,
      },
    };

    (api.getSystemInfo as ReturnType<typeof vi.fn>).mockResolvedValue(highDiskUsage);

    render(<SystemInfoPage />);

    await waitFor(() => {
      expect(screen.getByText('Storage')).toBeInTheDocument();
    });

    // The progress bar should have yellow color for 75-90% usage
    const progressBars = document.querySelectorAll('[class*="bg-yellow"]');
    expect(progressBars.length).toBeGreaterThan(0);
  });

  it('displays extended privacy disclosure items', async () => {
    (api.getSystemInfo as ReturnType<typeof vi.fn>).mockResolvedValue(mockSystemInfo);

    render(<SystemInfoPage />);

    await waitFor(() => {
      expect(screen.getByText("What's in the support bundle?")).toBeInTheDocument();
    });

    // Original items
    expect(screen.getByText(/App version and debug mode/)).toBeInTheDocument();
    expect(screen.getByText(/Debug logs \(sanitized\)/)).toBeInTheDocument();

    // New diagnostic items
    expect(screen.getByText(/Printer connectivity and firmware versions/)).toBeInTheDocument();
    expect(screen.getByText(/Integration status \(Spoolman, MQTT, HA\)/)).toBeInTheDocument();
    expect(screen.getByText(/Network interfaces \(subnets only\)/)).toBeInTheDocument();
    expect(screen.getByText(/Python package versions/)).toBeInTheDocument();
    expect(screen.getByText(/Database health checks/)).toBeInTheDocument();
    expect(screen.getByText(/Docker environment details/)).toBeInTheDocument();
  });

  it('shows bug report destination status and issue form link', async () => {
    (api.getSystemInfo as ReturnType<typeof vi.fn>).mockResolvedValue(mockSystemInfo);

    render(<SystemInfoPage />);

    await waitFor(() => {
      expect(screen.getByText('Bug Report Destination')).toBeInTheDocument();
    });

    expect(screen.getByText('Manual GitHub issue form is used')).toBeInTheDocument();
    expect(screen.getByText('ichwars/PrintOps')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /open issue form/i })).toHaveAttribute(
      'href',
      'https://github.com/ichwars/PrintOps/issues/new/choose'
    );
  });

  it('keeps the manual issue form state even when a relay is configured', async () => {
    (api.getSystemInfo as ReturnType<typeof vi.fn>).mockResolvedValue(mockSystemInfo);
    (bugReportApi.getStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      repository: 'ichwars/PrintOps',
      relay_configured: true,
      issue_url: 'https://github.com/ichwars/PrintOps/issues/new/choose',
    });

    render(<SystemInfoPage />);

    await waitFor(() => {
      expect(screen.getByText('Manual GitHub issue form is used')).toBeInTheDocument();
    });
    expect(screen.queryByText('Automatic GitHub issue creation is configured')).not.toBeInTheDocument();
  });

  it('shows bug report configuration loading state before status is available', async () => {
    (api.getSystemInfo as ReturnType<typeof vi.fn>).mockResolvedValue(mockSystemInfo);
    (bugReportApi.getStatus as ReturnType<typeof vi.fn>).mockImplementation(
      () => new Promise(() => {})
    );

    render(<SystemInfoPage />);

    await waitFor(() => {
      expect(screen.getByText('Checking bug report configuration...')).toBeInTheDocument();
    });
    expect(screen.queryByText('Manual GitHub issue form is used')).not.toBeInTheDocument();
  });

  it('shows bug report configuration error state without claiming manual mode', async () => {
    (api.getSystemInfo as ReturnType<typeof vi.fn>).mockResolvedValue(mockSystemInfo);
    (bugReportApi.getStatus as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('status failed'));

    render(<SystemInfoPage />);

    await waitFor(() => {
      expect(screen.getByText('Bug report configuration is currently unavailable')).toBeInTheDocument();
    });
    expect(screen.queryByText('Manual GitHub issue form is used')).not.toBeInTheDocument();
  });

  it('applies danger color for critical disk usage', async () => {
    const criticalDiskUsage = {
      ...mockSystemInfo,
      storage: {
        ...mockSystemInfo.storage,
        disk_percent_used: 95,
      },
    };

    (api.getSystemInfo as ReturnType<typeof vi.fn>).mockResolvedValue(criticalDiskUsage);

    render(<SystemInfoPage />);

    await waitFor(() => {
      expect(screen.getByText('Storage')).toBeInTheDocument();
    });

    // The progress bar should have red color for >90% usage
    const progressBars = document.querySelectorAll('[class*="bg-red"]');
    expect(progressBars.length).toBeGreaterThan(0);
  });
});
