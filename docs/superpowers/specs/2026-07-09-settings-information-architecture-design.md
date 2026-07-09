# PrintOps Settings Information Architecture

Date: 2026-07-09
Status: Draft for review

## Purpose

The Settings area should support how PrintOps users think about their work:
production, projects/files, material stock, orders/calculation, integrations,
security, and operations. The current implementation works, but it exposes too
many technical buckets directly in the left rail. As the product moved from
Bambuddy to PrintOps and gained a richer main navigation, Settings should be
grouped by user intent instead of implementation origin.

This design defines the target Settings structure and maps every current
Settings card or section to its future location. It is intentionally a design
spec, not an implementation patch.

## Goals

- Make `Allgemein` small and predictable.
- Put every setting in exactly one primary location.
- Align Settings with the PrintOps domains without duplicating the main app menu.
- Preserve old deep links such as `?tab=queue`, `?tab=users`, and `?tab=backup`.
- Keep cross-tab Settings search working for every moved card.
- Keep admin/security concerns visibly separate from production and operations.

## Non-Goals

- No backend settings schema changes.
- No permissions model changes.
- No redesign of individual card internals unless a move requires a heading or label update.
- No change to the main application navigation.
- No online deployment as part of this step.

## Target Top-Level Settings Navigation

| Target ID | Label | Purpose |
| --- | --- | --- |
| `general` | Allgemein | Basic instance preferences, language, date/time, appearance, start page, sidebar layout. |
| `users-security` | Benutzer & Sicherheit | Users, groups, sessions, authentication, MFA, SSO, LDAP, API keys, security status. |
| `printers-production` | Drucker & Produktion | Printer defaults, archive behaviour, cameras, queue dispatch, slicer pipeline, virtual printer, maintenance-related production automation, failure detection. |
| `projects-files` | Projekte & Dateien | File manager behaviour, library/archive file handling, storage rules for project data. |
| `warehouse-material` | Lager & Material | Filament checks, AMS thresholds, Spoolman, SpoolBuddy, spool catalog, color catalog, material mapping. |
| `orders-calculation` | Auftraege & Kalkulation | Currency, filament cost, electricity cost, cost display defaults, later invoice/order calculation settings. |
| `integrations` | Integrationen | Smart Plugs, notifications, Home Assistant, MQTT, webhooks, external URL, developer/API browser, external camera tokens. |
| `operations` | Betrieb | Updates, backups, restore/export, data management, storage usage, logs, Prometheus/monitoring, operational cleanup. |

The target structure should render as a Settings-specific rail. These are not
main navigation pages; they are configuration domains.

## URL and Alias Rules

New URLs should use canonical target IDs:

- `/settings`
- `/settings?tab=users-security`
- `/settings?tab=printers-production`
- `/settings?tab=projects-files`
- `/settings?tab=warehouse-material`
- `/settings?tab=orders-calculation`
- `/settings?tab=integrations`
- `/settings?tab=operations`

Existing URLs must keep working through aliases:

| Existing tab | Canonical destination | Default landing area |
| --- | --- | --- |
| `general` or no tab | `general` | Basic preferences |
| `users` | `users-security` | Users and groups |
| `email` | `users-security` | Email authentication |
| `apikeys` | `users-security` | API keys |
| `queue` | `printers-production` | Queue and dispatch |
| `virtual-printer` | `printers-production` | Virtual printer |
| `failure-detection` | `printers-production` | Failure detection |
| `filament` | `warehouse-material` | Filament checks |
| `spoolbuddy` | `warehouse-material` | SpoolBuddy |
| `plugs` | `integrations` | Smart Plugs |
| `notifications` | `integrations` | Notifications |
| `network` | `integrations` | External URL and network integrations |
| `backup` | `operations` | Backup |

If a moved search result points to a specific card, search should open the
canonical tab and then scroll to the existing card anchor.

## Mapping Matrix

