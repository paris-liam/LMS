const test = require('node:test');
const assert = require('node:assert/strict');
const zlib = require('node:zlib');
const L = require('../../tools/rental-sync/logic.js');

test('gzipBase64 round-trips through gunzip', async () => {
  const text = 'id,barcode\n1,2010000000014\n'.repeat(1000);
  const encoded = await L.gzipBase64(text);
  assert.equal(zlib.gunzipSync(Buffer.from(encoded, 'base64')).toString(), text);
});

test('fileProblem', () => {
  assert.equal(L.fileProblem(null, 'Barcodes export'), 'Choose the Barcodes export file.');
  assert.match(L.fileProblem({ size: L.MAX_FILE_BYTES + 1 }, 'Library export'), /over 5 MB/);
  assert.equal(L.fileProblem({ size: 10 }, 'Library export'), '');
});

test('batches', () => {
  assert.deepEqual(L.batches([1, 2, 3, 4, 5, 6, 7], 5), [[1, 2, 3, 4, 5], [6, 7]]);
  assert.deepEqual(L.batches([], 5), []);
});

test('byCreatedThenTitle and shortDate', () => {
  const list = [{ created: '2026-10-14', title: 'b' }, { created: '2026-10-13', title: 'z' }, { created: '2026-10-14', title: 'A' }];
  assert.deepEqual(list.sort(L.byCreatedThenTitle).map((c) => c.title), ['z', 'A', 'b']);
  assert.equal(L.shortDate('2026-10-14 10:00:00'), '2026-10-14');
  assert.equal(L.shortDate(''), '—');
});

test('isHttpsUrl', () => {
  assert.equal(L.isHttpsUrl('https://image.tmdb.org/t/p/w1280/a.jpg'), true);
  assert.equal(L.isHttpsUrl(' https://x.com/a.jpg '), true);
  assert.equal(L.isHttpsUrl('http://x.com/a.jpg'), false);
  assert.equal(L.isHttpsUrl('javascript:alert(1)'), false);
  assert.equal(L.isHttpsUrl(''), false);
});

const confident = { barcode: 'b', kind: 'confident', url: 'https://t/j.jpg', alt: 'Jaws (1975) poster', candidate: { title: 'Jaws', year: '1975' }, reason: '' };
const unsure = { ...confident, kind: 'unsure' };

test('initialPoster per kind', () => {
  assert.equal(L.initialPoster(confident).url, 'https://t/j.jpg');
  const u = L.initialPoster(unsure);
  assert.equal(u.url, '');
  assert.deepEqual(u.suggestion, { url: 'https://t/j.jpg', alt: 'Jaws (1975) poster', title: 'Jaws', year: '1975' });
  assert.equal(L.initialPoster({ kind: 'none', reason: 'no TMDB match' }).note, 'No poster found');
  assert.equal(L.initialPoster({ kind: 'error', reason: 'timeout' }).note, 'Poster lookup failed — paste a link or leave it blank');
});

test('acceptSuggestion and pastedPoster', () => {
  const accepted = L.acceptSuggestion(L.initialPoster(unsure));
  assert.equal(accepted.url, 'https://t/j.jpg');
  const pasted = L.pastedPoster(L.initialPoster(confident), 'https://mine/p.jpg');
  assert.deepEqual([pasted.url, pasted.alt, pasted.note], ['https://mine/p.jpg', '', '']);
  assert.equal(L.pastedPoster(pasted, '').url, 'https://t/j.jpg');            // clearing restores TMDB's
  assert.equal(L.pastedPoster(pasted, 'http://x/p.jpg').note, 'Links must start with https://');
});

function copyOf(barcode, itemId, extra = {}) {
  return { barcode, item_id: itemId, title: `T${itemId}`, set_aside: [], libib_duplicate: null, match: null,
    libib: { id: itemId, barcode, title: `T${itemId}`, tags: 'vhs, horror', description: '', created: '' }, ...extra };
}
const dupeOf = (title) => ({ item_id: 'old', title, format: 'VHS', genres: ['Horror'], copies: 1, created: '2025-01-01' });
const matchOf = (id) => ({ id: `gid://shopify/Product/${id}`, handle: 'h', title: 'Jaws', vendor: 'VHS', tags: ['Rental'],
  image: '', copies: 1, admin_url: `https://admin.shopify.com/store/s/products/${id}` });

