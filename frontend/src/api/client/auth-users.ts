import type {
  AdvancedAuthStatus,
  AuthStatus,
  BackupCodesResponse,
  EncryptionStatus,
  ForgotPasswordRequest,
  ForgotPasswordResponse,
  Group,
  GroupCreate,
  GroupDetail,
  GroupUpdate,
  LDAPSearchResult,
  LDAPStatus,
  LDAPTestResponse,
  LoginRequest,
  LoginResponse,
  OIDCLink,
  OIDCProvider,
  OIDCProviderCreate,
  PermissionsListResponse,
  ResetPasswordRequest,
  ResetPasswordResponse,
  SMTPSettings,
  SameOriginUrl,
  SetupRequest,
  SetupResponse,
  TOTPEnableResponse,
  TOTPSetupResponse,
  TestSMTPRequest,
  TestSMTPResponse,
  TwoFAStatus,
  TwoFAVerifyRequest,
  UserCreate,
  UserEmailPreferences,
  UserResponse,
  UserUpdate,
} from './types';
import { request } from './core';

export const authUsersMethods = {
  // Authentication
  getAuthStatus: () => request<AuthStatus>('/auth/status'),

  setupAuth: (data: SetupRequest) =>
    request<SetupResponse>('/auth/setup', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  login: (data: LoginRequest) =>
    request<LoginResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  logout: () =>
    request<{ message: string }>('/auth/logout', {
      method: 'POST',
    }),

  refreshToken: () =>
    request<LoginResponse>('/auth/refresh', {
      method: 'POST',
    }),

  getCurrentUser: () => request<UserResponse>('/auth/me'),

  disableAuth: () =>
    request<{ message: string; auth_enabled: boolean }>('/auth/disable', {
      method: 'POST',
    }),

  // Advanced Authentication
  testSMTP: (data: TestSMTPRequest) =>
    request<TestSMTPResponse>('/auth/smtp/test', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getSMTPSettings: () => request<SMTPSettings | null>('/auth/smtp'),

  saveSMTPSettings: (data: SMTPSettings) =>
    request<{ message: string }>('/auth/smtp', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  enableAdvancedAuth: () =>
    request<{ message: string; advanced_auth_enabled: boolean }>('/auth/advanced-auth/enable', {
      method: 'POST',
    }),

  disableAdvancedAuth: () =>
    request<{ message: string; advanced_auth_enabled: boolean }>('/auth/advanced-auth/disable', {
      method: 'POST',
    }),

  getAdvancedAuthStatus: () => request<AdvancedAuthStatus>('/auth/advanced-auth/status'),

  // LDAP Authentication
  getLDAPStatus: () => request<LDAPStatus>('/auth/ldap/status'),

  getEncryptionStatus: () => request<EncryptionStatus>('/auth/encryption-status'),

  testLDAP: () =>
    request<LDAPTestResponse>('/auth/ldap/test', {
      method: 'POST',
    }),

  searchLDAPDirectory: (q: string) =>
    request<LDAPSearchResult[]>(`/auth/ldap/search?q=${encodeURIComponent(q)}`),

  provisionLDAPUser: (username: string) =>
    request<UserResponse>('/auth/ldap/provision', {
      method: 'POST',
      body: JSON.stringify({ username }),
    }),

  forgotPassword: (data: ForgotPasswordRequest) =>
    request<ForgotPasswordResponse>('/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // H-6: Confirm password reset using the token from the emailed link
  forgotPasswordConfirm: (token: string, newPassword: string) =>
    request<ForgotPasswordResponse>('/auth/forgot-password/confirm', {
      method: 'POST',
      body: JSON.stringify({ token, new_password: newPassword }),
    }),

  resetUserPassword: (data: ResetPasswordRequest) =>
    request<ResetPasswordResponse>('/auth/reset-password', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // 2FA - status
  get2FAStatus: () => request<TwoFAStatus>('/auth/2fa/status'),

  // 2FA - TOTP
  setupTOTP: () => request<TOTPSetupResponse>('/auth/2fa/totp/setup', { method: 'POST' }),

  enableTOTP: (code: string) =>
    request<TOTPEnableResponse>('/auth/2fa/totp/enable', {
      method: 'POST',
      body: JSON.stringify({ code }),
    }),

  disableTOTP: (code: string) =>
    request<{ message: string }>('/auth/2fa/totp/disable', {
      method: 'POST',
      body: JSON.stringify({ code }),
    }),

  regenerateBackupCodes: (code: string) =>
    request<BackupCodesResponse>('/auth/2fa/totp/regenerate-backup-codes', {
      method: 'POST',
      body: JSON.stringify({ code }),
    }),

  // 2FA - Email OTP
  // Step 1: send a verification code to the user's email (proof of possession)
  enableEmailOTP: () =>
    request<{ message: string; setup_token: string }>('/auth/2fa/email/enable', { method: 'POST' }),

  // Step 2: confirm with the code received by email
  confirmEnableEmailOTP: (setup_token: string, code: string) =>
    request<{ message: string }>('/auth/2fa/email/enable/confirm', {
      method: 'POST',
      body: JSON.stringify({ setup_token, code }),
    }),

  // Disable requires account password for re-auth
  disableEmailOTP: (password: string) =>
    request<{ message: string }>('/auth/2fa/email/disable', {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),

  sendEmailOTP: (preAuthToken: string) =>
    request<{ message: string; pre_auth_token?: string }>('/auth/2fa/email/send', {
      method: 'POST',
      body: JSON.stringify({ pre_auth_token: preAuthToken }),
    }),

  // 2FA - verify (completes login)
  verify2FA: (data: TwoFAVerifyRequest) =>
    request<LoginResponse>('/auth/2fa/verify', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // 2FA - admin
  admin2FADisable: (userId: number) =>
    request<{ message: string }>(`/auth/2fa/admin/${userId}`, { method: 'DELETE' }),

  // OIDC providers (public list)
  getOIDCProviders: () => request<OIDCProvider[]>('/auth/oidc/providers'),

  // OIDC providers (admin)
  getOIDCProvidersAll: () => request<OIDCProvider[]>('/auth/oidc/providers/all'),

  createOIDCProvider: (data: OIDCProviderCreate) =>
    request<OIDCProvider>('/auth/oidc/providers', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateOIDCProvider: (id: number, data: Partial<OIDCProviderCreate>) =>
    request<OIDCProvider>(`/auth/oidc/providers/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteOIDCProvider: (id: number) =>
    request<{ message: string }>(`/auth/oidc/providers/${id}`, { method: 'DELETE' }),

  // OIDC provider icon proxy (#1333) — same-origin path so the strict
  // img-src CSP stays in force. Returns a SameOriginUrl-branded string
  // so a future caller can't accidentally substitute an attacker-
  // controlled URL where this is consumed.
  oidcProviderIconUrl: (id: number): SameOriginUrl =>
    `/api/v1/auth/oidc/providers/${id}/icon` as SameOriginUrl,

  deleteOIDCProviderIcon: (id: number) =>
    request<void>(`/auth/oidc/providers/${id}/icon`, { method: 'DELETE' }),

  refreshOIDCProviderIcon: (id: number) =>
    request<OIDCProvider>(`/auth/oidc/providers/${id}/icon/refresh`, { method: 'POST' }),

  // OIDC authorize URL
  getOIDCAuthorizeUrl: (providerId: number) =>
    request<{ auth_url: string }>(`/auth/oidc/authorize/${providerId}`),

  // OIDC exchange token for JWT
  exchangeOIDCToken: (oidcToken: string) =>
    request<LoginResponse>('/auth/oidc/exchange', {
      method: 'POST',
      body: JSON.stringify({ oidc_token: oidcToken }),
    }),

  // OIDC links for current user
  getOIDCLinks: () => request<OIDCLink[]>('/auth/oidc/links'),

  deleteOIDCLink: (providerId: number) =>
    request<{ message: string }>(`/auth/oidc/links/${providerId}`, { method: 'DELETE' }),

  // Users
  getUsers: () => request<UserResponse[]>('/users/'),

  getUser: (id: number) => request<UserResponse>(`/users/${id}`),

  createUser: (data: UserCreate) =>
    request<UserResponse>('/users/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateUser: (id: number, data: UserUpdate) =>
    request<UserResponse>(`/users/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteUser: (id: number, deleteItems: boolean = false) =>
    request<void>(`/users/${id}?delete_items=${deleteItems}`, {
      method: 'DELETE',
    }),

  getUserItemsCount: (id: number) =>
    request<{ archives: number; queue_items: number; library_files: number }>(`/users/${id}/items-count`),

  changePassword: (currentPassword: string, newPassword: string) =>
    request<{ message: string }>('/users/me/change-password', {
      method: 'POST',
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    }),

  // User Email Notifications
  getUserEmailPreferences: () =>
    request<UserEmailPreferences>('/user-notifications/preferences'),

  updateUserEmailPreferences: (data: UserEmailPreferences) =>
    request<UserEmailPreferences>('/user-notifications/preferences', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  // Groups
  getPermissions: () => request<PermissionsListResponse>('/groups/permissions'),

  getGroups: () => request<Group[]>('/groups/'),

  getGroup: (id: number) => request<GroupDetail>(`/groups/${id}`),

  createGroup: (data: GroupCreate) =>
    request<Group>('/groups/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateGroup: (id: number, data: GroupUpdate) =>
    request<Group>(`/groups/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteGroup: (id: number) =>
    request<void>(`/groups/${id}`, {
      method: 'DELETE',
    }),

  addUserToGroup: (groupId: number, userId: number) =>
    request<void>(`/groups/${groupId}/users/${userId}`, {
      method: 'POST',
    }),

  removeUserFromGroup: (groupId: number, userId: number) =>
    request<void>(`/groups/${groupId}/users/${userId}`, {
      method: 'DELETE',
    })
};
