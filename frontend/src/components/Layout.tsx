import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Printer, Archive, ListOrdered, BarChart3, Cloud, Settings, Sun, Moon, Monitor, ChevronLeft, ChevronRight, ChevronDown, Keyboard, Github, ArrowUpCircle, Wrench, FolderKanban, FolderOpen, X, Menu, Info, Plug, Bug, LogOut, Key, Loader2, ShieldAlert, Globe, Bell, Warehouse, ClipboardList, Package, Boxes, PackageCheck, FileText, Calculator, Users, Receipt, Database, type LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useTheme } from '../contexts/ThemeContext';
import { KeyboardShortcutsModal } from './KeyboardShortcutsModal';
import { InstallAppButton } from './InstallAppButton';
import { SwitchbarPopover } from './SwitchbarPopover';
import { useQuery, useQueries } from '@tanstack/react-query';
import { api, supportApi, pendingUploadsApi, type Permission } from '../api/client';
import { getIconByName } from './IconPicker';
import { useIsSidebarCompact } from '../hooks/useIsSidebarCompact';
import { useColorCatalogVersion } from '../hooks/useColorCatalogVersion';
import { useSponsorPrompt } from '../hooks/useSponsorPrompt';
import { useUnknownTagPrompt } from '../hooks/useUnknownTagPrompt';
import { UnknownSpoolModal } from './UnknownSpoolModal';
import { useAuth } from '../contexts/AuthContext';
import { useToast } from '../contexts/ToastContext';
import { Card, CardHeader, CardContent } from './Card';
import { parseUTCDate } from '../utils/date';
import { Button } from './Button';
import { BugReportBubble } from './BugReportBubble';
import {
  getHiddenSidebarSystemItemIds,
  getSidebarOrder,
  isExternalSidebarItemId,
  saveHiddenSidebarSystemItemIds,
  saveSidebarOrder,
  SIDEBAR_LAYOUT_CHANGED_EVENT,
} from '../utils/sidebarLayout';
import { TextField } from './ui';


interface NavItem {
  id: string;
  to: string;
  icon: LucideIcon;
  labelKey: string; // Translation key
  defaultLabel?: string;
  defaultLabelDe?: string;
  parentId?: string;
}

export const defaultNavItems: NavItem[] = [
  { id: 'dashboard', to: '/dashboard', icon: BarChart3, labelKey: 'printops.nav.dashboard', defaultLabel: 'Dashboard', defaultLabelDe: 'Dashboard' },
  { id: 'printers', to: '/printers', icon: Printer, labelKey: 'nav.printers' },
  { id: 'archives', to: '/archives', icon: Archive, labelKey: 'nav.archives', parentId: 'printers' },
  { id: 'queue', to: '/queue', icon: ListOrdered, labelKey: 'nav.queue', parentId: 'printers' },
  { id: 'profiles', to: '/profiles', icon: Cloud, labelKey: 'nav.profiles', parentId: 'printers' },
  { id: 'maintenance', to: '/maintenance', icon: Wrench, labelKey: 'nav.maintenance', parentId: 'printers' },
  { id: 'projects', to: '/projects', icon: FolderKanban, labelKey: 'nav.projects' },
  { id: 'files', to: '/files', icon: FolderOpen, labelKey: 'nav.files', parentId: 'projects' },
  { id: 'makerworld', to: '/makerworld', icon: Globe, labelKey: 'nav.makerworld', parentId: 'projects' },
  { id: 'inventory', to: '/warehouse', icon: Warehouse, labelKey: 'printops.nav.warehouse', defaultLabel: 'Warehouse', defaultLabelDe: 'Lager' },
  { id: 'warehouse-filament', to: '/warehouse/filament', icon: Package, labelKey: 'nav.inventory', parentId: 'inventory' },
  { id: 'warehouse-parts', to: '/warehouse/parts', icon: Boxes, labelKey: 'printops.nav.parts', defaultLabel: 'Small parts', defaultLabelDe: 'Kleinteile', parentId: 'inventory' },
  { id: 'warehouse-stock', to: '/warehouse/stock', icon: PackageCheck, labelKey: 'printops.nav.stock', defaultLabel: 'Stock position', defaultLabelDe: 'Warenlage', parentId: 'inventory' },
  { id: 'orders', to: '/orders', icon: ClipboardList, labelKey: 'printops.nav.orders', defaultLabel: 'Orders', defaultLabelDe: 'Aufträge' },
  { id: 'orders-offers', to: '/orders/offers', icon: FileText, labelKey: 'printops.nav.offers', defaultLabel: 'Offers', defaultLabelDe: 'Angebote', parentId: 'orders' },
  { id: 'orders-calculation', to: '/orders/calculation', icon: Calculator, labelKey: 'printops.nav.calculation', defaultLabel: 'Calculation', defaultLabelDe: 'Kalkulation', parentId: 'orders' },
  { id: 'orders-customers', to: '/orders/customers', icon: Users, labelKey: 'printops.nav.customers', defaultLabel: 'Customers', defaultLabelDe: 'Kunden', parentId: 'orders' },
  { id: 'orders-invoice', to: '/orders/invoices', icon: Receipt, labelKey: 'printops.nav.invoice', defaultLabel: 'Invoice', defaultLabelDe: 'Rechnung', parentId: 'orders' },
  // User-account feature: gated in isHidden() on advanced auth + user_notifications
  // + the notifications:user_email permission. Kept adjacent to Settings
  // intentionally. Do not drop this entry — without it the /notifications page
  // is orphaned (route + page still exist but no nav link) (#1901).
  { id: 'notifications', to: '/notifications', icon: Bell, labelKey: 'nav.notifications' },
  { id: 'settings', to: '/settings', icon: Settings, labelKey: 'nav.settings' },
  { id: 'settings-general', to: '/settings', icon: Settings, labelKey: 'settings.tabs.general', parentId: 'settings' },
  { id: 'settings-users-security', to: '/settings?tab=users-security', icon: ShieldAlert, labelKey: 'settings.tabs.usersSecurity', parentId: 'settings' },
  { id: 'settings-printers-production', to: '/settings?tab=printers-production', icon: Printer, labelKey: 'settings.tabs.printersProduction', parentId: 'settings' },
  { id: 'settings-projects-files', to: '/settings?tab=projects-files', icon: FileText, labelKey: 'settings.tabs.projectsFiles', parentId: 'settings' },
  { id: 'settings-warehouse-material', to: '/settings?tab=warehouse-material', icon: Warehouse, labelKey: 'settings.tabs.warehouseMaterial', parentId: 'settings' },
  { id: 'settings-orders-calculation', to: '/settings?tab=orders-calculation', icon: Calculator, labelKey: 'settings.tabs.ordersCalculation', parentId: 'settings' },
  { id: 'settings-integrations', to: '/settings?tab=integrations', icon: Plug, labelKey: 'settings.tabs.integrations', parentId: 'settings' },
  { id: 'settings-operations', to: '/settings?tab=operations', icon: Database, labelKey: 'settings.tabs.operations', parentId: 'settings' },
];

