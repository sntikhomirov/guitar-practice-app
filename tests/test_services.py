import unittest

from guitar_practice_app.models import TempoLog
from guitar_practice_app.services import AttemptStats, DuplicateExerciseError, Journal


class JournalTest(unittest.TestCase):
    def test_add_exercise(self):
        journal = Journal()

        exercise = journal.add_exercise("Гамма", "Описание")

        self.assertEqual(exercise.name, "Гамма")
        self.assertEqual(journal.exercise_names(), ["Гамма"])

    def test_add_duplicate_exercise_raises_error(self):
        journal = Journal()
        journal.add_exercise("Гамма")

        with self.assertRaises(DuplicateExerciseError):
            journal.add_exercise("гамма")

    def test_table_rows_contains_maximum_and_dates(self):
        journal = Journal(
            logs=[
                TempoLog("Гамма", 100, "восьмые", "2026-10-01"),
                TempoLog("Гамма", 120, "восьмые", "2026-10-02"),
            ]
        )
        journal.add_exercise("Гамма")

        rows = journal.table_rows()

        self.assertEqual(rows[0], ["Максимум", "120 / восьмые"])
        self.assertEqual(rows[1], ["2026-10-02", "120 / восьмые"])
        self.assertEqual(rows[2], ["2026-10-01", "100 / восьмые"])


class AttemptStatsTest(unittest.TestCase):
    def test_success_streak_suggests_increase(self):
        stats = AttemptStats()

        for _ in range(5):
            stats.add_success()

        self.assertEqual(stats.decision(), ("Прибавляем", "green"))

    def test_fail_streak_suggests_decrease(self):
        stats = AttemptStats()

        for _ in range(5):
            stats.add_fail()

        self.assertEqual(stats.decision(), ("Убавляем", "red"))


if __name__ == "__main__":
    unittest.main()
