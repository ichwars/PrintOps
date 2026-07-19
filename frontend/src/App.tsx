import { Component, lazy, Suspense, type ReactNode, type ErrorInfo } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Layout, getDefaultView } from './components/Layout';
import { useWebSocket } from './hooks/useWebSocket';
import { useStreamTokenSync } from './hooks/useCameraStreamToken';
import { ThemeProvider } from './contexts/ThemeContext';
import { ToastProvider } from './contexts/ToastContext';
import { SliceJobTrackerProvider } from './contexts/SliceJobTrackerContext';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { ColorCatalogProvider } from './contexts/ColorCatalogContext';
import { SpoolBuddyLayout } from './components/spoolbuddy/SpoolBuddyLayout';

const PrintersPage = lazy(() => import('./pages/PrintersPage').then(({ PrintersPage }) => ({ default: PrintersPage })));
const ArchivesPage = lazy(() => import('./pages/ArchivesPage').then(({ ArchivesPage }) => ({ default: ArchivesPage })));
const QueuePage = lazy(() => import('./pages/QueuePage').then(({ QueuePage }) => ({ default: QueuePage })));
const StatsPage = lazy(() => import('./pages/StatsPage').then(({ StatsPage }) => ({ default: StatsPage })));
const SettingsPage = lazy(() => import('./pages/SettingsPage').then(({ SettingsPage }) => ({ default: SettingsPage })));
const ProfilesPage = lazy(() => import('./pages/ProfilesPage').then(({ ProfilesPage }) => ({ default: ProfilesPage })));
const MaintenancePage = lazy(() => import('./pages/MaintenancePage').then(({ MaintenancePage }) => ({ default: MaintenancePage })));
const ProjectsPage = lazy(() => import('./pages/ProjectsPage').then(({ ProjectsPage }) => ({ default: ProjectsPage })));
const ProjectDetailPage = lazy(() => import('./pages/ProjectDetailPage').then(({ ProjectDetailPage }) => ({ default: ProjectDetailPage })));
const FileManagerPage = lazy(() => import('./pages/FileManagerPage').then(({ FileManagerPage }) => ({ default: FileManagerPage })));
const LibraryTrashPage = lazy(() => import('./pages/LibraryTrashPage').then(({ LibraryTrashPage }) => ({ default: LibraryTrashPage })));
const WarehousePage = lazy(() => import('./pages/WarehousePage').then(({ WarehousePage }) => ({ default: WarehousePage })));
const SmallPartsPage = lazy(() => import('./pages/SmallPartsPage').then(({ SmallPartsPage }) => ({ default: SmallPartsPage })));
const SuppliersPage = lazy(() => import('./pages/SuppliersPage').then(({ SuppliersPage }) => ({ default: SuppliersPage })));
const OrdersPage = lazy(() => import('./pages/OrdersPage').then(({ OrdersPage }) => ({ default: OrdersPage })));
const OrdersOverviewPage = lazy(() => import('./pages/OrdersOverviewPage').then(({ OrdersOverviewPage }) => ({ default: OrdersOverviewPage })));
const OffersPage = lazy(() => import('./pages/OffersPage').then(({ OffersPage }) => ({ default: OffersPage })));
const OrderDetailPage = lazy(() => import('./pages/OrderDetailPage').then(({ OrderDetailPage }) => ({ default: OrderDetailPage })));
const OrdersCustomersPage = lazy(() => import('./pages/OrdersCustomersPage').then(({ OrdersCustomersPage }) => ({ default: OrdersCustomersPage })));
const CalculationsPage = lazy(() => import('./pages/CalculationsPage').then(({ CalculationsPage }) => ({ default: CalculationsPage })));
const CameraPage = lazy(() => import('./pages/CameraPage').then(({ CameraPage }) => ({ default: CameraPage })));
const StreamOverlayPage = lazy(() => import('./pages/StreamOverlayPage').then(({ StreamOverlayPage }) => ({ default: StreamOverlayPage })));
const ExternalLinkPage = lazy(() => import('./pages/ExternalLinkPage').then(({ ExternalLinkPage }) => ({ default: ExternalLinkPage })));
const GroupEditPage = lazy(() => import('./pages/GroupEditPage').then(({ GroupEditPage }) => ({ default: GroupEditPage })));
const InventoryPage = lazy(() => import('./pages/InventoryPage'));
const MakerworldPage = lazy(() => import('./pages/MakerworldPage').then(({ MakerworldPage }) => ({ default: MakerworldPage })));
const SystemInfoPage = lazy(() => import('./pages/SystemInfoPage').then(({ SystemInfoPage }) => ({ default: SystemInfoPage })));
const LoginPage = lazy(() => import('./pages/LoginPage').then(({ LoginPage }) => ({ default: LoginPage })));
const SetupPage = lazy(() => import('./pages/SetupPage').then(({ SetupPage }) => ({ default: SetupPage })));
const NotificationsPage = lazy(() => import('./pages/NotificationsPage').then(({ NotificationsPage }) => ({ default: NotificationsPage })));
const GCodeViewerPage = lazy(() => import('./pages/GCodeViewerPage').then(({ GCodeViewerPage }) => ({ default: GCodeViewerPage })));
const SpoolBuddyDashboard = lazy(() => import('./pages/spoolbuddy/SpoolBuddyDashboard').then(({ SpoolBuddyDashboard }) => ({ default: SpoolBuddyDashboard })));
const SpoolBuddyAmsPage = lazy(() => import('./pages/spoolbuddy/SpoolBuddyAmsPage').then(({ SpoolBuddyAmsPage }) => ({ default: SpoolBuddyAmsPage })));
const SpoolBuddySettingsPage = lazy(() => import('./pages/spoolbuddy/SpoolBuddySettingsPage').then(({ SpoolBuddySettingsPage }) => ({ default: SpoolBuddySettingsPage })));
const SpoolBuddyCalibrationPage = lazy(() => import('./pages/spoolbuddy/SpoolBuddyCalibrationPage').then(({ SpoolBuddyCalibrationPage }) => ({ default: SpoolBuddyCalibrationPage })));
const SpoolBuddyWriteTagPage = lazy(() => import('./pages/spoolbuddy/SpoolBuddyWriteTagPage').then(({ SpoolBuddyWriteTagPage }) => ({ default: SpoolBuddyWriteTagPage })));
const SpoolBuddyInventoryPage = lazy(() => import('./pages/spoolbuddy/SpoolBuddyInventoryPage').then(({ SpoolBuddyInventoryPage }) => ({ default: SpoolBuddyInventoryPage })));
class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null; errorInfo: ErrorInfo | null }> {
  state = { error: null as Error | null, errorInfo: null as ErrorInfo | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.setState({ errorInfo });
    console.error('React crash:', error, errorInfo);
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 24, color: '#ef4444', backgroundColor: '#18181b', minHeight: '100vh', fontFamily: 'monospace' }}>
          <h1 style={{ fontSize: 20, marginBottom: 12 }}>UI Crash</h1>
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 14 }}>{this.state.error.message}</pre>
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, color: '#a1a1aa', marginTop: 12 }}>
            {this.state.error.stack}
          </pre>
          <button
            onClick={() => { this.setState({ error: null, errorInfo: null }); }}
            style={{ marginTop: 16, padding: '8px 16px', backgroundColor: '#3b82f6', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer' }}
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60,
      retry: 1,
    },
  },
});

