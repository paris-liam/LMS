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

function apiUrl(owner, repo, path) {
  return `https://api.github.com/repos/${owner}/${repo}/contents/${path}`;
}

function headers(token) {
  return {
    Authorization: `Bearer ${token}`,
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'Content-Type': 'application/json',
  };
}

async function getFile({ owner, repo, branch, token, path }, fetchImpl = fetch) {
  const url = `${apiUrl(owner, repo, path)}?ref=${encodeURIComponent(branch)}`;
  const response = await fetchImpl(url, { headers: headers(token) });
  if (response.status === 404) return null;
  if (!response.ok) {
    const body = await response.json();
    throw new Error(`GitHub getFile failed (${response.status}): ${body.message || 'unknown error'}`);
  }
  const body = await response.json();
  return {
    content: Buffer.from(body.content, 'base64').toString('utf-8'),
    sha: body.sha,
  };
}

async function putFile({ owner, repo, branch, token, path, content, sha, message }, fetchImpl = fetch) {
  const url = apiUrl(owner, repo, path);
  const requestBody = {
    message,
    content: Buffer.from(content, 'utf-8').toString('base64'),
    branch,
  };
  if (sha) requestBody.sha = sha;

  const response = await fetchImpl(url, {
    method: 'PUT',
    headers: headers(token),
    body: JSON.stringify(requestBody),
  });
  if (!response.ok) {
    const body = await response.json();
    throw new Error(`GitHub putFile failed (${response.status}): ${body.message || 'unknown error'}`);
  }
  const body = await response.json();
  return { sha: body.content.sha };
}

async function saveOnce({ owner, repo, branch, token, path, pick, message }, fetchImpl) {
  const file = await getFile({ owner, repo, branch, token, path }, fetchImpl);
  if (file === null) {
    throw new Error(`Batch file does not exist: ${path}`);
  }
  const picks = mergePick(JSON.parse(file.content), pick);
  const { sha } = await putFile(
    { owner, repo, branch, token, path, content: JSON.stringify(picks, null, 2), sha: file.sha, message },
    fetchImpl,
  );
  return { sha, picks };
}

async function saveWithRetry(args, fetchImpl = fetch) {
  try {
    return await saveOnce(args, fetchImpl);
  } catch (err) {
    if (!String(err.message).includes('409')) throw err;
    return await saveOnce(args, fetchImpl);
  }
}

module.exports = { isValidBatchId, mergePick, getFile, putFile, saveWithRetry };
module.exports.getFile = getFile;
module.exports.putFile = putFile;
module.exports.saveWithRetry = saveWithRetry;