test('groupForCreate groups by Libib item in first-seen order', () => {
  const a1 = copyOf('2010000000031', 'a'), b1 = copyOf('2010000000017', 'b'), a2 = copyOf('2010000000024', 'a');
  assert.deepEqual(L.groupForCreate([a1, b1, a2]), [{ item_id: 'a', copies: [a1, a2] }, { item_id: 'b', copies: [b1] }]);
  assert.deepEqual(L.groupForCreate([]), []);
});

test('groupKey is the lowest barcode, matching the server result barcode', () => {
  const group = { item_id: 'a', copies: [copyOf('2010000000031', 'a'), copyOf('2010000000024', 'a')] };
  assert.equal(L.groupKey(group), '2010000000024');
});

test('choiceState blocks while any match lacks a choice', () => {
  const plain = copyOf('1', 'a'), dupe = copyOf('2', 'b', { libib_duplicate: dupeOf('Jaws') });
  const m1 = copyOf('3', 'c', { match: matchOf(1) }), m2 = copyOf('4', 'd', { match: matchOf(2) });
  const copies = [plain, dupe, m1, m2];
  const none = L.choiceState(copies, new Map());
  assert.deepEqual(none.dupes, [dupe]);
  assert.deepEqual(none.matches, [m1, m2]);
  assert.equal(none.blocked, true);
  assert.equal(L.choiceState(copies, new Map([['3', 'add']])).blocked, true);
  assert.equal(L.choiceState(copies, new Map([['3', 'add'], ['4', 'skip']])).blocked, false);
  assert.equal(L.choiceState([plain, dupe], new Map()).blocked, false);   // an undismissed duplicate never blocks
});

test('applyChoices routes copies and writes the set-aside texts', () => {
  const plain = copyOf('1', 'a');
  const dupe = copyOf('2', 'b', { title: 'Jaws 2', libib_duplicate: dupeOf('Jaws, The') });
  const kept = copyOf('3', 'c', { libib_duplicate: dupeOf('Halloween') });
  const add = copyOf('4', 'd', { match: matchOf(1) }), skip = copyOf('5', 'e', { match: matchOf(2) });
  const out = L.applyChoices([plain, dupe, kept, add, skip], new Map([['c', 'not_duplicate'], ['4', 'add'], ['5', 'skip']]));
  assert.deepEqual(out.create, [plain, kept]);
  assert.deepEqual(out.add, [add]);
  assert.deepEqual(out.setAside.map((c) => [c.barcode, c.set_aside]), [
    ['2', ['In Libib, delete “Jaws 2” and add this copy to “Jaws, The” instead. It will show up next time you sync.']],
    ['5', ["If this copy isn't the same movie, move it to its own item in Libib."]],
  ]);
  assert.deepEqual(dupe.set_aside, []);   // the input copy is not changed
});

test('a duplicate choice covers every copy of the Libib item, and the item gets one card', () => {
  const flag = { libib_duplicate: dupeOf('Halloween') };
  const c1 = copyOf('2010000000024', 'h', flag), c2 = copyOf('2010000000031', 'h', flag);
  const other = copyOf('2010000000048', 'j', { libib_duplicate: dupeOf('Jaws') });
  assert.deepEqual(L.choiceState([c1, c2, other], new Map()).dupes, [c1, other]);
  const out = L.applyChoices([c1, c2, other], new Map([['h', 'not_duplicate']]));
  assert.deepEqual(out.create, [c1, c2]);
  assert.deepEqual(L.groupForCreate(out.create), [{ item_id: 'h', copies: [c1, c2] }]);
  assert.deepEqual(out.setAside.map((c) => c.barcode), ['2010000000048']);
  // a barcode key is not a dismissal
  assert.deepEqual(L.applyChoices([c1, c2], new Map([['2010000000024', 'not_duplicate']])).create, []);
});

test('createPayload sends every copy of the group and only https posters', () => {
  const group = { item_id: 'a', copies: [copyOf('2010000000024', 'a'), copyOf('2010000000031', 'a')] };
  const items = group.copies.map((c) => c.libib);
  assert.deepEqual(L.createPayload(group, L.initialPoster(confident)),
    { items, poster: { url: 'https://t/j.jpg', alt: 'Jaws (1975) poster' } });
  assert.deepEqual(L.createPayload(group, L.initialPoster(unsure)), { items, poster: null });
  assert.deepEqual(L.createPayload(group, { url: 'http://x', alt: '' }), { items, poster: null });
  assert.deepEqual(L.createPayload(group, undefined), { items, poster: null });
});

