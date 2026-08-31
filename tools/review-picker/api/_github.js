const BATCH_ID_PATTERN = /^[a-z0-9][a-z0-9._-]*$/;

function isValidBatchId(batch) {
  return typeof batch === 'string' && batch.length > 0 && BATCH_ID_PATTERN.test(batch);
}

function mergePick(picks, pick) {
  const index = picks.findIndex((p) => p.handle === pick.handle);
  if (index === -1) {
    return [...picks, pick];
  }
  const copy = [...picks];
  copy[index] = pick;
  return copy;
}

module.exports = { isValidBatchId, mergePick };
