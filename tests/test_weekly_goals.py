import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from guitar_practice_app.cycles import cycle_start, cycle_end
from guitar_practice_app.models import Exercise, TempoLog
from guitar_practice_app.services import Journal
from guitar_practice_app.storage import JournalStorage


class PracticeCycleTest(unittest.TestCase):
    def test_cycle_starts_wednesday_and_ends_tuesday(self):
        self.assertEqual(cycle_start(date(2026, 10, 6)), date(2026, 9, 30))
        self.assertEqual(cycle_end(date(2026, 10, 6)), date(2026, 10, 6))
        self.assertEqual(cycle_start(date(2026, 10, 7)), date(2026, 10, 7))
        self.assertEqual(cycle_end(date(2026, 10, 7)), date(2026, 10, 13))

    def test_cycle_crosses_year_boundary(self):
        self.assertEqual(cycle_start(date(2026, 1, 1)), date(2025, 12, 31))
        self.assertEqual(cycle_end(date(2026, 1, 1)), date(2026, 1, 6))


class WeeklyGoalTest(unittest.TestCase):
    def setUp(self):
        self.day = date(2026, 10, 4)
        self.journal = Journal(exercises=[Exercise("Гамма")], logs=[
            TempoLog("Гамма", 300, "четверти", "2026-09-29"),
            TempoLog("Гамма", 60, "восьмые триоли", "2026-09-30"),
        ])

    def test_weekly_uses_current_cycle_but_total_uses_entire_history(self):
        self.journal.set_exercise_goal("Гамма", 100, "восьмые", as_of=self.day)
        self.journal.set_exercise_goal("Гамма", 400, "четверти", kind="total")
        weekly = self.journal.goal_progress("Гамма", as_of=self.day)
        total = self.journal.goal_progress("Гамма", kind="total", as_of=self.day)
        self.assertEqual(weekly.percent, 90)
        self.assertEqual(total.percent, 75)

    def test_future_result_is_not_used_for_weekly_progress(self):
        self.journal.add_tempo_log("Гамма", 500, "четверти", "2026-10-05")
        self.journal.set_exercise_goal("Гамма", 200, "четверти", as_of=self.day)
        self.assertEqual(self.journal.goal_progress("Гамма", as_of=self.day).percent, 90)

    def test_completed_weekly_goal_hides_exercise_from_plan(self):
        self.journal.set_exercise_goal("Гамма", 60, "восьмые триоли", as_of=self.day)
        self.assertEqual(self.journal.practice_plan(as_of=self.day), [])

    def test_raising_weekly_goal_returns_exercise_to_plan(self):
        self.journal.set_exercise_goal("Гамма", 180, "четверти", as_of=self.day)
        self.journal.set_exercise_goal("Гамма", 200, "четверти", as_of=self.day)
        self.assertEqual([item.exercise for item in self.journal.practice_plan(as_of=self.day)], ["Гамма"])

    def test_reached_total_goal_does_not_hide_exercise(self):
        self.journal.set_exercise_goal("Гамма", 100, "четверти", kind="total")
        self.assertTrue(self.journal.goal_progress("Гамма", kind="total").reached)
        self.assertEqual(len(self.journal.practice_plan(as_of=self.day)), 1)

    def test_new_wednesday_does_not_carry_goal_forward(self):
        self.journal.set_exercise_goal("Гамма", 180, "четверти", as_of=self.day)
        next_cycle = date(2026, 10, 7)
        self.assertIsNone(self.journal.goal_progress("Гамма", as_of=next_cycle).percent)
        self.assertEqual(len(self.journal.practice_plan(as_of=next_cycle)), 1)
        self.assertTrue(self.journal.goal_progress("Гамма", as_of=date(2026, 10, 6)).reached)

    def test_new_cycle_has_its_own_goal_and_history_is_preserved(self):
        self.journal.set_exercise_goal("Гамма", 180, "четверти", as_of=self.day)
        self.journal.set_exercise_goal("Гамма", 250, "четверти", as_of=date(2026, 10, 7))
        self.assertEqual(len(self.journal.exercises[0].weekly_goals), 2)
        old = self.journal.goal_progress("Гамма", as_of=self.day)
        new = self.journal.goal_progress("Гамма", as_of=date(2026, 10, 7))
        self.assertTrue(old.reached)
        self.assertEqual(new.percent, 0)

    def test_edit_same_cycle_replaces_goal_without_duplicate(self):
        self.journal.set_exercise_goal("Гамма", 180, "четверти", as_of=self.day)
        self.journal.set_exercise_goal("Гамма", 250, "четверти", as_of=self.day)
        self.assertEqual(len(self.journal.exercises[0].weekly_goals), 1)
        self.assertEqual(self.journal.goal_progress("Гамма", as_of=self.day).target_tempo, 250)

    def test_removing_current_goal_keeps_past_and_total(self):
        self.journal.set_exercise_goal("Гамма", 180, "четверти", as_of=self.day)
        self.journal.set_exercise_goal("Гамма", 250, "четверти", as_of=date(2026, 10, 7))
        self.journal.set_exercise_goal("Гамма", 500, "четверти", kind="total")
        self.journal.clear_exercise_goal("Гамма", as_of=date(2026, 10, 7))
        self.assertIsNone(self.journal.goal_progress("Гамма", as_of=date(2026, 10, 7)).percent)
        self.assertTrue(self.journal.goal_progress("Гамма", as_of=self.day).reached)
        self.assertEqual(self.journal.goal_progress("Гамма", kind="total").target_tempo, 500)

    def test_clearing_previous_cycle_does_not_restore_it_from_legacy_fields(self):
        self.journal.set_exercise_goal("Гамма", 180, "четверти", as_of=self.day)
        self.journal.set_exercise_goal("Гамма", 250, "четверти", as_of=date(2026, 10, 7))
        self.journal.clear_exercise_goal("Гамма", as_of=self.day)
        self.assertIsNone(self.journal.goal_progress("Гамма", as_of=self.day).percent)
        self.assertEqual(self.journal.goal_progress("Гамма", as_of=date(2026, 10, 7)).target_tempo, 250)

    def test_both_goal_types_and_history_survive_reload(self):
        self.journal.set_exercise_goal("Гамма", 180, "четверти", as_of=self.day)
        self.journal.set_exercise_goal("Гамма", 250, "четверти", as_of=date(2026, 10, 7))
        self.journal.set_exercise_goal("Гамма", 500, "четверти", kind="total")
        with tempfile.TemporaryDirectory() as directory:
            storage = JournalStorage(Path(directory) / "journal.json")
            storage.save(self.journal.exercises, self.journal.logs)
            loaded = Journal(*storage.load())
        self.assertEqual(loaded.exercises, self.journal.exercises)
        self.assertTrue(loaded.goal_progress("Гамма", as_of=self.day).reached)
        self.assertEqual(loaded.goal_progress("Гамма", kind="total").target_tempo, 500)

    def test_legacy_single_goal_becomes_weekly_goal_for_current_cycle(self):
        with patch("guitar_practice_app.cycles.date", wraps=date) as clock:
            clock.today.return_value = self.day
            exercise = Exercise.from_dict({"name": "Гамма", "target_tempo": 180, "target_duration": "четверти"})
        self.assertEqual(exercise.target_week_start, "2026-09-30")
        self.assertIsNone(exercise.total_target_tempo)
        self.assertEqual(len(exercise.weekly_goals), 1)
