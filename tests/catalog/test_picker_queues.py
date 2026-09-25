import json
import tempfile
import unittest
from pathlib import Path

from catalog.picker.page import build_launcher_html
from catalog.picker.queues import (
    BATCH_ID_PATTERN, append_to_queue, load_products, update_manifest, validate_batch_id, write_launcher,
)


def result(title, year="1982"):
    return {"id": 1, "title": title, "release_date": f"{year}-01-01",
            "poster_path": "/p.jpg", "overview": "Overview."}


def fetcher(results):
    def fetch(query, year):
        return {"results": results}
    return fetch

def review_row(handle, title="X"):
    return {"Handle": handle, "Title": title, "Vendor": "VHS", "Genre": "horror",
            "Kind": "ambiguous", "Reason": "r"}


class TestAppendToQueue(unittest.TestCase):
    def test_new_handles_are_added_and_registered(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools_dir = Path(tmp)
            registry = {}
            outcome = append_to_queue(
                [review_row("a"), review_row("b")], tools_dir, "ambiguous-queue",
                fetcher([result("X")]), registry, sleep_fn=lambda s: None,
            )
            self.assertEqual(outcome["added"], 2)
            self.assertEqual(outcome["batch_total"], 2)
            self.assertEqual(registry["a"], {"batch": "ambiguous-queue", "status": "queued"})
            self.assertEqual(registry["b"], {"batch": "ambiguous-queue", "status": "queued"})

    def test_a_handle_already_in_the_registry_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools_dir = Path(tmp)
            registry = {"a": {"batch": "ambiguous-queue", "status": "queued"}}
            outcome = append_to_queue(
                [review_row("a"), review_row("b")], tools_dir, "ambiguous-queue",
                fetcher([result("X")]), registry, sleep_fn=lambda s: None,
            )
            self.assertEqual(outcome["added"], 1)
            products = load_products(tools_dir, "ambiguous-queue")
            self.assertEqual([p["handle"] for p in products], ["b"])

    def test_a_second_call_merges_into_the_existing_product_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools_dir = Path(tmp)
            registry = {}
            append_to_queue([review_row("a")], tools_dir, "ambiguous-queue",
                             fetcher([result("X")]), registry, sleep_fn=lambda s: None)
            outcome = append_to_queue([review_row("b")], tools_dir, "ambiguous-queue",
                                       fetcher([result("X")]), registry, sleep_fn=lambda s: None)
            self.assertEqual(outcome["added"], 1)
            self.assertEqual(outcome["batch_total"], 2)
            products = load_products(tools_dir, "ambiguous-queue")
            self.assertEqual({p["handle"] for p in products}, {"a", "b"})
            page = (tools_dir / "ambiguous-queue" / "index.html").read_text(encoding="utf-8")
            self.assertIn('"a"', page)
            self.assertIn('"b"', page)

    def test_no_new_rows_touches_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools_dir = Path(tmp)
            registry = {"a": {"batch": "ambiguous-queue", "status": "resolved"}}
            outcome = append_to_queue([review_row("a")], tools_dir, "ambiguous-queue",
                                       fetcher([result("X")]), registry, sleep_fn=lambda s: None)
            self.assertEqual(outcome["added"], 0)
            self.assertFalse((tools_dir / "ambiguous-queue").exists())


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



class TestBatchIdValidation(unittest.TestCase):
    def test_accepts_the_batch_ids_the_api_accepts(self):
        for batch_id in ["out-x", "out-product_export_3", "ambiguous-queue", "a.b"]:
            self.assertEqual(validate_batch_id(batch_id), batch_id)

    def test_rejects_the_batch_ids_the_api_rejects(self):
        for batch_id in ["Out-X", "out x", "_leading", "-leading", "", "../secrets", "foo/bar", None]:
            with self.assertRaises(ValueError):
                validate_batch_id(batch_id)

    def test_append_rejects_a_bad_batch_id_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                append_to_queue([review_row("a")], Path(tmp), "Bad Batch", fetcher([]), {},
                                sleep_fn=lambda s: None)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_the_python_pattern_matches_the_javascript_one(self):
        js = (Path(__file__).resolve().parents[2]
              / "tools" / "review-picker" / "api" / "_github.js").read_text(encoding="utf-8")
        self.assertIn("const BATCH_ID_PATTERN = /^[a-z0-9][a-z0-9._-]*$/;", js)
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
