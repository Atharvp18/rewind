/**
 * Money is always an integer number of cents (tech spec 0.5). This file only
 * formats cents for display; it never does arithmetic on dollars.
 */

export function formatCents(cents: number): string {
  if (!Number.isInteger(cents)) {
    throw new Error(`formatCents expects integer cents, got ${cents}`);
  }
  const sign = cents < 0 ? '-' : '';
  const abs = Math.abs(cents);
  const dollars = Math.trunc(abs / 100);
  const rest = String(abs % 100).padStart(2, '0');
  const grouped = String(dollars).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return `${sign}$${grouped}.${rest}`;
}

/** Spoken-friendly label for screen readers: "12 dollars and 99 cents". */
export function centsForScreenReader(cents: number): string {
  const abs = Math.abs(cents);
  const dollars = Math.trunc(abs / 100);
  const rest = abs % 100;
  const d = `${dollars} ${dollars === 1 ? 'dollar' : 'dollars'}`;
  const c = rest ? ` and ${rest} ${rest === 1 ? 'cent' : 'cents'}` : '';
  return `${cents < 0 ? 'minus ' : ''}${d}${c}`;
}
