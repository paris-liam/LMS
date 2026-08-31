import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "formatting-scripts"))

from hosted_review_page import build_hosted_picker_html


def sample_product():
    return {
        "handle": "the-thing", "title": "The Thing", "vendor": "VHS", "genre": "horror",
        "reason": "ambiguous match", "candidates": [
            {"id": 1, "title": "The Thing", "year": "1982", "overview": "Overview.", "poster_path": "/p.jpg"},
        ],
    }


class TestBuildHostedPickerHtml(unittest.TestCase):
    def test_embeds_the_batch_id(self):
        html = build_hosted_picker_html([sample_product()], "out-product_export_3")
        self.assertIn('"out-product_export_3"', html)

    def test_embeds_product_json(self):
        html = build_hosted_picker_html([sample_product()], "batch")
        self.assertIn('"the-thing"', html)
        self.assertIn('"The Thing"', html)

    def test_has_no_export_button(self):
        html = build_hosted_picker_html([sample_product()], "batch")
        self.assertNotIn("Export picks", html)
        self.assertNotIn("tmdb-picks.json", html)

    def test_references_the_save_pick_endpoint(self):
        html = build_hosted_picker_html([sample_product()], "batch")
        self.assertIn("/api/save-pick", html)

    def test_references_the_get_picks_endpoint_with_batch_id(self):
        html = build_hosted_picker_html([sample_product()], "my-batch")
        self.assertIn("/api/get-picks?batch=my-batch", html)

    def test_escapes_closing_script_tags_in_overview_text(self):
        product = sample_product()
        product["candidates"][0]["overview"] = "a </script><script>alert(1)</script> b"
        html = build_hosted_picker_html([product], "batch")
        self.assertNotIn("</script><script>alert", html)

    def test_has_a_plain_language_header(self):
        html = build_hosted_picker_html([sample_product()], "batch")
        self.assertIn("save automatically", html.lower())


def slice_from(html, start_marker, end_marker):
    """The chunk of the generated script starting at start_marker, up to end_marker."""
    start = html.index(start_marker)
    return html[start:html.index(end_marker, start + len(start_marker))]


def cards_handler(html, event_name):
    """Body of the document.getElementById("cards") listener for one event."""
    marker = f'document.getElementById("cards").addEventListener("{event_name}"'
    return slice_from(html, marker, "\n});")


def save_pick_fn(html):
    return slice_from(html, "async function savePick(", "\n// Manual free-text saves")


class TestManualFieldDoesNotRerender(unittest.TestCase):
    """Finding 1: typing in a manual field must not destroy the DOM it lives in."""

    def setUp(self):
        self.html = build_hosted_picker_html([sample_product()], "batch")
        self.input_handler = cards_handler(self.html, "input")

    def test_the_input_handler_does_not_call_render(self):
        self.assertNotIn("render()", self.input_handler)

    def test_save_state_is_updated_in_place_not_by_rerendering(self):
        self.assertIn("function setSaveState(handle, state)", self.html)
        self.assertIn('card.querySelector(".save-state")', self.html)
        # savePick must never trigger a full re-render.
        self.assertNotIn("render()", save_pick_fn(self.html))

    def test_radio_change_still_marks_the_card_decided(self):
        change_handler = cards_handler(self.html, "change")
        self.assertIn("markDecided(handle)", change_handler)
        self.assertIn("savePick(handle, input.value)", change_handler)
        self.assertIn('card.classList.add("decided")', self.html)


class TestManualSaveIsDebounced(unittest.TestCase):
    """Finding 2: one commit per keystroke would swamp CI; debounce manual saves."""

    def setUp(self):
        self.html = build_hosted_picker_html([sample_product()], "batch")

    def test_input_handler_queues_a_debounced_save_rather_than_saving_immediately(self):
        input_handler = cards_handler(self.html, "input")
        self.assertIn("queueManualSave(handle)", input_handler)
        self.assertNotIn('savePick(handle, "manual")', input_handler)

    def test_the_debounce_uses_a_trailing_timer_of_about_1500ms(self):
        self.assertIn("const MANUAL_DEBOUNCE_MS = 1500;", self.html)
        queue = slice_from(self.html, "function queueManualSave(", "\n}")
        self.assertIn("clearTimeout(debounceTimers[handle])", queue)
        self.assertIn("MANUAL_DEBOUNCE_MS", queue)

    def test_radio_selection_still_saves_immediately(self):
        change_handler = cards_handler(self.html, "change")
        self.assertIn("savePick(handle, input.value)", change_handler)
        self.assertNotIn("queueManualSave", change_handler)


