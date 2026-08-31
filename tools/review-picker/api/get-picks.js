const { isValidBatchId, getFile } = require('./_github.js');

async function handler(req, res) {
  if (req.method !== 'GET') {
    res.status(405).json({ error: 'method not allowed' });
    return;
  }

  const batch = req.query ? req.query.batch : undefined;
  if (!isValidBatchId(batch)) {
    res.status(400).json({ error: 'invalid or missing batch' });
    return;
  }

  const { GITHUB_TOKEN, GITHUB_OWNER = 'paris-liam', GITHUB_REPO = 'LMS', GITHUB_BRANCH = 'main' } = process.env;
  if (!GITHUB_TOKEN) {
    res.status(500).json({ error: 'server not configured (missing GITHUB_TOKEN)' });
    return;
  }
  const path = `tools/review-picker/data/${batch}.json`;

  try {
    const file = await getFile({ owner: GITHUB_OWNER, repo: GITHUB_REPO, branch: GITHUB_BRANCH, token: GITHUB_TOKEN, path });
    if (file === null) {
      res.status(404).json({ error: `unknown batch: ${batch}` });
      return;
    }
    res.status(200).json(JSON.parse(file.content));
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
}

module.exports = handler;
