# Responsive PrintOps Dark-UI Logo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a clean, contrast-safe PrintOps wide SVG that stays legible at the current 178 × 58 pixel login size, then show it in a non-persistent local browser preview.

**Architecture:** Add one source-controlled SVG under the Vite public assets and one focused Vitest contract test that guards its palette and structure. Keep the existing production logo references unchanged until the new asset has been visually approved; preview the new SVG by replacing the image source only in the live browser tab.

**Tech Stack:** SVG 1.1, React/Vite public assets, Vitest, TypeScript, in-app browser preview

## Global Constraints

- Preserve the exact word `PrintOps`, the printer/stack/checkmark meaning, and the left-symbol/right-wordmark arrangement.
- Use `#F4F7FA` for `Print` and structural contours.
- Use `#FFB71B` for `Ops`, arrows, the top print layer, and the check badge.
- Use no gradients, textures, shadows, glow effects, filters, masks, or embedded raster images.
- Use an exact `viewBox="0 0 1206 391"` and no artificial outer padding.
- Use a 10-unit minimum structural stroke at the 391-unit SVG height; this renders at approximately 1.48 CSS pixels at 58 pixels high.
- Do not replace existing `/img/printops_logo.svg` references before visual approval.

---

### Task 1: Add the clean Dark-UI SVG contract and asset

**Files:**
- Create: `frontend/src/__tests__/assets/PrintOpsLogoDark.test.ts`
- Create: `frontend/public/img/printops_logo_dark.svg`

**Interfaces:**
- Consumes: Vite's existing `/img/*` public-asset convention and the approved design specification.
- Produces: `/img/printops_logo_dark.svg`, a standalone responsive SVG suitable for an `<img>` element.

- [ ] **Step 1: Write the failing SVG contract test**

```ts
import fs from 'node:fs';
import path from 'node:path';

const logoPath = path.resolve(process.cwd(), 'public/img/printops_logo_dark.svg');

describe('PrintOps dark UI logo asset', () => {
  const source = fs.readFileSync(logoPath, 'utf8');

  it('uses a tight responsive SVG canvas', () => {
    expect(source).toContain('viewBox="0 0 1206 391"');
    expect(source).not.toMatch(/<svg[^>]+\s(?:width|height)=/i);
    expect(source).toContain('id="printops-symbol"');
    expect(source).toContain('id="printops-wordmark"');
  });

  it('uses the approved dark UI palette', () => {
    expect(source).toContain('#F4F7FA');
    expect(source).toContain('#FFB71B');
    expect(source).not.toMatch(/#14171E|#1D2026/i);
  });

  it('contains only scalable, filter-free artwork', () => {
    expect(source).not.toMatch(/<(?:image|text|filter|mask|linearGradient|radialGradient)\b/i);
    expect(source).not.toMatch(/(?:href|xlink:href)="data:image\//i);
    expect(source).not.toMatch(/\bfilter=/i);
  });

  it('keeps the structural contour legible at the login size', () => {
    expect(source).toContain('stroke-width="10"');
    expect(source).toContain('aria-label="PrintOps"');
  });
});
```

- [ ] **Step 2: Run the test and verify the missing asset fails**

Run: `npm.cmd run test:run -- src/__tests__/assets/PrintOpsLogoDark.test.ts`

Expected: FAIL with `ENOENT` for `public/img/printops_logo_dark.svg`.

- [ ] **Step 3: Author the SVG with explicit construction rules**

Create `frontend/public/img/printops_logo_dark.svg` as a manually reviewed SVG. Use the original PNG only as a visual reference. Reconstruct the printer frame, nozzle, arrows, three stacked layers, badge, and check with direct SVG paths. For the wordmark, retain the existing letter silhouettes only after separating them into one path per letter and removing duplicated outline paths; do not run an automatic raster trace.

The root element uses the namespace `http://www.w3.org/2000/svg`, `viewBox="0 0 1206 391"`, `role="img"`, and `aria-label="PrintOps"`, with no fixed width or height. Its first child group is `id="printops-symbol"` with round line caps and joins; it contains exactly the printer frame, nozzle, two arrows, three stack layers, badge circle, and check path. Its second child group is `id="printops-wordmark"`; it contains exactly eight filled letter paths for `P`, `r`, `i`, `n`, `t`, `O`, `p`, and `s`.

Construction measurements:

- Symbol bounds: `x=0..360`, `y=0..391`.
- Wordmark bounds: `x=420..1206`, vertically centered at `y=118..273`.
- Gap between symbol and wordmark: at least 60 viewBox units.
- Printer frame and layer outlines: `stroke-width="10"`.
- Orange arrow and badge outlines: `stroke="#F4F7FA" stroke-width="10"`.
- Wordmark letters: filled paths only, with no stroke.
- `Print` fill: `#F4F7FA`; `Ops` fill: `#FFB71B`.
- Check mark fill: `#11151B`.

- [ ] **Step 4: Run the focused contract test**

Run: `npm.cmd run test:run -- src/__tests__/assets/PrintOpsLogoDark.test.ts`

Expected: 4 tests pass, 0 tests fail.

- [ ] **Step 5: Run the frontend build**

Run: `npm.cmd run build`

Expected: TypeScript and Vite complete with exit code 0; `dist/img/printops_logo_dark.svg` exists.

- [ ] **Step 6: Commit the isolated asset and test**

```powershell
git add -- frontend/public/img/printops_logo_dark.svg frontend/src/__tests__/assets/PrintOpsLogoDark.test.ts
git commit -m "feat: add responsive dark UI logo"
```

---

### Task 2: Verify the logo at production sizes without replacing production assets

**Files:**
- Read: `frontend/public/img/printops_logo_dark.svg`
- Read: `frontend/src/pages/LoginPage.tsx`
- No source file modifications.

**Interfaces:**
- Consumes: `/img/printops_logo_dark.svg` from Task 1 and the running Vite preview.
- Produces: a visual approval result at the three specified sizes; it does not change persistent logo references.

- [ ] **Step 1: Start the existing frontend development server**

Run: `npm.cmd run dev -- --host 127.0.0.1 --port 5180`

Expected: Vite reports `http://127.0.0.1:5180/` and serves the login page.

- [ ] **Step 2: Inject the new asset only into the live login tab**

In the browser developer preview, set the single `img[alt="PrintOps"]` source to `/img/printops_logo_dark.svg` and leave `LoginPage.tsx` unchanged.

Expected DOM state:

```text
img[alt="PrintOps"]
src = http://127.0.0.1:5180/img/printops_logo_dark.svg
rendered size = approximately 178 × 58 pixels
```

- [ ] **Step 3: Capture and inspect three target sizes**

Inspect the same SVG on `#171B21` at:

```text
178 × 58 px  — current login size
240 × 78 px  — enlarged login/setup size
256 × 83 px  — expanded sidebar size
```

Expected at every size: `PrintOps` is immediately readable; arrows, stack layers, nozzle, badge, and check remain distinct; no dark region merges with the background; no edge looks rasterized.

- [ ] **Step 4: Verify production references remain unchanged**

Run: `git diff -- frontend/src/pages/LoginPage.tsx frontend/src/components/Layout.tsx frontend/src/pages/SetupPage.tsx frontend/src/pages/StreamOverlayPage.tsx`

Expected: no diff output.

- [ ] **Step 5: Hand off the browser preview for visual approval**

Keep the live preview tab open and report the test sizes. Do not replace `/img/printops_logo.svg` until the user explicitly approves the new asset.