function splitRoute(route: string) {
  const [path, query = ''] = route.split('?');
  return { path, query };
}

function routeQueryMatches(search: string, routeQuery: string) {
  const currentParams = new URLSearchParams(search);
  const routeParams = new URLSearchParams(routeQuery);
  for (const [key, value] of routeParams) {
    if (currentParams.get(key) !== value) return false;
  }
  return true;
}

function routePathMatches(pathname: string, route: string) {
  const { path } = splitRoute(route);
  return pathname === path || pathname.startsWith(`${path}/`);
}

function routeMatches(pathname: string, search: string, route: string) {
  const { path, query } = splitRoute(route);
  if (query) {
    return pathname === path && routeQueryMatches(search, query);
  }
  if (path === '/settings') {
    return pathname === path && !new URLSearchParams(search).has('tab');
  }
  return pathname === route || pathname.startsWith(`${route}/`);
}

function getActiveParentNavItemId(pathname: string, search: string) {
  const activeChild = defaultNavItems.find((item) => item.parentId && routeMatches(pathname, search, item.to));
  if (activeChild) return activeChild.parentId;

  return defaultNavItems.find((item) => {
    if (item.parentId) return false;
    const hasChildren = defaultNavItems.some((child) => child.parentId === item.id);
    return hasChildren && routePathMatches(pathname, item.to);
  })?.id;
}

// Get default view from localStorage
export function getDefaultView(): string {
  const stored = localStorage.getItem('defaultView');
  if (!stored || stored === '/' || stored === '/stats') return '/dashboard';
  return stored;
}

// Save default view to localStorage
export function setDefaultView(path: string) {
  localStorage.setItem('defaultView', path);
}

