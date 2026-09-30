import importlib.util
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "regroup_picker", Path(__file__).resolve().parents[2] / "scripts" / "regroup-picker.py")
regroup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(regroup)


def queued(batch="ambiguous-queue"):
    return {"batch": batch, "status": "queued"}


class TestPlanRegroup(unittest.TestCase):
    def test_splits_by_type_chunks_floor_sales_drops_unflagged_and_leaves_decided_alone(self):
        floor = [f"f{i:03d}" for i in range(101)]
        registry = {h: queued() for h in ["r1", "gone", "u1", *floor]}
        registry["done"] = {"batch": "ambiguous-queue", "status": "applied"}
        tags = {"r1": "Rental", "u1": "DVD", "new-r": "Rental, DVD", "done": "Rental",
                **{h: "Floor Sale" for h in floor}}
        old = {h: {"handle": h, "title": h} for h in ["r1", "gone", "u1", "done", *floor]}
        flagged = {"r1", "u1", "new-r", "done", *floor}
        groups, dropped, fresh = regroup.plan_regroup(
            flagged, tags, registry, old, {"new-r": {"Title": "New R"}})
        self.assertEqual(groups["rentals"], ["new-r", "r1"])
        self.assertEqual(len(groups["floor-sale-01"]), 100)
        self.assertEqual(len(groups["floor-sale-02"]), 1)
        self.assertEqual(groups["untyped"], ["u1"])
        self.assertEqual(dropped, ["gone"])
        self.assertEqual(fresh, ["new-r"])
        self.assertNotIn("done", [h for v in groups.values() for h in v])


if __name__ == "__main__":
    unittest.main()
