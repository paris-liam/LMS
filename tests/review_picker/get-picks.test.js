const test = require('node:test');
const assert = require('node:assert/strict');
const handler = require('../../tools/review-picker/api/get-picks.js');

function fakeRes() {
  const res = { statusCode: null, body: null };
  res.status = (code) => { res.statusCode = code; return res; };
  res.json = (body) => { res.body = body; return res; };
  return res;
}

test('rejects a missing batch query param', async () => {
  const res = fakeRes();
  await handler({ method: 'GET', query: {} }, res);
  assert.equal(res.statusCode, 400);
});

test('rejects an invalid batch id', async () => {
  const res = fakeRes();
  await handler({ method: 'GET', query: { batch: '../secrets' } }, res);
  assert.equal(res.statusCode, 400);
});

test('rejects non-GET requests', async () => {
  const res = fakeRes();
  await handler({ method: 'POST', query: { batch: 'out-x' } }, res);
  assert.equal(res.statusCode, 405);
});