function StreamTokenSync() {
  useStreamTokenSync();
  return null;
}

function RouteFallback() {
  return (
    <div className="min-h-screen flex items-center justify-center" role="status" aria-live="polite">
      Loading...
    </div>
  );
}

function WebSocketProvider({ children }: { children: React.ReactNode }) {
  useWebSocket();
  return <>{children}</>;
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { authEnabled, loading, user } = useAuth();
  const location = useLocation();

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center">Loading...</div>;
  }

  if (authEnabled && !user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <>{children}</>;
}

function PermissionRoute({ permission, children }: { permission: string; children: React.ReactNode }) {
  // Permission-gated route: any user with the given permission can enter, not
  // just admins. Individual components below this guard apply their own
  // per-action permission checks. Used for pages where delegation is supported
  // (e.g. settings:read grants read-only access to Settings; specific tabs
  // require their own permissions like users:read, groups:update, etc.).
  const { authEnabled, loading, user, hasPermission } = useAuth();
  const location = useLocation();

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center">Loading...</div>;
  }

  // Auth disabled → open access (backward compatibility)
  if (!authEnabled) {
    return <>{children}</>;
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  if (!hasPermission(permission as Parameters<typeof hasPermission>[0])) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}

function SetupRoute({ children }: { children: React.ReactNode }) {
  const { authEnabled, loading } = useAuth();

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center">Loading...</div>;
  }

  // If auth is already enabled, redirect to login
  // Otherwise, allow access to setup page (even if setup was completed before)
  // This allows users to enable auth later if they skipped it during initial setup
  if (authEnabled) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

