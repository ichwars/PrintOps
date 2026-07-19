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