export function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { mode, toggleMode } = useTheme();
  const { t, i18n } = useTranslation();
  const isSidebarCompact = useIsSidebarCompact();

  // Theme toggle: mode → icon and tooltip
  const ThemeIcon = { dark: Sun, light: Monitor, system: Moon }[mode];
  const themeSwitchTitle = t({ dark: 'nav.switchToLight', light: 'nav.switchToSystem', system: 'nav.switchToDark' }[mode]);

  // Re-render Layout (and the page rendered inside <Outlet />) whenever the
  // backend color catalog is (re)populated, so pages that mounted before the
  // catalog fetched — and cached HSL-fallback color names during their first
  // render — refresh with the real catalog names. See #857.
  useColorCatalogVersion();
  const { user, authEnabled, logout, hasPermission } = useAuth();
  const { showToast } = useToast();
  const [showChangePasswordModal, setShowChangePasswordModal] = useState(false);
  const [changePasswordData, setChangePasswordData] = useState({ currentPassword: '', newPassword: '', confirmPassword: '' });
  const [changePasswordLoading, setChangePasswordLoading] = useState(false);
  const [sidebarExpanded, setSidebarExpanded] = useState(() => {
    const stored = localStorage.getItem('sidebarExpanded');
    return stored !== 'false';
  });
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const [showSwitchbar, setShowSwitchbar] = useState(false);
  const [expandedNavMenuIds, setExpandedNavMenuIds] = useState<string[]>(() => {
    const activeParentId = getActiveParentNavItemId(location.pathname, location.search);
    return activeParentId ? [activeParentId] : [];
  });
  const defaultSidebarOrder = useMemo(() => defaultNavItems.map(i => i.id), []);
  const [sidebarOrder, setSidebarOrder] = useState<string[]>(() => getSidebarOrder(defaultNavItems.map(i => i.id)));
  const [hiddenSystemItemIds, setHiddenSystemItemIds] = useState<string[]>(getHiddenSidebarSystemItemIds);
  const hasRedirected = useRef(false);
  const [dismissedUpdateVersion, setDismissedUpdateVersion] = useState<string | null>(() =>
    sessionStorage.getItem('dismissedUpdateVersion')
  );
  const [plateDetectionAlert, setPlateDetectionAlert] = useState<{
    printer_id: number;
    printer_name: string;
    message: string;
  } | null>(null);

  // Check for updates
  const { data: versionInfo } = useQuery({
    queryKey: ['version'],
    queryFn: api.getVersion,
    staleTime: Infinity,
  });

  const { data: settings } = useQuery({
    queryKey: ['settings'],
    queryFn: api.getSettings,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  // Sponsor-prompt toast — fires once per session post-auth if a milestone is eligible.
  useSponsorPrompt(settings?.currency ?? 'EUR');

  // Unknown-spool prompt — surfaces a confirmation modal when the AMS reports a
  // tag with no inventory match (only when `auto_add_unknown_rfid` is off).
  const unknownSpool = useUnknownTagPrompt();

  // Fetch default sidebar order via a public endpoint (no settings:read needed)
  const { data: defaultSidebarData } = useQuery({
    queryKey: ['default-sidebar-order'],
    queryFn: api.getDefaultSidebarOrder,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  // Apply admin default sidebar order once per user (skipped if already applied).
  // Uses a per-user localStorage flag to prevent re-application.
  useEffect(() => {
    const defaultOrder = defaultSidebarData?.default_sidebar_order;
    if (!defaultOrder) return;
    // Wait for auth state to settle before applying to avoid double-execution
    if (authEnabled && !user) return;
    const appliedKey = user ? `sidebarDefaultApplied_${user.id}` : 'sidebarDefaultApplied';
    if (localStorage.getItem(appliedKey)) return;
    try {
      const parsed = JSON.parse(defaultOrder);
      const orderArr = Array.isArray(parsed) ? parsed : parsed.order;
      if (!Array.isArray(orderArr) || orderArr.length === 0) return;
      // Filter to valid sidebar item IDs only
      const validIds = new Set(defaultNavItems.map(i => i.id));
      const filtered = orderArr.filter((id: string) => typeof id === 'string' && (validIds.has(id) || isExternalSidebarItemId(id)));
      if (filtered.length > 0) {
        setSidebarOrder(filtered);
        saveSidebarOrder(filtered);
        const hiddenIds = Array.isArray(parsed) ? [] : parsed.hiddenSystemItemIds;
        if (Array.isArray(hiddenIds)) {
          const filteredHiddenIds = hiddenIds.filter((id: string) => typeof id === 'string' && validIds.has(id) && id !== 'settings');
          setHiddenSystemItemIds(filteredHiddenIds);
          saveHiddenSidebarSystemItemIds(filteredHiddenIds);
        }
        localStorage.setItem(appliedKey, '1');
      }
    } catch (e) {
      console.error('Failed to apply default sidebar order:', e);
    }
  }, [defaultSidebarData?.default_sidebar_order, setSidebarOrder, user, authEnabled]);

  // Check advanced auth status — the notifications nav item is gated on it
  // (rendered only when authEnabled && advanced_auth_enabled && user_notifications_enabled).
  const { data: advancedAuthStatus } = useQuery({
    queryKey: ['advancedAuthStatus'],
    queryFn: api.getAdvancedAuthStatus,
    staleTime: 5 * 60 * 1000, // 5 minutes
    enabled: authEnabled,
  });

  const { data: updateCheck } = useQuery({
    queryKey: ['updateCheck'],
    queryFn: api.checkForUpdates,
    enabled: settings?.check_updates !== false,
    staleTime: 60 * 60 * 1000, // 1 hour
    refetchInterval: 60 * 60 * 1000, // Check every hour
  });

  // Fetch external links for sidebar
  const { data: externalLinks } = useQuery({
    queryKey: ['external-links'],
    queryFn: api.getExternalLinks,
  });

  // Fetch smart plugs to check for switchbar items
  const { data: smartPlugs } = useQuery({
    queryKey: ['smart-plugs'],
    queryFn: api.getSmartPlugs,
    staleTime: 30 * 1000, // 30 seconds
  });

  const hasSwitchbarPlugs = smartPlugs?.some(p => p.show_in_switchbar) ?? false;

  const expandedNavMenuIdSet = useMemo(() => new Set(expandedNavMenuIds), [expandedNavMenuIds]);

  const toggleNavMenu = useCallback((id: string) => {
    setExpandedNavMenuIds((current) =>
      current.includes(id)
        ? []
        : [id],
    );
  }, []);

  const getNavItemLabel = useCallback((item: NavItem) => {
    const defaultValue = i18n.resolvedLanguage?.startsWith('de')
      ? item.defaultLabelDe ?? item.defaultLabel
      : item.defaultLabel;
    return t(item.labelKey, { defaultValue });
  }, [i18n.resolvedLanguage, t]);

  // Check debug logging state
  const { data: debugLoggingState } = useQuery({
    queryKey: ['debugLogging'],
    queryFn: supportApi.getDebugLoggingState,
    staleTime: 60 * 1000, // 1 minute
    refetchInterval: 60 * 1000, // Refresh every minute
  });

  // Check developer LAN mode warnings
  const { data: devModeWarnings } = useQuery({
    queryKey: ['developer-mode-warnings'],
    queryFn: api.getDeveloperModeWarnings,
    staleTime: 10 * 1000,
    refetchInterval: 30 * 1000,
    refetchOnWindowFocus: true,
  });

  // Fetch pending queue items count for badge
  const { data: queueItems } = useQuery({
    queryKey: ['queue', 'pending'],
    queryFn: () => api.getQueue(undefined, 'pending'),
    staleTime: 5 * 1000, // 5 seconds
    refetchInterval: 5 * 1000, // Refresh every 5 seconds
    refetchOnWindowFocus: true,
  });
  const pendingQueueCount = queueItems?.length ?? 0;

  // Fetch pending uploads count for archive badge (virtual printer review items)
  const { data: pendingUploadsData } = useQuery({
    queryKey: ['pending-uploads', 'count'],
    queryFn: pendingUploadsApi.getCount,
    staleTime: 5 * 1000, // 5 seconds
    refetchInterval: 5 * 1000, // Refresh every 5 seconds
    refetchOnWindowFocus: true,
  });
  const pendingUploadsCount = pendingUploadsData?.count ?? 0;

  // Check if any printer with pending queue items needs plate clearing
  const queuePrinterIds = useMemo(() => {
    const ids = new Set<number>();
    queueItems?.forEach(item => {
      if (item.printer_id) ids.add(item.printer_id);
    });
    return Array.from(ids);
  }, [queueItems]);

  const printerStatusQueries = useQueries({
    queries: queuePrinterIds.map(id => ({
      queryKey: ['printerStatus', id],
      queryFn: () => api.getPrinterStatus(id),
      staleTime: 30 * 1000, // WebSocket keeps this warm
    })),
  });

  const needsClearPlate = printerStatusQueries.some(result => {
    const status = result.data;
    if (!status) return false;
    return !!status.awaiting_plate_clear;
  });

  // Calculate debug duration client-side for real-time updates
  const [debugDuration, setDebugDuration] = useState<number | null>(null);
  useEffect(() => {
    if (!debugLoggingState?.enabled || !debugLoggingState.enabled_at) {
      setDebugDuration(null);
      return;
    }
    const enabledAt = parseUTCDate(debugLoggingState.enabled_at)?.getTime() ?? Date.now();
    const updateDuration = () => {
      setDebugDuration(Math.floor((Date.now() - enabledAt) / 1000));
    };
    updateDuration();
    const interval = setInterval(updateDuration, 1000);
    return () => clearInterval(interval);
  }, [debugLoggingState?.enabled, debugLoggingState?.enabled_at]);

  // Build the unified sidebar items list - memoized to prevent re-renders
  const navItemsMap = useMemo(() => new Map(defaultNavItems.map(item => [item.id, item])), []);
  const extLinksMap = useMemo(() => new Map((externalLinks || []).map(link => [`ext-${link.id}`, link])), [externalLinks]);

  // Compute the ordered sidebar: include stored order + any new items
  // Hide nav items the user doesn't have read permission for
  const orderedSidebarIds = (() => {
    const result: string[] = [];
    const seen = new Set<string>();

    // Map nav item IDs to the permission(s) required to see them. Resources
    // that ship in three tiers (legacy `*:read` + granular `*:read_own` /
    // `*:read_all`) list all three: the default Operators group is seeded
    // with `_own` only, so gating on the legacy alone hides the entry from
    // every non-admin user even though the underlying API accepts their
    // request (#1755).
    const navPermissions: Record<string, Permission | Permission[]> = {
      dashboard: 'stats:read',
      archives: ['archives:read', 'archives:read_own', 'archives:read_all'],
      queue: ['queue:read', 'queue:read_own', 'queue:read_all'],
      profiles: 'kprofiles:read',
      maintenance: 'maintenance:read',
      projects: 'projects:read',
      inventory: 'inventory:read',
      'warehouse-filament': 'inventory:read',
      'warehouse-parts': 'inventory:read',
      'warehouse-stock': 'inventory:read',
      files: ['library:read', 'library:read_own', 'library:read_all'],
      makerworld: 'makerworld:view',
      orders: ['orders:read', 'customers:read', 'calculations:read', 'commercial_documents:read'],
      'orders-offers': 'commercial_documents:read',
      'orders-calculation': 'calculations:read',
      'orders-customers': 'customers:read',
      'orders-invoice': 'commercial_documents:read',
      settings: 'settings:read',
      'settings-general': 'settings:read',
      'settings-users-security': 'settings:read',
      'settings-printers-production': 'settings:read',
      'settings-projects-files': 'settings:read',
      'settings-warehouse-material': 'settings:read',
      'settings-orders-calculation': 'settings:read',
      'settings-integrations': 'settings:read',
      'settings-operations': 'settings:read',
      // The user-email-preferences API requires notifications:user_email, so
      // gate the nav item on the same permission (both default groups —
      // Administrators and Operators — hold it). The advanced-auth /
      // user_notifications enablement gate is applied separately below.
      notifications: 'notifications:user_email',
    };

    const isHidden = (id: string) => {
      // User-toggled hide (#1673) wins first — cheapest check, explicit intent.
      if (hiddenSystemItemIds.includes(id)) return true;
      const item = navItemsMap.get(id);
      if (item?.parentId && hiddenSystemItemIds.includes(item.parentId)) return true;
      // Permission gate accepts Permission | Permission[] so resources with
      // granular `*:read_own` / `*:read_all` tiers (default Operators group)
      // don't get hidden from users who only hold the granular variant (#1755).
      if (authEnabled && id in navPermissions) {
        const required = navPermissions[id];
        const granted = Array.isArray(required)
          ? required.some((p) => hasPermission(p))
          : hasPermission(required);
        if (!granted) return true;
      }
      // notifications nav item also requires advanced auth to be enabled and user_notifications_enabled setting
      if (id === 'notifications' && (!authEnabled || !advancedAuthStatus?.advanced_auth_enabled || (settings?.user_notifications_enabled === false))) return true;
      return false;
    };

    // Add items in stored order
    for (const id of sidebarOrder) {
      if (isHidden(id)) continue;
      if (navItemsMap.has(id) || extLinksMap.has(id)) {
        result.push(id);
        seen.add(id);
      }
    }

    // Add any new internal nav items not in stored order
    for (const item of defaultNavItems) {
      if (isHidden(item.id)) continue;
      if (!seen.has(item.id)) {
        const defaultIndex = defaultSidebarOrder.indexOf(item.id);
        let insertAt = result.length;
        for (let i = defaultIndex + 1; i < defaultSidebarOrder.length; i += 1) {
          const nextIndex = result.indexOf(defaultSidebarOrder[i]);
          if (nextIndex !== -1) {
            insertAt = nextIndex;
            break;
          }
        }
        if (insertAt === result.length) {
          for (let i = defaultIndex - 1; i >= 0; i -= 1) {
            const previousIndex = result.indexOf(defaultSidebarOrder[i]);
            if (previousIndex !== -1) {
              insertAt = previousIndex + 1;
              break;
            }
          }
        }
        result.splice(insertAt, 0, item.id);
        seen.add(item.id);
      }
    }

    // Add any new external links not in stored order
    for (const link of externalLinks || []) {
      const extId = `ext-${link.id}`;
      if (!seen.has(extId)) {
        result.push(extId);
        seen.add(extId);
      }
    }

    return result;
  })();

  // Show update banner if update available and not dismissed for this version.
  // Suppressed when running as a Home Assistant addon — HA Supervisor surfaces
  // its own update notification in the HA UI, so the in-app banner is duplicate
  // noise that links to a page that just says "update via HA."
  const showUpdateBanner = updateCheck?.update_available &&
    updateCheck.latest_version &&
    updateCheck.latest_version !== dismissedUpdateVersion &&
    !updateCheck.is_ha_addon;

  const dismissUpdateBanner = () => {
    if (updateCheck?.latest_version) {
      sessionStorage.setItem('dismissedUpdateVersion', updateCheck.latest_version);
      setDismissedUpdateVersion(updateCheck.latest_version);
    }
  };

  // Redirect to default view on initial load
  useEffect(() => {
    if (!hasRedirected.current && location.pathname === '/') {
      const defaultView = getDefaultView();
      if (defaultView !== '/') {
        hasRedirected.current = true;
        navigate(defaultView, { replace: true });
      }
    }
  }, [location.pathname, navigate]);

  useEffect(() => {
    const activeParentId = getActiveParentNavItemId(location.pathname, location.search);
    if (!activeParentId) return;
    setExpandedNavMenuIds([activeParentId]);
  }, [location.pathname, location.search]);

  useEffect(() => {
    localStorage.setItem('sidebarExpanded', String(sidebarExpanded));
  }, [sidebarExpanded]);

  useEffect(() => {
    const refreshSidebarLayout = () => {
      setSidebarOrder(getSidebarOrder(defaultSidebarOrder));
      setHiddenSystemItemIds(getHiddenSidebarSystemItemIds());
    };
    window.addEventListener(SIDEBAR_LAYOUT_CHANGED_EVENT, refreshSidebarLayout);
    window.addEventListener('storage', refreshSidebarLayout);
    return () => {
      window.removeEventListener(SIDEBAR_LAYOUT_CHANGED_EVENT, refreshSidebarLayout);
      window.removeEventListener('storage', refreshSidebarLayout);
    };
  }, [defaultSidebarOrder]);

  // Close compact drawer on navigation
  useEffect(() => {
    if (isSidebarCompact) {
      setMobileDrawerOpen(false);
    }
  }, [location.pathname, isSidebarCompact]);

  // Listen for plate detection warnings (objects on plate, print paused)
  // Only show to users with printers:control permission
  useEffect(() => {
    const handlePlateNotEmpty = (event: Event) => {
      // Only show alert to users who can control printers
      if (!hasPermission('printers:control')) {
        return;
      }
      const detail = (event as CustomEvent).detail;
      setPlateDetectionAlert({
        printer_id: detail.printer_id,
        printer_name: detail.printer_name,
        message: detail.message,
      });
    };
    window.addEventListener('plate-not-empty', handlePlateNotEmpty);
    return () => window.removeEventListener('plate-not-empty', handlePlateNotEmpty);
  }, [hasPermission]);

  // Global keyboard shortcuts for navigation
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    const target = e.target as HTMLElement;
    // Ignore if typing in an input/textarea
    if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
      return;
    }

    // Number keys for navigation (1-9) - follows sidebar order including external links
    if (!e.metaKey && !e.ctrlKey && !e.altKey) {
      const keyNum = parseInt(e.key);
      if (keyNum >= 1 && keyNum <= orderedSidebarIds.length && keyNum <= 9) {
        const id = orderedSidebarIds[keyNum - 1];
        e.preventDefault();

        if (isExternalSidebarItemId(id)) {
          // External link
          const extLink = extLinksMap.get(id);
          if (extLink?.open_in_new_tab) {
            window.open(extLink.url, '_blank', 'noopener,noreferrer');
          } else {
            const linkId = id.replace('ext-', '');
            navigate(`/external/${linkId}`);
          }
        } else {
          // Internal nav item
          const navItem = navItemsMap.get(id);
          if (navItem) {
            const hasChildren = orderedSidebarIds.some((childId) => navItemsMap.get(childId)?.parentId === id);
            if (hasChildren) {
              toggleNavMenu(id);
            } else {
              navigate(navItem.to);
            }
          }
        }
        return;
      }

      switch (e.key) {
        case '?':
          e.preventDefault();
          setShowShortcuts(true);
          break;
        case 'Escape':
          setShowShortcuts(false);
          break;
      }
    }
  }, [navigate, orderedSidebarIds, navItemsMap, extLinksMap, toggleNavMenu]);

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  const renderNavIcon = (itemId: string, Icon: LucideIcon, isSmall = false) => {
    const showQueueBadge = itemId === 'queue' && pendingQueueCount > 0;
    const showArchiveBadge = itemId === 'archives' && pendingUploadsCount > 0;
    const badgeCount = showQueueBadge ? pendingQueueCount : showArchiveBadge ? pendingUploadsCount : 0;
    const showBadge = showQueueBadge || showArchiveBadge;
    const showClearPlateDot = itemId === 'printers' && needsClearPlate;

    return (
      <div className="relative">
        <Icon className={`${isSmall ? 'w-4 h-4' : 'w-5 h-5'} flex-shrink-0`} />
        {showClearPlateDot && (
          <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 bg-yellow-500 rounded-full border-2 border-bambu-dark-secondary" />
        )}
        {showBadge && (
          <span className={`absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] px-1 flex items-center justify-center text-[10px] font-bold rounded-full ${
            showArchiveBadge ? 'bg-blue-500 text-white' : 'bg-yellow-500 text-black'
          }`}>
            {badgeCount > 99 ? '99+' : badgeCount}
          </span>
        )}
      </div>
    );
  };

  return (
    <div className="flex min-h-screen">
      {/* Compact Header */}
      {isSidebarCompact && (
        <header className="fixed top-0 left-0 right-0 z-40 h-14 bg-bambu-dark-secondary border-b border-bambu-dark-tertiary flex items-center px-4">
          <button
            onClick={() => setMobileDrawerOpen(true)}
            className="p-2 -ml-2 rounded-lg hover:bg-bambu-dark-tertiary transition-colors"
            aria-label="Open menu"
          >
            <Menu className="w-6 h-6 text-white" />
          </button>
          <img
            src="/img/printops_logo.svg"
            alt="PrintOps"
            className="h-8 ml-3"
          />
        </header>
      )}

      {/* Compact Drawer Backdrop */}
      {isSidebarCompact && mobileDrawerOpen && (
        <div
          className="fixed inset-0 bg-black/60 z-40 transition-opacity"
          onClick={() => setMobileDrawerOpen(false)}
        />
      )}

      {/* Sidebar / Mobile Drawer */}
      <aside
        className={`bg-bambu-dark-secondary border-r border-bambu-dark-tertiary flex flex-col transition-all duration-300 ${
          isSidebarCompact
            ? `fixed inset-y-0 left-0 z-50 w-72 transform ${mobileDrawerOpen ? 'translate-x-0' : '-translate-x-full'}`
            : `fixed inset-y-0 left-0 z-30 ${sidebarExpanded ? 'w-64' : 'w-16'}`
        }`}
      >
        {/* Logo */}
        <div className={`border-b border-bambu-dark-tertiary flex items-center justify-center ${isSidebarCompact || sidebarExpanded ? 'p-4' : 'p-2'}`}>
          <img
            src={isSidebarCompact || sidebarExpanded ? '/img/printops_logo.svg' : '/img/printops_icon.png'}
            alt="PrintOps"
            className={isSidebarCompact || sidebarExpanded ? 'h-16 w-auto' : 'h-10 w-10 object-contain'}
          />
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-2 overflow-y-auto">
          <ul className="space-y-2">
            {orderedSidebarIds.filter((id) => {
              const navItem = navItemsMap.get(id);
              return !navItem?.parentId || !orderedSidebarIds.includes(navItem.parentId);
            }).map((id) => {
              const isExternal = isExternalSidebarItemId(id);

              if (isExternal) {
                // Render external link
                const link = extLinksMap.get(id);
                if (!link) return null;

                const LinkIcon = link.custom_icon ? null : getIconByName(link.icon);
                return (
                  <li key={id}>
                    {link.open_in_new_tab ? (
                      <a
                        href={link.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={`flex items-center ${isSidebarCompact || sidebarExpanded ? 'gap-3 px-4' : 'justify-center px-2'} py-3 rounded-lg transition-colors group text-bambu-gray-light hover:bg-bambu-dark-tertiary hover:text-white`}
                        title={!isSidebarCompact && !sidebarExpanded ? link.name : undefined}
                      >
                        {link.custom_icon ? (
                          <img
                            src={api.getExternalLinkIconUrl(link.id)}
                            alt=""
                            className="w-5 h-5 flex-shrink-0"
                          />
                        ) : (
                          LinkIcon && <LinkIcon className="w-5 h-5 flex-shrink-0" />
                        )}
                        {(isSidebarCompact || sidebarExpanded) && <span>{link.name}</span>}
                      </a>
                    ) : (
                      <NavLink
                        to={`/external/${link.id}`}
                        className={({ isActive }) =>
                          `flex items-center ${isSidebarCompact || sidebarExpanded ? 'gap-3 px-4' : 'justify-center px-2'} py-3 rounded-lg transition-colors group ${
                            isActive
                              ? 'bg-bambu-green text-white'
                              : 'text-bambu-gray-light hover:bg-bambu-dark-tertiary hover:text-white'
                          }`
                        }
                        title={!isSidebarCompact && !sidebarExpanded ? link.name : undefined}
                      >
                        {link.custom_icon ? (
                          <img
                            src={api.getExternalLinkIconUrl(link.id)}
                            alt=""
                            className="w-5 h-5 flex-shrink-0"
                          />
                        ) : (
                          LinkIcon && <LinkIcon className="w-5 h-5 flex-shrink-0" />
                        )}
                        {(isSidebarCompact || sidebarExpanded) && <span>{link.name}</span>}
                      </NavLink>
                    )}
                  </li>
                );
              } else {
                // Render internal nav item
                const navItem = navItemsMap.get(id);
                if (!navItem) return null;

                const { to, icon: Icon } = navItem;
                const isChildItem = Boolean(navItem.parentId && orderedSidebarIds.includes(navItem.parentId));
                const isExpanded = isSidebarCompact || sidebarExpanded;
                const childIds = orderedSidebarIds.filter((childId) => navItemsMap.get(childId)?.parentId === id);
                const hasChildren = childIds.length > 0;
                const isMenuOpen = expandedNavMenuIdSet.has(id);
                const hasActiveChild = childIds.some((childId) => {
                  const childItem = navItemsMap.get(childId);
                  return childItem ? routeMatches(location.pathname, location.search, childItem.to) : false;
                });
                const isParentLinkActive = routeMatches(location.pathname, location.search, to) && !hasActiveChild;
                const submenuId = `sidebar-submenu-${id}`;

                if (hasChildren) {
                  return (
                    <li key={id}>
                      <div className={`flex items-center ${isExpanded ? 'gap-1' : 'justify-center gap-0.5'}`}>
                        <NavLink
                          to={to}
                          end
                          onClick={() => {
                            setExpandedNavMenuIds((current) => (current.includes(id) ? current : [id]));
                          }}
                          className={() =>
                            `min-w-0 flex items-center ${isExpanded ? 'flex-1 gap-3 px-4' : 'justify-center px-2'} py-3 rounded-lg transition-colors group ${
                              isParentLinkActive
                                ? 'bg-bambu-green text-white'
                                : 'text-bambu-gray-light hover:bg-bambu-dark-tertiary hover:text-white'
                            }`
                          }
                          title={!isSidebarCompact && !sidebarExpanded ? getNavItemLabel(navItem) : undefined}
                        >
                          {renderNavIcon(id, Icon)}
                          {isExpanded && <span className="truncate">{getNavItemLabel(navItem)}</span>}
                        </NavLink>
                        <button
                          type="button"
                          aria-expanded={isMenuOpen}
                          aria-controls={submenuId}
                          onClick={() => toggleNavMenu(id)}
                          className={`flex items-center justify-center ${isExpanded ? 'px-2' : 'px-1'} py-3 rounded-lg transition-colors ${
                            isMenuOpen
                              ? 'bg-bambu-dark-tertiary text-white'
                              : 'text-bambu-gray-light hover:bg-bambu-dark-tertiary hover:text-white'
                          }`}
                          title={getNavItemLabel(navItem)}
                        >
                          {isMenuOpen ? (
                            <ChevronDown className="w-4 h-4 flex-shrink-0" />
                          ) : (
                            <ChevronRight className="w-4 h-4 flex-shrink-0" />
                          )}
                        </button>
                      </div>
                      {isMenuOpen && (
                        <ul id={submenuId} className="mt-1 space-y-1">
                          {childIds.map((childId) => {
                            const childItem = navItemsMap.get(childId);
                            if (!childItem) return null;
                            const ChildIcon = childItem.icon;
                            const childActive = routeMatches(location.pathname, location.search, childItem.to);

                            return (
                              <li key={childId}>
                                <NavLink
                                  to={childItem.to}
                                  className={() =>
                                    `flex items-center ${isExpanded ? 'ml-5 gap-2 px-3 text-sm' : 'justify-center px-2'} py-2 rounded-lg transition-colors group ${
                                      childActive
                                        ? 'bg-bambu-green text-white'
                                        : 'text-bambu-gray-light hover:bg-bambu-dark-tertiary hover:text-white'
                                    }`
                                  }
                                  title={!isSidebarCompact && !sidebarExpanded ? getNavItemLabel(childItem) : undefined}
                                >
                                  {renderNavIcon(childId, ChildIcon, true)}
                                  {isExpanded && <span>{getNavItemLabel(childItem)}</span>}
                                </NavLink>
                              </li>
                            );
                          })}
                        </ul>
                      )}
                    </li>
                  );
                }

                return (
                  <li key={id}>
                    <NavLink
                      to={to}
                      className={({ isActive }) =>
                        `flex items-center ${isExpanded ? `${isChildItem ? 'ml-5 gap-2 px-3 text-sm' : 'gap-3 px-4'}` : 'justify-center px-2'} ${isChildItem ? 'py-2' : 'py-3'} rounded-lg transition-colors group ${
                          isActive
                            ? 'bg-bambu-green text-white'
                            : 'text-bambu-gray-light hover:bg-bambu-dark-tertiary hover:text-white'
                        }`
                      }
                      title={!isSidebarCompact && !sidebarExpanded ? getNavItemLabel(navItem) : undefined}
                    >
                      {renderNavIcon(id, Icon, isChildItem)}
                      {isExpanded && <span>{getNavItemLabel(navItem)}</span>}
                    </NavLink>
                  </li>
                );
              }
            })}
          </ul>
        </nav>

        {/* Collapse toggle - hide on compact sidebar */}
        {!isSidebarCompact && (
          <button
            onClick={() => setSidebarExpanded(!sidebarExpanded)}
            className="p-2 mx-2 mb-2 rounded-lg hover:bg-bambu-dark-tertiary transition-colors text-bambu-gray-light hover:text-white flex items-center justify-center"
            title={sidebarExpanded ? t('nav.collapseSidebar') : t('nav.expandSidebar')}
          >
            {sidebarExpanded ? (
              <ChevronLeft className="w-5 h-5" />
            ) : (
              <ChevronRight className="w-5 h-5" />
            )}
          </button>
        )}

        {/* Footer */}
        <div className="flex-shrink-0 p-2 border-t border-bambu-dark-tertiary">
          {isSidebarCompact || sidebarExpanded ? (
            <div className="flex flex-col gap-2 px-2">
              {/* Top row: icons */}
              <div className="flex items-center justify-center gap-1 flex-wrap">
                {hasSwitchbarPlugs && (
                  <div className="relative">
                    <button
                      onMouseEnter={() => setShowSwitchbar(true)}
                      className={`p-2 rounded-lg hover:bg-bambu-dark-tertiary transition-colors ${
                        showSwitchbar ? 'text-bambu-green' : 'text-bambu-gray-light hover:text-white'
                      }`}
                      title={t('nav.smartSwitches', { defaultValue: 'Smart Switches' })}
                    >
                      <Plug className="w-5 h-5" />
                    </button>
                    {showSwitchbar && (
                      <SwitchbarPopover onClose={() => setShowSwitchbar(false)} />
                    )}
                  </div>
                )}
                {hasPermission('system:read') ? (
                  <NavLink
                    to="/system"
                    className={({ isActive }) =>
                      `p-2 rounded-lg hover:bg-bambu-dark-tertiary transition-colors ${
                        isActive ? 'text-bambu-green' : 'text-bambu-gray-light hover:text-white'
                      }`
                    }
                    title={t('nav.system')}
                  >
                    <Info className="w-5 h-5" />
                  </NavLink>
                ) : (
                  <span
                    className="p-2 rounded-lg text-bambu-gray/50 cursor-not-allowed"
                    title="You do not have permission to view system information"
                  >
                    <Info className="w-5 h-5" />
                  </span>
                )}
                <InstallAppButton />
                <a
                  href="https://github.com/ichwars/PrintOps"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-2 rounded-lg hover:bg-bambu-dark-tertiary transition-colors text-bambu-gray-light hover:text-white"
                  title={t('nav.viewOnGithub')}
                >
                  <Github className="w-5 h-5" />
                </a>
                <button
                  onClick={() => setShowShortcuts(true)}
                  className="p-2 rounded-lg hover:bg-bambu-dark-tertiary transition-colors text-bambu-gray-light hover:text-white"
                  title={t('nav.keyboardShortcuts')}
                >
                  <Keyboard className="w-5 h-5" />
                </button>
                <button
                  onClick={toggleMode}
                  className="p-2 rounded-lg hover:bg-bambu-dark-tertiary transition-colors text-bambu-gray-light hover:text-white"
                  title={themeSwitchTitle}
                >
                  <ThemeIcon className="w-5 h-5" />
                </button>
                {authEnabled && user && (
                  <>
                    <button
                      onClick={() => setShowChangePasswordModal(true)}
                      className="p-2 rounded-lg hover:bg-bambu-dark-tertiary transition-colors text-bambu-gray-light hover:text-white"
                      title={t('changePassword.title')}
                    >
                      <Key className="w-5 h-5" />
                    </button>
                    <button
                      onClick={logout}
                      className="p-2 rounded-lg hover:bg-bambu-dark-tertiary transition-colors text-bambu-gray-light hover:text-white"
                      title={t('nav.logout', { defaultValue: 'Logout' })}
                    >
                      <LogOut className="w-5 h-5" />
                    </button>
                  </>
                )}
              </div>
              {/* Bottom row: version */}
              <div className="flex items-center justify-center gap-2">
                <span className="text-sm text-bambu-gray">v{versionInfo?.version || '...'}</span>
                {updateCheck?.update_available && (
                  <button
                    onClick={() => navigate('/settings')}
                    className="flex items-center gap-1 text-xs text-bambu-green hover:text-bambu-green/80 transition-colors"
                    title={t('nav.updateAvailable', { version: updateCheck.latest_version })}
                  >
                    <ArrowUpCircle className="w-4 h-4" />
                    <span>{t('nav.update')}</span>
                  </button>
                )}
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-1 overflow-y-auto max-h-[50vh]">
              {updateCheck?.update_available && (
                <button
                  onClick={() => navigate('/settings')}
                  className="p-2 rounded-lg hover:bg-bambu-dark-tertiary transition-colors text-bambu-green hover:text-bambu-green/80"
                  title={t('nav.updateAvailable', { version: updateCheck.latest_version })}
                >
                  <ArrowUpCircle className="w-5 h-5" />
                </button>
              )}
              {hasSwitchbarPlugs && (
                <div className="relative">
                  <button
                    onMouseEnter={() => setShowSwitchbar(true)}
                    className={`p-2 rounded-lg hover:bg-bambu-dark-tertiary transition-colors ${
                      showSwitchbar ? 'text-bambu-green' : 'text-bambu-gray-light hover:text-white'
                    }`}
                    title={t('nav.smartSwitches', { defaultValue: 'Smart Switches' })}
                  >
                    <Plug className="w-5 h-5" />
                  </button>
                  {showSwitchbar && (
                    <SwitchbarPopover onClose={() => setShowSwitchbar(false)} />
                  )}
                </div>
              )}
              {hasPermission('system:read') ? (
                <NavLink
                  to="/system"
                  className={({ isActive }) =>
                    `p-2 rounded-lg hover:bg-bambu-dark-tertiary transition-colors ${
                      isActive ? 'text-bambu-green' : 'text-bambu-gray-light hover:text-white'
                    }`
                  }
                  title={t('nav.system')}
                >
                  <Info className="w-5 h-5" />
                </NavLink>
              ) : (
                <span
                  className="p-2 rounded-lg text-bambu-gray/50 cursor-not-allowed"
                  title="You do not have permission to view system information"
                >
                  <Info className="w-5 h-5" />
                </span>
              )}
              <InstallAppButton />
              <a
                href="https://github.com/ichwars/PrintOps"
                target="_blank"
                rel="noopener noreferrer"
                className="p-2 rounded-lg hover:bg-bambu-dark-tertiary transition-colors text-bambu-gray-light hover:text-white"
                title={t('nav.viewOnGithub')}
              >
                <Github className="w-5 h-5" />
              </a>
              <button
                onClick={() => setShowShortcuts(true)}
                className="p-2 rounded-lg hover:bg-bambu-dark-tertiary transition-colors text-bambu-gray-light hover:text-white"
                title={t('nav.keyboardShortcuts')}
              >
                <Keyboard className="w-5 h-5" />
              </button>
              <button
                onClick={toggleMode}
                className="p-2 rounded-lg hover:bg-bambu-dark-tertiary transition-colors text-bambu-gray-light hover:text-white"
                title={themeSwitchTitle}
              >
                <ThemeIcon className="w-5 h-5" />
              </button>
              {authEnabled && user && (
                <>
                  <button
                    onClick={() => setShowChangePasswordModal(true)}
                    className="p-2 rounded-lg hover:bg-bambu-dark-tertiary transition-colors text-bambu-gray-light hover:text-white"
                    title={t('changePassword.title')}
                  >
                    <Key className="w-5 h-5" />
                  </button>
                  <button
                    onClick={logout}
                    className="p-2 rounded-lg hover:bg-bambu-dark-tertiary transition-colors text-bambu-gray-light hover:text-white"
                    title={t('nav.logout', { defaultValue: 'Logout' })}
                  >
                    <LogOut className="w-5 h-5" />
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      </aside>

      {/* Main content */}
      <main className={`flex-1 bg-bambu-dark overflow-auto transition-all duration-300 ${
        isSidebarCompact ? 'mt-14' : sidebarExpanded ? 'ml-64' : 'ml-16'
      }`}>
        {/* Debug logging indicator */}
        {debugLoggingState?.enabled && (
          <div className="bg-amber-100 dark:bg-amber-500/20 border-b border-amber-300 dark:border-amber-500/30 px-4 py-2 flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm">
              <Bug className="w-4 h-4 text-amber-500 animate-pulse" />
              <span className="text-amber-800 dark:text-amber-200">
                {t('support.debugLoggingActive', { defaultValue: 'Debug logging is active' })}
                {debugDuration !== null && (
                  <span className="text-amber-700/80 dark:text-amber-300/70 ml-2">
                    ({Math.floor(debugDuration / 60)}m {debugDuration % 60}s)
                  </span>
                )}
              </span>
              <button
                onClick={() => navigate('/system')}
                className="text-amber-700 dark:text-amber-400 hover:text-amber-900 dark:hover:text-amber-300 font-medium underline ml-2"
              >
                {t('support.manageLogs', { defaultValue: 'Manage' })}
              </button>
            </div>
          </div>
        )}
        {devModeWarnings && devModeWarnings.length > 0 && (
          <div className="bg-orange-100 dark:bg-orange-500/20 border-b border-orange-300 dark:border-orange-500/30 px-4 py-2 flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm">
              <ShieldAlert className="w-4 h-4 text-orange-500" />
              <span className="text-orange-800 dark:text-orange-200">
                {t('printers.developerModeWarning', {
                  names: devModeWarnings.map(w => w.name).join(', '),
                  defaultValue: `Developer LAN mode is not enabled on: ${devModeWarnings.map(w => w.name).join(', ')}. Some features may not work.`
                })}
              </span>
              <a href="https://wiki.bambulab.com/en/knowledge-sharing/enable-developer-mode"
                 target="_blank" rel="noopener noreferrer"
                 className="text-orange-700 dark:text-orange-400 hover:text-orange-900 dark:hover:text-orange-300 font-medium underline ml-2">
                {t('printers.howToEnable', { defaultValue: 'How to enable' })}
              </a>
            </div>
          </div>
        )}
        {/* Persistent update banner */}
        {showUpdateBanner && (
          <div className="bg-bambu-green/20 border-b border-bambu-green/30 px-4 py-2 flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm">
              <ArrowUpCircle className="w-4 h-4 text-bambu-green" />
              <span>
                {t('nav.updateAvailableBanner', {
                  version: updateCheck?.latest_version,
                  defaultValue: `Version ${updateCheck?.latest_version} is available!`
                })}
              </span>
              <button
                onClick={() => navigate('/settings')}
                className="text-bambu-green hover:text-bambu-green/80 font-medium underline"
              >
                {t('nav.viewUpdate', { defaultValue: 'View update' })}
              </button>
            </div>
            <button
              onClick={dismissUpdateBanner}
              className="p-1 hover:bg-bambu-dark-tertiary rounded transition-colors"
              title={t('common.dismiss', { defaultValue: 'Dismiss' })}
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}
        <Outlet />
      </main>

      <UnknownSpoolModal
        prompt={unknownSpool.prompt}
        isPending={unknownSpool.isPending}
        onConfirm={unknownSpool.confirm}
        onCancel={unknownSpool.cancel}
      />

      {/* Keyboard Shortcuts Modal */}
      {showShortcuts && (
        <KeyboardShortcutsModal
          onClose={() => setShowShortcuts(false)}
          sidebarItems={orderedSidebarIds.map(id => {
            if (isExternalSidebarItemId(id)) {
              const extLink = extLinksMap.get(id);
              return extLink ? { type: 'external' as const, label: extLink.name } : null;
            } else {
              const navItem = navItemsMap.get(id);
              return navItem
                ? { type: 'nav' as const, label: getNavItemLabel(navItem), labelKey: navItem.defaultLabel ? undefined : navItem.labelKey }
                : null;
            }
          }).filter(Boolean) as { type: 'nav' | 'external'; label: string; labelKey?: string }[]}
        />
      )}

      {/* Plate Detection Alert Modal */}
      {plateDetectionAlert && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-[100] p-4">
          <div className="bg-bambu-dark-secondary border-2 border-yellow-500 rounded-xl shadow-2xl max-w-md w-full animate-in fade-in zoom-in duration-200">
            <div className="p-6 text-center">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-yellow-500/20 flex items-center justify-center">
                <svg className="w-10 h-10 text-yellow-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <h2 className="text-xl font-bold text-yellow-700 dark:text-yellow-400 mb-2">
                {t('plateAlert.title')}
              </h2>
              <p className="text-lg text-white mb-2">
                {plateDetectionAlert.printer_name}
              </p>
              <p className="text-bambu-gray mb-6">
                {t('plateAlert.message')}
              </p>
              <button
                onClick={() => setPlateDetectionAlert(null)}
                className="w-full py-3 px-6 bg-yellow-500 hover:bg-yellow-600 text-black font-semibold rounded-lg transition-colors"
              >
                {t('plateAlert.understand')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Change Password Modal */}
      {showChangePasswordModal && (
        <div
          className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
          onClick={() => {
            setShowChangePasswordModal(false);
            setChangePasswordData({ currentPassword: '', newPassword: '', confirmPassword: '' });
          }}
        >
          <Card
            className="w-full max-w-md"
            onClick={(e: React.MouseEvent) => e.stopPropagation()}
          >
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Key className="w-5 h-5 text-bambu-green" />
                  <h2 className="text-lg font-semibold text-white">{t('changePassword.title')}</h2>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setShowChangePasswordModal(false);
                    setChangePasswordData({ currentPassword: '', newPassword: '', confirmPassword: '' });
                  }}
                >
                  <X className="w-5 h-5" />
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <TextField
                  type="text"
                  name="username"
                  autoComplete="username"
                  value={user?.username ?? ''}
                  readOnly
                  hidden
                  aria-hidden="true"
                  tabIndex={-1}
                />
                <div>
                  <label className="block text-sm font-medium text-white mb-2">
                    {t('changePassword.currentPassword')}
                  </label>
                  <TextField
                    type="password"
                    value={changePasswordData.currentPassword}
                    onChange={(e) => setChangePasswordData({ ...changePasswordData, currentPassword: e.target.value })}
                    className="w-full px-4 py-3 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-lg text-white placeholder-bambu-gray focus:outline-none focus:ring-2 focus:ring-bambu-green/50 focus:border-bambu-green transition-colors"
                    placeholder={t('changePassword.currentPasswordPlaceholder')}
                    autoComplete="current-password"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-white mb-2">
                    {t('changePassword.newPassword')}
                  </label>
                  <TextField
                    type="password"
                    value={changePasswordData.newPassword}
                    onChange={(e) => setChangePasswordData({ ...changePasswordData, newPassword: e.target.value })}
                    className="w-full px-4 py-3 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-lg text-white placeholder-bambu-gray focus:outline-none focus:ring-2 focus:ring-bambu-green/50 focus:border-bambu-green transition-colors"
                    placeholder={t('changePassword.newPasswordPlaceholder')}
                    autoComplete="new-password"
                    minLength={6}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-white mb-2">
                    {t('changePassword.confirmPassword')}
                  </label>
                  <TextField
                    type="password"
                    value={changePasswordData.confirmPassword}
                    onChange={(e) => setChangePasswordData({ ...changePasswordData, confirmPassword: e.target.value })}
                    className={`w-full px-4 py-3 bg-bambu-dark-secondary border rounded-lg text-white placeholder-bambu-gray focus:outline-none focus:ring-2 focus:ring-bambu-green/50 focus:border-bambu-green transition-colors ${
                      changePasswordData.confirmPassword && changePasswordData.newPassword !== changePasswordData.confirmPassword
                        ? 'border-red-500'
                        : 'border-bambu-dark-tertiary'
                    }`}
                    placeholder={t('changePassword.confirmPasswordPlaceholder')}
                    autoComplete="new-password"
                    minLength={6}
                  />
                  {changePasswordData.confirmPassword && changePasswordData.newPassword !== changePasswordData.confirmPassword && (
                    <p className="text-red-700 dark:text-red-400 text-xs mt-1">{t('changePassword.passwordsDoNotMatch')}</p>
                  )}
                </div>
              </div>
              <div className="mt-6 flex justify-end gap-3">
                <Button
                  variant="secondary"
                  onClick={() => {
                    setShowChangePasswordModal(false);
                    setChangePasswordData({ currentPassword: '', newPassword: '', confirmPassword: '' });
                  }}
                >
                  {t('common.cancel')}
                </Button>
                <Button
                  onClick={async () => {
                    if (changePasswordData.newPassword !== changePasswordData.confirmPassword) {
                      showToast(t('changePassword.passwordsDoNotMatch'), 'error');
                      return;
                    }
                    if (changePasswordData.newPassword.length < 6) {
                      showToast(t('changePassword.passwordTooShort'), 'error');
                      return;
                    }
                    setChangePasswordLoading(true);
                    try {
                      await api.changePassword(changePasswordData.currentPassword, changePasswordData.newPassword);
                      showToast(t('changePassword.success'), 'success');
                      setShowChangePasswordModal(false);
                      setChangePasswordData({ currentPassword: '', newPassword: '', confirmPassword: '' });
                    } catch (error: unknown) {
                      const message = error instanceof Error ? error.message : t('changePassword.failed');
                      showToast(message, 'error');
                    } finally {
                      setChangePasswordLoading(false);
                    }
                  }}
                  disabled={changePasswordLoading || !changePasswordData.currentPassword || !changePasswordData.newPassword || changePasswordData.newPassword !== changePasswordData.confirmPassword || changePasswordData.newPassword.length < 6}
                >
                  {changePasswordLoading ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      {t('changePassword.changing')}
                    </>
                  ) : (
                    <>
                      <Key className="w-4 h-4" />
                      {t('changePassword.title')}
                    </>
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
      <BugReportBubble />
    </div>
  );
}
