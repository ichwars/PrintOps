import { describe, expect, it } from 'vitest';
import { normalizeOrderTags } from '../../lib/orderTagNormalization';

describe('order tag normalization', () => {
  it('selects the smallest display for each NFKC-casefold key', () => {
    expect(normalizeOrderTags(['\u212B', 'A\u030A', '\u00C5', 'vip', 'VIP', 'Stra\u00DFe', 'STRASSE']))
      .toEqual(['STRASSE', 'VIP', 'A\u030A']);
  });

  it('sorts key and display pairs by Python Unicode code points', () => {
    expect(normalizeOrderTags(['Z', 'a'])).toEqual(['a', 'Z']);
    expect(normalizeOrderTags(['\u{10000}', '\uE000'])).toEqual(['\uE000', '\u{10000}']);
  });

  it('strips U+0085 like Python str.strip', () => {
    expect(normalizeOrderTags(['\u0085priority\u0085'])).toEqual(['priority']);
  });

  it('preserves U+FEFF like Python str.strip', () => {
    expect(normalizeOrderTags(['\uFEFFpriority\uFEFF'])).toEqual(['\uFEFFpriority\uFEFF']);
  });
});