function App() {
  return (
    <ErrorBoundary>
      <ToastProvider>
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            {/* ThemeProvider sits inside AuthProvider so its initial
                ``api.getSettings()`` fetch can wait for AuthContext to
                resolve — otherwise it fires unconditionally on every
                login page load and returns 401. ErrorBoundary uses
                inline styles, so a missing theme on a crash screen is
                not a regression. */}
            <ThemeProvider>
            <ColorCatalogProvider>
            <SliceJobTrackerProvider>
            <StreamTokenSync />
            <BrowserRouter>
              <Suspense fallback={<RouteFallback />}>
              <Routes>
                {/* Setup page - only accessible if auth not enabled */}
                <Route path="/setup" element={<SetupRoute><SetupPage /></SetupRoute>} />

                {/* Login page */}
                <Route path="/login" element={<LoginPage />} />

                {/* Camera page - standalone, no layout, no WebSocket (doesn't need real-time updates) */}
                <Route path="/camera/:printerId" element={<CameraPage />} />

                {/* Stream overlay page - standalone for OBS/streaming embeds, no auth required */}
                <Route path="/overlay/:printerId" element={<StreamOverlayPage />} />

                {/* SpoolBuddy kiosk UI */}
                <Route element={<ProtectedRoute><WebSocketProvider><SpoolBuddyLayout /></WebSocketProvider></ProtectedRoute>}>
                  <Route path="spoolbuddy" element={<SpoolBuddyDashboard />} />
                  <Route path="spoolbuddy/ams" element={<SpoolBuddyAmsPage />} />
                  <Route path="spoolbuddy/write-tag" element={<SpoolBuddyWriteTagPage />} />
                  <Route path="spoolbuddy/inventory" element={<SpoolBuddyInventoryPage />} />
                  <Route path="spoolbuddy/settings" element={<SpoolBuddySettingsPage />} />
                  <Route path="spoolbuddy/calibration" element={<SpoolBuddyCalibrationPage />} />
                </Route>

                {/* Main app with WebSocket for real-time updates */}
                <Route element={<ProtectedRoute><WebSocketProvider><Layout /></WebSocketProvider></ProtectedRoute>}>
                  <Route index element={<Navigate to={getDefaultView()} replace />} />
                  <Route path="dashboard" element={<StatsPage />} />
                  <Route path="printers" element={<PrintersPage />} />
                  <Route path="archives" element={<ArchivesPage />} />
                  <Route path="queue" element={<QueuePage />} />
                  {/* Slicer Pipelines (#1425) — Pipelines tab lives on the
                      Print Queue page (Queue + History + Timeline +
                      Pipelines). Old standalone URL redirects. */}
                  <Route path="pipelines/runs" element={<Navigate to="/queue?tab=pipelines" replace />} />
                  <Route path="stats" element={<Navigate to="/dashboard" replace />} />
                  <Route path="profiles" element={<ProfilesPage />} />
                  <Route path="maintenance" element={<MaintenancePage />} />
                  <Route path="projects" element={<ProjectsPage />} />
                  <Route path="projects/:id" element={<ProjectDetailPage />} />
                  <Route path="warehouse" element={<WarehousePage />} />
                  <Route path="warehouse/filament" element={<InventoryPage />} />
                  <Route path="warehouse/parts" element={<SmallPartsPage />} />
                  <Route path="warehouse/stock" element={<WarehousePage />} />
                  <Route path="warehouse/suppliers" element={<PermissionRoute permission="inventory:read"><SuppliersPage /></PermissionRoute>} />
                  <Route path="warehouse/material" element={<Navigate to="/warehouse/parts" replace />} />
                  <Route path="warehouse/goods" element={<Navigate to="/warehouse/stock" replace />} />
                  <Route path="inventory" element={<Navigate to="/warehouse/filament" replace />} />
                  <Route path="orders" element={<OrdersOverviewPage />} />
                  <Route path="orders/:id" element={<OrderDetailPage />} />
                  <Route path="orders/customers" element={<OrdersCustomersPage />} />
                  <Route path="orders/calculation" element={<CalculationsPage />} />
                  <Route path="orders/offers" element={<OffersPage />} />
                  <Route path="orders/invoices" element={<OrdersPage />} />
                  <Route path="files" element={<FileManagerPage />} />
                  <Route path="files/trash" element={<LibraryTrashPage />} />
                  <Route path="makerworld" element={<PermissionRoute permission="makerworld:view"><MakerworldPage /></PermissionRoute>} />
                  <Route path="settings" element={<PermissionRoute permission="settings:read"><SettingsPage /></PermissionRoute>} />
                  <Route path="groups/new" element={<PermissionRoute permission="groups:create"><GroupEditPage /></PermissionRoute>} />
                  <Route path="groups/:id/edit" element={<PermissionRoute permission="groups:update"><GroupEditPage /></PermissionRoute>} />
                  <Route path="users" element={<Navigate to="/settings?tab=users" replace />} />
                  <Route path="groups" element={<Navigate to="/settings?tab=users" replace />} />
                  <Route path="system" element={<SystemInfoPage />} />
                  <Route path="notifications" element={<NotificationsPage />} />
                  <Route path="gcode-viewer" element={<GCodeViewerPage />} />
                  <Route path="external/:id" element={<ExternalLinkPage />} />
                  <Route path="camera-tokens" element={<Navigate to="/settings?tab=apikeys#card-camera-tokens" replace />} />
                </Route>
              </Routes>
              </Suspense>
            </BrowserRouter>
            </SliceJobTrackerProvider>
            </ColorCatalogProvider>
            </ThemeProvider>
          </AuthProvider>
        </QueryClientProvider>
      </ToastProvider>
    </ErrorBoundary>
  );
}

export default App;
