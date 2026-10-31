import unittest
from notifier import snapshot, changes

class ComparisonTests(unittest.TestCase):
    def test_baseline_and_changes(self):
        key = 'x' * 32
        original = [('Mathematik', [['Test', '5.5', '01.10.2026', '1', ''], ['Geplant', '', '05.11.2026', '1', '']])]
        old = snapshot(original, key)
        self.assertEqual(len(old), 1)
        self.assertEqual(changes(old, snapshot(original, key)), 0)
        original[0][1][0][1] = '5.8'
        self.assertEqual(changes(old, snapshot(original, key)), 1)
        original[0][1][1][1] = '6'
        self.assertEqual(changes(old, snapshot(original, key)), 2)
        self.assertNotIn('Mathematik', str(old))

    def test_bad_rows_fail_closed(self):
        for row in [['Test', '99', '01.10.2026', '1', ''], ['Login erforderlich']]:
            with self.assertRaises(ValueError):
                snapshot([('Fach', [row])], 'x' * 32)

if __name__ == '__main__':
    unittest.main()
