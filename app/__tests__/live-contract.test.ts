/**
 * Live contract: the app's own API client (src/lib/api.ts) against a running backend.
 *
 *   REWIND_LIVE_URL=https://shelf-sense-zwvv.onrender.com npm run test:live
 *
 * Skipped unless REWIND_LIVE_URL is set. Read-only or short-lived: it opens questions that expire on
 * their own and answers "no" to the check-in, so it never charges a card or changes the shared cart.
 */
import * as api from '@/lib/api';

const LIVE = process.env.REWIND_LIVE_URL;

/**
 * jest-expo replaces fetch with a mock, so this file brings a minimal real one (Node's http and
 * https): enough for JSON requests and binary audio, which is all these tests send.
 */
function nodeFetch(url: string, init: { method?: string; headers?: Record<string, string>; body?: unknown } = {}) {
  const lib = url.startsWith('https:') ? require('node:https') : require('node:http');
  return new Promise<any>((resolve, reject) => {
    const req = lib.request(url, { method: init.method ?? 'GET', headers: init.headers }, (res: any) => {
      const chunks: Buffer[] = [];
      res.on('data', (c: Buffer) => chunks.push(c));
      res.on('end', () => {
        const body = Buffer.concat(chunks);
        resolve({
          ok: res.statusCode >= 200 && res.statusCode < 300,
          status: res.statusCode,
          json: async () => JSON.parse(body.toString('utf8')),
          arrayBuffer: async () => body.buffer.slice(body.byteOffset, body.byteOffset + body.byteLength),
        });
      });
    });
    req.on('error', reject);
    if (typeof init.body === 'string') req.write(init.body);
    req.end();
  });
}
const describeLive = LIVE ? describe : describe.skip;

describeLive(`live backend ${LIVE ?? ''}`, () => {
  beforeAll(() => {
    api.testing.live = true;
    api.testing.baseUrl = LIVE!.replace(/\/+$/, '');
    (globalThis as any).fetch = nodeFetch;
  });
  afterAll(() => {
    api.testing.live = false;
    api.testing.baseUrl = null;
  });
  jest.setTimeout(30_000);

  it('health: every upstream reports', async () => {
    const h = await api.getHealth();
    expect(['ok', 'degraded', 'down']).toContain(h.status);
    for (const u of ['claude', 'cartesia', 'moss', 'nessie', 'supabase']) expect(h.upstreams).toHaveProperty(u);
  });

  it('cards carry the fields the profile and chooser read, in integer cents', async () => {
    const cards = await api.getCards();
    expect(cards.length).toBeGreaterThan(0);
    for (const c of cards) {
      expect(['hsa', 'fsa', 'general']).toContain(c.type);
      expect(Number.isInteger(c.balance_cents)).toBe(true);
      expect(c).toHaveProperty('last4');
      expect(c).toHaveProperty('network');
    }
  });

  it('cart: groups with items and a total', async () => {
    const cart = await api.getCart();
    expect(Number.isInteger(cart.total_cents)).toBe(true);
    for (const g of cart.groups) {
      expect(Array.isArray(g.items)).toBe(true);
      for (const i of g.items) expect(typeof i.display_name).toBe('string');
    }
  });

  it('checkout preview: groups carry their items (the app shape)', async () => {
    const p = await api.checkoutPreview();
    expect(Number.isInteger(p.total_cents)).toBe(true);
    for (const g of p.groups) expect(Array.isArray(g.items)).toBe(true);
    expect(typeof p.voice.text).toBe('string');
  });

  it('voice: "what\'s in my cart" is read_cart with the cart as the result', async () => {
    const r = await api.command("what's in my cart", 1, null);
    expect(r.action).toBe('read_cart');
    expect(r.result).toHaveProperty('groups');
  });

  it('voice: "find invoice history" opens the history', async () => {
    expect((await api.command('find invoice history', 1, null)).action).toBe('open_history');
  });

  it('voice: a yes with no live question is E_PROMPT_EXPIRED', async () => {
    await expect(api.command('yes', 1, null)).rejects.toMatchObject({ code: 'E_PROMPT_EXPIRED' });
  });

  it('history: invoices in the History page shape', async () => {
    const list = await api.getPaymentHistory();
    expect(Array.isArray(list)).toBe(true);
    for (const inv of list) {
      expect(inv.total_cents).toBe(inv.subtotal_cents + inv.tax_cents);
      expect(inv.store).toHaveProperty('phone');
      expect(Array.isArray(inv.payments)).toBe(true);
    }
  });

  it('check-in: the demo store asks, and "no" leaves it unchanged', async () => {
    const asked = await api.nearbyStore(null, 'store_walmart');
    if (asked === null) return; // already checked in on this server: nothing to ask
    expect(asked.store.name).toBe('Walmart Pharmacy');
    expect(asked.voice.response_scope).toBe('confirm_checkin');
    const r = await api.command('no', 1, asked.voice.prompt_id);
    expect(r.action).toBe('skip');
  });

  it('check-in: far from the store is not at the store', async () => {
    expect(await api.stillAtStore('store_walmart', { lat: 40, lng: -100 })).toBe(false);
  });

  it('review: an item that is not in the cart says so', async () => {
    const r = await api.reviewCartItem('no-such-item');
    expect(r.item_id ?? null).toBeNull();
    expect(r.voice.text).toMatch(/no longer/);
  });

  it('reissue: an unknown scan is E_NOT_FOUND', async () => {
    await expect(api.reissuePrompt('no-such-scan', 'confirm_add')).rejects.toMatchObject({ code: 'E_NOT_FOUND' });
  });

  it('speech: Cartesia returns playable audio for a line', async () => {
    const t = await api.tts('Hello from Rewind.', 'normal');
    expect(t.sentences.length).toBeGreaterThan(0);
    const url = api.audioUrl(t.sentences[0].audio_url);
    const audio = await fetch(url);
    expect(audio.status).toBe(200);
    expect((await audio.arrayBuffer()).byteLength).toBeGreaterThan(1000);
  });
});
