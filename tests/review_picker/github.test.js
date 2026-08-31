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
