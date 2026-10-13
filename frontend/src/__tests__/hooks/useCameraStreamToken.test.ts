/**
 * Unit tests for rewriteMediaSrcWithToken — the DOM walker that retrofits a
 * media token onto <img>/<video> src URLs that rendered before the
 * token arrived (regression guard for the post-login blank-thumbnails bug).
 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { rewriteMediaSrcWithToken } from '../../hooks/useCameraStreamToken';

describe('rewriteMediaSrcWithToken', () => {
  let root: HTMLDivElement;

  beforeEach(() => {
    root = document.createElement('div');
    document.body.appendChild(root);
  });

  afterEach(() => {
    root.remove();
  });

  const addImg = (src: string) => {
    const img = document.createElement('img');
    img.setAttribute('src', src);
    root.appendChild(img);
    return img;
  };

  const addVideo = (src: string) => {
    const v = document.createElement('video');
    v.setAttribute('src', src);
    root.appendChild(v);
    return v;
  };

  it('appends token to /api/v1/ images that have no query string', () => {
    const img = addImg('/api/v1/library/files/42/thumbnail');
    const count = rewriteMediaSrcWithToken(root, 'abc123');
    expect(count).toBe(1);
    expect(img.getAttribute('src')).toBe('/api/v1/library/files/42/thumbnail?token=abc123');
  });

  it('appends token to URLs that already have a query string using & separator', () => {
    const img = addImg('/api/v1/archives/5/thumbnail?v=1700000000000');
    rewriteMediaSrcWithToken(root, 'abc123');
    expect(img.getAttribute('src')).toBe('/api/v1/archives/5/thumbnail?v=1700000000000&token=abc123');
  });

  it('leaves images alone that already carry the current token', () => {
    const img = addImg('/api/v1/library/files/42/thumbnail?token=abc123');
    const count = rewriteMediaSrcWithToken(root, 'abc123');
    expect(count).toBe(0);
    expect(img.getAttribute('src')).toBe('/api/v1/library/files/42/thumbnail?token=abc123');
  });

  it('replaces a stale token with the current one', () => {
    const img = addImg('/api/v1/library/files/42/thumbnail?token=OLD');
    rewriteMediaSrcWithToken(root, 'NEW');
    expect(img.getAttribute('src')).toBe('/api/v1/library/files/42/thumbnail?token=NEW');
  });

  it('replaces a stale token that sits in the middle of the query string', () => {
    const img = addImg('/api/v1/archives/5/thumbnail?token=OLD&v=1700000000000');
    rewriteMediaSrcWithToken(root, 'NEW');
    // Old token stripped, v preserved, new token appended.
    expect(img.getAttribute('src')).toBe('/api/v1/archives/5/thumbnail?v=1700000000000&token=NEW');
  });

  it('ignores images that do not point at /api/v1/', () => {
    const img = addImg('https://cdn.example.com/static/logo.png');
    rewriteMediaSrcWithToken(root, 'abc123');
    expect(img.getAttribute('src')).toBe('https://cdn.example.com/static/logo.png');
  });

  it('updates <video> elements as well', () => {
    const v = addVideo('/api/v1/archives/7/timelapse?fps=10');
    rewriteMediaSrcWithToken(root, 'abc123');
    expect(v.getAttribute('src')).toBe('/api/v1/archives/7/timelapse?fps=10&token=abc123');
  });

  it('url-encodes tokens containing special characters', () => {
    const img = addImg('/api/v1/library/files/42/thumbnail');
    rewriteMediaSrcWithToken(root, 'a b/c=d');
    expect(img.getAttribute('src')).toBe('/api/v1/library/files/42/thumbnail?token=a%20b%2Fc%3Dd');
  });
  it('keeps media credentials off cameras, foreign origins and unrelated API paths', () => {
    const camera = addImg('/api/v1/printers/1/camera/snapshot?token=CAMERA');
    const foreign = addImg('https://other.example/api/v1/library/files/1/thumbnail');
    const unrelated = addImg('/api/v1/auth/me');
    expect(rewriteMediaSrcWithToken(root, 'MEDIA')).toBe(0);
    expect(camera.getAttribute('src')).toBe('/api/v1/printers/1/camera/snapshot?token=CAMERA');
    expect(foreign.getAttribute('src')).toBe('https://other.example/api/v1/library/files/1/thumbnail');
    expect(unrelated.getAttribute('src')).toBe('/api/v1/auth/me');
  });

  it('keeps camera credentials off thumbnails', () => {
    const media = addImg('/api/v1/library/files/1/thumbnail?token=MEDIA');
    const camera = addVideo('/api/v1/printers/1/camera/stream');
    expect(rewriteMediaSrcWithToken(root, 'CAMERA', 'camera')).toBe(1);
    expect(media.getAttribute('src')).toBe('/api/v1/library/files/1/thumbnail?token=MEDIA');
    expect(camera.getAttribute('src')).toBe('/api/v1/printers/1/camera/stream?token=CAMERA');
  });

  it('updates new result-photo URLs while keeping other origins untouched', () => {
    const photo = addImg('/api/v1/library/files/42/photos/result.jpg?token=OLD');
    const foreign = addImg('https://other.example/api/v1/library/files/42/photos/result.jpg');
    expect(rewriteMediaSrcWithToken(root, 'NEW')).toBe(1);
    expect(photo.getAttribute('src')).toBe('/api/v1/library/files/42/photos/result.jpg?token=NEW');
    expect(foreign.getAttribute('src')).not.toContain('token=');
  });

  it('preserves explicit overlay camera credentials when a session token arrives', () => {
    window.history.replaceState({}, '', '/overlay/1?token=bblt_fixture');
    const camera = addImg('/api/v1/printers/1/camera/stream?token=bblt_fixture');
    rewriteMediaSrcWithToken(root, 'SESSION', 'camera');
    expect(camera.getAttribute('src')).toBe('/api/v1/printers/1/camera/stream?token=bblt_fixture');
    window.history.replaceState({}, '', '/');
  });

});
