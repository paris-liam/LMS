// The rental sync page: five steps, state kept in memory for the session.
// Libib text only ever goes into the page as text nodes (see el()).
(function () {
  'use strict';
  const L = window.RentalSyncLogic;
  const $ = (id) => document.getElementById(id);
  const state = { store: '', vocabulary: { formats: [], genres: [] }, found: [], selected: new Set(),
    ready: [], setAside: [], posters: new Map(), results: [], creating: false };

  function el(tag, props, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props || {})) {
      if (key === 'class') node.className = value;
      else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
      else if (value === true) node.setAttribute(key, '');
      else if (value !== false && value != null) node.setAttribute(key, value);
    }
    for (const child of children.flat()) {
      if (child != null && child !== false) node.append(child instanceof Node ? child : String(child));
    }
    return node;
  }

  // --- login + api ------------------------------------------------------
  let loginWaiters = [];
  function requireLogin() {
    $('login').hidden = false;
    $('password').focus();
    return new Promise((resolve) => loginWaiters.push(resolve));
  }
  $('login-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    $('login-error').textContent = '';
    let res;
    try {
      res = await fetch('/api/rental_sync/login', { method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password: $('password').value }) });
    } catch (_) {
      $('login-error').textContent = "Couldn't reach the sync app — check the internet connection.";
      return;
    }
    if (!res.ok) { $('login-error').textContent = "That password isn't right."; return; }
    $('password').value = '';
    $('login').hidden = true;
    const waiters = loginWaiters;
    loginWaiters = [];
    waiters.forEach((resolve) => resolve());
  });
  const api = L.makeApi({ fetch: (url, options) => fetch(url, options), requireLogin });

  function showError(container, error) {
    container.replaceChildren(
      el('p', { class: 'error' }, error.message),
      error.detail ? el('details', {}, el('summary', {}, 'Show details'), el('pre', { class: 'small' }, error.detail)) : null);
  }

  function showStep(n) {
    document.querySelectorAll('[data-step]').forEach((s) => { s.hidden = Number(s.dataset.step) !== n; });
    document.querySelectorAll('#steps li').forEach((li, i) => {
      li.classList.toggle('current', i + 1 === n);
      li.classList.toggle('done', i + 1 < n);
    });
    window.scrollTo(0, 0);
  }

  // --- step 1: upload -----------------------------------------------------
  async function loadStatus() {
    try {
      const data = await api('status');
      state.store = data.store;
      $('store-name').textContent = data.store;
      $('last-run').textContent = L.describeLastRun(data.last_run);
    } catch (error) {
      showError($('last-run'), error);
    }
  }

  $('upload-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const out = $('upload-error');
    const button = $('find-button');
    out.replaceChildren();
    const barcodes = $('barcodes-file').files[0];
    const library = $('library-file').files[0];
    const problem = L.fileProblem(barcodes, 'Barcodes export') || L.fileProblem(library, 'Library export');
    if (problem) { out.replaceChildren(el('p', { class: 'error' }, problem)); return; }
    button.disabled = true;
    button.textContent = 'Looking…';
    try {
      const data = await api('prepare', {
        barcodes: await L.gzipBase64(await barcodes.text()),
        library: await L.gzipBase64(await library.text()),
      });
      state.vocabulary = data.vocabulary;
      state.found = [...data.ready, ...data.set_aside].sort(L.byCreatedThenTitle);
      state.selected = new Set(state.found.map((c) => c.barcode));
      renderFound();
      showStep(2);
    } catch (error) {
      showError(out, error);
    } finally {
      button.disabled = false;
      button.textContent = 'Find new rentals';
    }
  });

  // --- step 2: new copies ----------------------------------------------------
  function renderFound() {
    const n = state.found.length;
    $('found-summary').textContent = n
      ? `${n} new ${n === 1 ? 'copy' : 'copies'} in Libib that ${n === 1 ? "isn't" : "aren't"} in Shopify yet.`
      : "Everything in Libib's Rental Library is already in Shopify.";
    $('found-table').hidden = !n;
    $('found-rows').replaceChildren(...state.found.map((copy) => {
      const box = el('input', { type: 'checkbox', checked: true, 'aria-label': `Include ${copy.title || copy.barcode}`,
        onchange: (e) => {
          if (e.target.checked) state.selected.add(copy.barcode); else state.selected.delete(copy.barcode);
          updateFoundButton();
        } });
      return el('tr', {}, el('td', {}, box), el('td', {}, copy.title || '(no title)'),
        el('td', { class: 'mono' }, copy.barcode), el('td', {}, L.shortDate(copy.created)));
    }));
    updateFoundButton();
  }
  function updateFoundButton() {
    const n = state.selected.size;
    $('found-continue').disabled = n === 0;
    $('found-continue').textContent = `Continue with ${n}`;
  }
  $('found-back').addEventListener('click', () => showStep(1));
  $('found-continue').addEventListener('click', () => { renderDetails(); showStep(3); });

  // --- step 3: details --------------------------------------------------------
  function copyCard(copy, isAside) {
    const field = (label, value) => [el('dt', {}, label), el('dd', {}, value || '—')];
    return el('article', { class: isAside ? 'card aside' : 'card' },
      el('h3', {}, copy.title || '(no title)', ' ', el('span', { class: 'mono muted' }, copy.barcode)),
      isAside ? el('ul', { class: 'reasons' }, copy.set_aside.map((r) => el('li', {}, r))) : null,
      el('dl', {},
        field('Format', copy.format),
        field('Genre', copy.genres.map((g) => g.name).join(', ')),
        field('Extra tags', copy.extra_tags.join(', ')),
        field('Description', copy.description)),
      copy.warnings.length ? el('ul', { class: 'warnings' }, copy.warnings.map((w) => el('li', {}, w))) : null);
  }
  function renderDetails() {
    const chosen = state.found.filter((c) => state.selected.has(c.barcode));
    state.ready = chosen.filter((c) => !c.set_aside.length);
    state.setAside = chosen.filter((c) => c.set_aside.length);
    $('set-aside').hidden = !state.setAside.length;
    $('vocab-formats').textContent = state.vocabulary.formats.join(', ');
    $('vocab-genres').textContent = state.vocabulary.genres.join(', ');
    $('set-aside-cards').replaceChildren(...state.setAside.map((c) => copyCard(c, true)));
    $('ready-heading').textContent = state.ready.length ? `${state.ready.length} ready to sync` : 'Nothing ready to sync';
    $('ready-cards').replaceChildren(...state.ready.map((c) => copyCard(c, false)));
    $('details-continue').disabled = !state.ready.length;
  }
  $('details-back').addEventListener('click', () => showStep(2));
  $('details-continue').addEventListener('click', () => { buildPosterCards(); showStep(4); startPosters(); });

  // --- step 4: posters --------------------------------------------------------
  const posterCards = new Map();
  function buildPosterCards() {
    posterCards.clear();
    state.posters = new Map(state.ready.map((c) => [c.barcode, { url: '', alt: '', original: { url: '', alt: '' },
      suggestion: null, note: 'Looking up…' }]));
    $('poster-cards').replaceChildren(...state.ready.map((copy) => {
      const note = el('p', { class: 'note' });
      const img = el('img', { alt: `Poster for ${copy.title}`, hidden: true });
      const empty = el('div', { class: 'poster-empty' }, 'No poster');
      img.addEventListener('error', () => {
        if (img.getAttribute('src')) { note.textContent = "That link didn't load as an image — check it."; note.classList.add('error'); }
      });
      const useIt = el('button', { type: 'button', class: 'secondary', hidden: true, onclick: () => {
        state.posters.set(copy.barcode, L.acceptSuggestion(state.posters.get(copy.barcode)));
        updatePosterCard(copy.barcode);
      } }, 'Use it');
      const input = el('input', { type: 'url', placeholder: 'Paste image URL (https://…)',
        'aria-label': `Poster link for ${copy.title}` });
      input.addEventListener('input', () => {
        state.posters.set(copy.barcode, L.pastedPoster(state.posters.get(copy.barcode), input.value));
        updatePosterCard(copy.barcode);
      });
      posterCards.set(copy.barcode, { img, empty, note, useIt });
      return el('article', { class: 'card poster-card' },
        el('div', { class: 'poster' }, img, empty),
        el('div', {}, el('h3', {}, copy.title),
          el('p', { class: 'muted small' }, `${copy.format} · ${copy.genres.map((g) => g.name).join(', ')}`),
          note, useIt, input));
    }));
    state.ready.forEach((c) => updatePosterCard(c.barcode));
  }
  function updatePosterCard(barcode) {
    const poster = state.posters.get(barcode);
    const card = posterCards.get(barcode);
    const unsure = !poster.url && poster.suggestion;
    const shown = poster.url || (unsure ? poster.suggestion.url : '');
    card.img.hidden = !shown;
    card.empty.hidden = Boolean(shown);
    if (shown && card.img.getAttribute('src') !== shown) card.img.setAttribute('src', shown);
    if (!shown) card.img.removeAttribute('src');
    card.img.classList.toggle('suggested', Boolean(unsure));
    card.note.classList.toggle('error', poster.note.startsWith('Links must'));
    card.note.textContent = unsure
      ? `Not sure — check this: is it “${poster.suggestion.title}” (${poster.suggestion.year || '?'})?`
      : poster.note;
    card.useIt.hidden = !unsure;
  }
  async function startPosters() {
    const button = $('posters-continue');
    button.disabled = true;
    button.textContent = 'Looking up posters…';
    for (const batch of L.batches(state.ready)) {
      try {
        const data = await api('posters', { copies: batch });
        data.posters.forEach((result) => state.posters.set(result.barcode, L.initialPoster(result)));
      } catch (_) {
        batch.forEach((c) => state.posters.set(c.barcode, L.initialPoster({ kind: 'error' })));
      }
      batch.forEach((c) => updatePosterCard(c.barcode));
    }
    button.disabled = false;
    button.textContent = `Create ${state.ready.length} ${state.ready.length === 1 ? 'product' : 'products'} in Shopify`;
  }
  $('posters-back').addEventListener('click', () => showStep(3));
  $('posters-continue').addEventListener('click', startCreate);

  // --- step 5: create -----------------------------------------------------
  function setProgress(done, total) {
    $('progress-bar').style.width = `${total ? Math.round((done / total) * 100) : 100}%`;
    $('progress-text').textContent = `${done} of ${total} done`;
  }
  async function startCreate() {
    if (state.creating) return;
    state.creating = true;
    $('posters-continue').disabled = true;
    showStep(5);
    state.results = [];
    const marks = new Map();
    $('create-rows').replaceChildren(...state.ready.map((copy) => {
      const mark = el('span', { class: 'status' }, '…');
      marks.set(copy.barcode, mark);
      return el('li', {}, mark, ' ', copy.title);
    }));
    for (const [i, copy] of state.ready.entries()) {
      setProgress(i, state.ready.length);
      let result;
      try {
        result = await api('create', L.createPayload(copy, state.posters.get(copy.barcode)));
      } catch (error) {
        result = { status: 'failed', barcode: copy.barcode, title: copy.title, admin_url: '', poster: 'none',
          message: `${error.message} If it was created anyway, the next sync will skip it.`, problems: [] };
      }
      state.results.push(result);
      const mark = marks.get(copy.barcode);
      mark.textContent = result.status === 'failed' ? '✗' : '✓';
      mark.className = `status ${result.status}`;
    }
    setProgress(state.ready.length, state.ready.length);
    const summary = L.summarize(state.results);
    let finishError = null;
    try {
      await api('finish', L.finishPayload(summary, state.setAside.length));
    } catch (error) {
      finishError = error;
    }
    state.creating = false;
    renderResults(summary, finishError);
  }
  function renderResults(summary, finishError) {
    const link = (r) => (r.admin_url ? el('a', { href: r.admin_url, target: '_blank', rel: 'noopener' }, r.title) : r.title);
    const group = (title, items, render) => (items.length
      ? el('section', { class: 'result-group' }, el('h3', {}, `${title} (${items.length})`), el('ul', {}, items.map(render)))
      : null);
    $('results').replaceChildren(
      el('p', { class: 'last-run' }, `${summary.created.length} created, ${summary.skipped.length} already in Shopify, ${summary.failed.length} failed.`),
      group('Failed', summary.failed, (r) => el('li', {}, link(r), ' ', el('span', { class: 'mono muted' }, r.barcode),
        el('p', { class: 'error small' }, r.message))),
      summary.failed.length ? el('p', {}, "Fix the issue and run the sync again — products already created won't be duplicated.") : null,
      group("Created, but the poster didn't load — add it in Shopify admin", summary.posterFailed, (r) => el('li', {}, link(r))),
      group('Created', summary.created, (r) => el('li', {}, link(r))),
      group('Already in Shopify — skipped', summary.skipped, (r) => el('li', {}, r.title, ' ', el('span', { class: 'muted small' }, r.message))),
      finishError ? el('p', { class: 'error small' }, `The products are done, but the "last sync" time wasn't saved: ${finishError.message}`) : null);
    $('print-link').href = L.printBarcodesUrl(state.store);
    $('print-block').hidden = !summary.created.length;
    $('restart').hidden = false;
  }
  $('restart').addEventListener('click', () => window.location.reload());
  window.addEventListener('beforeunload', (event) => {
    if (state.creating) { event.preventDefault(); event.returnValue = ''; }
  });

  showStep(1);
  loadStatus();
})();
