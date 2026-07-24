# PrintOps Brand Asset Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace legacy Bambuddy branding with the approved PrintOps main logo, compact icon, browser favicons, PWA icons, and GitHub README artwork.

**Architecture:** Keep one optimized SVG for full-wordmark contexts and deterministic transparent PNGs for compact/icon metadata contexts. Maintain identical public assets in `frontend/public/img` and checked-in production assets in `static/img`, while updating application, HTML, manifest, and service-worker references explicitly so the dirty production bundle is not rebuilt in place.

**Tech Stack:** React, TypeScript, Vite, Vitest, SVG, PNG, Web App Manifest, service worker

## Global Constraints

- Preserve all unrelated working-tree changes.
- Do not modify `C:\Users\droth\Pictures\Logos\printops_logo.svg` or `E:\IconOnly_Transparent_NoBuffer.png`.
- Main SVG content remains unchanged except root dimensions and `viewBox="90 305 1060 413"`.
- Collapsed desktop sidebar uses the icon only at 40×40 CSS pixels.
- Do not declare the transparent no-buffer icon as `maskable`.
- GitHub scope is limited to the README image already referencing `static/img/printops_logo.svg`.
- Do not rebrand SpoolBuddy assets or update application screenshots.
- Verification builds must not write into the dirty `static` directory.

---

### Task 1: Install and Contract-Test the Approved Assets

**Files:**
- Create: `frontend/src/__tests__/assets/BrandAssets.test.ts`
- Replace: `frontend/public/img/printops_logo.svg`
- Create: `frontend/public/img/printops_icon.png`
- Replace: `frontend/public/img/android-chrome-192x192.png`
- Replace: `frontend/public/img/android-chrome-512x512.png`
- Replace: `frontend/public/img/favicon-16x16.png`
- Replace: `frontend/public/img/favicon-32x32.png`
- Replace: `frontend/public/img/favicon.png`
- Replace: `frontend/public/img/apple-touch-icon.png`
- Delete: `frontend/public/img/printops_icon.svg`
- Mirror the same asset changes under: `static/img/`

**Interfaces:**
- Consumes: approved source logo and prepared `outputs/icon-set/*.png` exports.
- Produces: `/img/printops_logo.svg`, `/img/printops_icon.png`, standard favicon files, and 192/512 PWA files.

- [ ] **Step 1: Write the failing asset contract test**

```ts
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(process.cwd(), '..');
const publicImg = path.join(process.cwd(), 'public', 'img');
const staticImg = path.join(root, 'static', 'img');

const pngs: Record<string, [number, number]> = {
  'printops_icon.png': [192, 192],
  'android-chrome-192x192.png': [192, 192],
  'android-chrome-512x512.png': [512, 512],
  'favicon-16x16.png': [16, 16],
  'favicon-32x32.png': [32, 32],
  'favicon.png': [512, 512],
  'apple-touch-icon.png': [180, 180],
};

function pngMetadata(file: string) {
  const data = fs.readFileSync(file);
  expect(data.subarray(1, 4).toString('ascii')).toBe('PNG');
  return {
    width: data.readUInt32BE(16),
    height: data.readUInt32BE(20),
    colorType: data[25],
  };
}

function sha256(file: string) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

describe('PrintOps brand assets', () => {
  it('uses the tight responsive main-logo canvas in both asset trees', () => {
    for (const directory of [publicImg, staticImg]) {
      const source = fs.readFileSync(path.join(directory, 'printops_logo.svg'), 'utf8');
      expect(source).toContain('viewBox="90 305 1060 413"');
      expect(source).not.toMatch(/<svg[^>]+\s(?:width|height)=/i);
    }
  });

  it.each(Object.entries(pngs))('%s has the required dimensions and alpha', (name, [width, height]) => {
    for (const directory of [publicImg, staticImg]) {
      const metadata = pngMetadata(path.join(directory, name));
      expect(metadata).toMatchObject({ width, height });
      expect([4, 6]).toContain(metadata.colorType);
    }
  });

  it('keeps frontend and static assets byte-identical', () => {
    for (const name of ['printops_logo.svg', ...Object.keys(pngs)]) {
      expect(sha256(path.join(publicImg, name))).toBe(sha256(path.join(staticImg, name)));
    }
  });

  it('removes the legacy SVG icon', () => {
    expect(fs.existsSync(path.join(publicImg, 'printops_icon.svg'))).toBe(false);
    expect(fs.existsSync(path.join(staticImg, 'printops_icon.svg'))).toBe(false);
  });
});
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run: `npx.cmd vitest run src/__tests__/assets/BrandAssets.test.ts`

Expected: FAIL because the approved files, dimensions, tight SVG canvas, and PNG icon are not installed yet.

- [ ] **Step 3: Install the exact approved assets**

Copy `C:\Users\droth\Pictures\Logos\printops_logo.svg` to `frontend/public/img/printops_logo.svg`, remove its fixed `width="1280" height="1024"`, and replace `viewBox="0 0 1280 1024"` with `viewBox="90 305 1060 413" preserveAspectRatio="xMidYMid meet"`. Copy the normalized result byte-for-byte to `static/img/printops_logo.svg`.

Copy these deterministic PNGs to both asset trees:

```text
outputs/icon-set/icon-192x192.png       -> printops_icon.png
outputs/icon-set/icon-192x192.png       -> android-chrome-192x192.png
outputs/icon-set/icon-512x512.png       -> android-chrome-512x512.png
outputs/icon-set/favicon-16x16.png      -> favicon-16x16.png
outputs/icon-set/favicon-32x32.png      -> favicon-32x32.png
outputs/icon-set/favicon-512x512.png    -> favicon.png
outputs/icon-set/apple-touch-icon-180x180.png -> apple-touch-icon.png
```

Delete only `frontend/public/img/printops_icon.svg` and `static/img/printops_icon.svg` after confirming the exact resolved paths are under the repository.

- [ ] **Step 4: Run the focused test and confirm GREEN**

Run: `npx.cmd vitest run src/__tests__/assets/BrandAssets.test.ts`

Expected: 1 file passed; all asset-contract tests passed.

- [ ] **Step 5: Commit only Task 1 files**

```powershell
git add -- frontend/src/__tests__/assets/BrandAssets.test.ts frontend/public/img static/img
git commit -m "feat: install PrintOps brand assets"
```

### Task 2: Wire Application, Favicons, Manifest, and Service Worker

**Files:**
- Create: `frontend/src/__tests__/assets/BrandReferences.test.ts`
- Modify: `frontend/src/components/Layout.tsx:671-678`
- Modify: `frontend/index.html:22-27`
- Modify: `frontend/public/manifest.json:11-44,68-94`
- Modify: `frontend/public/sw.js:8-10,203-204`
- Modify: `static/index.html:22-27`
- Modify: `static/manifest.json:11-44,68-94`
- Modify: `static/sw.js:8-10,203-204`

**Interfaces:**
- Consumes: Task 1 public asset names.
- Produces: correct full-logo/icon switching, favicon metadata, PWA installation metadata, and notification assets.

- [ ] **Step 1: Write the failing reference contract test**

```ts
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(process.cwd(), '..');
const read = (file: string) => fs.readFileSync(file, 'utf8');

