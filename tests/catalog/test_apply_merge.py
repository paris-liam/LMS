import unittest

from catalog.apply.merge import merge
from catalog.core.picks import Pick
from catalog.tmdb.match import POSTER_BASE_URL


def row(handle="the-thing", **overrides):
    base = {"Handle": handle, "Title": "The Thing", "Body (HTML)": "", "Image Src": "", "Image Alt Text": "",
            "Tags": "Rental, VHS, Horror", "Vendor": "VHS", "Option1 Name": "Genre", "Option1 Value": "Horror"}
    base.update(overrides)
    return base


def changes_of(result):
    return {(c.handle, c.field): (c.after, c.source) for c in result.changes}


QUEUED = {"the-thing": {"batch": "ambiguous-queue", "status": "queued"}}


class TestAutoFix(unittest.TestCase):
    def test_autofix_becomes_changes(self):
        result = merge([row()], {"the-thing": {"changes": {"Vendor": "Blu-Ray"}, "rules": ["format-alias"]}}, [], {})
        self.assertEqual(changes_of(result), {("the-thing", "Vendor"): ("Blu-Ray", "auto-fix")})

    def test_autofix_already_in_shopify_is_dropped(self):
        result = merge([row(Vendor="Blu-Ray")], {"the-thing": {"changes": {"Vendor": "Blu-Ray"}, "rules": []}}, [], {})
        self.assertEqual(result.changes, [])

    def test_autofix_for_a_vanished_product_is_ignored(self):
        result = merge([], {"gone": {"changes": {"Vendor": "VHS"}, "rules": []}}, [], {})
        self.assertEqual(result.ignored[0][0], "gone")


class TestPicks(unittest.TestCase):
    def test_tmdb_pick_fills_empty_fields_and_alt(self):
        result = merge([row()], {}, [Pick("ambiguous-queue", "the-thing", "tmdb", "/t.jpg", "A shapeshifter.")], QUEUED)
        c = changes_of(result)
        self.assertEqual(c[("the-thing", "Image Src")][0], f"{POSTER_BASE_URL}/t.jpg")
        self.assertEqual(c[("the-thing", "Image Alt Text")][0], "The Thing poster")
        self.assertEqual(c[("the-thing", "Body (HTML)")][0], "<p>A shapeshifter.</p>")
        self.assertEqual(c[("the-thing", "Image Src")][1], "pick:ambiguous-queue")
        self.assertEqual(set(result.applied["the-thing"]), {"Image Src", "Image Alt Text", "Body (HTML)"})

    def test_tmdb_pick_never_overwrites(self):
        result = merge([row(**{"Image Src": "https://cdn/x.jpg", "Image Alt Text": "x"})], {},
                       [Pick("q", "the-thing", "tmdb", "/t.jpg", "")], QUEUED)
        self.assertEqual(result.changes, [])
        self.assertEqual(result.resolved, ["the-thing"])

    def test_current_cycle_manual_pick_overwrites(self):
        result = merge([row(**{"Image Src": "https://cdn/old.jpg", "Image Alt Text": "Old", "Body (HTML)": "<p>old</p>"})],
                       {}, [Pick("ambiguous-queue", "the-thing", "manual", image_src="https://new.jpg", overview="New.")],
                       QUEUED)
        c = changes_of(result)
        self.assertEqual(c[("the-thing", "Image Src")][0], "https://new.jpg")
        self.assertEqual(c[("the-thing", "Body (HTML)")][0], "<p>New.</p>")
        self.assertNotIn(("the-thing", "Image Alt Text"), c)  # existing alt text kept

    def test_manual_pick_tmdb_thumbnail_is_upgraded_to_full_size(self):
        # The picker shows TMDB candidates at w185; a pasted thumbnail link
        # would put a 185px poster on the store.
        for size in ("w92", "w185", "w500", "original"):
            result = merge([row()], {}, [Pick("q", "the-thing", "manual",
                                              image_src=f"https://image.tmdb.org/t/p/{size}/abc.jpg")], QUEUED)
            self.assertEqual(changes_of(result)[("the-thing", "Image Src")][0], f"{POSTER_BASE_URL}/abc.jpg")

    def test_manual_pick_other_image_hosts_are_kept_as_given(self):
        url = "https://m.media-amazon.com/images/I/71-awWlPjEL._SX466_.jpg"
        result = merge([row()], {}, [Pick("q", "the-thing", "manual", image_src=url)], QUEUED)
        self.assertEqual(changes_of(result)[("the-thing", "Image Src")][0], url)

    def test_legacy_manual_pick_only_fills_gaps(self):
        result = merge([row(**{"Image Src": "https://cdn/fixed-since.jpg"})], {},
                       [Pick("review-9.2-gaps", "the-thing", "manual", image_src="https://old.jpg", overview="Old.")],
                       {})  # not in the registry: an older batch
        c = changes_of(result)
        self.assertNotIn(("the-thing", "Image Src"), c)
        self.assertEqual(c[("the-thing", "Body (HTML)")][0], "<p>Old.</p>")

    def test_empty_manual_pick_is_ignored(self):
        result = merge([row()], {}, [Pick("q", "the-thing", "manual")], QUEUED)
        self.assertEqual(result.changes, [])
        self.assertEqual(result.applied, {})
        self.assertIn("empty manual pick", result.ignored[0][1])

    def test_skip_pick(self):
        result = merge([row()], {}, [Pick("ambiguous-queue", "the-thing", "skip")], QUEUED)
        self.assertEqual(result.skipped, ["the-thing"])
        self.assertEqual(result.changes, [])

    def test_already_skipped_is_not_skipped_again(self):
        result = merge([row()], {}, [Pick("q", "the-thing", "skip")], {"the-thing": {"status": "skipped"}})
        self.assertEqual(result.skipped, [])

    def test_applied_or_resolved_handles_are_left_alone(self):
        for status in ("applied", "resolved"):
            with self.subTest(status=status):
                result = merge([row()], {}, [Pick("q", "the-thing", "tmdb", "/t.jpg", "O.")],
                               {"the-thing": {"status": status}})
                self.assertEqual(result.changes, [])

    def test_pick_for_a_product_not_in_the_snapshot_is_ignored(self):
        result = merge([], {}, [Pick("q", "gone", "tmdb", "/t.jpg", "O.")], {})
        self.assertEqual(result.ignored[0][0], "gone")

    def test_later_batch_wins_for_the_same_handle(self):
        picks = [Pick("old", "the-thing", "tmdb", "/old.jpg", ""), Pick("ambiguous-queue", "the-thing", "tmdb", "/new.jpg", "")]
        c = changes_of(merge([row()], {}, picks, QUEUED))
        self.assertEqual(c[("the-thing", "Image Src")], (f"{POSTER_BASE_URL}/new.jpg", "pick:ambiguous-queue"))

    def test_pick_beats_autofix_on_the_same_field(self):
        autofix = {"the-thing": {"changes": {"Image Src": f"{POSTER_BASE_URL}/auto.jpg"}, "rules": ["poster-missing"]}}
        c = changes_of(merge([row()], autofix, [Pick("q", "the-thing", "tmdb", "/picked.jpg", "")], QUEUED))
        self.assertEqual(c[("the-thing", "Image Src")], (f"{POSTER_BASE_URL}/picked.jpg", "pick:q"))

    def test_changes_are_sorted(self):
        result = merge([row("b"), row("a")], {"b": {"changes": {"Vendor": "DVD"}, "rules": []},
                                              "a": {"changes": {"Vendor": "DVD"}, "rules": []}}, [], {})
        self.assertEqual([c.handle for c in result.changes], ["a", "b"])

    def test_pick_overview_is_escaped(self):
        c = changes_of(merge([row()], {}, [Pick("q", "the-thing", "tmdb", "", "A & B")], QUEUED))
        self.assertEqual(c[("the-thing", "Body (HTML)")][0], "<p>A &amp; B</p>")

    def test_pre_escaped_pick_overview_is_not_double_escaped(self):
        c = changes_of(merge([row()], {}, [Pick("q", "the-thing", "manual", "", "A &amp; B")], QUEUED))
        self.assertEqual(c[("the-thing", "Body (HTML)")][0], "<p>A &amp; B</p>")


