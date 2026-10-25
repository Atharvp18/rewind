import { Working } from '@/lib/phrases';

describe('what the agent says it is doing', () => {
  it.each([
    ["I'm ready to checkout", 'Getting your total ready.'],
    ['show me my cart', 'Opening your cart.'],
    ['open my purchase history', 'Opening your purchase history.'],
    ['remove the last one', 'Taking that off your cart.'],
    ['clear my cart', 'Checking before I clear your cart.'],
    ['yes', 'Adding that for you.'],
    ['put it on my visa', 'Adding that for you.'],
    ['no thanks', 'Okay, skipping that.'],
    ['say that again', 'Getting that again.'],
    ['purple monkey dishwasher', 'Working on that.'],
  ])('"%s" -> %s', (said, line) => {
    expect(Working.forRequest(said)).toBe(line);
  });

  it('never says a bare "Looking"', () => {
    for (const line of Working.scan) expect(line.toLowerCase()).not.toBe('looking.');
    expect(Working.scan).toHaveLength(3);
  });
});