class TestUnmatchedTmdbPickStaysUndecided(unittest.TestCase):
    """Finding 3: an unmatched stored tmdb pick must not become a blank manual pick."""

    def setUp(self):
        self.html = build_hosted_picker_html([sample_product()], "batch")
        self.fn = slice_from(self.html, "function pickChoiceIndex(", "function matchesRemote(")

    def test_no_match_returns_null_not_manual(self):
        self.assertIn("return idx === -1 ? null : String(idx);", self.fn)
        self.assertNotIn('return idx === -1 ? "manual"', self.fn)

    def test_falls_back_to_matching_on_poster_path_alone(self):
        self.assertIn("c.poster_path && c.poster_path === remotePick.poster_path", self.fn)

    def test_hydration_leaves_an_unmatched_handle_undecided(self):
        hydrate = slice_from(self.html, "async function hydrateFromServer(", "function esc(")
        self.assertIn("if (choice === null) {", hydrate)
        self.assertIn("delete picks[remotePick.handle];", hydrate)


class TestPendingSavesSurviveReload(unittest.TestCase):
    """Finding 4: a failed save must be re-attempted after a page reload."""

    def setUp(self):
        self.html = build_hosted_picker_html([sample_product()], "batch")

    def test_pending_handles_are_tracked_in_localstorage(self):
        self.assertIn('const PENDING_KEY = "tmdb-review-pending::" + BATCH_ID;', self.html)
        self.assertIn("localStorage.setItem(PENDING_KEY, JSON.stringify(pending))", self.html)

    def test_a_handle_is_marked_pending_when_a_save_starts(self):
        save_pick = save_pick_fn(self.html)
        self.assertIn("markPending(handle)", save_pick)

    def test_pending_is_cleared_only_after_a_confirmed_response(self):
        save_pick = save_pick_fn(self.html)
        confirmed = save_pick.index('setSaveState(handle, "saved")')
        self.assertIn("clearPending(handle)", save_pick[confirmed:])
        # the failure branch must not clear it
        failure = save_pick.index("} catch (e) {")
        self.assertNotIn("clearPending", save_pick[failure:])

    def test_hydration_resends_pending_handles_the_server_does_not_have(self):
        self.assertIn("resendPending(remotePicks)", self.html)
        resend = slice_from(self.html, "function resendPending(", "async function hydrateFromServer(")
        self.assertIn("matchesRemote(handle, value, byHandle[handle])", resend)
        self.assertIn("savePick(handle, value)", resend)

    def test_resend_skips_a_handle_with_a_debounced_save_already_queued(self):
        # Otherwise hydrateFromServer's resend races the debounce timer and the
        # same manual pick is POSTed twice on load.
        resend = slice_from(self.html, "function resendPending(", "async function hydrateFromServer(")
        self.assertIn("if (debounceTimers[handle]) continue;", resend)

    def test_hydration_does_not_clobber_a_locally_pending_handle(self):
        hydrate = slice_from(self.html, "async function hydrateFromServer(", "function esc(")
        self.assertIn("if (pending.indexOf(remotePick.handle) !== -1) continue;", hydrate)


class TestRetryIsBoundedAndNotStale(unittest.TestCase):
    """Finding 5: cap retries, back off, and never clobber a newer correction."""

    def setUp(self):
        self.html = build_hosted_picker_html([sample_product()], "batch")
        self.save_pick = save_pick_fn(self.html)

    def test_retries_are_capped(self):
        self.assertIn("const MAX_SAVE_ATTEMPTS = 5;", self.html)
        self.assertIn("if (attempt + 1 >= MAX_SAVE_ATTEMPTS)", self.save_pick)

    def test_exhausted_retries_leave_a_persistent_failed_state(self):
        self.assertIn('setSaveState(handle, "failed")', self.save_pick)
        self.assertIn('state === "failed"', self.html)

    def test_backoff_is_exponential_not_a_fixed_3s(self):
        self.assertIn("const RETRY_BASE_MS = 3000;", self.html)
        self.assertIn("RETRY_BASE_MS * Math.pow(2, attempt)", self.save_pick)
        self.assertNotIn("}, 3000)", self.save_pick)

    def test_a_stale_retry_is_abandoned_when_the_pick_changed(self):
        self.assertIn("if (picks[handle] !== value) return;", self.save_pick)
        self.assertIn("if (debounceTimers[handle]) return;", self.save_pick)


