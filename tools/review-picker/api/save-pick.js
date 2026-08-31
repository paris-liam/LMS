const { isValidBatchId, saveWithRetry } = require('./_github.js');

const VALID_CHOICES = new Set(['tmdb', 'manual', 'skip']);

// This endpoint is deliberately unauthenticated (unlisted URL, no login), so cap
// field lengths to stop anyone with the URL bloating the committed data file.
const MAX_HANDLE_LENGTH = 200;
const MAX_OVERVIEW_LENGTH = 4000;
const MAX_IMAGE_SRC_LENGTH = 2000;

function validatePickPayload(body) {
  if (!body || typeof body !== 'object') return { valid: false, error: 'missing request body' };
  if (!isValidBatchId(body.batch)) return { valid: false, error: 'invalid or missing batch' };
  if (typeof body.handle !== 'string' || body.handle.length === 0) {
    return { valid: false, error: 'missing handle' };
  }
  if (body.handle.length > MAX_HANDLE_LENGTH) {
    return { valid: false, error: `handle too long (max ${MAX_HANDLE_LENGTH} characters)` };
  }
  if (!VALID_CHOICES.has(body.choice)) {
    return { valid: false, error: `invalid choice: ${body.choice}` };
  }
  if (typeof body.overview === 'string' && body.overview.length > MAX_OVERVIEW_LENGTH) {
    return { valid: false, error: `overview too long (max ${MAX_OVERVIEW_LENGTH} characters)` };
  }
  if (typeof body.image_src === 'string' && body.image_src.length > MAX_IMAGE_SRC_LENGTH) {
    return { valid: false, error: `image_src too long (max ${MAX_IMAGE_SRC_LENGTH} characters)` };
  }
  if (typeof body.poster_path === 'string' && body.poster_path.length > MAX_IMAGE_SRC_LENGTH) {
    return { valid: false, error: `poster_path too long (max ${MAX_IMAGE_SRC_LENGTH} characters)` };
  }
  return { valid: true };
}

function pickFromBody(body) {
  const pick = { handle: body.handle, choice: body.choice };
  if (body.choice === 'tmdb') {
    pick.poster_path = body.poster_path || '';
    pick.overview = body.overview || '';
  } else if (body.choice === 'manual') {
    pick.image_src = body.image_src || '';
    pick.overview = body.overview || '';
  }
  return pick;
}

async function handler(req, res) {
  if (req.method !== 'POST') {
    res.status(405).json({ ok: false, error: 'method not allowed' });
    return;
  }

  const validation = validatePickPayload(req.body);
  if (!validation.valid) {
    res.status(400).json({ ok: false, error: validation.error });
    return;
  }

  const { GITHUB_TOKEN, GITHUB_OWNER = 'paris-liam', GITHUB_REPO = 'LMS', GITHUB_BRANCH = 'main' } = process.env;
  if (!GITHUB_TOKEN) {
    res.status(500).json({ ok: false, error: 'server not configured (missing GITHUB_TOKEN)' });
    return;
  }
  const path = `tools/review-picker/data/${req.body.batch}.json`;

  try {
    await saveWithRetry({
      owner: GITHUB_OWNER,
      repo: GITHUB_REPO,
      branch: GITHUB_BRANCH,
      token: GITHUB_TOKEN,
      path,
      pick: pickFromBody(req.body),
      message: `review-picker: ${req.body.handle} -> ${req.body.choice}`,
    });
    res.status(200).json({ ok: true });
  } catch (err) {
    const status = String(err.message).includes('does not exist') ? 400 : 500;
    res.status(status).json({ ok: false, error: err.message });
  }
}

module.exports = handler;
module.exports.validatePickPayload = validatePickPayload;
module.exports.pickFromBody = pickFromBody;
module.exports.MAX_HANDLE_LENGTH = MAX_HANDLE_LENGTH;
module.exports.MAX_OVERVIEW_LENGTH = MAX_OVERVIEW_LENGTH;
module.exports.MAX_IMAGE_SRC_LENGTH = MAX_IMAGE_SRC_LENGTH;
