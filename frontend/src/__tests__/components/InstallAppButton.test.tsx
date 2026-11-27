/**
 * Tests for InstallAppButton - the in-app PWA install trigger (#1460).
 */

import { describe, it, expect, vi, afterEach } from 'vitest';
import { act } from 'react';
import { render, screen, waitFor } from '../utils';
import userEvent from '@testing-library/user-event';
import { InstallAppButton } from '../../components/InstallAppButton';

// Scoped so the assertion ignores unrelated buttons (e.g. a toast's dismiss).
const INSTALL_BUTTON = { name: 'Install app' } as const;

/** Build a fake beforeinstallprompt event with a controllable userChoice. */
function makeInstallPromptEvent(outcome: 'accepted' | 'dismissed') {
  const event = new Event('beforeinstallprompt') as Event & {
    prompt: () => Promise<void>;
    userChoice: Promise<{ outcome: string; platform: string }>;
  };
  event.prompt = vi.fn().mockResolvedValue(undefined);
  event.userChoice = Promise.resolve({ outcome, platform: 'web' });
  return event;
}

const IPHONE_UA =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1';

/** Stub the navigator so the component sees an iPhone (non-standalone). */
function stubIosUserAgent(ua: string) {
  Object.defineProperty(window.navigator, 'userAgent', {
    value: ua,
    configurable: true,
  });
  Object.defineProperty(window.navigator, 'maxTouchPoints', {
    value: 5,
    configurable: true,
  });
}

/** Restore the jsdom navigator: deleting the own property re-exposes the
 *  prototype userAgent getter (maxTouchPoints simply reads as undefined). */
function restoreNavigator() {
  delete (window.navigator as Partial<Navigator>).userAgent;
  delete (window.navigator as { maxTouchPoints?: number }).maxTouchPoints;
}

describe('InstallAppButton', () => {
  afterEach(() => {
    restoreNavigator();
  });

  it('renders nothing until the browser fires beforeinstallprompt', () => {
    render(<InstallAppButton />);
    expect(screen.queryByRole('button', INSTALL_BUTTON)).toBeNull();
  });

  it('shows the install button on iOS Safari (no beforeinstallprompt there)', () => {
    stubIosUserAgent(IPHONE_UA);
    render(<InstallAppButton />);
    expect(screen.getByRole('button', INSTALL_BUTTON)).toBeInTheDocument();
  });

  it('renders nothing on iOS when already running standalone', () => {
    stubIosUserAgent(IPHONE_UA);
    const originalMatchMedia = window.matchMedia;
    window.matchMedia = vi.fn().mockReturnValue({
      matches: true,
      media: '(display-mode: standalone)',
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => true,
    });
    try {
      render(<InstallAppButton />);
      expect(screen.queryByRole('button', INSTALL_BUTTON)).toBeNull();
    } finally {
      window.matchMedia = originalMatchMedia;
    }
  });

  it('shows the Share-sheet instructions toast when tapped on iOS', async () => {
    const user = userEvent.setup();
    stubIosUserAgent(IPHONE_UA);
    render(<InstallAppButton />);

    await user.click(screen.getByRole('button', INSTALL_BUTTON));

    // The iOS hint is a toast rendered into the body by ToastProvider.
    await waitFor(() =>
      expect(document.body.textContent).toContain('Add to Home Screen')
    );
  });

  it('recognises iPadOS (desktop-like UA with touch points)', () => {
    stubIosUserAgent(
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15'
    );
    render(<InstallAppButton />);
    expect(screen.getByRole('button', INSTALL_BUTTON)).toBeInTheDocument();
  });

  it('shows the install button once beforeinstallprompt fires', async () => {
    render(<InstallAppButton />);
    await act(async () => {
      window.dispatchEvent(makeInstallPromptEvent('accepted'));
    });
    expect(await screen.findByRole('button', INSTALL_BUTTON)).toBeInTheDocument();
  });

  it('fires the captured prompt on click and hides itself afterwards', async () => {
    const user = userEvent.setup();
    const event = makeInstallPromptEvent('accepted');
    render(<InstallAppButton />);

    await act(async () => {
      window.dispatchEvent(event);
    });
    await user.click(await screen.findByRole('button', INSTALL_BUTTON));

    expect(event.prompt).toHaveBeenCalledTimes(1);
    // A captured prompt can only be used once, so the button must disappear.
    await waitFor(() =>
      expect(screen.queryByRole('button', INSTALL_BUTTON)).toBeNull()
    );
  });

  it('hides itself even when the user dismisses the prompt', async () => {
    const user = userEvent.setup();
    const event = makeInstallPromptEvent('dismissed');
    render(<InstallAppButton />);

    await act(async () => {
      window.dispatchEvent(event);
    });
    await user.click(await screen.findByRole('button', INSTALL_BUTTON));

    await waitFor(() =>
      expect(screen.queryByRole('button', INSTALL_BUTTON)).toBeNull()
    );
  });

  it('hides the button when the app reports it was installed', async () => {
    render(<InstallAppButton />);
    await act(async () => {
      window.dispatchEvent(makeInstallPromptEvent('accepted'));
    });
    expect(await screen.findByRole('button', INSTALL_BUTTON)).toBeInTheDocument();

    await act(async () => {
      window.dispatchEvent(new Event('appinstalled'));
    });
    await waitFor(() =>
      expect(screen.queryByRole('button', INSTALL_BUTTON)).toBeNull()
    );
  });
});
