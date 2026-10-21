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

  function groupForCreate(copies) {
    const groups = new Map();
    for (const copy of copies) {
      if (!groups.has(copy.item_id)) groups.set(copy.item_id, { item_id: copy.item_id, copies: [] });
      groups.get(copy.item_id).copies.push(copy);
    }
    return [...groups.values()];
  }

  // the server sorts a group's barcodes and reports the lowest as the result's barcode
  function groupKey(group) {
    return group.copies.map((c) => c.barcode).sort()[0];
  }

  // duplicate choices are keyed by Libib item (one card per item), match choices by barcode
  function choiceState(copies, choices) {
    const flagged = copies.filter((c) => c.libib_duplicate);
    const dupes = flagged.filter((c, i) => flagged.findIndex((d) => d.item_id === c.item_id) === i);
    const matches = copies.filter((c) => c.match);
    return { dupes, matches, blocked: matches.some((c) => !['add', 'skip'].includes(choices.get(c.barcode))) };
  }

  function applyChoices(copies, choices) {
    const out = { create: [], add: [], setAside: [] };
    const aside = (copy, reason) => out.setAside.push({ ...copy, set_aside: [...copy.set_aside, reason] });
    for (const copy of copies) {
      if (copy.match) {
        if (choices.get(copy.barcode) === 'add') out.add.push(copy);
        else aside(copy, "If this copy isn't the same movie, move it to its own item in Libib.");
      } else if (copy.libib_duplicate && choices.get(copy.item_id) !== 'not_duplicate') {
        aside(copy, `In Libib, delete “${copy.title}” and add this copy to “${copy.libib_duplicate.title}” instead. `
          + 'It will show up next time you sync.');
      } else {
        out.create.push(copy);
      }
    }
    return out;
  }

  function createPayload(group, poster) {
    const usable = poster && isHttpsUrl(poster.url);
    // URL-normalised (lower-case scheme) because the server requires a literal "https://" prefix
    return { items: group.copies.map((c) => c.libib),
      poster: usable ? { url: new URL(poster.url.trim()).href, alt: poster.alt || '' } : null };
  }

  function addCopyPayload(copy) {
    return { item: copy.libib, product_id: copy.match.id };
  }

  function summarize(results) {
    const out = { created: [], added: [], skipped: [], failed: [], posterFailed: [] };
    for (const r of results) {
      if (r.status === 'created') {
        out.created.push(r);
        if (r.poster === 'failed') out.posterFailed.push(r);
      } else if (r.status === 'added') {
        out.added.push(r);
      } else if (r.status === 'skipped_exists') {
        out.skipped.push(r);
      } else {
        out.failed.push(r);
      }
    }
    return out;
  }

  function finishPayload(summary, setAsideCount) {
    return { created: summary.created.length, added: summary.added.length, skipped: summary.skipped.length,
      failed: summary.failed.length, set_aside: setAsideCount };
  }

  function barcodesToPrint(results) {
    return results.flatMap((r) => {
      if (r.status === 'created') return r.barcodes;
      return r.status === 'added' ? [r.barcode] : [];
    });
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
        const offline = new Error("Couldn't reach the sync app — check the internet connection and try again.");
        offline.kind = 'network';
        offline.detail = '';
        throw offline;
      }
      let data = {};
      try { data = await res.json(); } catch (_) { /* not JSON: use the status below */ }
      if (res.status === 401 && path !== 'login') {
        await requireLogin();
        return api(path, body);
      }
      if (!res.ok) {
        const error = new Error((data.error && data.error.message) || `Something went wrong (${res.status}).`);
        error.kind = (data.error && data.error.kind) || '';
        error.detail = (data.error && data.error.detail) || '';
        throw error;
      }
      return data;
    };
  }

  return { MAX_FILE_BYTES, POSTER_BATCH_SIZE, gzipBase64, fileProblem, batches, byCreatedThenTitle, shortDate,
    isHttpsUrl, initialPoster, acceptSuggestion, pastedPoster, groupForCreate, groupKey, choiceState, applyChoices,
    createPayload, addCopyPayload, summarize, finishPayload, barcodesToPrint, printBarcodesUrl, describeLastRun,
    makeApi };
});
