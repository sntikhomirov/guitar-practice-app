import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from guitar_practice_app.archive_ui import ExerciseArchiveWindow
from guitar_practice_app.gui import GuitarPracticeApp
from guitar_practice_app.models import Exercise, TempoLog
from guitar_practice_app.practice import PracticeController
from guitar_practice_app.services import AttemptStats, DuplicateExerciseError, Journal
from guitar_practice_app.storage import JournalStorage


class ExerciseArchiveTest(unittest.TestCase):
    def setUp(self):
        self.day = date(2026, 11, 4)
        self.journal = Journal(exercises=[Exercise("Гамма", "Описание"), Exercise("Легато")], logs=[
            TempoLog("Гамма", 80, "восьмые", "2026-11-01", 5, 1),
            TempoLog("Легато", 90, "четверти", "2026-11-02"),
        ])
        self.journal.set_exercise_goal("Гамма", 120, "восьмые", as_of=self.day)
        self.journal.set_exercise_goal("Гамма", 150, "восьмые", kind="total")

    def test_archive_preserves_exercise_fields_and_all_records(self):
        original = self.journal.exercise_by_name("Гамма")
        logs = list(self.journal.logs)
        archived = self.journal.archive_exercise("Гамма")
        self.assertEqual(archived, replace(original, archived=True))
        self.assertEqual(self.journal.logs, logs)
        self.assertEqual(len(self.journal.exercise_history("Гамма")), 1)

    def test_archive_is_hidden_from_active_lists_and_plan(self):
        self.journal.archive_exercise("Гамма")
        self.assertEqual(self.journal.exercise_names(), ["Легато"])
        self.assertEqual(self.journal.sorted_exercise_names(), ["Легато"])
        self.assertEqual(self.journal.exercise_names(include_archived=True), ["Гамма", "Легато"])
        self.assertEqual([item.exercise for item in self.journal.practice_plan(as_of=self.day)], ["Легато"])

    def test_table_does_not_show_dates_belonging_only_to_archived_exercises(self):
        self.journal.archive_exercise("Гамма")
        self.assertEqual(self.journal.table_rows(), [
            ["Максимум", "90 / 4 (=90)"], ["2026-11-02", "90 / 4"],
        ])

    def test_restore_keeps_goals_and_returns_exercise_to_plan(self):
        original = self.journal.exercise_by_name("Гамма")
        self.journal.archive_exercise("Гамма")
        restored = self.journal.restore_exercise("Гамма")
        self.assertEqual(restored, original)
        self.assertIn("Гамма", self.journal.exercise_names())
        self.assertIn("Гамма", [item.exercise for item in self.journal.practice_plan(as_of=self.day)])
        self.assertEqual(self.journal.goal_progress("Гамма", as_of=self.day).target_tempo, 120)

    def test_restore_does_not_bypass_existing_plan_rules(self):
        self.journal.add_tempo_log("Гамма", 130, "восьмые", "2026-11-04")
        self.journal.archive_exercise("Гамма")
        self.journal.restore_exercise("Гамма")
        self.assertNotIn("Гамма", [item.exercise for item in self.journal.practice_plan(as_of=self.day)])

    def test_all_exercises_can_be_archived(self):
        self.journal.archive_exercise("Гамма")
        self.journal.archive_exercise("Легато")
        self.assertEqual(self.journal.exercise_names(), [])
        self.assertEqual(self.journal.table_rows(), [])
        self.assertEqual(self.journal.practice_plan(as_of=self.day), [])
        self.assertEqual(len(self.journal.logs), 2)

    def test_archive_without_records_and_repeated_operations_are_safe(self):
        self.journal.add_exercise("Новое")
        self.journal.archive_exercise("Новое")
        self.journal.archive_exercise("Новое")
        self.assertEqual(self.journal.exercise_history("Новое"), [])
        self.journal.restore_exercise("Новое")
        self.journal.restore_exercise("Новое")
        self.assertIn("Новое", self.journal.exercise_names())

    def test_archived_name_cannot_be_reused(self):
        self.journal.archive_exercise("Гамма")
        with self.assertRaises(DuplicateExerciseError):
            self.journal.add_exercise("гамма")

    def test_new_results_cannot_be_saved_to_archived_exercise(self):
        self.journal.archive_exercise("Гамма")
        original = list(self.journal.logs)
        with self.assertRaises(ValueError):
            self.journal.add_tempo_log("Гамма", 100, "четверти", "2026-11-04")
        with self.assertRaises(ValueError):
            self.journal.add_practice_session("Гамма", 100, "четверти", "2026-11-04", AttemptStats())
        self.assertEqual(self.journal.logs, original)

    def test_archived_history_can_still_be_corrected(self):
        self.journal.archive_exercise("Гамма")
        self.journal.update_tempo_log(0, 85, "восьмые", "2026-11-01", 4, 1)
        self.assertEqual(self.journal.logs[0].tempo, 85)
        self.assertTrue(self.journal.exercise_by_name("Гамма").archived)

    def test_unknown_exercise_raises_without_changes(self):
        original = list(self.journal.exercises)
        for operation in (self.journal.archive_exercise, self.journal.restore_exercise):
            with self.assertRaises(ValueError):
                operation("Нет такого")
        self.assertEqual(self.journal.exercises, original)

    def test_status_and_goals_survive_save_and_reload(self):
        self.journal.archive_exercise("Гамма")
        with tempfile.TemporaryDirectory() as folder:
            storage = JournalStorage(Path(folder) / "journal.json")
            storage.save(self.journal.exercises, self.journal.logs)
            loaded = Journal(*storage.load())
        self.assertEqual(loaded.exercises, self.journal.exercises)
        self.assertEqual(loaded.logs, self.journal.logs)
        self.assertEqual(loaded.exercise_names(), ["Легато"])
        loaded.restore_exercise("Гамма")
        self.assertEqual(loaded.goal_progress("Гамма", kind="total").target_tempo, 150)

    def test_old_json_without_archive_flag_loads_as_active(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "journal.json"
            path.write_text(json.dumps({"exercises": [{"name": "Гамма"}], "logs": []}), encoding="utf-8")
            exercises, _ = JournalStorage(path).load()
        self.assertFalse(exercises[0].archived)

    def test_invalid_archive_flag_is_rejected(self):
        with self.assertRaises(ValueError):
            Exercise.from_dict({"name": "Гамма", "archived": "false"})


class ArchiveWorkflowTest(unittest.TestCase):
    def make_app(self):
        app = GuitarPracticeApp.__new__(GuitarPracticeApp)
        app.root = Mock()
        app.journal = Journal(exercises=[Exercise("Гамма"), Exercise("Легато")])
        app.stats = AttemptStats()
        app.session_exercise_combobox = Mock()
        app.session_exercise_combobox.get.return_value = "Гамма"
        app.history_exercise_combobox = Mock()
        app.history_exercise_combobox.get.return_value = "Гамма"
        app.save_journal = Mock()
        app.practice = PracticeController(app.journal, app.save_journal, app.stats)
        app.refresh_exercise_list = Mock()
        app.refresh_journal_table = Mock()
        app.refresh_practice_plan = Mock()
        return app

    def test_active_attempts_block_archiving_current_exercise(self):
        app = self.make_app()
        app.stats.add_success()
        with self.assertRaises(ValueError):
            app.set_exercise_archived("Гамма", True)
        self.assertFalse(app.journal.exercise_by_name("Гамма").archived)
        app.save_journal.assert_not_called()

    def test_archiving_other_exercise_keeps_attempts_and_form(self):
        app = self.make_app()
        app.stats.add_success()
        app.set_exercise_archived("Легато", True)
        self.assertEqual(app.stats.success, 1)
        app.refresh_practice_plan.assert_called_once_with(prefill=False)

    def test_success_refreshes_all_active_views(self):
        app = self.make_app()
        app.set_exercise_archived("Гамма", True)
        app.save_journal.assert_called_once()
        app.refresh_exercise_list.assert_called_once()
        app.refresh_journal_table.assert_called_once()
        app.refresh_practice_plan.assert_called_once_with(prefill=True)

    def test_save_failure_rolls_back_archive_status(self):
        app = self.make_app()
        app.save_journal.side_effect = OSError("Нет доступа")
        with self.assertRaises(OSError):
            app.set_exercise_archived("Гамма", True)
        self.assertFalse(app.journal.exercise_by_name("Гамма").archived)
        app.refresh_exercise_list.assert_not_called()

    def test_save_failure_rolls_back_restore_status(self):
        app = self.make_app()
        app.journal.archive_exercise("Гамма")
        app.save_journal.side_effect = OSError("Нет доступа")
        with self.assertRaises(OSError):
            app.set_exercise_archived("Гамма", False)
        self.assertTrue(app.journal.exercise_by_name("Гамма").archived)

    def test_cancel_confirmation_does_not_archive(self):
        app = self.make_app()
        with patch("guitar_practice_app.gui.messagebox.askyesno", return_value=False):
            app.archive_selected_exercise()
        self.assertFalse(app.journal.exercise_by_name("Гамма").archived)
        app.save_journal.assert_not_called()

    def test_restore_from_archive_window_calls_callback_and_refreshes(self):
        window = ExerciseArchiveWindow.__new__(ExerciseArchiveWindow)
        window.selected_name = Mock(return_value="Гамма")
        window.restore_exercise = Mock()
        window.refresh = Mock()
        window.restore_selected()
        window.restore_exercise.assert_called_once_with("Гамма")
        window.refresh.assert_called_once()

    def test_archive_refresh_keeps_selected_exercise_after_history(self):
        window = ExerciseArchiveWindow.__new__(ExerciseArchiveWindow)
        window.journal = Journal(exercises=[Exercise("Гамма", archived=True)])
        window.selected_name = Mock(return_value="Гамма")
        window.table = Mock()
        window.table.get_children.return_value = ("0",)
        window.status = Mock()
        window.select_record = Mock()
        window.refresh()
        window.table.selection_set.assert_called_once_with("0")

    def test_lists_clear_stale_selection_when_all_exercises_archived(self):
        app = self.make_app()
        app.journal.archive_exercise("Гамма")
        app.journal.archive_exercise("Легато")
        widgets = [Mock(), Mock(), Mock()]
        for widget in widgets:
            widget.get.return_value = "Гамма"
            widget.__setitem__ = Mock()
        app.exercise_combobox, app.session_exercise_combobox, app.history_exercise_combobox = widgets
        GuitarPracticeApp.refresh_exercise_list(app)
        for widget in widgets:
            widget.set.assert_called_once_with("")
