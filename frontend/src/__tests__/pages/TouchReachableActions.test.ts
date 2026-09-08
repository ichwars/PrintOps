import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const source = (path: string) => readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../..', path), 'utf8');

// jsdom cannot evaluate media-query opacity. These source contracts cover every
// affected owner; production browser tests verify the generated CSS and menus.
describe('touch/focus visibility contracts', () => {
  for (const [path, reveal] of [
    ['pages/ArchivesPage.tsx', 'focus-visible:opacity-100'],
    ['pages/FileManagerPage.tsx', 'group-focus-within:opacity-100'],
    ['pages/ProjectsPage.tsx', 'focus-visible:opacity-100'],
    ['pages/ProfilesPage.tsx', 'focus-visible:opacity-100'],
    ['components/TagManagementModal.tsx', 'group-focus-within:opacity-100'],
    ['components/EditArchiveModal.tsx', 'focus-visible:opacity-100'],
    ['pages/printers/PrinterCardOverlays.tsx', 'focus-visible:opacity-100'],
  ]) {
    it(`${path} hides actions only for a hover-capable pointer and reveals keyboard focus`, () => {
      const text = source(path);
      expect(text).toContain('can-hover:opacity-0 group-hover:opacity-100');
      expect(text).toContain(reveal);
      expect(text).not.toMatch(/(?<!can-hover:)opacity-0 group-hover:opacity-100/);
    });
  }

  it('does not substitute screen width for pointer capability', () => {
    expect(source('index.css')).toContain('@custom-variant can-hover (@media (hover: hover) and (pointer: fine));');
    for (const path of ['pages/FileManagerPage.tsx', 'pages/ArchivesPage.tsx']) {
      expect(source(path)).not.toContain('useIsMobile');
    }
  });
});
