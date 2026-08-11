import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "formatting-scripts"))

from handles import HandleAllocator, derive_handle, slugify


class TestSlugify(unittest.TestCase):
    def test_drops_apostrophes_rather_than_hyphenating_them(self):
        self.assertEqual(slugify("The Monkey's Uncle"), "the-monkeys-uncle")
        self.assertEqual(slugify("Trick 'r Treat"), "trick-r-treat")

    def test_commas_and_spaces_become_single_hyphens(self):
        self.assertEqual(slugify("Paris, Texas"), "paris-texas")

    def test_trims_leading_and_trailing_hyphens(self):
        self.assertEqual(slugify("  Rushmore!  "), "rushmore")

    def test_accents_are_dropped_like_the_sheet_formula(self):
        self.assertEqual(slugify("Amélie"), "am-lie")
        self.assertEqual(slugify("8½"), "8")


class TestDeriveHandle(unittest.TestCase):
    def test_the_worked_examples_from_the_client_guide(self):
        self.assertEqual(derive_handle("Rushmore", "VHS", "Rental"), "rushmore-vhs-rental")
        self.assertEqual(derive_handle("Rushmore", "DVD", "Rental"), "rushmore-dvd-rental")
        self.assertEqual(derive_handle("Paris, Texas", "DVD", "Rental"), "paris-texas-dvd-rental")
        self.assertEqual(
            derive_handle("The Monkey's Uncle", "VHS", "Floor Sale"),
            "the-monkeys-uncle-vhs-floor-sale",
        )
        self.assertEqual(derive_handle("The Thing", "4K", "Floor Sale"), "the-thing-4k-floor-sale")

    def test_blu_ray_keeps_its_internal_hyphen(self):
        self.assertEqual(derive_handle("Alien", "Blu-Ray", "Rental"), "alien-blu-ray-rental")


class TestHandleAllocator(unittest.TestCase):
    def test_first_use_is_unsuffixed(self):
        allocator = HandleAllocator()
        self.assertEqual(allocator.allocate("rushmore-vhs-rental"), "rushmore-vhs-rental")

    def test_repeat_copies_count_up(self):
        allocator = HandleAllocator()
        allocator.allocate("rushmore-vhs-rental")
        self.assertEqual(allocator.allocate("rushmore-vhs-rental"), "rushmore-vhs-rental-2")
        self.assertEqual(allocator.allocate("rushmore-vhs-rental"), "rushmore-vhs-rental-3")

    def test_different_format_is_a_different_handle(self):
        allocator = HandleAllocator()
        allocator.allocate("rushmore-vhs-rental")
        self.assertEqual(allocator.allocate("rushmore-dvd-rental"), "rushmore-dvd-rental")

    def test_reserved_handles_are_avoided(self):
        """A client's hand-typed handle override must not be re-issued."""
        allocator = HandleAllocator()
        allocator.reserve("amelie-dvd-rental")
        self.assertEqual(allocator.allocate("amelie-dvd-rental"), "amelie-dvd-rental-2")


if __name__ == "__main__":
    unittest.main()
