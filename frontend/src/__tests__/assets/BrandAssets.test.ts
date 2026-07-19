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