import json
import tempfile
from pathlib import Path

from hosted_review_page import write_hosted_picker


def result(title, year="1982"):
    return {"id": 1, "title": title, "release_date": f"{year}-01-01",
            "poster_path": "/p.jpg", "overview": "Overview."}


def fetcher(results):
    def fetch(query, year):
        return {"results": results}
    return fetch


class TestWriteHostedPicker(unittest.TestCase):
    def test_writes_the_batch_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools_dir = Path(tmp)
            write_hosted_picker(
                [{"Handle": "the-thing", "Title": "The Thing", "Kind": "ambiguous", "Reason": "r"}],
                tools_dir, "out-x", fetcher([result("The Thing")]), sleep_fn=lambda s: None,
            )
            page = tools_dir / "out-x" / "index.html"
            self.assertTrue(page.exists())
            self.assertIn("the-thing", page.read_text(encoding="utf-8"))

    def test_creates_an_empty_data_file_for_a_new_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools_dir = Path(tmp)
            write_hosted_picker(
                [{"Handle": "x", "Title": "X", "Kind": "ambiguous", "Reason": "r"}],
                tools_dir, "out-x", fetcher([result("X")]), sleep_fn=lambda s: None,
            )
            data_file = tools_dir / "data" / "out-x.json"
            self.assertEqual(json.loads(data_file.read_text(encoding="utf-8")), [])

    def test_does_not_clobber_an_existing_data_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools_dir = Path(tmp)
            data_dir = tools_dir / "data"
            data_dir.mkdir(parents=True)
            existing = [{"handle": "x", "choice": "skip"}]
            (data_dir / "out-x.json").write_text(json.dumps(existing), encoding="utf-8")

            write_hosted_picker(
                [{"Handle": "x", "Title": "X", "Kind": "ambiguous", "Reason": "r"}],
                tools_dir, "out-x", fetcher([result("X")]), sleep_fn=lambda s: None,
            )
            self.assertEqual(json.loads((data_dir / "out-x.json").read_text(encoding="utf-8")), existing)

    def test_returns_the_product_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            result_dict = write_hosted_picker(
                [{"Handle": "x", "Title": "X", "Kind": "ambiguous", "Reason": "r"},
                 {"Handle": "y", "Title": "Y", "Kind": "ambiguous", "Reason": "r"}],
                Path(tmp), "out-x", fetcher([result("X")]), sleep_fn=lambda s: None,
            )
            self.assertEqual(result_dict["products"], 2)

    def test_updates_the_manifest_and_launcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools_dir = Path(tmp)
            write_hosted_picker(
                [{"Handle": "x", "Title": "X", "Kind": "ambiguous", "Reason": "r"}],
                tools_dir, "out-x", fetcher([result("X")]), sleep_fn=lambda s: None,
            )
            manifest = json.loads((tools_dir / "batches.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest, [{"batch_id": "out-x", "total": 1}])
            self.assertTrue((tools_dir / "index.html").exists())


from hosted_review_page import update_manifest, write_launcher


class TestManifest(unittest.TestCase):
    def test_creates_the_manifest_with_one_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools_dir = Path(tmp)
            manifest = update_manifest(tools_dir, "out-x", 5)
            self.assertEqual(manifest, [{"batch_id": "out-x", "total": 5}])
            on_disk = json.loads((tools_dir / "batches.json").read_text(encoding="utf-8"))
            self.assertEqual(on_disk, manifest)

    def test_appends_a_second_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools_dir = Path(tmp)
            update_manifest(tools_dir, "out-x", 5)
            manifest = update_manifest(tools_dir, "out-y", 3)
            self.assertEqual(manifest, [
                {"batch_id": "out-x", "total": 5},
                {"batch_id": "out-y", "total": 3},
            ])

    def test_updates_an_existing_batch_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools_dir = Path(tmp)
            update_manifest(tools_dir, "out-x", 5)
            manifest = update_manifest(tools_dir, "out-x", 9)
            self.assertEqual(manifest, [{"batch_id": "out-x", "total": 9}])


class TestWriteLauncher(unittest.TestCase):
    def test_writes_an_index_page_that_reads_the_manifest_and_get_picks(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools_dir = Path(tmp)
            write_launcher(tools_dir)
            html = (tools_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn("batches.json", html)
            self.assertIn("/api/get-picks", html)


from hosted_review_page import build_launcher_html, validate_batch_id


class TestBatchIdValidation(unittest.TestCase):
    """Finding 6: reject a bad batch id at generation time, not on the client's page."""

    def valid_rows(self):
        return [{"Handle": "x", "Title": "X", "Kind": "ambiguous", "Reason": "r"}]

    def write(self, tmp, batch_id):
        return write_hosted_picker(
            self.valid_rows(), Path(tmp), batch_id, fetcher([result("X")]),
            sleep_fn=lambda s: None,
        )

    def test_accepts_the_batch_ids_the_api_accepts(self):
        for batch_id in ["out-x", "out-product_export_3", "out-new-unformatted-8-30", "a.b"]:
            self.assertEqual(validate_batch_id(batch_id), batch_id)

    def test_rejects_the_batch_ids_the_api_rejects(self):
        for batch_id in ["Out-X", "out x", "_leading", "-leading", "", "../secrets", "foo/bar", None]:
            with self.assertRaises(ValueError):
                validate_batch_id(batch_id)

    def test_write_hosted_picker_raises_for_an_uppercase_batch_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError) as ctx:
                self.write(tmp, "Out-Product-Export")
            self.assertIn("Out-Product-Export", str(ctx.exception))
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_write_hosted_picker_raises_for_a_batch_id_with_a_space(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                self.write(tmp, "out product export")

    def test_write_hosted_picker_succeeds_for_a_valid_batch_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.write(tmp, "out-product_export_3")
            self.assertTrue((Path(tmp) / "out-product_export_3" / "index.html").exists())

    def test_the_python_pattern_matches_the_javascript_one(self):
        js = (Path(__file__).resolve().parents[2]
              / "tools" / "review-picker" / "api" / "_github.js").read_text(encoding="utf-8")
        self.assertIn("const BATCH_ID_PATTERN = /^[a-z0-9][a-z0-9._-]*$/;", js)
        from hosted_review_page import BATCH_ID_PATTERN
        self.assertEqual(BATCH_ID_PATTERN.pattern, r"^[a-z0-9][a-z0-9._-]*$")


class TestLauncherHandlesFailedGetPicks(unittest.TestCase):
    """Finding 8: a failed /api/get-picks must not render 'undefined / N decided'."""

    def setUp(self):
        self.html = build_launcher_html()

    def test_checks_response_ok_before_parsing_get_picks(self):
        self.assertIn("if (!response.ok) throw new Error(`get-picks failed (${response.status})`);", self.html)
        self.assertNotIn('await (await fetch(`/api/get-picks', self.html)

    def test_verifies_the_result_is_an_array(self):
        self.assertIn("if (!Array.isArray(picks)) throw", self.html)

    def test_checks_response_ok_before_parsing_the_manifest(self):
        self.assertIn('if (!manifestResponse.ok) throw new Error("batches.json unavailable");', self.html)
        self.assertNotIn('await (await fetch("batches.json")).json()', self.html)

    def test_keeps_the_progress_unavailable_fallback(self):
        self.assertIn('"progress unavailable"', self.html)

    def test_the_committed_launcher_matches_the_generator(self):
        committed = (Path(__file__).resolve().parents[2]
                     / "tools" / "review-picker" / "index.html").read_text(encoding="utf-8")
        self.assertEqual(committed, self.html)


if __name__ == "__main__":
    unittest.main()