class TestReviewFixes(unittest.TestCase):
    def test_old_batch_manual_pick_for_a_queued_handle_only_fills_gaps(self):
        result = merge([row(**{"Image Src": "https://cdn/current.jpg"})], {},
                       [Pick("review-ambigeous-queue-8.31-1", "the-thing", "manual",
                             image_src="https://old.jpg", overview="Old.")], QUEUED)
        c = changes_of(result)
        self.assertNotIn(("the-thing", "Image Src"), c)
        self.assertEqual(c[("the-thing", "Body (HTML)")][0], "<p>Old.</p>")

    def test_old_batch_skip_for_a_queued_handle_is_ignored(self):
        result = merge([row()], {}, [Pick("review-9.2-gaps", "the-thing", "skip")], QUEUED)
        self.assertEqual(result.skipped, [])
        self.assertIn("superseded", result.ignored[0][1])

    def test_this_runs_applied_picks_are_reemitted(self):
        registry = {"the-thing": {"batch": "ambiguous-queue", "status": "applied", "run": "r1",
                                  "values": {"Image Src": "https://img/x.jpg"}}}
        result = merge([row()], {}, [], registry, run_id="r1")
        self.assertEqual(changes_of(result), {("the-thing", "Image Src"): ("https://img/x.jpg", "applied:r1")})
        self.assertEqual(result.applied, {})  # already recorded; not re-marked

    def test_another_runs_applied_picks_are_not_reemitted(self):
        registry = {"the-thing": {"status": "applied", "run": "r0", "values": {"Image Src": "https://img/x.jpg"}}}
        self.assertEqual(merge([row()], {}, [], registry, run_id="r1").changes, [])


if __name__ == "__main__":
    unittest.main()
