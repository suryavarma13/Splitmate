import unittest
from decimal import Decimal
from apps.expenses.calculators import split_equally, split_by_percentage, split_custom

class SplitCalculatorTests(unittest.TestCase):
    def test_equal_split_remainder(self):
        self.assertEqual(split_equally(100, ["a", "b", "c"]), {"a": 34, "b": 33, "c": 33})

    def test_percentage_split_exact_total(self):
        result = split_by_percentage(1001, {"a": Decimal("50"), "b": Decimal("30"), "c": Decimal("20")})
        self.assertEqual(sum(result.values()), 1001)

    def test_custom_split_validation(self):
        self.assertEqual(split_custom(100, {"a": 60, "b": 40}), {"a": 60, "b": 40})
        with self.assertRaises(ValueError):
            split_custom(100, {"a": 50, "b": 40})

if __name__ == "__main__":
    unittest.main()
