import unittest

from guitar_practice_app.tempo import duration_label, normalized_tempo


class TempoTest(unittest.TestCase):
    def test_duration_label(self):
        self.assertEqual(duration_label("четверти"), "4")
        self.assertEqual(duration_label("восьмые триоли"), "8т")
        self.assertEqual(duration_label("шестнадцатые триоли"), "16т")

    def test_normalized_tempo(self):
        self.assertEqual(normalized_tempo(100, "четверти"), 100)
        self.assertEqual(normalized_tempo(70, "восьмые"), 140)
        self.assertEqual(normalized_tempo(55, "восьмые триоли"), 165)
        self.assertEqual(normalized_tempo(45, "шестнадцатые"), 180)
        self.assertEqual(normalized_tempo(30, "шестнадцатые триоли"), 180)


if __name__ == "__main__":
    unittest.main()
