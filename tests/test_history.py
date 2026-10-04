import unittest
from datetime import date
from unittest.mock import Mock, patch

from guitar_practice_app.gui import GuitarPracticeApp
from guitar_practice_app.history_ui import ExerciseHistoryWindow
from guitar_practice_app.models import Exercise, TempoLog
from guitar_practice_app.services import AttemptStats, Journal


class CounterRegressionTest(unittest.TestCase):
    def test_five_successes_after_failure_do_not_suggest_increase(self):
        stats = AttemptStats()
        stats.add_fail()
        for _ in range(5):
            stats.add_success()
        self.assertEqual(stats.success_streak, 5)
        self.assertEqual(stats.decision()[0], "")

    def test_success_percentage_can_still_suggest_increase_after_failure(self):
        stats = AttemptStats()
        stats.add_fail()
        for _ in range(7):
            stats.add_success()
        self.assertEqual(stats.decision()[0], "Прибавляем")


class ExerciseHistoryTest(unittest.TestCase):
    def setUp(self):
        self.journal = Journal(exercises=[Exercise("Гамма"), Exercise("Легато")], logs=[
            TempoLog("Гамма", 100, "восьмые", "2026-10-01"),
            TempoLog("Легато", 80, "четверти", "2026-10-02"),
            TempoLog("Гамма", 90, "восьмые", "2026-10-02", 3, 1),
            TempoLog("Гамма", 90, "восьмые", "2026-10-02", 3, 1),
        ])

    def test_history_is_filtered_sorted_and_keeps_duplicates(self):
        self.assertEqual([index for index, _ in self.journal.exercise_history("Гамма")], [3, 2, 0])
        self.assertEqual(self.journal.exercise_history("Нет записей"), [])

    def test_update_preserves_exercise_and_list_position(self):
        replacement = self.journal.update_tempo_log(2, "110", "восьмые триоли", "2026-10-03", "5", "2")
        self.assertEqual(replacement, TempoLog("Гамма", 110, "восьмые триоли", "2026-10-03", 5, 2))
        self.assertEqual(len(self.journal.logs), 4)
        self.assertEqual(self.journal.logs[3].tempo, 90)
        self.assertEqual(self.journal.max_tempo_text("Гамма"), "110 / 8т (=330)")

    def test_invalid_update_does_not_change_logs(self):
        original = list(self.journal.logs)
        for changes in (
            {"tempo": "abc"}, {"tempo": 0}, {"duration": "unknown"},
            {"log_date": "2026-02-30"}, {"success": -1}, {"fail": "abc"},
        ):
            values = dict(tempo=90, duration="восьмые", log_date="2026-10-02", success=0, fail=0)
            values.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.journal.update_tempo_log(2, **values)
            self.assertEqual(self.journal.logs, original)

    def test_delete_only_removes_selected_duplicate(self):
        original_duplicate = self.journal.logs[3]
        self.journal.delete_tempo_log(2)
        self.assertEqual(len(self.journal.logs), 3)
        self.assertIs(self.journal.logs[2], original_duplicate)

    def test_invalid_indexes_do_not_modify_logs(self):
        original = list(self.journal.logs)
        for index in (-1, 4):
            with self.assertRaises(ValueError):
                self.journal.delete_tempo_log(index)
        self.assertEqual(self.journal.logs, original)

    def test_deleting_latest_records_returns_exercise_to_plan(self):
        self.journal.delete_tempo_log(3)
        self.journal.delete_tempo_log(2)
        plan = self.journal.practice_plan(as_of=date(2026, 10, 2))
        self.assertEqual([item.exercise for item in plan], ["Гамма"])
        self.assertEqual(plan[0].last_date, "2026-10-01")


class HistoryWorkflowTest(unittest.TestCase):
    def test_counter_labels_are_initialized_on_startup(self):
        with patch.multiple(
            GuitarPracticeApp,
            configure_style=Mock(), load_journal=Mock(return_value=Journal()),
            create_counter_tab=Mock(), create_journal_tab=Mock(), create_goals_tab=Mock(),
            refresh_exercise_list=Mock(), refresh_journal_table=Mock(),
            refresh_practice_plan=Mock(), update_stats=Mock(),
        ), patch("guitar_practice_app.gui.ttk.Notebook"), patch("guitar_practice_app.gui.ttk.Frame"):
            app = GuitarPracticeApp(Mock())
            app.update_stats.assert_called_once_with()

    def test_refresh_preserves_active_counter_form(self):
        app = GuitarPracticeApp.__new__(GuitarPracticeApp)
        app.stats = AttemptStats()
        app.save_journal = Mock()
        app.refresh_journal_table = Mock()
        app.refresh_practice_plan = Mock()
        app.stats.add_success()
        app.on_history_changed()
        app.refresh_practice_plan.assert_called_once_with(prefill=False)

    def test_refresh_prefills_form_when_no_attempts(self):
        app = GuitarPracticeApp.__new__(GuitarPracticeApp)
        app.stats = AttemptStats()
        app.save_journal = Mock()
        app.refresh_journal_table = Mock()
        app.refresh_practice_plan = Mock()
        app.on_history_changed()
        app.refresh_practice_plan.assert_called_once_with(prefill=True)

    def test_save_failure_restores_history(self):
        history = ExerciseHistoryWindow.__new__(ExerciseHistoryWindow)
        history.journal = Journal(logs=[TempoLog("Гамма", 100, "восьмые", "2026-10-01")])
        original = list(history.journal.logs)
        history.window = Mock()
        history.on_change = Mock(side_effect=OSError("Нет доступа к файлу"))
        history.refresh = Mock()
        with patch("guitar_practice_app.history_ui.messagebox.showerror") as showerror:
            history.apply_change(lambda: history.journal.delete_tempo_log(0))
        self.assertEqual(history.journal.logs, original)
        showerror.assert_called_once()
        history.refresh.assert_not_called()