describe('PrintOps brand references', () => {
  it.each(['frontend/index.html', 'static/index.html'])('%s declares explicit favicon sizes', (file) => {
    const html = read(path.join(root, file));
    expect(html).toContain('sizes="16x16" href="/img/favicon-16x16.png"');
    expect(html).toContain('sizes="32x32" href="/img/favicon-32x32.png"');
    expect(html).toContain('sizes="512x512" href="/img/favicon.png"');
    expect(html).toContain('sizes="180x180" href="/img/apple-touch-icon.png"');
    expect(html).not.toContain('printops_icon.svg');
  });

  it.each(['frontend/public/manifest.json', 'static/manifest.json'])('%s uses exact PWA icons', (file) => {
    const manifest = JSON.parse(read(path.join(root, file)));
    expect(manifest.icons).toEqual([
      { src: '/img/android-chrome-192x192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
      { src: '/img/android-chrome-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
    ]);
    expect(manifest.shortcuts.every((shortcut: { icons: Array<{ src: string }> }) =>
      shortcut.icons[0].src === '/img/android-chrome-192x192.png')).toBe(true);
  });

  it.each(['frontend/public/sw.js', 'static/sw.js'])('%s contains no legacy icon reference', (file) => {
    const source = read(path.join(root, file));
    expect(source).toContain('/img/android-chrome-192x192.png');
    expect(source).toContain('/img/favicon-32x32.png');
    expect(source).not.toContain('printops_icon.svg');
  });

  it('uses the PNG icon only for the collapsed desktop sidebar', () => {
    const layout = read(path.join(root, 'frontend/src/components/Layout.tsx'));
    expect(layout).toContain("'/img/printops_icon.png'");
    expect(layout).toContain("'h-10 w-10 object-contain'");
    expect(layout).not.toContain("'/img/printops_icon.svg'");
  });
});
```

- [ ] **Step 2: Run the reference test and confirm RED**

Run: `npx.cmd vitest run src/__tests__/assets/BrandReferences.test.ts`

Expected: FAIL on legacy SVG references and duplicate manifest entries.

- [ ] **Step 3: Implement the metadata and layout mapping**

Use this collapsed-sidebar branch in `Layout.tsx`:

```tsx
<img
  src={isSidebarCompact || sidebarExpanded ? '/img/printops_logo.svg' : '/img/printops_icon.png'}
  alt="PrintOps"
  className={isSidebarCompact || sidebarExpanded ? 'h-16 w-auto' : 'h-10 w-10 object-contain'}
/>
```

Use these favicon links in both HTML files and remove the invalid startup-image link:

```html
<link rel="icon" type="image/png" sizes="16x16" href="/img/favicon-16x16.png" />
<link rel="icon" type="image/png" sizes="32x32" href="/img/favicon-32x32.png" />
<link rel="icon" type="image/png" sizes="512x512" href="/img/favicon.png" />
<link rel="apple-touch-icon" sizes="180x180" href="/img/apple-touch-icon.png" />
```

Replace manifest icons with exactly the two `purpose: "any"` PNG entries from the test, and give every shortcut a typed 192×192 PNG icon. In both service workers, precache the main SVG, compact PNG, favicon PNGs, Apple icon, and 192/512 PWA PNGs. Use `/img/android-chrome-192x192.png` for notification `icon` and `/img/favicon-32x32.png` for `badge`.

- [ ] **Step 4: Run both focused tests and confirm GREEN**

Run: `npx.cmd vitest run src/__tests__/assets/BrandAssets.test.ts src/__tests__/assets/BrandReferences.test.ts`

Expected: 2 files passed; all brand tests passed.

- [ ] **Step 5: Commit only Task 2 files**

`static/index.html` already contains an unrelated generated bundle-hash change. Stage the branding version of that file from `HEAD` with Git plumbing so the user's bundle-hash change remains only in the working tree:

```powershell
$headStaticHtml = (git show HEAD:static/index.html) -join "`n"
$oldHeadBlock = @'
    <link rel="icon" type="image/svg+xml" href="/img/printops_icon.svg" />
    <link rel="apple-touch-icon" href="/img/printops_icon.svg" />

    <!-- Splash screens for iOS -->
    <link rel="apple-touch-startup-image" href="/img/printops_icon.svg" />
'@
$newBrandBlock = @'
    <link rel="icon" type="image/png" sizes="16x16" href="/img/favicon-16x16.png" />
    <link rel="icon" type="image/png" sizes="32x32" href="/img/favicon-32x32.png" />
    <link rel="icon" type="image/png" sizes="512x512" href="/img/favicon.png" />
    <link rel="apple-touch-icon" sizes="180x180" href="/img/apple-touch-icon.png" />
'@
$brandStaticHtml = $headStaticHtml.Replace($oldHeadBlock.TrimEnd(), $newBrandBlock.TrimEnd()) + "`n"
$brandBlob = $brandStaticHtml | git hash-object -w --stdin
git update-index --cacheinfo 100644,$brandBlob,static/index.html
git add -- frontend/src/__tests__/assets/BrandReferences.test.ts frontend/src/components/Layout.tsx frontend/index.html frontend/public/manifest.json frontend/public/sw.js static/manifest.json static/sw.js
git diff --cached --check
git commit -m "feat: wire PrintOps branding across app metadata"
```

### Task 3: Verify Build, Repository Presentation, and UI States

**Files:**
- Verify: `README.md`
- Verify: all Task 1 and Task 2 files
- Temporary output only: `tmp/brand-build/`

**Interfaces:**
- Consumes: completed asset and reference migration.
- Produces: evidence that source, production assets, PWA metadata, and visual states are correct without altering unrelated work.

- [ ] **Step 1: Verify README/GitHub mapping and intended diff**

Run:

```powershell
rg -n 'static/img/printops_logo.svg' README.md
git diff --check
git status --short
```

Expected: README still references the replaced tracked SVG; no whitespace errors; unrelated pre-existing changes remain present but unstaged by the branding commits.

- [ ] **Step 2: Run the complete frontend test suite**

Run: `npm.cmd run test:run`

Expected: all Vitest files pass and all locales remain in parity.

- [ ] **Step 3: Build outside the dirty production directory**

Run from `frontend`:

```powershell
npm.cmd run build -- --outDir ../tmp/brand-build
```

Expected: TypeScript and Vite exit 0; output is written under `tmp/brand-build`, not `static`.

- [ ] **Step 4: Verify visual states locally**

Start the frontend without replacing project files, then inspect:

1. Login page: full logo uses the tight SVG canvas and fits the existing `h-16` slot.
2. Expanded/sidebar or opened mobile drawer: full logo remains contained within the 256-pixel sidebar.
3. Collapsed desktop sidebar: only the 40×40 PrintOps icon is visible.
4. Browser tab: 16×16 or 32×32 favicon is the new orange-gold icon.

Expected: no clipping, dark-on-dark loss, or legacy Bambuddy artwork.

- [ ] **Step 5: Remove only temporary verification output**

Resolve `tmp/brand-build` to an absolute path under the repository, verify it is the expected target, then remove it. Do not remove or restore any unrelated path.

- [ ] **Step 6: Final verification**

Run:

```powershell
git log -3 --oneline
git status --short
rg -n 'printops_icon\.svg' frontend/src frontend/index.html frontend/public static/index.html static/manifest.json static/sw.js
```

Expected: the branding commits are present; no intended file remains unstaged; the final `rg` returns no legacy PrintOps icon SVG references.
