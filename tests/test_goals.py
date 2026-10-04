import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from guitar_practice_app.goals_ui import ExerciseGoalWindow, ExerciseGoalsPanel
from guitar_practice_app.gui import GuitarPracticeApp
from guitar_practice_app.models import Exercise, TempoLog
from guitar_practice_app.services import Journal
from guitar_practice_app.storage import JournalStorage


class ExerciseGoalsTest(unittest.TestCase):
    def setUp(self):
        for module in ("guitar_practice_app.services", "guitar_practice_app.cycles"):
            clock = patch(f"{module}.date", wraps=date)
            mocked_date = clock.start()
            mocked_date.today.return_value = date(2026, 10, 4)
            self.addCleanup(clock.stop)
        self.journal = Journal(exercises=[Exercise("Гамма", "Описание")], logs=[
            TempoLog("Гамма", 150, "четверти", "2026-10-01"),
            TempoLog("Гамма", 60, "восьмые триоли", "2026-10-02"),
        ])

    def test_progress_compares_normalized_maximum_and_target(self):
        self.journal.set_exercise_goal("Гамма", "100", "восьмые")
        progress = self.journal.goal_progress("Гамма")
        self.assertEqual(progress.maximum_normalized, 180)
        self.assertEqual(progress.target_normalized, 200)
        self.assertEqual(progress.percent, 90)
        self.assertFalse(progress.reached)

    def test_goal_can_be_changed_without_losing_description_or_logs(self):
        original_logs = list(self.journal.logs)
        self.journal.set_exercise_goal("Гамма", 100, "восьмые")
        changed = self.journal.set_exercise_goal("Гамма", 90, "восьмые триоли")
        self.assertEqual(changed.description, "Описание")
        self.assertEqual(changed.target_tempo, 90)
        self.assertEqual(self.journal.logs, original_logs)
        self.assertAlmostEqual(self.journal.goal_progress("Гамма").percent, 180 / 270 * 100)

    def test_no_goal_and_cleared_goal_have_no_percentage(self):
        self.assertIsNone(self.journal.goal_progress("Гамма").percent)
        self.journal.set_exercise_goal("Гамма", 100, "восьмые")
        self.journal.clear_exercise_goal("Гамма")
        exercise = self.journal.exercise_by_name("Гамма")
        self.assertIsNone(exercise.target_tempo)
        self.assertEqual(exercise.target_duration, "")
        self.assertFalse(self.journal.goal_progress("Гамма").reached)

    def test_no_records_means_zero_progress(self):
        journal = Journal(exercises=[Exercise("Новое", target_tempo=100, target_duration="четверти")])
        progress = journal.goal_progress("Новое")
        self.assertEqual(progress.percent, 0)
        self.assertEqual(progress.maximum_text, "")
        self.assertFalse(progress.reached)

    def test_reached_and_exceeded_goals_are_capped_at_100(self):
        for tempo in (180, 100):
            with self.subTest(tempo=tempo):
                self.journal.set_exercise_goal("Гамма", tempo, "четверти")
                progress = self.journal.goal_progress("Гамма")
                self.assertEqual(progress.percent, 100)
                self.assertTrue(progress.reached)

    def test_near_goal_is_not_marked_as_reached(self):
        self.journal.set_exercise_goal("Гамма", 181, "четверти")
        self.assertLess(self.journal.goal_progress("Гамма").percent, 100)
        self.assertFalse(self.journal.goal_progress("Гамма").reached)

    def test_invalid_goals_do_not_modify_exercises(self):
        original = list(self.journal.exercises)
        for tempo, duration in ((0, "четверти"), (-1, "четверти"), ("", "четверти"),
                                ("abc", "четверти"), (1.5, "четверти"), (True, "четверти"),
                                (100, "unknown"), (100, "")):
            with self.subTest(tempo=tempo, duration=duration), self.assertRaises(ValueError):
                self.journal.set_exercise_goal("Гамма", tempo, duration)
            self.assertEqual(self.journal.exercises, original)

    def test_unknown_exercise_is_rejected(self):
        with self.assertRaises(ValueError):
            self.journal.set_exercise_goal("Не существует", 100, "четверти")

    def test_editing_or_deleting_record_recalculates_progress(self):
        self.journal.set_exercise_goal("Гамма", 200, "четверти")
        self.journal.update_tempo_log(1, 80, "восьмые триоли", "2026-10-02")
        self.assertTrue(self.journal.goal_progress("Гамма").reached)
        self.journal.delete_tempo_log(1)
        self.assertEqual(self.journal.goal_progress("Гамма").percent, 75)


