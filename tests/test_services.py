import unittest
from datetime import date

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

        self.assertEqual(rows[0], ["Максимум", "120 / 8 (=240)"])
        self.assertEqual(rows[1], ["2026-10-02", "120 / 8"])
        self.assertEqual(rows[2], ["2026-10-01", "100 / 8"])

    def test_max_tempo_uses_normalized_tempo(self):
        journal = Journal(
            logs=[
                TempoLog("Гамма", 151, "четверти", "2026-10-01"),
                TempoLog("Гамма", 55, "восьмые триоли", "2026-10-02"),
            ]
        )
        journal.add_exercise("Гамма")

        self.assertEqual(journal.max_tempo_text("Гамма"), "55 / 8т (=165)")

    def test_add_practice_session_saves_attempt_stats(self):
        journal = Journal()
        journal.add_exercise("Гамма")
        stats = AttemptStats()
        stats.add_success()
        stats.add_success()
        stats.add_fail()

        log = journal.add_practice_session("Гамма", 90, "восьмые", "2026-10-01", stats)

        self.assertEqual(log.success, 2)
        self.assertEqual(log.fail, 1)

    def test_exercises_are_sorted_by_max_normalized_tempo(self):
        journal = Journal(
            logs=[
                TempoLog("Медленное", 40, "восьмые", "2026-10-01"),
                TempoLog("Быстрое", 30, "шестнадцатые", "2026-10-01"),
            ]
        )
        journal.add_exercise("Быстрое")
        journal.add_exercise("Медленное")

        self.assertEqual(journal.sorted_exercise_names(), ["Медленное", "Быстрое"])

    def test_practice_plan_sorts_by_weekly_count_then_max_normalized_tempo(self):
        journal = Journal(
            logs=[
                TempoLog("Редкое", 90, "четверти", "2026-09-25"),
                TempoLog("Частое медленное", 60, "четверти", "2026-10-01"),
                TempoLog("Частое быстрое", 50, "восьмые", "2026-10-01"),
            ]
        )
        journal.add_exercise("Частое быстрое")
        journal.add_exercise("Редкое")
        journal.add_exercise("Частое медленное")

        plan = journal.practice_plan(as_of=date(2026, 10, 2))

        self.assertEqual(
            [item.exercise for item in plan],
            ["Редкое", "Частое медленное", "Частое быстрое"],
        )

    def test_practice_plan_start_tempo_is_last_tempo_minus_ten_percent_rounded_up(self):
        journal = Journal(
            logs=[
                TempoLog("Гамма", 100, "четверти", "2026-10-01"),
                TempoLog("Гамма", 55, "восьмые триоли", "2026-10-02"),
            ]
        )
        journal.add_exercise("Гамма")

        plan = journal.practice_plan(as_of=date(2026, 10, 2))

        self.assertEqual(plan[0].start_tempo, 50)
        self.assertEqual(plan[0].start_duration, "8т")
        self.assertEqual(plan[0].last_tempo, "55 / 8т")

    def test_practice_plan_supports_exercises_without_logs(self):
        journal = Journal()
        journal.add_exercise("Новое")

        plan = journal.practice_plan(as_of=date(2026, 10, 2))

        self.assertEqual(plan[0].exercise, "Новое")
        self.assertEqual(plan[0].weekly_practice_count, 0)
        self.assertIsNone(plan[0].start_tempo)


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
