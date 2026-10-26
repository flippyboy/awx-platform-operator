import unittest
from datetime import date

import calver


class CalverTest(unittest.TestCase):
    def test_parse(self):
        self.assertTrue(calver.is_calver("2026.10.26"))
        self.assertTrue(calver.is_calver("v2026.10.26-1"))
        self.assertTrue(calver.is_calver("2026.10.26-12"))
        self.assertFalse(calver.is_calver("2026.10.26-0"))
        self.assertFalse(calver.is_calver("2026.10.26-01"))
        self.assertFalse(calver.is_calver("2026.1.5"))
        self.assertFalse(calver.is_calver("2026.02.31"))
        self.assertFalse(calver.is_calver("0.1.13"))
        self.assertFalse(calver.is_calver("2026.10.26.1"))

    def test_next_version(self):
        day = date(2026, 10, 26)
        self.assertEqual(calver.next_version("0.1.13", today=day), "2026.10.26")
        self.assertEqual(calver.next_version("2026.10.25", today=day), "2026.10.26")
        self.assertEqual(calver.next_version("2026.10.25-4", today=day), "2026.10.26")
        self.assertEqual(calver.next_version("2026.10.26", today=day), "2026.10.26-1")
        self.assertEqual(calver.next_version("v2026.10.26-1", today=day), "2026.10.26-2")
        self.assertEqual(calver.next_version("", today=day), "2026.10.26")


if __name__ == "__main__":
    unittest.main()
