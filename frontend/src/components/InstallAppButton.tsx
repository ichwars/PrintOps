import { useState, useEffect } from 'react';
import { Download } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useToast } from '../contexts/ToastContext';

// The beforeinstallprompt event is not in the standard TS DOM lib.
interface BeforeInstallPromptEvent extends Event {
  readonly platforms: string[];
  prompt: () => Promise<void>;
  readonly userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>;
}

// iOS Safari never fires beforeinstallprompt; the only install path is the
// Share-sheet "Add to Home Screen" action. Modern iPadOS masquerades as
// desktop Safari, so touch points are the reliable tablet signal.
function isIos(): boolean {
  const ua = navigator.userAgent;
  const isIosUa = /iPhone|iPad|iPod/.test(ua);
  const isIpadOs = /Macintosh/.test(ua) && navigator.maxTouchPoints > 1;
  return isIosUa || isIpadOs;
}

function isStandalone(): boolean {
  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    (window.navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

/**
 * Sidebar-footer button that installs PrintOps as a PWA.
 *
 * Chrome for Android removed the automatic install banner in Chrome 108, so
 * without an in-app trigger the only install path on Android is a buried
 * browser-menu item (#1460). This button captures the `beforeinstallprompt`
 * event and re-fires it on click. On iOS Safari (which has no programmatic
 * install at all) the button instead surfaces the Share-sheet instructions,
 * and it renders nothing when the app is already running standalone.
 */
export function InstallAppButton() {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const [promptEvent, setPromptEvent] = useState<BeforeInstallPromptEvent | null>(null);
  const [iosHint, setIosHint] = useState(false);

  useEffect(() => {
    const onBeforeInstallPrompt = (e: Event) => {
      // Suppress Chrome's own mini-infobar (desktop) so this button is the
      // single, predictable install entry point.
      e.preventDefault();
      setPromptEvent(e as BeforeInstallPromptEvent);
    };
    const onInstalled = () => setPromptEvent(null);
    window.addEventListener('beforeinstallprompt', onBeforeInstallPrompt);
    window.addEventListener('appinstalled', onInstalled);
    if (!isStandalone() && isIos()) {
      setIosHint(true);
    }
    return () => {
      window.removeEventListener('beforeinstallprompt', onBeforeInstallPrompt);
      window.removeEventListener('appinstalled', onInstalled);
    };
  }, []);

  if (!promptEvent && !iosHint) {
    return null;
  }

  const handleInstall = async () => {
    if (!promptEvent) {
      showToast(t('nav.installAppIosHint'), 'info');
      return;
    }
    await promptEvent.prompt();
    const { outcome } = await promptEvent.userChoice;
    // A captured prompt can only be used once; drop it either way so the
    // button hides until the browser fires a fresh beforeinstallprompt.
    setPromptEvent(null);
    if (outcome === 'accepted') {
      showToast(t('nav.installAppSuccess'), 'success');
    }
  };

  return (
    <button
      onClick={handleInstall}
      className="p-2 rounded-lg hover:bg-bambu-dark-tertiary transition-colors text-bambu-gray-light hover:text-white"
      title={t('nav.installApp')}
      aria-label={t('nav.installApp')}
    >
      <Download className="w-5 h-5" />
    </button>
  );
}
