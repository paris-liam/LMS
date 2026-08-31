const test = require('node:test');
const assert = require('node:assert/strict');
const { isValidBatchId, mergePick } = require('../../tools/review-picker/api/_github.js');

test('isValidBatchId accepts a normal batch slug', () => {
  assert.equal(isValidBatchId('out-product_export_3'), true);
});

test('isValidBatchId accepts hyphens and digits', () => {
  assert.equal(isValidBatchId('out-new-unformatted-8-30'), true);
});

test('isValidBatchId rejects path traversal', () => {
  assert.equal(isValidBatchId('../../secrets'), false);
});

test('isValidBatchId rejects slashes', () => {
  assert.equal(isValidBatchId('foo/bar'), false);
});

test('isValidBatchId rejects empty string', () => {
  assert.equal(isValidBatchId(''), false);
});

test('isValidBatchId rejects non-string input', () => {
  assert.equal(isValidBatchId(undefined), false);
  assert.equal(isValidBatchId(null), false);
  assert.equal(isValidBatchId(42), false);
});

test('mergePick inserts a new handle', () => {
  const before = [{ handle: 'a', choice: 'skip' }];
  const after = mergePick(before, { handle: 'b', choice: 'skip' });
  assert.deepEqual(after, [
    { handle: 'a', choice: 'skip' },
    { handle: 'b', choice: 'skip' },
  ]);
});

test('mergePick replaces an existing handle in place', () => {
  const before = [
    { handle: 'a', choice: 'skip' },
    { handle: 'b', choice: 'skip' },
  ];
  const after = mergePick(before, { handle: 'a', choice: 'manual', overview: 'x' });
  assert.deepEqual(after, [
    { handle: 'a', choice: 'manual', overview: 'x' },
    { handle: 'b', choice: 'skip' },
  ]);
});

test('mergePick does not mutate the input array', () => {
  const before = [{ handle: 'a', choice: 'skip' }];
  mergePick(before, { handle: 'a', choice: 'manual' });
  assert.deepEqual(before, [{ handle: 'a', choice: 'skip' }]);
});

const { getFile, putFile } = require('../../tools/review-picker/api/_github.js');

function fakeFetch(responses) {
  let call = 0;
  return async (url, opts) => {
    const response = responses[call];
    call += 1;
    return response(url, opts);
  };
}

test('getFile decodes base64 content and returns sha', async () => {
  const body = JSON.stringify([{ handle: 'a', choice: 'skip' }]);
  const fetchImpl = fakeFetch([
    async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        content: Buffer.from(body, 'utf-8').toString('base64'),
        sha: 'abc123',
      }),
    }),
  ]);
  const result = await getFile(
    { owner: 'paris-liam', repo: 'LMS', branch: 'main', token: 't', path: 'tools/review-picker/data/x.json' },
    fetchImpl,
  );
  assert.equal(result.content, body);
  assert.equal(result.sha, 'abc123');
});

test('getFile returns null on a 404', async () => {
  const fetchImpl = fakeFetch([async () => ({ ok: false, status: 404, json: async () => ({}) })]);
  const result = await getFile(
    { owner: 'paris-liam', repo: 'LMS', branch: 'main', token: 't', path: 'tools/review-picker/data/missing.json' },
    fetchImpl,
  );
  assert.equal(result, null);
});

test('getFile throws on a non-404 error status', async () => {
  const fetchImpl = fakeFetch([async () => ({ ok: false, status: 500, json: async () => ({ message: 'boom' }) })]);
  await assert.rejects(
    getFile({ owner: 'o', repo: 'r', branch: 'main', token: 't', path: 'x.json' }, fetchImpl),
  );
});

test('putFile base64-encodes the content and sends the sha', async () => {
  let capturedBody;
  const fetchImpl = fakeFetch([
    async (url, opts) => {
      capturedBody = JSON.parse(opts.body);
      return { ok: true, status: 200, json: async () => ({ content: { sha: 'new-sha' } }) };
    },
  ]);
  const result = await putFile(
    {
      owner: 'paris-liam', repo: 'LMS', branch: 'main', token: 't',
      path: 'tools/review-picker/data/x.json', content: '[1]', sha: 'old-sha', message: 'update picks',
    },
    fetchImpl,
  );
  assert.equal(capturedBody.sha, 'old-sha');
  assert.equal(capturedBody.branch, 'main');
  assert.equal(capturedBody.message, 'update picks');
  assert.equal(Buffer.from(capturedBody.content, 'base64').toString('utf-8'), '[1]');
  assert.equal(result.sha, 'new-sha');
});

