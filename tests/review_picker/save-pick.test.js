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

const {
  MAX_HANDLE_LENGTH, MAX_OVERVIEW_LENGTH, MAX_IMAGE_SRC_LENGTH,
} = require('../../tools/review-picker/api/save-pick.js');

test('accepts fields at exactly the length limits', () => {
  const result = validatePickPayload({
    batch: 'out-x',
    handle: 'h'.repeat(MAX_HANDLE_LENGTH),
    choice: 'manual',
    image_src: 'i'.repeat(MAX_IMAGE_SRC_LENGTH),
    overview: 'o'.repeat(MAX_OVERVIEW_LENGTH),
  });
  assert.equal(result.valid, true);
});

test('rejects an over-long handle', () => {
  const result = validatePickPayload({
    batch: 'out-x', handle: 'h'.repeat(MAX_HANDLE_LENGTH + 1), choice: 'skip',
  });
  assert.equal(result.valid, false);
  assert.match(result.error, /handle too long/);
});

test('rejects an over-long overview', () => {
  const result = validatePickPayload({
    batch: 'out-x', handle: 'movie-1', choice: 'manual',
    overview: 'o'.repeat(MAX_OVERVIEW_LENGTH + 1),
  });
  assert.equal(result.valid, false);
  assert.match(result.error, /overview too long/);
});

test('rejects an over-long image_src', () => {
  const result = validatePickPayload({
    batch: 'out-x', handle: 'movie-1', choice: 'manual',
    image_src: 'i'.repeat(MAX_IMAGE_SRC_LENGTH + 1),
  });
  assert.equal(result.valid, false);
  assert.match(result.error, /image_src too long/);
});

test('rejects an over-long poster_path', () => {
  const result = validatePickPayload({
    batch: 'out-x', handle: 'movie-1', choice: 'tmdb',
    poster_path: 'p'.repeat(MAX_IMAGE_SRC_LENGTH + 1),
  });
  assert.equal(result.valid, false);
  assert.match(result.error, /poster_path too long/);
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

test('handler returns 400 for an over-long overview', async () => {
  const res = fakeRes();
  await handler({
    method: 'POST',
    body: {
      batch: 'out-x', handle: 'movie-1', choice: 'manual',
      overview: 'o'.repeat(MAX_OVERVIEW_LENGTH + 1),
    },
  }, res);
  assert.equal(res.statusCode, 400);
  assert.match(res.body.error, /overview too long/);
});

test('handler reports a clear error when GITHUB_TOKEN is unset', async () => {
  const previous = process.env.GITHUB_TOKEN;
  delete process.env.GITHUB_TOKEN;
  try {
    const res = fakeRes();
    await handler({
      method: 'POST',
      body: { batch: 'out-x', handle: 'movie-1', choice: 'skip' },
    }, res);
    assert.equal(res.statusCode, 500);
    assert.equal(res.body.ok, false);
    assert.match(res.body.error, /GITHUB_TOKEN/);
  } finally {
    if (previous !== undefined) process.env.GITHUB_TOKEN = previous;
  }
});