test('createPayload sends the normalised poster URL so an upper-case scheme still passes the server check', () => {
  const group = { item_id: 'a', copies: [copyOf('2010000000024', 'a')] };
  assert.deepEqual(L.createPayload(group, { url: ' HTTPS://Mine.example/p.jpg ', alt: '' }),
    { items: [group.copies[0].libib], poster: { url: 'https://mine.example/p.jpg', alt: '' } });
});

test('addCopyPayload sends the Libib copy and the matched product id', () => {
  const copy = copyOf('2010000000024', 'a', { match: matchOf(7) });
  assert.deepEqual(L.addCopyPayload(copy), { item: copy.libib, product_id: 'gid://shopify/Product/7' });
});

test('summarize and finishPayload', () => {
  const s = L.summarize([
    { status: 'created', poster: 'ok' }, { status: 'created', poster: 'failed' },
    { status: 'skipped_exists' }, { status: 'failed' }, { status: 'added' }]);
  assert.deepEqual([s.created.length, s.posterFailed.length, s.skipped.length, s.failed.length, s.added.length],
    [2, 1, 1, 1, 1]);
  assert.deepEqual(L.finishPayload(s, 4), { created: 2, added: 1, skipped: 1, failed: 1, set_aside: 4 });
});

test('barcodesToPrint lists every created copy and every added copy', () => {
  assert.deepEqual(L.barcodesToPrint([
    { status: 'created', barcode: '11', barcodes: ['11', '12'] },
    { status: 'skipped_exists', barcode: '21', barcodes: ['21'] },
    { status: 'failed', barcode: '31', barcodes: ['31'] },
    { status: 'added', barcode: '41' },
    { status: 'skipped_exists', barcode: '51' }]), ['11', '12', '41']);
  assert.deepEqual(L.barcodesToPrint([]), []);
});

test('printBarcodesUrl', () => {
  assert.equal(L.printBarcodesUrl('lms-sandbox-lutsfahz.myshopify.com'),
    'https://admin.shopify.com/store/lms-sandbox-lutsfahz/products?tag=Barcode%20Not%20Printed');
});

test('describeLastRun', () => {
  assert.equal(L.describeLastRun(null), 'No sync yet.');
  const text = L.describeLastRun({ finished_at: '2026-10-14T19:12:00+00:00', created: 18 });
  assert.match(text, /^Last successful sync: Oct 14, 2026/);
  assert.match(text, /18 created$/);
});

function fakeResponse(status, body) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

test('api retries the same request after login', async () => {
  const calls = [];
  let logins = 0;
  const replies = [fakeResponse(401, { error: { message: 'Please log in again.' } }), fakeResponse(200, { ok: 1 })];
  const api = L.makeApi({
    fetch: async (url, options) => { calls.push([url, options.body]); return replies.shift(); },
    requireLogin: async () => { logins += 1; },
  });
  assert.deepEqual(await api('create', { item: { barcode: 'b' } }), { ok: 1 });
  assert.equal(logins, 1);
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[0], calls[1]);
});

test('api surfaces server messages and network failures', async () => {
  const api = L.makeApi({
    fetch: async () => fakeResponse(503, { error: { kind: 'shopify', message: "Shopify didn't respond", detail: 'HTTP 502' } }),
    requireLogin: async () => {},
  });
  await assert.rejects(api('status'), (e) => e.message === "Shopify didn't respond" && e.detail === 'HTTP 502'
    && e.kind === 'shopify');
  const offline = L.makeApi({ fetch: async () => { throw new TypeError('Failed to fetch'); }, requireLogin: async () => {} });
  await assert.rejects(offline('status'), (e) => /Couldn't reach the sync app/.test(e.message) && e.kind === 'network');
  const bare = L.makeApi({ fetch: async () => fakeResponse(500, {}), requireLogin: async () => {} });
  await assert.rejects(bare('status'), (e) => e.kind === '' && e.detail === '');
});
