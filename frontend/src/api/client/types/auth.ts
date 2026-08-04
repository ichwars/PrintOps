// Permission type - all available permissions
export type Permission =
  | 'printers:read' | 'printers:create' | 'printers:update' | 'printers:delete' | 'printers:control' | 'printers:files' | 'printers:ams_rfid' | 'printers:clear_plate'
  | 'archives:read' | 'archives:read_own' | 'archives:read_all' | 'archives:create'
  | 'archives:update_own' | 'archives:update_all' | 'archives:delete_own' | 'archives:delete_all'
  | 'archives:reprint_own' | 'archives:reprint_all' | 'archives:purge'
  | 'queue:read' | 'queue:read_own' | 'queue:read_all' | 'queue:create'
  | 'queue:update_own' | 'queue:update_all' | 'queue:delete_own' | 'queue:delete_all'
  | 'queue:reorder'
  | 'library:read' | 'library:read_own' | 'library:read_all' | 'library:upload'
  | 'library:update_own' | 'library:update_all' | 'library:delete_own' | 'library:delete_all'
  | 'library:purge'
  | 'projects:read' | 'projects:create' | 'projects:update' | 'projects:delete'
  | 'customers:read' | 'customers:manage'
  | 'calculations:read' | 'calculations:update' | 'calculations:approve'
  | 'orders:read' | 'orders:update' | 'orders:cancel' | 'orders:manage_production'
  | 'commercial_documents:read' | 'commercial_documents:draft' | 'commercial_documents:approve'
  | 'commercial_documents:issue' | 'commercial_documents:correct' | 'commercial_documents:export'
  | 'commercial_documents:tax_override'
  | 'document_layouts:read' | 'document_layouts:manage'
  | 'document_templates:read' | 'document_templates:manage'
  | 'payments:read' | 'payments:manage'
  | 'order_audit:read'
  | 'order_settings:read' | 'order_settings:manage'
  | 'accounting_integrations:manage'
  | 'filaments:read' | 'filaments:create' | 'filaments:update' | 'filaments:delete'
  | 'inventory:read' | 'inventory:create' | 'inventory:update' | 'inventory:delete' | 'inventory:view_assignments'
  | 'inventory:forecast_read' | 'inventory:forecast_write'
  | 'smart_plugs:read' | 'smart_plugs:create' | 'smart_plugs:update' | 'smart_plugs:delete' | 'smart_plugs:control'
  | 'camera:view'
  | 'maintenance:read' | 'maintenance:create' | 'maintenance:update' | 'maintenance:delete'
  | 'kprofiles:read' | 'kprofiles:create' | 'kprofiles:update' | 'kprofiles:delete'
  | 'notifications:read' | 'notifications:create' | 'notifications:update' | 'notifications:delete' | 'notifications:user_email'
  | 'notification_templates:read' | 'notification_templates:update'
  | 'external_links:read' | 'external_links:create' | 'external_links:update' | 'external_links:delete'
  | 'discovery:scan'
  | 'firmware:read' | 'firmware:update'
  | 'ams_history:read'
  | 'stats:read' | 'stats:filter_by_user'
  | 'system:read'
  | 'settings:read' | 'settings:update' | 'settings:backup' | 'settings:restore'
  | 'github:backup' | 'github:restore'
  | 'cloud:auth' | 'orca_cloud:auth'
  | 'makerworld:view' | 'makerworld:import'
  | 'api_keys:read' | 'api_keys:create' | 'api_keys:update' | 'api_keys:delete'
  | 'users:read' | 'users:create' | 'users:update' | 'users:delete'
  | 'groups:read' | 'groups:create' | 'groups:update' | 'groups:delete'
  | 'pipelines:read' | 'pipelines:write' | 'pipelines:run'
  | 'websocket:connect';

// Group types
export interface GroupBrief {
  id: number;
  name: string;
}

export interface Group {
  id: number;
  name: string;
  description: string | null;
  permissions: Permission[];
  is_system: boolean;
  user_count: number;
  created_at: string;
  updated_at: string;
}

export interface GroupDetail extends Group {
  users: Array<{ id: number; username: string; is_active: boolean }>;
}

export interface GroupCreate {
  name: string;
  description?: string;
  permissions: Permission[];
}

export interface GroupUpdate {
  name?: string;
  description?: string;
  permissions?: Permission[];
}

export interface PermissionInfo {
  value: Permission;
  label: string;
}

export interface PermissionCategory {
  name: string;
  permissions: PermissionInfo[];
}

export interface PermissionsListResponse {
  categories: PermissionCategory[];
  all_permissions: Permission[];
}

// User email notification preferences
export interface UserEmailPreferences {
  notify_print_start: boolean;
  notify_print_complete: boolean;
  notify_print_failed: boolean;
  notify_print_stopped: boolean;
}

// Auth types
export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token?: string;
  token_type?: string;
  user?: UserResponse;
  /** Set when 2FA verification is required before a full token is issued. */
  requires_2fa?: boolean;
  pre_auth_token?: string;
  two_fa_methods?: string[];
}

export interface UserResponse {
  id: number;
  username: string;
  email?: string;
  role: string;  // Deprecated, kept for backward compatibility
  is_active: boolean;
  is_admin: boolean;  // Computed from role and group membership
  auth_source: string;  // "local" or "ldap"
  groups: GroupBrief[];
  permissions: Permission[];  // All permissions from groups
  allowed_printer_ids?: number[] | null;
  created_at: string;
}

export interface UserCreate {
  username: string;
  password?: string;  // Optional when advanced auth is enabled
  email?: string;
  role: string;
  group_ids?: number[];
  allowed_printer_ids?: number[] | null;
}