| Current tab / card | Current content | Target group | Target sub-area | Notes |
| --- | --- | --- | --- | --- |
| `general` / `card-general` | Language, default view, date format, time format, default printer | Split between `general` and `printers-production` | Basic preferences / printer defaults | Language, date/time and default view stay in `general`. Default printer moves to printer defaults. |
| `general` / `card-appearance` | Theme mode, dark/light background, accent, style | `general` | Appearance | Keep near language and start page. |
| `general` / `card-sidebar-links` | Sidebar layout, hidden pages, external links | `general` | Navigation | This is the right home for sidebar configuration. Keep Settings itself required. |
| `general` / `card-archive` | Auto archive prints, thumbnails, finish photo | `printers-production` | Archive behaviour | This changes production output and archive capture, not general app preference. |
| `general` / `card-camera` | Per-printer camera source, snapshot URL, rotation | `printers-production` | Cameras | Printer-specific operational setup. |
| `general` / `card-cost` | Currency, default filament cost, electricity price, energy display mode | `orders-calculation` | Cost defaults | Better matches future offers, calculations, invoices, and order costing. |
| `general` / `card-filemanager` | File manager archive mode, disk warning, auto purge | `projects-files` | File manager | Project/library file behaviour belongs with projects and files. |
| `general` / `card-data` | Clear notification logs, reset UI prefs, storage usage, backup/restore shortcut | Split between `operations` and `general` | Data management / UI preferences | Storage and logs move to `operations`. UI preference reset stays in `general`. Backup shortcut becomes a link to `operations`. |
| `general` / `card-updates` | App update checks, firmware update checks, release notes | `operations` | Updates | Operational lifecycle management. |
| `network` / `card-externalurl` | Public/external base URL | `integrations` | External access | Used by notifications and external integrations. |
| `network` / `card-ftpretry` | FTP retry count/backoff | `printers-production` | Upload reliability | It affects print file delivery to printers. |
| `network` / `card-ha` | Home Assistant connection | `integrations` | Home Assistant | External system integration. |
| `network` / `card-mqtt` | MQTT publishing | `integrations` | MQTT | External system integration. |
| `network` / `card-prometheus` | Metrics endpoint and token | `operations` | Monitoring | Operational observability, even though implemented as network config. |
| `plugs` / `card-plugs` | Smart Plug list, power controls, energy summary | `integrations` | Smart Plugs | External device integration. Energy cost display can reuse order cost settings. |
| `notifications` / `card-providers` | Notification providers, notification language, user notifications toggle | `integrations` | Notifications | Keep provider management and delivery settings together. |
| `notifications` / bed cooled threshold | Temperature threshold for cooled-bed notification | `printers-production` | Completion rules | The event source is production state; notifications consume it. |
| `notifications` / `card-templates` | Notification message templates | `integrations` | Notifications | Delivery content belongs next to providers. |
| `apikeys` / `card-createapi` | API key creation and key list | `users-security` | API keys | Credentials are security-sensitive. |
| `apikeys` / `card-webhooks` | Webhook endpoints | `integrations` | Webhooks | External integration endpoints. |
| `apikeys` / `card-camera-tokens` | Long-lived camera stream tokens | `users-security` | Tokens | Security-sensitive external access. |
| `apikeys` / `card-apibrowser` | API browser/tester | `integrations` | Developer API | Developer-facing integration helper. |
| `queue` / `card-print-options` | Default print options | `printers-production` | Queue and dispatch | Defaults for production runs. |
| `queue` / `card-plate` | Plate-clear confirmation | `printers-production` | Queue safety | Production safety/dispatch gate. |
| `queue` / `card-temp-fan-presets` | Temperature and fan quick presets | `printers-production` | Printer controls | Used by printer/queue controls. |
| `queue` / `card-staggered` | Staggered batch start defaults | `printers-production` | Queue and dispatch | Production scheduling. |
| `queue` / `card-preheat` | Preheat and heat soak defaults | `printers-production` | Start conditions | Material-related, but operationally part of dispatch. |
| `queue` / `card-gcode` | G-code injection snippets | `printers-production` | Automation | Production automation per printer model. |
| `queue` / `card-pipelines` | Slicer pipeline management | `printers-production` | Slicer and pipelines | Supports print preparation/dispatch. |
| `queue` / `card-slicer` | Preferred slicer and sidecar/API settings | `printers-production` | Slicer and pipelines | Print production tooling. |
| `queue` / `card-drying` | Queue drying settings | `warehouse-material` | Material conditioning | Material stock condition. Provide a cross-link from production if needed. |
| `filament` / `card-filamentchecks` | Filament checks and warnings | `warehouse-material` | Filament checks | Directly tied to material stock. |
| `filament` / `card-printmodal` | Print modal custom material mapping | `warehouse-material` | Material mapping | Material selection behaviour. |
| `filament` / `card-amsthresholds` | AMS humidity/temp thresholds and retention | `warehouse-material` | AMS thresholds | Material/storage monitoring. |
| `filament` / `card-spoolman` | Spoolman sync/inventory integration | `warehouse-material` | Filament integrations | Primary purpose is material inventory. |
| `filament` / `card-spool-catalog` | Spool catalog | `warehouse-material` | Catalogs | Material master data. |
| `filament` / `card-color-catalog` | Color catalog | `warehouse-material` | Catalogs | Material/color master data. |
| `spoolbuddy` / `card-spoolbuddy` | SpoolBuddy devices, scale/NFC support | `warehouse-material` | SpoolBuddy | Hardware for material inventory. |
| `virtual-printer` / `card-vp` | Virtual printer and proxy/archive modes | `printers-production` | Virtual printer | Behaves like printer production infrastructure. |
| `failure-detection` / `card-fd-ml` | ML/failure detection setup | `printers-production` | Failure detection | Production monitoring. |
| `failure-detection` / `card-fd-perprinter` | Per-printer detection settings | `printers-production` | Failure detection | Production monitoring. |
| `failure-detection` / `card-fd-status` | Detection service status | `printers-production` | Failure detection | Production monitoring, with operational status display. |
| `failure-detection` / `card-fd-history` | Detection history | `printers-production` | Failure detection | Production monitoring history. |
| `users` / auth toggle card | Enable/disable local authentication | `users-security` | Authentication | Keep at top of security group. |
| `users` / `card-session-policy` | Session maximum lifetime | `users-security` | Sessions | Security control. |
| `users` / `card-currentuser` | Current user profile/password | `users-security` | Account | Security/account control. |
| `users` / `card-users` | User list and user creation | `users-security` | Users | Security/account control. |
| `users` / `card-groups` | Groups, roles, permissions | `users-security` | Groups and permissions | Security/account control. |
| `users` / `card-smtp`, `card-smtp-config` | SMTP configuration | `users-security` | Email authentication | Required for advanced auth and reset flows. |
| `users` / `card-email-advanced-auth` | Password reset and advanced email auth | `users-security` | Email authentication | Security/authentication. |
| `users` / `card-email-test` | SMTP test | `users-security` | Email authentication | Stays with SMTP. |
| `users` / `card-ldap`, `card-ldap-server` | LDAP auth and server configuration | `users-security` | LDAP | Security/authentication. |
| `users` / `card-2fa-totp` | TOTP 2FA | `users-security` | MFA | Security/authentication. |
| `users` / `card-2fa-emailotp` | Email one-time codes | `users-security` | MFA | Security/authentication. |
| `users` / `card-2fa-linked` | Linked SSO accounts | `users-security` | MFA and SSO | Security/authentication. |
| `users` / `card-oidc` | OIDC/SSO providers | `users-security` | SSO | Security/authentication. |
| `users` / `card-mfa-encryption` | Security/encryption status | `users-security` | Security status | Security status card. |
| `backup` / `card-backup` | Backup tab wrapper | `operations` | Backup | Wrapper only. |
| `backup` / `card-backup-github` | GitHub backup | `operations` | Backup | Operational data safety. |
| `backup` / `card-backup-history` | Backup history | `operations` | Backup history | Operational data safety. |
| `backup` / `card-backup-local` | Manual local backup/export | `operations` | Backup | Operational data safety. |
| `backup` / `card-backup-scheduled` | Scheduled backups | `operations` | Backup scheduling | Operational data safety. |

