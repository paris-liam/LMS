const test = require('node:test');
const assert = require('node:assert/strict');
const { validatePickPayload } = require('../../tools/review-picker/api/save-pick.js');

test('accepts a valid skip pick', () => {
  const result = validatePickPayload({ batch: 'out-x', handle: 'movie-1', choice: 'skip' });
  assert.equal(result.valid, true);
});

test('accepts a valid tmdb pick', () => {
  const result = validatePickPayload({
    batch: 'out-x', handle: 'movie-1', choice: 'tmdb', poster_path: '/p.jpg', overview: 'text',
  });
  assert.equal(result.valid, true);
});

test('accepts a valid manual pick', () => {
  const result = validatePickPayload({
    batch: 'out-x', handle: 'movie-1', choice: 'manual', image_src: 'https://x/y.jpg', overview: 'text',
  });
  assert.equal(result.valid, true);
});

test('rejects a missing batch', () => {
  const result = validatePickPayload({ handle: 'movie-1', choice: 'skip' });
  assert.equal(result.valid, false);
  assert.match(result.error, /batch/);
});

test('rejects an invalid batch id', () => {
  const result = validatePickPayload({ batch: '../secrets', handle: 'movie-1', choice: 'skip' });
  assert.equal(result.valid, false);
  assert.match(result.error, /batch/);
});

test('rejects a missing handle', () => {
  const result = validatePickPayload({ batch: 'out-x', choice: 'skip' });
  assert.equal(result.valid, false);
  assert.match(result.error, /handle/);
});

test('rejects an unknown choice', () => {
  const result = validatePickPayload({ batch: 'out-x', handle: 'movie-1', choice: 'maybe' });
  assert.equal(result.valid, false);
  assert.match(result.error, /choice/);
});

const handler = require('../../tools/review-picker/api/save-pick.js');

function fakeRes() {
  const res = { statusCode: null, body: null };
  res.status = (code) => { res.statusCode = code; return res; };
  res.json = (body) => { res.body = body; return res; };
  return res;
}

test('handler rejects non-POST requests', async () => {
  const res = fakeRes();
  await handler({ method: 'GET', body: {} }, res);
  assert.equal(res.statusCode, 405);
});

test('handler returns 400 for an invalid payload', async () => {
  const res = fakeRes();
  await handler({ method: 'POST', body: { batch: 'x' } }, res);
  assert.equal(res.statusCode, 400);
  assert.equal(res.body.ok, false);
});