class GoalStorageTest(unittest.TestCase):
    def test_old_exercise_without_goal_is_supported(self):
        for version in (None, 1):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "journal.json"
                data = {"exercises": [{"name": "Гамма", "description": "Старый журнал"}], "logs": []}
                if version is not None:
                    data["version"] = version
                path.write_text(json.dumps(data), encoding="utf-8")
                exercises, logs = JournalStorage(path).load()
                self.assertEqual(exercises, [Exercise("Гамма", "Старый журнал")])
                self.assertEqual(logs, [])

    def test_goal_roundtrip_and_removal(self):
        with tempfile.TemporaryDirectory() as folder:
            storage = JournalStorage(Path(folder) / "journal.json")
            expected = Exercise("Гамма", "Описание", 120, "шестнадцатые")
            storage.save([expected], [])
            exercises, logs = storage.load()
            self.assertEqual(exercises, [expected])
            journal = Journal(exercises, logs)
            journal.clear_exercise_goal("Гамма")
            storage.save(journal.exercises, journal.logs)
            self.assertEqual(storage.load()[0], [Exercise("Гамма", "Описание")])


class GoalEditorTest(unittest.TestCase):
    def test_save_error_restores_goal_and_keeps_editor_open(self):
        editor = ExerciseGoalWindow.__new__(ExerciseGoalWindow)
        editor.journal = Journal(exercises=[Exercise("Гамма")])
        editor.window = Mock()
        editor.save_journal = Mock(side_effect=OSError("Нет доступа"))
        editor.refresh = Mock()
        with patch("guitar_practice_app.goals_ui.messagebox.showerror") as error:
            editor.apply_change(lambda: editor.journal.set_exercise_goal("Гамма", 100, "четверти"))
        self.assertIsNone(editor.journal.exercises[0].target_tempo)
        error.assert_called_once()
        editor.refresh.assert_not_called()
        editor.window.destroy.assert_not_called()

    def test_saved_goal_refreshes_cards_and_closes_editor(self):
        editor = ExerciseGoalWindow.__new__(ExerciseGoalWindow)
        editor.journal = Journal(exercises=[Exercise("Гамма")])
        editor.window = Mock()
        editor.save_journal = Mock()
        editor.refresh = Mock()
        editor.apply_change(lambda: editor.journal.set_exercise_goal("Гамма", 100, "четверти"))
        editor.save_journal.assert_called_once()
        editor.refresh.assert_called_once()
        editor.window.destroy.assert_called_once()


class PlanScrollbarTest(unittest.TestCase):
    def test_scrollbar_is_hidden_when_all_rows_fit(self):
        app = GuitarPracticeApp.__new__(GuitarPracticeApp)
        app.plan_scrollbar = Mock()
        app.update_plan_scrollbar("0.0", "1.0")
        app.plan_scrollbar.grid_remove.assert_called_once()
        app.plan_scrollbar.grid.assert_not_called()

    def test_scrollbar_is_shown_when_rows_overflow(self):
        app = GuitarPracticeApp.__new__(GuitarPracticeApp)
        app.plan_scrollbar = Mock()
        app.update_plan_scrollbar("0.0", "0.6")
        app.plan_scrollbar.grid.assert_called_once()
        app.plan_scrollbar.grid_remove.assert_not_called()


class GoalGridTest(unittest.TestCase):
    def test_six_cards_use_two_rows_and_three_columns(self):
        panel = ExerciseGoalsPanel.__new__(ExerciseGoalsPanel)
        panel.winfo_width = Mock(return_value=1040)
        panel.cards = Mock()
        panel.card_widgets = [Mock() for _ in range(6)]
        panel.layout_shape = (0, 0)
        panel.layout_cards()
        self.assertEqual(panel.layout_shape, (3, 2))
        panel.card_widgets[5].grid.assert_called_once_with(
            row=1, column=2, sticky="nsew", padx=6, pady=4,
        )