export interface UserUpdate {
  username?: string;
  password?: string;
  email?: string;
  role?: string;
  is_active?: boolean;
  group_ids?: number[];
  allowed_printer_ids?: number[] | null;
}

export interface SetupRequest {
  auth_enabled: boolean;
  admin_username?: string;
  admin_password?: string;
}

export interface ForgotPasswordRequest {
  email: string;
}

export interface ForgotPasswordResponse {
  message: string;
}

export interface ResetPasswordRequest {
  user_id: number;
}

export interface ResetPasswordResponse {
  message: string;
}

export interface SMTPSettings {
  smtp_host: string;
  smtp_port: number;
  smtp_username?: string;
  smtp_password?: string;
  smtp_security: 'starttls' | 'ssl' | 'none';
  smtp_auth_enabled: boolean;
  smtp_from_email: string;
  smtp_from_name: string;
}

// 2FA / MFA interfaces
export interface TwoFAStatus {
  totp_enabled: boolean;
  email_otp_enabled: boolean;
  backup_codes_remaining: number;
}

export interface TOTPSetupResponse {
  secret: string;
  qr_code_b64: string;
  issuer: string;
}

export interface TOTPEnableResponse {
  message: string;
  backup_codes: string[];
}

export interface BackupCodesResponse {
  backup_codes: string[];
  message: string;
}

export interface TwoFAVerifyRequest {
  pre_auth_token: string;
  code: string;
  method: 'totp' | 'email' | 'backup';
}

/**
 * A URL that is known to be same-origin (a relative path starting with ``/``).
 *
 * Branded so that producers of same-origin URLs (e.g. ``api.oidcProviderIconUrl``)
 * can be distinguished from arbitrary strings at the type level.  The brand
 * is compile-time only; at runtime these are plain strings.
 *
 * Purpose: CSP-safe image sources for ``<img src=...>``. The strict
 * ``img-src 'self' data: blob:`` CSP rejects anything that isn't same-origin,
 * so callers that demand a ``SameOriginUrl`` get a compile-time guarantee
 * that no external URL slips through.
 */
export type SameOriginUrl = string & { readonly __brand: 'SameOriginUrl' };

// OIDC interfaces
export interface OIDCProvider {
  id: number;
  name: string;
  issuer_url: string;
  client_id: string;
  scopes: string;
  is_enabled: boolean;
  allow_private_network: boolean;
  auto_create_users: boolean;
  auto_link_existing_accounts: boolean;
  email_claim: string;
  require_email_verified: boolean;
  icon_url?: string | null;
  default_group_id?: number | null;
  // True when the backend has cached icon bytes for this provider.
  // Login page / admin preview consume this via the proxy URL
  // /api/v1/auth/oidc/providers/{id}/icon (#1333) so the SPA never
  // hotlinks the external icon URL — that would require loosening
  // the strict img-src CSP.  Required, not optional: the backend always
  // includes this field in the response (Pydantic default-False is
  // populated unconditionally in the route handler).
  has_icon: boolean;
  // #1589: when true, the LoginPage redirects unauthenticated visitors
  // straight to this provider on mount. At most one provider may carry this.
  is_autologin: boolean;
  is_env_managed?: boolean;
}

export interface OIDCProviderCreate {
  name: string;
  issuer_url: string;
  client_id: string;
  client_secret: string;
  scopes?: string;
  is_enabled?: boolean;
  allow_private_network?: boolean;
  auto_create_users?: boolean;
  auto_link_existing_accounts?: boolean;
  email_claim?: string;
  require_email_verified?: boolean;
  icon_url?: string | null;
  default_group_id?: number | null;
  is_autologin?: boolean;  // #1589
}

export interface OIDCLink {
  id: number;
  provider_id: number;
  provider_name: string;
  provider_email?: string | null;
  created_at: string;
}

export interface TestSMTPRequest {
  test_recipient: string;
}

export interface TestSMTPResponse {
  success: boolean;
  message: string;
}

export interface AdvancedAuthStatus {
  advanced_auth_enabled: boolean;
  smtp_configured: boolean;
  // #1589: false hides the username/password form on the LoginPage; the env
  // var PRINTOPS_LOCAL_LOGIN=true on the server flips this back to true so
  // the recovery path remains visible.
  local_login_enabled: boolean;
  // #1589: when set, LoginPage redirects to this provider's authorize URL
  // on mount unless ?fallback=local is in the URL or the redirect times out.
  autologin_provider_id: number | null;
}

export interface LDAPStatus {
  ldap_enabled: boolean;
  ldap_configured: boolean;
}

export interface EncryptionRowCounts {
  oidc_providers: number;
  user_totp: number;
}

export interface EncryptionStatus {
  key_configured: boolean;
  key_source: 'env' | 'file' | 'generated' | 'none';
  legacy_plaintext_rows: EncryptionRowCounts;
  encrypted_rows: EncryptionRowCounts;
  decryption_broken: boolean;
  // B2: count of rows skipped during the last legacy re-encryption migration.
  // Surfaced via a yellow secondary banner in SecurityStatusCard.
  migration_error_count: number;
}

export interface LDAPTestResponse {
  success: boolean;
  message: string;
}

export interface LDAPSearchResult {
  username: string;
  email: string | null;
  display_name: string | null;
  dn: string;
  already_provisioned: boolean;
}

export interface SetupResponse {
  auth_enabled: boolean;
  admin_created?: boolean;
}

export interface AuthStatus {
  auth_enabled: boolean;
  requires_setup: boolean;
}
