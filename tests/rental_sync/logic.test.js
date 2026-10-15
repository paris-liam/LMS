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

test('createPayload only sends https posters', () => {
  const copy = { libib: { barcode: 'b', title: 'Jaws', tags: 'vhs, horror', description: '', created: '' } };
  assert.deepEqual(L.createPayload(copy, L.initialPoster(confident)),
    { item: copy.libib, poster: { url: 'https://t/j.jpg', alt: 'Jaws (1975) poster' } });
  assert.deepEqual(L.createPayload(copy, L.initialPoster(unsure)), { item: copy.libib, poster: null });
  assert.deepEqual(L.createPayload(copy, { url: 'http://x', alt: '' }), { item: copy.libib, poster: null });
  assert.deepEqual(L.createPayload(copy, undefined), { item: copy.libib, poster: null });
});

test('createPayload sends the normalised poster URL so an upper-case scheme still passes the server check', () => {
  const copy = { libib: { barcode: 'b', title: 'Jaws', tags: 'vhs, horror', description: '', created: '' } };
  assert.deepEqual(L.createPayload(copy, { url: ' HTTPS://Mine.example/p.jpg ', alt: '' }),
    { item: copy.libib, poster: { url: 'https://mine.example/p.jpg', alt: '' } });
});

test('summarize and finishPayload', () => {
  const s = L.summarize([
    { status: 'created', poster: 'ok' }, { status: 'created', poster: 'failed' },
    { status: 'skipped_exists' }, { status: 'failed' }]);
  assert.deepEqual([s.created.length, s.posterFailed.length, s.skipped.length, s.failed.length], [2, 1, 1, 1]);
  assert.deepEqual(L.finishPayload(s, 4), { created: 2, skipped: 1, failed: 1, set_aside: 4 });
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
