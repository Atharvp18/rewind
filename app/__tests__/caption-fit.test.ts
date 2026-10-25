import { fitCaption, MAX_LINES, MIN_FONT_PT } from '@/lib/caption-fit';

const WIDTH = 300; // usable text width in pt

describe('caption fit', () => {
  it('keeps a short reply at the full font', () => {
    expect(fitCaption('Added Advil to your FSA card.', 22, WIDTH)).toEqual({
      font: 22,
      shown: 'Added Advil to your FSA card.',
    });
  });

  it('shrinks a longer reply, but never below the readable minimum', () => {
    const text = 'Advil Ibuprofen 200mg, $12.99. HSA eligible. Use your FSA card. Add it to your cart now?';
    const { font, shown } = fitCaption(text, 22, WIDTH);
    expect(font).toBeLessThan(22);
    expect(font).toBeGreaterThanOrEqual(MIN_FONT_PT);
    expect(shown).toBe(text);
  });

  it('shows only the latest sentences when even the smallest font cannot fit three lines', () => {
    const text = Array.from({ length: 12 }, (_, i) => `This is sentence number ${i + 1} of a long reply.`).join(' ');
    const { font, shown } = fitCaption(text, 22, WIDTH);
    expect(font).toBe(MIN_FONT_PT);
    expect(shown.startsWith('… ')).toBe(true);
    expect(shown.endsWith('sentence number 12 of a long reply.')).toBe(true);
    expect(shown.length).toBeLessThan(text.length);
    // fits three lines at the minimum font
    expect(shown.length).toBeLessThanOrEqual(Math.floor(WIDTH / (MIN_FONT_PT * 0.54)) * MAX_LINES);
  });

  it('keeps the end of one sentence that is longer than the whole caption', () => {
    const { shown } = fitCaption('word '.repeat(200) + 'the end.', 22, WIDTH);
    expect(shown.endsWith('the end.')).toBe(true);
  });

  it('a user text size above the minimum is never reduced below it', () => {
    const { font } = fitCaption('x'.repeat(10), 30, WIDTH);
    expect(font).toBe(30);
  });
});