test('putFile omits sha for a brand-new file', async () => {
  let capturedBody;
  const fetchImpl = fakeFetch([
    async (url, opts) => {
      capturedBody = JSON.parse(opts.body);
      return { ok: true, status: 201, json: async () => ({ content: { sha: 'first-sha' } }) };
    },
  ]);
  await putFile(
    { owner: 'o', repo: 'r', branch: 'main', token: 't', path: 'x.json', content: '[]', message: 'create' },
    fetchImpl,
  );
  assert.equal('sha' in capturedBody, false);
});

test('putFile throws on a 409 conflict', async () => {
  const fetchImpl = fakeFetch([async () => ({ ok: false, status: 409, json: async () => ({ message: 'conflict' }) })]);
  await assert.rejects(
    putFile({ owner: 'o', repo: 'r', branch: 'main', token: 't', path: 'x.json', content: '[]', sha: 's', message: 'm' }, fetchImpl),
    /409/,
  );
});

const { saveWithRetry } = require('../../tools/review-picker/api/_github.js');

function jsonResponse(status, jsonBody) {
  return { ok: status >= 200 && status < 300, status, json: async () => jsonBody };
}

function fileResponse(picksArray, sha) {
  return jsonResponse(200, {
    content: Buffer.from(JSON.stringify(picksArray), 'utf-8').toString('base64'),
    sha,
  });
}

test('saveWithRetry succeeds on the first try', async () => {
  const calls = [];
  const fetchImpl = async (url, opts) => {
    calls.push(opts ? opts.method || 'GET' : 'GET');
    if (calls.length === 1) return fileResponse([{ handle: 'a', choice: 'skip' }], 'sha-1');
    return jsonResponse(200, { content: { sha: 'sha-2' } });
  };
  const result = await saveWithRetry(
    {
      owner: 'o', repo: 'r', branch: 'main', token: 't',
      path: 'tools/review-picker/data/batch.json',
      pick: { handle: 'b', choice: 'skip' },
      message: 'pick b',
    },
    fetchImpl,
  );
  assert.deepEqual(result.picks, [
    { handle: 'a', choice: 'skip' },
    { handle: 'b', choice: 'skip' },
  ]);
  assert.equal(result.sha, 'sha-2');
  assert.deepEqual(calls, ['GET', 'PUT']);
});

test('saveWithRetry retries once on a 409 then succeeds', async () => {
  const calls = [];
  const fetchImpl = async (url, opts) => {
    const method = opts ? opts.method || 'GET' : 'GET';
    calls.push(method);
    if (method === 'GET') return fileResponse([{ handle: 'a', choice: 'skip' }], `sha-${calls.length}`);
    if (calls.filter((m) => m === 'PUT').length === 1) return jsonResponse(409, { message: 'conflict' });
    return jsonResponse(200, { content: { sha: 'final-sha' } });
  };
  const result = await saveWithRetry(
    { owner: 'o', repo: 'r', branch: 'main', token: 't', path: 'x.json', pick: { handle: 'b', choice: 'skip' }, message: 'm' },
    fetchImpl,
  );
  assert.equal(result.sha, 'final-sha');
  assert.deepEqual(calls, ['GET', 'PUT', 'GET', 'PUT']);
});

test('saveWithRetry throws if the retry also conflicts', async () => {
  const fetchImpl = async (url, opts) => {
    const method = opts ? opts.method || 'GET' : 'GET';
    if (method === 'GET') return fileResponse([], 'sha-x');
    return jsonResponse(409, { message: 'conflict' });
  };
  await assert.rejects(
    saveWithRetry({ owner: 'o', repo: 'r', branch: 'main', token: 't', path: 'x.json', pick: { handle: 'b', choice: 'skip' }, message: 'm' }, fetchImpl),
    /409/,
  );
});

test('saveWithRetry throws if the batch file does not exist', async () => {
  const fetchImpl = async () => jsonResponse(404, {});
  await assert.rejects(
    saveWithRetry({ owner: 'o', repo: 'r', branch: 'main', token: 't', path: 'x.json', pick: { handle: 'b', choice: 'skip' }, message: 'm' }, fetchImpl),
    /does not exist/,
  );
});
