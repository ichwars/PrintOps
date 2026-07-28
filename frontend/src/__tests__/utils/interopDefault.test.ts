import { describe, it, expect } from 'vitest';

import { resolveInteropDefault } from '../../utils/interopDefault';

const Comp = function Keyboard() {
  return null;
};

describe('resolveInteropDefault', () => {
  it('returns a bare function component unchanged', () => {
    expect(resolveInteropDefault(Comp)).toBe(Comp);
  });

  it('unwraps an interop namespace object via .default', () => {
    const moduleObject = { default: Comp, KeyboardReact: Comp };
    expect(resolveInteropDefault(moduleObject, ['KeyboardReact'])).toBe(Comp);
  });

  it('falls back to a named export when there is no .default', () => {
    const moduleObject = { KeyboardReact: Comp };
    expect(resolveInteropDefault(moduleObject, ['KeyboardReact'])).toBe(Comp);
  });

  it('leaves a forwardRef-like object unchanged', () => {
    const forwardRefLike = { $$typeof: Symbol.for('react.forward_ref'), render: Comp };
    expect(resolveInteropDefault(forwardRefLike)).toBe(forwardRefLike);
  });

  it('returns a string tag unchanged', () => {
    expect(resolveInteropDefault('div')).toBe('div');
  });

  it('returns the value unchanged when nothing usable is found', () => {
    const opaque = { something: 1 };
    expect(resolveInteropDefault(opaque, ['KeyboardReact'])).toBe(opaque);
  });
});
