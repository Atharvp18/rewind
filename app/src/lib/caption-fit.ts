// Fits a spoken reply into the caption pill: three lines, never smaller than a readable size.

/**
 * The caption is three lines at most. A long reply first shrinks the font, but never below a readable
 * size (MIN_FONT_PT, the iOS body size). If it still does not fit, only the latest sentences are shown;
 * tapping repeats the whole reply and screen readers always get all of it.
 */
export const MAX_LINES = 3;
export const MIN_FONT_PT = 17;
const SHRINK_STEP = 0.05;
/** Average glyph width as a share of the font size, with a safety margin so a line never wraps early. */
const CHAR_WIDTH = 0.54;

/** The largest font (from `base` down to MIN_FONT_PT) that fits `text` in MAX_LINES, and the text to show. */
export function fitCaption(text: string, base: number, usableWidth: number): { font: number; shown: string } {
  const capacity = (font: number) => Math.floor(usableWidth / (font * CHAR_WIDTH)) * MAX_LINES;
  for (let font = base; font >= MIN_FONT_PT; font -= base * SHRINK_STEP) {
    if (text.length <= capacity(font)) return { font: Math.round(font), shown: text };
  }
  const font = Math.min(base, MIN_FONT_PT);
  const room = capacity(font) - 2; // room for the leading "…"
  const sentences = text.split(/(?<=[.!?])\s+/);
  let shown = '';
  for (let i = sentences.length - 1; i >= 0; i--) {
    const next = shown ? `${sentences[i]} ${shown}` : sentences[i];
    if (next.length > room) break;
    shown = next;
  }
  // One sentence longer than the whole caption: keep its end.
  if (!shown) shown = text.slice(-room);
  return { font, shown: shown === text ? text : `… ${shown}` };
}