## Navigation Behaviour

- The Settings rail should default to `Allgemein`.
- Canonical tabs should appear in the order listed in this document.
- Legacy tab IDs should not appear visually, but should resolve silently.
- A moved search result should show the canonical group name and optional sub-area.
- Existing user sub-tabs can remain visually inside `Benutzer & Sicherheit`.
- Existing queue sub-tabs can remain visually inside `Drucker & Produktion`.
- If a canonical group contains many sections, use compact local sub-tabs or section chips inside the group, not additional top-level Settings rail entries.

## Implementation Shape

The safest implementation is a small information-architecture layer before any
large component extraction:

1. Add a central Settings navigation config with canonical group IDs, labels,
   icons, legacy aliases, and optional sub-areas.
2. Extend `SettingsSearchTab` to support canonical IDs while keeping legacy IDs
   accepted through an alias resolver.
3. Replace the hardcoded Settings rail buttons in `SettingsPage.tsx` with config
   rendering.
4. Move card render blocks into the target canonical groups. Split only cards
   that truly mix two target domains, such as `card-general` and `card-data`.
5. Update i18n labels for all locale files or provide stable fallbacks where
   parity checks require them.
6. Update tests for canonical tabs, legacy aliases, search jumps, and sidebar
   behaviour.

This avoids a broad component refactor while still fixing the user-facing IA.

## Files Expected To Change During Implementation

- `frontend/src/pages/SettingsPage.tsx`
- `frontend/src/lib/settingsSearch.ts`
- `frontend/src/i18n/locales/de.ts`
- `frontend/src/i18n/locales/en.ts`
- Other locale files if the parity check requires explicit keys.
- `frontend/src/__tests__/pages/SettingsPage.test.tsx`
- Potentially docs screenshots after the UI is accepted locally.

## Test Plan

- Run the existing Settings page tests.
- Add/adjust tests that verify the new canonical Settings tabs render.
- Add alias tests:
  - `?tab=queue` opens `Drucker & Produktion`.
  - `?tab=filament` opens `Lager & Material`.
  - `?tab=backup` opens `Betrieb`.
  - `?tab=email` opens `Benutzer & Sicherheit` with email auth selected.
- Add search tests:
  - Searching "Sidebar" lands in `Allgemein`.
  - Searching "SpoolBuddy" lands in `Lager & Material`.
  - Searching "Backup" lands in `Betrieb`.
  - Searching "Virtual Printer" lands in `Drucker & Produktion`.
- Keep the existing Sidebar tests, especially that Settings cannot be hidden.
- Run the i18n parity check if available.
- Verify locally in the browser at `http://127.0.0.1:8000/settings`.

## Self-Review

- Placeholder scan: no placeholders or undecided target groups remain.
- Consistency check: every current registered Settings card has a primary target group.
- Scope check: this is one implementation unit because it changes one Settings page,
  one search registry, labels, and the related tests.
- Ambiguity check: cross-domain items have explicit primary homes. Smart Plugs are
  treated as integrations. Cost settings are treated as order/calculation defaults.
  Queue drying is treated as material conditioning with a possible production
  cross-link.
