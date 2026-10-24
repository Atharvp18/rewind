/**
 * Tech spec 0.5: money is always an integer number of cents. A float in a
 * money field is a bug even if the demo passes. The app only formats cents.
 */
import { centsForScreenReader, formatCents } from '@/lib/money';

describe('formatCents', () => {
  it.each([
    [0, '$0.00'],
    [5, '$0.05'],
    [99, '$0.99'],
    [100, '$1.00'],
    [1299, '$12.99'], // Advil (spec 3.3)
    [549, '$5.49'], // bandages
    [499, '$4.99'], // kettle corn
    [34000, '$340.00'], // run 1 HSA seed
    [500000, '$5,000.00'], // Visa credit seed, thousands separator
    [123456789, '$1,234,567.89'],
  ])('%i cents → %s', (cents, text) => {
    expect(formatCents(cents)).toBe(text);
  });

  it('formats negatives with the sign in front', () => {
    expect(formatCents(-549)).toBe('-$5.49');
    expect(formatCents(-5)).toBe('-$0.05');
  });

  it.each([12.99, 0.5, NaN, Infinity, -1.25])('rejects the non-integer %p (float money is a bug)', (bad) => {
    expect(() => formatCents(bad)).toThrow(/integer cents/);
  });

  it('reproduces the demo arithmetic exactly (spec 4.4)', () => {
    const total = 1299 + 549;
    expect(total).toBe(1848);
    expect(formatCents(total)).toBe('$18.48');
    expect(formatCents(34000 - total)).toBe('$321.52'); // run 1 on the spec's original HSA-only seed
    expect(formatCents(2500 - total)).toBe('$6.52'); // run 1 on the FSA-first seed
  });
});

describe('centsForScreenReader', () => {
  it.each([
    [1299, '12 dollars and 99 cents'],
    [100, '1 dollar'],
    [101, '1 dollar and 1 cent'],
    [5, '0 dollars and 5 cents'],
    [0, '0 dollars'],
    [34000, '340 dollars'],
    [-549, 'minus 5 dollars and 49 cents'],
  ])('%i cents is read as "%s"', (cents, spoken) => {
    expect(centsForScreenReader(cents)).toBe(spoken);
  });
});
