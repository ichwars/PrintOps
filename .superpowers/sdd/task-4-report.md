Status: DONE

Files changed
- frontend/src/pages/SettingsPage.tsx
- frontend/src/__tests__/pages/SettingsPage.test.tsx
- .superpowers/sdd/task-4-report.md

Summary of behavior changes
- Kept General focused on language, default view, date/time, appearance, sidebar links, and a dedicated UI preferences reset card.
- Moved the default printer setting into a dedicated `card-default-printer` under Printers & Production.
- Kept notification log clearing, storage usage, and backup/restore controls in Operations data management.
- Updated settings search anchors so Default Printer resolves to Printers & Production and Reset UI Preferences resolves to General.
- Fixed the storage usage query guard so it only loads on the Operations tab.

Tests run and results
- `npm.cmd run test -- SettingsPage.test.tsx --run` — PASS (95 tests)

Commit hash
- 82999368c9b507a997ac6a256331865cafad6005
