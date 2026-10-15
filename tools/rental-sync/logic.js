// Pure helpers for the rental sync page. Loaded as a plain <script> in the
// browser (window.RentalSyncLogic) and with require() in the node tests.
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.RentalSyncLogic = api;
})(typeof self !== 'undefined' ? self : this, function () {
  const MAX_FILE_BYTES = 5 * 1024 * 1024;
  const POSTER_BATCH_SIZE = 5;
  const PRINT_TAG = 'Barcode Not Printed';

  async function gzipBase64(text) {
    const stream = new Blob([text]).stream().pipeThrough(new CompressionStream('gzip'));
    const bytes = new Uint8Array(await new Response(stream).arrayBuffer());
    let binary = '';
    for (let i = 0; i < bytes.length; i += 0x8000) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    }
    return btoa(binary);
  }

  function fileProblem(file, label) {
    if (!file) return `Choose the ${label} file.`;
    if (file.size > MAX_FILE_BYTES) return `The ${label} is over 5 MB — is it the right Libib export?`;
    return '';
  }

  function batches(list, size = POSTER_BATCH_SIZE) {
    const out = [];
    for (let i = 0; i < list.length; i += size) out.push(list.slice(i, i + size));
    return out;
  }

  function byCreatedThenTitle(a, b) {
    const created = (a.created || '').localeCompare(b.created || '');
    return created || (a.title || '').toLowerCase().localeCompare((b.title || '').toLowerCase());
  }

  function shortDate(text) {
    return text ? String(text).slice(0, 10) : '—';
  }

  function isHttpsUrl(text) {
    try {
      return new URL(String(text).trim()).protocol === 'https:';
    } catch (_) {
      return false;
    }
  }

  function initialPoster(result) {
    const base = { url: '', alt: '', original: { url: '', alt: '' }, suggestion: null, note: '' };
    if (result.kind === 'confident') {
      return { ...base, url: result.url, alt: result.alt, original: { url: result.url, alt: result.alt } };
    }
    if (result.kind === 'unsure') {
      const c = result.candidate || {};
      return { ...base, suggestion: { url: result.url, alt: result.alt, title: c.title || '', year: c.year || '' } };
    }
    if (result.kind === 'error') return { ...base, note: 'Poster lookup failed — paste a link or leave it blank' };
    return { ...base, note: 'No poster found' };
  }

  function acceptSuggestion(poster) {
    const s = poster.suggestion;
    return { ...poster, url: s.url, alt: s.alt, original: { url: s.url, alt: s.alt }, note: '' };
  }

  function pastedPoster(poster, text) {
    const url = String(text || '').trim();
    if (!url) return { ...poster, url: poster.original.url, alt: poster.original.alt, note: '' };
    return { ...poster, url, alt: '', note: isHttpsUrl(url) ? '' : 'Links must start with https://' };
  }

  function createPayload(copy, poster) {
    const usable = poster && isHttpsUrl(poster.url);
    return { item: copy.libib, poster: usable ? { url: poster.url.trim(), alt: poster.alt || '' } : null };
  }

  function summarize(results) {
    const out = { created: [], skipped: [], failed: [], posterFailed: [] };
    for (const r of results) {
      if (r.status === 'created') {
        out.created.push(r);
        if (r.poster === 'failed') out.posterFailed.push(r);
      } else if (r.status === 'skipped_exists') {
        out.skipped.push(r);
      } else {
        out.failed.push(r);
      }
    }
    return out;
  }

  function finishPayload(summary, setAsideCount) {
    return { created: summary.created.length, skipped: summary.skipped.length,
      failed: summary.failed.length, set_aside: setAsideCount };
  }

  function printBarcodesUrl(store) {
    const slug = String(store || '').split('.')[0];
    return `https://admin.shopify.com/store/${encodeURIComponent(slug)}/products?tag=${encodeURIComponent(PRINT_TAG)}`;
  }

  function describeLastRun(lastRun) {
    if (!lastRun) return 'No sync yet.';
    const when = new Date(lastRun.finished_at).toLocaleString('en-US', {
      dateStyle: 'medium', timeStyle: 'short', timeZone: 'America/New_York' });
    return `Last successful sync: ${when} — ${lastRun.created} created`;
  }

  // fetch wrapper: JSON in/out; a 401 waits for requireLogin() and then
  // re-sends the exact same request, so an expired session loses nothing.
  function makeApi({ fetch, requireLogin }) {
    return async function api(path, body) {
      const options = body === undefined
        ? { method: 'GET', credentials: 'same-origin' }
        : { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
      let res;
      try {
        res = await fetch(`/api/rental_sync/${path}`, options);
      } catch (_) {
        throw new Error("Couldn't reach the sync app — check the internet connection and try again.");
      }
      let data = {};
      try { data = await res.json(); } catch (_) { /* not JSON: use the status below */ }
      if (res.status === 401 && path !== 'login') {
        await requireLogin();
        return api(path, body);
      }
      if (!res.ok) {
        const error = new Error((data.error && data.error.message) || `Something went wrong (${res.status}).`);
        error.detail = (data.error && data.error.detail) || '';
        throw error;
      }
      return data;
    };
  }

  return { MAX_FILE_BYTES, POSTER_BATCH_SIZE, gzipBase64, fileProblem, batches, byCreatedThenTitle, shortDate,
    isHttpsUrl, initialPoster, acceptSuggestion, pastedPoster, createPayload, summarize, finishPayload,
    printBarcodesUrl, describeLastRun, makeApi };
});
