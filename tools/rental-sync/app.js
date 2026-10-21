// The rental sync page: five steps, state kept in memory for the session.
// Libib text only ever goes into the page as text nodes (see el()).
(function () {
  'use strict';
  const L = window.RentalSyncLogic;
  const $ = (id) => document.getElementById(id);
  const state = { store: '', vocabulary: { formats: [], genres: [] }, found: [], selected: new Set(),
    candidates: [], setAside: [], choices: new Map(), plan: { create: [], add: [], setAside: [] }, groups: [], adds: [],
    setAsideCount: 0, posterCopies: [], posters: new Map(), results: [], creating: false };

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

  // replaceChildren() would turn null/false children into the text "null"/"false"
  function fill(container, ...children) {
    container.replaceChildren(...children.filter((child) => child != null && child !== false));
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

  function detailsBlock(detail) {
    return detail ? el('details', {}, el('summary', {}, 'Show details'), el('pre', { class: 'small' }, detail)) : null;
  }

  function showError(container, error) {
    fill(container, el('p', { class: 'error' }, error.message), detailsBlock(error.detail));
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
      state.choices = new Map();
      posterBuild = null;
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
  const field = (label, value) => [el('dt', {}, label), el('dd', {}, value || '—')];
  const genreNames = (copy) => copy.genres.map((g) => g.name).join(', ');
  const adminLink = (url, text) => (L.isHttpsUrl(url) ? el('a', { href: url, target: '_blank', rel: 'noopener' }, text) : text);
  function copyCard(copy, isAside) {
    return el('article', { class: isAside ? 'card aside' : 'card' },
      el('h3', {}, copy.title || '(no title)', ' ', el('span', { class: 'mono muted' }, copy.barcode)),
      isAside ? el('ul', { class: 'reasons' }, copy.set_aside.map((r) => el('li', {}, r))) : null,
      isAside && copy.products && copy.products.length
        ? el('ul', {}, copy.products.map((url, i) => el('li', {}, adminLink(url, `Shopify product ${i + 1}`)))) : null,
      el('dl', {},
        field('Format', copy.format),
        field('Genre', genreNames(copy)),
        field('Extra tags', copy.extra_tags.join(', ')),
        field('Description', copy.description)),
      copy.warnings.length ? el('ul', { class: 'warnings' }, copy.warnings.map((w) => el('li', {}, w))) : null);
  }

  // dupe cards keyed by Libib item, match cards by barcode: key -> update(choice, setAsideReason)
  const choiceCards = new Map();
  function choose(key, choice) {
    if (choice) state.choices.set(key, choice); else state.choices.delete(key);
    updateChoices();
  }
  function choiceButton(label, onclick) {
    return el('button', { type: 'button', class: 'secondary choice', 'aria-pressed': 'false', onclick }, label);
  }
  function side(heading, ...children) {
    return el('div', { class: 'side' }, el('h4', {}, heading), ...children);
  }
  function dupeCard(copy) {
    const other = copy.libib_duplicate;
    const copies = state.candidates.filter((c) => c.item_id === copy.item_id);
    const status = el('p', { class: 'note', 'aria-live': 'polite' });
    const button = choiceButton('Not a duplicate',
      () => choose(copy.item_id, state.choices.get(copy.item_id) === 'not_duplicate' ? null : 'not_duplicate'));
    const card = el('article', { class: 'card choice-card' },
      el('div', { class: 'sides' },
        side('New in Libib', el('dl', {}, field('Title', copy.title),
          field(copies.length > 1 ? 'Barcodes' : 'Barcode', copies.map((c) => c.barcode).join(', ')),
          field('Format', copy.format), field('Genre', genreNames(copy)), field('Copies', String(copies.length)),
          field('Added', L.shortDate(copy.created)))),
        side('Already in Libib', el('dl', {}, field('Title', other.title), field('Format', other.format),
          field('Genre', other.genres.join(', ')), field('Copies', String(other.copies)),
          field('Added', L.shortDate(other.created))))),
      status, el('div', { class: 'choices' }, button));
    choiceCards.set(copy.item_id, (choice, reason) => {
      const dismissed = choice === 'not_duplicate';
      button.setAttribute('aria-pressed', String(dismissed));
      card.classList.toggle('aside', !dismissed);
      status.textContent = dismissed ? 'Not a duplicate — it will become its own product.' : reason;
    });
    return card;
  }
  function matchCard(copy) {
    const product = copy.match;
    const status = el('p', { class: 'note', 'aria-live': 'polite' });
    const add = choiceButton('Add as a copy', () => choose(copy.barcode, 'add'));
    const skip = choiceButton('Skip this run', () => choose(copy.barcode, 'skip'));
    const poster = L.isHttpsUrl(product.image)
      ? el('img', { src: product.image, alt: `Poster for ${product.title}` })
      : el('div', { class: 'poster-empty' }, 'No poster');
    const card = el('article', { class: 'card choice-card' },
      el('div', { class: 'sides' },
        side('New copy in Libib', el('dl', {}, field('Title', copy.title), field('Barcode', copy.barcode),
          field('Format', copy.format), field('Genre', genreNames(copy)), field('Added', L.shortDate(copy.created)))),
        side('Product in Shopify', el('div', { class: 'match-product' }, el('div', { class: 'poster' }, poster),
          el('div', {}, el('dl', {}, field('Title', product.title), field('Format', product.vendor),
            field('Copies', String(product.copies))),
          el('p', { class: 'small' }, adminLink(product.admin_url, 'Open it in Shopify admin')))))),
      status, el('div', { class: 'choices' }, add, skip));
    choiceCards.set(copy.barcode, (choice, reason) => {
      add.setAttribute('aria-pressed', String(choice === 'add'));
      skip.setAttribute('aria-pressed', String(choice === 'skip'));
      card.classList.toggle('aside', choice === 'skip');
      status.textContent = choice === 'add' ? `This copy will be added to “${product.title}” in Shopify.`
        : choice === 'skip' ? reason : 'Choose one to continue.';
    });
    return card;
  }
  function renderDetails() {
    const chosen = state.found.filter((c) => state.selected.has(c.barcode));
    state.candidates = chosen.filter((c) => !c.set_aside.length);
    state.setAside = chosen.filter((c) => c.set_aside.length);
    const { dupes, matches } = L.choiceState(state.candidates, state.choices);
    choiceCards.clear();
    $('dupes').hidden = !dupes.length;
    $('dupe-cards').replaceChildren(...dupes.map(dupeCard));
    $('matches').hidden = !matches.length;
    $('match-cards').replaceChildren(...matches.map(matchCard));
    $('set-aside').hidden = !state.setAside.length;
    $('vocab-formats').textContent = state.vocabulary.formats.join(', ');
    $('vocab-genres').textContent = state.vocabulary.genres.join(', ');
    $('set-aside-cards').replaceChildren(...state.setAside.map((c) => copyCard(c, true)));
    const plain = state.candidates.filter((c) => !c.libib_duplicate && !c.match);
    $('ready-cards').replaceChildren(...plain.map((c) => copyCard(c, false)));
    updateChoices();
  }
  function updateChoices() {
    const { blocked } = L.choiceState(state.candidates, state.choices);
    state.plan = L.applyChoices(state.candidates, state.choices);
    const reasons = new Map(state.plan.setAside.map((c) => [c.match ? c.barcode : c.item_id, c.set_aside[c.set_aside.length - 1]]));
    choiceCards.forEach((update, key) => update(state.choices.get(key), reasons.get(key)));
    const n = state.plan.create.length + state.plan.add.length;
    $('ready-heading').textContent = n ? `${n} ready to sync` : 'Nothing ready to sync';
    $('details-continue').disabled = blocked || !n;
    $('details-hint').textContent = blocked ? 'Answer every “Already in Shopify?” card to continue.' : '';
  }
  $('details-back').addEventListener('click', () => showStep(2));
  $('details-continue').addEventListener('click', () => {
    state.groups = L.groupForCreate(state.plan.create);
    state.adds = state.plan.add;
    state.setAsideCount = state.setAside.length + state.plan.setAside.length;
    if (!state.groups.length) { startCreate(); return; }
    const key = state.plan.create.map((c) => c.barcode).join('\n');
    if (posterBuild && posterBuild.key === key && posterBuild.done) {
      $('posters-continue').textContent = createLabel();
      showStep(4);
      return;
    }
    buildPosterCards();
    posterBuild = { key, done: false };
    showStep(4);
    startPosters(posterBuild);
  });

  // --- step 4: posters (one per new product, keyed by its group's lowest barcode) ---
  const posterCards = new Map();
  const editedPosters = new Set(); // barcodes the user pasted into or accepted: lookups must not overwrite them
  let posterRun = 0;
  let posterBuild = null; // { key, done } for the poster cards currently built
  const keyCopy = (group) => group.copies.find((c) => c.barcode === L.groupKey(group));
  function createLabel() {
    const p = state.groups.length;
    const a = state.adds.length;
    const adds = a ? ` and add ${a} ${a === 1 ? 'copy' : 'copies'}` : '';
    return `Create ${p} ${p === 1 ? 'product' : 'products'}${adds} in Shopify`;
  }
  function buildPosterCards() {
    posterCards.clear();
    editedPosters.clear();
    state.posterCopies = state.groups.map(keyCopy);
    state.posters = new Map(state.posterCopies.map((c) => [c.barcode, { url: '', alt: '', original: { url: '', alt: '' },
      suggestion: null, note: 'Looking up…' }]));
    $('poster-cards').replaceChildren(...state.groups.map((group) => {
      const copy = keyCopy(group);
      const count = group.copies.length > 1 ? ` · ${group.copies.length} copies` : '';
      const note = el('p', { class: 'note' });
      const img = el('img', { alt: `Poster for ${copy.title}`, hidden: true });
      const empty = el('div', { class: 'poster-empty' }, 'No poster');
      img.addEventListener('error', () => {
        if (img.getAttribute('src')) { note.textContent = "That link didn't load as an image — check it."; note.classList.add('error'); }
      });
      const useIt = el('button', { type: 'button', class: 'secondary', hidden: true, onclick: () => {
        editedPosters.add(copy.barcode);
        state.posters.set(copy.barcode, L.acceptSuggestion(state.posters.get(copy.barcode)));
        updatePosterCard(copy.barcode);
      } }, 'Use it');
      const input = el('input', { type: 'url', placeholder: 'Paste image URL (https://…)',
        'aria-label': `Poster link for ${copy.title}` });
      input.addEventListener('input', () => {
        if (input.value.trim()) editedPosters.add(copy.barcode); else editedPosters.delete(copy.barcode);
        state.posters.set(copy.barcode, L.pastedPoster(state.posters.get(copy.barcode), input.value));
        updatePosterCard(copy.barcode);
      });
      posterCards.set(copy.barcode, { img, empty, note, useIt });
      return el('article', { class: 'card poster-card' },
        el('div', { class: 'poster' }, img, empty),
        el('div', {}, el('h3', {}, copy.title),
          el('p', { class: 'muted small' }, `${copy.format} · ${genreNames(copy)}${count}`),
          note, useIt, input));
    }));
    state.posterCopies.forEach((c) => updatePosterCard(c.barcode));
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
  async function startPosters(build) {
    const run = ++posterRun;
    const button = $('posters-continue');
    button.disabled = true;
    button.textContent = 'Looking up posters…';
    for (const batch of L.batches(state.posterCopies)) {
      let results = null;
      try {
        results = (await api('posters', { copies: batch })).posters;
      } catch (_) { /* leave null: every copy in the batch gets the error note */ }
      if (run !== posterRun) return;
      const byBarcode = new Map((results || []).map((r) => [r.barcode, r]));
      batch.forEach((c) => {
        if (!state.posters.has(c.barcode)) return;
        const fresh = L.initialPoster(byBarcode.get(c.barcode) || { kind: 'error' });
        const current = state.posters.get(c.barcode);
        // keep what the user pasted; only refresh what clearing the box falls back to
        state.posters.set(c.barcode, editedPosters.has(c.barcode)
          ? { ...current, original: fresh.original, suggestion: fresh.suggestion } : fresh);
      });
      batch.forEach((c) => { if (posterCards.has(c.barcode)) updatePosterCard(c.barcode); });
    }
    build.done = true;
    button.disabled = false;
    button.textContent = createLabel();
  }
  $('posters-back').addEventListener('click', () => showStep(3));
  $('posters-continue').addEventListener('click', startCreate);

  // --- step 5: create products, then add copies --------------------------------
  function setProgress(done, total) {
    $('progress-bar').style.width = `${total ? Math.round((done / total) * 100) : 100}%`;
    $('progress-text').textContent = `${done} of ${total} done`;
  }
  function createJobs() {
    const creates = state.groups.map((group) => {
      const copy = keyCopy(group);
      const n = group.copies.length;
      return { key: copy.barcode, title: copy.title, barcodes: group.copies.map((c) => c.barcode).sort(), adminUrl: '',
        row: n > 1 ? `${copy.title} (${n} copies)` : copy.title,
        send: () => api('create', L.createPayload(group, state.posters.get(copy.barcode))) };
    });
    const adds = state.adds.map((copy) => ({ key: copy.barcode, title: copy.title, barcodes: [copy.barcode],
      adminUrl: copy.match.admin_url, row: `${copy.title} — add as a copy`,
      send: () => api('add_copy', L.addCopyPayload(copy)) }));
    return [...creates, ...adds];
  }
  async function startCreate() {
    if (state.creating) return;
    state.creating = true;
    $('posters-continue').disabled = true;
    showStep(5);
    state.results = [];
    const jobs = createJobs();
    const marks = new Map();
    $('create-rows').replaceChildren(...jobs.map((job) => {
      const mark = el('span', { class: 'status' }, '…');
      marks.set(job.key, mark);
      return el('li', {}, mark, ' ', job.row);
    }));
    const failedRow = (job, message, detail = '') => ({ status: 'failed', barcode: job.key, barcodes: job.barcodes,
      title: job.title, admin_url: job.adminUrl, poster: 'none', message, detail, problems: [], print: [] });
    const markRow = (job, result) => {
      const mark = marks.get(job.key);
      mark.textContent = result.status === 'failed' ? '✗' : '✓';
      mark.className = `status ${result.status}`;
    };
    let setupError = null;
    for (const [i, job] of jobs.entries()) {
      setProgress(i, jobs.length);
      let result;
      try {
        result = await job.send();
      } catch (error) {
        result = failedRow(job, `${error.message} Run the sync again to check it.`, error.detail);
        if (error.kind === 'setup') {
          setupError = error;
          result = failedRow(job, error.message, error.detail);
        }
      }
      state.results.push(result);
      markRow(job, result);
      if (setupError) {
        // a setup problem will fail every remaining copy the same way: stop and say so
        for (const rest of jobs.slice(i + 1)) {
          const skipped = failedRow(rest, 'Not attempted — the app setup needs fixing first.');
          state.results.push(skipped);
          markRow(rest, skipped);
        }
        break;
      }
    }
    setProgress(jobs.length, jobs.length);
    if (setupError) {
      state.creating = false;
      renderResults(L.summarize(state.results), null, setupError);
      return;
    }
    const summary = L.summarize(state.results);
    let finishError = null;
    try {
      await api('finish', L.finishPayload(summary, state.setAsideCount));
    } catch (error) {
      finishError = error;
    }
    state.creating = false;
    renderResults(summary, finishError);
  }
  function renderResults(summary, finishError, setupError) {
    const setupBox = setupError ? el('div', { class: 'setup-error' }) : null;
    if (setupError) showError(setupBox, setupError);
    const link = (r) => (r.admin_url ? el('a', { href: r.admin_url, target: '_blank', rel: 'noopener' }, r.title) : r.title);
    const copies = (r) => (r.barcodes && r.barcodes.length > 1 ? ` (${r.barcodes.length} copies)` : '');
    const group = (title, items, render) => (items.length
      ? el('section', { class: 'result-group' }, el('h3', {}, `${title} (${items.length})`), el('ul', {}, items.map(render)))
      : null);
    fill($('results'),
      setupBox,
      el('p', { class: 'last-run' }, `${summary.created.length} created, ${summary.added.length} added as a copy, `
        + `${summary.skipped.length} already in Shopify, ${summary.failed.length} failed.`),
      group('Failed', summary.failed, (r) => el('li', {}, link(r), ' ', el('span', { class: 'mono muted' }, r.barcode),
        el('p', { class: 'error small' }, r.message), detailsBlock(r.detail))),
      summary.failed.length ? el('p', {}, "Fix the issue and run the sync again — products and copies already in Shopify won't be duplicated.") : null,
      group("Created, but the poster didn't load — add it in Shopify admin", summary.posterFailed, (r) => el('li', {}, link(r))),
      group('Created', summary.created, (r) => el('li', {}, link(r), copies(r))),
      group('Added as a copy', summary.added, (r) => el('li', {}, link(r), ' ', el('span', { class: 'mono muted' }, r.barcode))),
      group('Already in Shopify — skipped', summary.skipped, (r) => el('li', {}, r.title, ' ', el('span', { class: 'muted small' }, r.message))),
      finishError ? el('p', { class: 'error small' }, `The products are done, but the "last sync" time wasn't saved: ${finishError.message}`) : null);
    $('print-link').href = L.printBarcodesUrl(state.store);
    const toPrint = L.barcodesToPrint(state.results);
    $('print-barcodes').replaceChildren(...toPrint.map((b) => el('li', {}, b)));
    $('print-block').hidden = !toPrint.length;
    $('restart').hidden = false;
  }
  $('restart').addEventListener('click', () => window.location.reload());
  window.addEventListener('beforeunload', (event) => {
    if (state.creating) { event.preventDefault(); event.returnValue = ''; }
  });

  showStep(1);
  loadStatus();
})();
