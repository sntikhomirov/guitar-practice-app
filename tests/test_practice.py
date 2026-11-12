import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from guitar_practice_app.gui import GuitarPracticeApp
from guitar_practice_app.models import Exercise, TempoLog
from guitar_practice_app.practice import PracticeController
from guitar_practice_app.services import AttemptStats, Journal
from guitar_practice_app.storage import JournalStorage


class PracticeControllerTest(unittest.TestCase):
    def setUp(self):
        self.journal = Journal(exercises=[Exercise("Гамма"), Exercise("Легато")])
        self.stats = AttemptStats()
        self.save = Mock()
        self.practice = PracticeController(self.journal, self.save, self.stats)
        self.params = ("Гамма", "80", "восьмые", "2026-11-11")
        self.day = date(2026, 11, 11)

    def result(self, tempo="80"):
        self.stats.add_success()
        return self.practice.save_result("Гамма", tempo, "восьмые", self.params[3])

    def test_multiple_tempos_belong_to_one_unfinished_session(self):
        first = self.result()
        second = self.result("90")
        self.assertEqual(first.session_id, second.session_id)
        self.assertEqual(len(self.journal.sessions), 1)
        self.assertEqual(self.practice.session.status, "in_progress")
        self.assertEqual(self.stats.total(), 0)
        self.assertEqual(self.stats.success_streak, 0)
        self.assertIn("Гамма", [item.exercise for item in self.journal.practice_plan(as_of=self.day)])

    def test_repeated_tempo_stays_as_separate_result(self):
        self.result()
        self.result()
        self.assertEqual(len(self.journal.logs), 2)
        self.assertEqual(self.journal.weekly_practice_count("Гамма", self.day), 1)

    def test_finish_without_new_attempts_does_not_duplicate_result(self):
        self.result()
        self.practice.finish(*self.params)
        self.assertEqual(len(self.journal.logs), 1)
        self.assertEqual(self.journal.sessions[0].status, "completed")
        self.assertIsNone(self.practice.session)
        self.assertNotIn("Гамма", [item.exercise for item in self.journal.practice_plan(as_of=self.day)])
        self.assertIn("Гамма", [item.exercise for item in self.journal.practice_plan(as_of=date(2026, 11, 12))])

    def test_finish_saves_final_attempts_and_completion_in_one_write(self):
        self.result()
        self.stats.add_fail()
        self.save.reset_mock()
        self.practice.finish("Гамма", "90", "восьмые", self.params[3])
        self.save.assert_called_once()
        self.assertEqual(len(self.journal.logs), 2)
        self.assertEqual(self.journal.logs[-1].fail, 1)
        self.assertEqual(self.journal.sessions[0].status, "completed")
        self.assertEqual(self.stats.total(), 0)

    def test_finish_can_save_first_and_only_result(self):
        self.stats.add_success()
        self.practice.finish(*self.params)
        self.assertEqual(len(self.journal.logs), 1)
        self.assertEqual(self.journal.sessions[0].status, "completed")

    def test_empty_session_cannot_be_finished(self):
        with self.assertRaises(ValueError):
            self.practice.finish(*self.params)
        self.assertEqual(self.journal.logs, [])
        self.assertEqual(self.journal.sessions, [])
        self.save.assert_not_called()

    def test_save_error_rolls_back_first_result_and_preserves_attempts(self):
        self.stats.add_success()
        self.save.side_effect = OSError("Нет места")
        with self.assertRaises(OSError):
            self.practice.save_result(*self.params)
        self.assertEqual(self.journal.logs, [])
        self.assertEqual(self.journal.sessions, [])
        self.assertIsNone(self.practice.session_id)
        self.assertEqual(self.stats.total(), 1)

    def test_failed_finish_preserves_saved_results_attempts_and_open_status(self):
        self.result()
        original = list(self.journal.logs)
        self.stats.add_fail()
        self.save.side_effect = OSError("Нет места")
        with self.assertRaises(OSError):
            self.practice.finish(*self.params)
        self.assertEqual(self.journal.logs, original)
        self.assertEqual(self.practice.session.status, "in_progress")
        self.assertEqual(self.stats.fail, 1)

    def test_failed_finish_without_new_attempts_does_not_mark_complete(self):
        self.result()
        self.save.side_effect = OSError("Ошибка")
        with self.assertRaises(OSError):
            self.practice.finish(*self.params)
        self.assertEqual(self.practice.session.status, "in_progress")
        self.assertEqual(len(self.journal.logs), 1)

    def test_retry_after_error_does_not_duplicate_result(self):
        self.stats.add_success()
        self.save.side_effect = OSError("Нет места")
        with self.assertRaises(OSError):
            self.practice.save_result(*self.params)
        self.save.side_effect = None
        self.practice.save_result(*self.params)
        self.assertEqual(len(self.journal.logs), 1)

    def test_interrupt_is_not_completion_and_new_attempt_has_new_id(self):
        original = self.result()
        self.practice.interrupt()
        self.assertEqual(self.journal.sessions[0].status, "interrupted")
        self.assertIn("Гамма", [item.exercise for item in self.journal.practice_plan(as_of=self.day)])
        new = self.result()
        self.assertNotEqual(original.session_id, new.session_id)
        self.assertEqual(self.journal.weekly_practice_count("Гамма", self.day), 2)

    def test_failure_to_interrupt_does_not_forget_current_session(self):
        self.result()
        session_id = self.practice.session_id
        self.save.side_effect = OSError("Ошибка")
        with self.assertRaises(OSError):
            self.practice.interrupt()
        self.assertEqual(self.practice.session_id, session_id)
        self.assertEqual(self.practice.session.status, "in_progress")

    def test_repeat_after_completion_is_new_session(self):
        self.result()
        first = self.practice.session_id
        self.practice.finish(*self.params)
        self.result()
        self.assertNotEqual(self.practice.session_id, first)
        self.assertEqual(self.journal.weekly_practice_count("Гамма", self.day), 2)

    def test_goal_does_not_hide_active_session(self):
        self.journal.set_exercise_goal("Гамма", 80, "восьмые", as_of=self.day)
        self.result()
        self.assertNotIn("Гамма", [item.exercise for item in self.journal.practice_plan(as_of=self.day)])
        plan = self.journal.practice_plan(as_of=self.day, active_session_id=self.practice.session_id)
        self.assertIn("Гамма", [item.exercise for item in plan])
        self.practice.finish(*self.params)
        self.assertNotIn("Гамма", [item.exercise for item in self.journal.practice_plan(as_of=self.day)])

    def test_date_and_exercise_cannot_change_inside_existing_session(self):
        self.result()
        for params in (("Гамма", "90", "восьмые", "2026-11-12"),
                       ("Легато", "90", "восьмые", self.params[3])):
            self.stats.add_success()
            with self.subTest(params=params), self.assertRaises(ValueError):
                self.practice.save_result(*params)
        self.assertEqual(len(self.journal.logs), 1)

    def test_finish_without_attempts_cannot_target_another_exercise(self):
        self.result()
        with self.assertRaises(ValueError):
            self.practice.finish("Легато", "80", "восьмые", self.params[3])
        self.assertEqual(self.practice.session.status, "in_progress")

    def test_duration_can_change_between_results(self):
        self.result()
        self.stats.add_success()
        self.practice.save_result("Гамма", "60", "шестнадцатые", self.params[3])
        self.assertEqual([log.duration for log in self.journal.logs], ["восьмые", "шестнадцатые"])
        self.assertEqual(len(self.journal.sessions), 1)

    def test_duplicate_sessions_in_one_day_are_not_collapsed_after_reload(self):
        self.result()
        self.practice.finish(*self.params)
        self.result()
        self.practice.finish(*self.params)
        loaded = Journal(self.journal.exercises, self.journal.logs, self.journal.sessions)
        self.assertEqual(len(loaded.sessions), 2)
        self.assertEqual(loaded.weekly_practice_count("Гамма", self.day), 2)

    def test_history_date_edit_moves_entire_session(self):
        self.result()
        self.result("90")
        self.practice.finish(*self.params)
        self.journal.update_tempo_log(0, 85, "восьмые", "2026-11-10", 2, 1)
        self.assertEqual([log.date for log in self.journal.logs], ["2026-11-10", "2026-11-10"])
        self.assertEqual([log.tempo for log in self.journal.logs], [85, 90])
        self.assertEqual(self.journal.sessions[0].date, "2026-11-10")
        self.assertIn("Гамма", [item.exercise for item in self.journal.practice_plan(as_of=self.day)])

    def test_last_result_deletion_removes_completion(self):
        self.result()
        self.result("90")
        self.practice.finish(*self.params)
        self.journal.delete_tempo_log(0)
        self.assertEqual(len(self.journal.sessions), 1)
        self.journal.delete_tempo_log(0)
        self.assertEqual(self.journal.sessions, [])
        self.assertEqual(self.journal.weekly_practice_count("Гамма", self.day), 0)
        self.assertIn("Гамма", [item.exercise for item in self.journal.practice_plan(as_of=self.day)])

    def test_manual_result_forms_separate_completed_session(self):
        self.result()
        active_id = self.practice.session_id
        manual = self.journal.add_tempo_log("Гамма", 90, "восьмые", self.params[3])
        self.assertNotEqual(manual.session_id, active_id)
        self.assertEqual(self.journal.session_by_id(manual.session_id).status, "completed")
        self.assertEqual(self.practice.session.status, "in_progress")


class SessionStorageTest(unittest.TestCase):
    def test_old_journal_migrates_only_on_save_and_keeps_records(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "journal.json"
            path.write_text('{"version": 1, "exercises": [{"name": "Гамма"}], "logs": ['
                            '{"exercise":"Гамма","tempo":80,"duration":"восьмые","date":"2026-11-11"},'
                            '{"exercise":"Гамма","tempo":90,"duration":"восьмые","date":"2026-11-11"}]}',
                            encoding="utf-8")
            before = path.read_bytes()
            storage = JournalStorage(path)
            journal = Journal(*storage.load_state())
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(len(journal.sessions), 1)
            storage.save(journal.exercises, journal.logs, journal.sessions)
            loaded = Journal(*storage.load_state())
            self.assertEqual(loaded.sessions, journal.sessions)
            self.assertEqual(loaded.logs, journal.logs)

    def test_legacy_logs_are_grouped_by_exercise_and_date_without_loss(self):
        logs = [TempoLog("Гамма", 80, "восьмые", "2026-11-11", 1, 2),
                TempoLog("Гамма", 90, "восьмые", "2026-11-11", 3, 4),
                TempoLog("Легато", 80, "восьмые", "2026-11-11"),
                TempoLog("Гамма", 80, "восьмые", "2026-11-10")]
        journal = Journal([Exercise("Гамма"), Exercise("Легато")], logs)
        self.assertEqual(len(journal.sessions), 3)
        self.assertEqual(journal.logs[0].session_id, journal.logs[1].session_id)
        self.assertEqual([log.tempo for log in journal.logs], [80, 90, 80, 80])
        self.assertEqual([(log.success, log.fail) for log in journal.logs], [(1, 2), (3, 4), (0, 0), (0, 0)])
        self.assertTrue(all(session.status == "completed" for session in journal.sessions))

    def test_restart_interrupts_without_resuming_or_marking_complete(self):
        journal = Journal([Exercise("Гамма")])
        stats = AttemptStats()
        with tempfile.TemporaryDirectory() as folder:
            storage = JournalStorage(Path(folder) / "journal.json")
            practice = PracticeController(journal, lambda: storage.save(journal.exercises, journal.logs, journal.sessions), stats)
            stats.add_success()
            practice.save_result("Гамма", 80, "восьмые", "2026-11-11")
            loaded = Journal(*storage.load_state())
            next_practice = PracticeController(loaded, Mock(), AttemptStats())
            self.assertIsNone(next_practice.session)
            self.assertEqual(loaded.sessions[0].status, "interrupted")
            self.assertEqual(len(loaded.logs), 1)
            self.assertIn("Гамма", [item.exercise for item in loaded.practice_plan(as_of=date(2026, 11, 11))])

    def test_completed_session_survives_reload(self):
        journal = Journal([Exercise("Гамма")])
        stats = AttemptStats()
        with tempfile.TemporaryDirectory() as folder:
            storage = JournalStorage(Path(folder) / "journal.json")
            practice = PracticeController(journal, lambda: storage.save(journal.exercises, journal.logs, journal.sessions), stats)
            stats.add_success()
            practice.finish("Гамма", 80, "восьмые", "2026-11-11")
            loaded = Journal(*storage.load_state())
        self.assertEqual(loaded.logs, journal.logs)
        self.assertEqual(loaded.sessions, journal.sessions)


class Field:
    def __init__(self, value=""):
        self.value = value
        self.state = "normal"

    def get(self):
        return self.value

    def set(self, value):
        self.value = str(value)

    def delete(self, *args):
        self.value = ""

    def insert(self, index, value):
        self.value = str(value)

    def configure(self, **kwargs):
        self.state = kwargs.get("state", self.state)


class PracticeWorkflowTest(unittest.TestCase):
    def setUp(self):
        app = GuitarPracticeApp.__new__(GuitarPracticeApp)
        self.app = app
        app.root = Mock()
        app.journal = Journal([Exercise("Гамма"), Exercise("Легато")])
        app.stats = AttemptStats()
        app.save_journal = Mock()
        app.practice = PracticeController(app.journal, app.save_journal, app.stats)
        app._changing_parameters = False
        app._session_parameters = ("Гамма", "80", "восьмые", "2026-11-11")
        app.session_exercise_combobox, app.session_tempo_entry, app.session_duration_combobox, app.session_date_entry = (
            Field(value) for value in app._session_parameters)
        app.session_status = Mock()
        app.update_stats = Mock()
        app.refresh_journal_table = Mock()
        app.refresh_practice_plan = Mock()

    def test_save_preserves_parameters_locks_date_and_does_not_advance(self):
        app = self.app
        app.stats.add_success()
        original = app.read_session_parameters()
        app.save_practice_session()
        self.assertEqual(app.read_session_parameters(), original)
        self.assertEqual(app.session_date_entry.state, "readonly")
        self.assertEqual(app.stats.total(), 0)
        app.refresh_practice_plan.assert_called_with(prefill=False)

    def test_tempo_change_saves_attempts_using_previous_tempo(self):
        app = self.app
        app.stats.add_success()
        app.session_tempo_entry.set("90")
        with patch("guitar_practice_app.gui.ask_unsaved_attempts", return_value="save"):
            self.assertTrue(app.resolve_session_parameters())
        self.assertEqual(app.journal.logs[0].tempo, 80)
        self.assertEqual(app.session_tempo_entry.get(), "90")
        self.assertEqual(app.stats.total(), 0)

    def test_history_edit_does_not_accept_unconfirmed_tempo_for_active_attempts(self):
        app = self.app
        app.stats.add_success()
        app.save_practice_session()
        app.stats.add_fail()
        app.session_tempo_entry.set("100")
        app.journal.update_tempo_log(0, 85, "восьмые", "2026-11-11", 1, 0)
        app.on_history_changed()

        self.assertEqual(app._session_parameters[1], "80")
        self.assertEqual(app.session_tempo_entry.get(), "100")
        self.assertEqual(app.stats.fail, 1)
        with patch("guitar_practice_app.gui.ask_unsaved_attempts", return_value="save") as prompt:
            app.save_practice_session()
        prompt.assert_called_once_with(app.root)
        self.assertEqual([log.tempo for log in app.journal.logs], [85, 80])
        self.assertEqual(app.journal.logs[-1].fail, 1)

    def test_date_sync_preserves_confirmed_exercise_tempo_and_duration(self):
        app = self.app
        app.stats.add_success()
        app.save_practice_session()
        app.session_exercise_combobox.set("Легато")
        app.session_tempo_entry.set("100")
        app.session_duration_combobox.set("четверти")
        app.journal.update_tempo_log(0, 80, "восьмые", "2026-11-10", 1, 0)
        app.sync_session_date()
        self.assertEqual(app._session_parameters, ("Гамма", "80", "восьмые", "2026-11-10"))
        self.assertEqual(app.read_session_parameters(), ("Легато", "100", "четверти", "2026-11-10"))

    def test_parameter_change_cancel_restores_previous_values_and_attempts(self):
        app = self.app
        app.stats.add_fail()
        app.session_duration_combobox.set("четверти")
        with patch("guitar_practice_app.gui.ask_unsaved_attempts", return_value=None):
            self.assertFalse(app.resolve_session_parameters())
        self.assertEqual(app.session_duration_combobox.get(), "восьмые")
        self.assertEqual(app.stats.fail, 1)
        self.assertEqual(app.journal.logs, [])

    def test_parameter_change_discard_does_not_create_a_result(self):
        app = self.app
        app.stats.add_success()
        app.session_tempo_entry.set("90")
        with patch("guitar_practice_app.gui.ask_unsaved_attempts", return_value="discard"):
            self.assertTrue(app.resolve_session_parameters())
        self.assertEqual(app.stats.total(), 0)
        self.assertEqual(app.journal.logs, [])

    def test_parameter_change_save_error_restores_fields_and_attempts(self):
        app = self.app
        app.stats.add_success()
        app.session_tempo_entry.set("90")
        app.save_journal.side_effect = OSError("Ошибка")
        with patch("guitar_practice_app.gui.ask_unsaved_attempts", return_value="save"), \
                patch("guitar_practice_app.gui.messagebox.showerror"):
            self.assertFalse(app.resolve_session_parameters())
        self.assertEqual(app.session_tempo_entry.get(), "80")
        self.assertEqual(app.stats.total(), 1)
        self.assertEqual(app.journal.logs, [])

    def test_locked_date_is_not_changed_programmatically(self):
        app = self.app
        app.stats.add_success()
        app.save_practice_session()
        app.session_date_entry.set("2026-11-12")
        app.resolve_session_parameters()
        self.assertEqual(app.session_date_entry.get(), "2026-11-11")

    def test_switching_exercise_interrupts_old_session(self):
        app = self.app
        app.stats.add_success()
        app.save_practice_session()
        app.session_exercise_combobox.set("Легато")
        self.assertTrue(app.resolve_session_parameters())
        self.assertEqual(app.journal.sessions[0].status, "interrupted")
        self.assertIsNone(app.practice.session)
        self.assertEqual(app.session_date_entry.state, "normal")

    def test_save_failure_keeps_attempts_and_does_not_advance(self):
        app = self.app
        app.stats.add_success()
        app.save_journal.side_effect = OSError("Ошибка записи")
        with patch("guitar_practice_app.gui.messagebox.showerror"):
            app.save_practice_session()
        self.assertEqual(app.stats.total(), 1)
        self.assertEqual(app.journal.logs, [])
        app.refresh_practice_plan.assert_not_called()

    def test_finish_advances_only_after_success(self):
        app = self.app
        app.stats.add_success()
        app.finish_exercise()
        self.assertEqual(app.journal.sessions[0].status, "completed")
        app.refresh_practice_plan.assert_called_once_with(prefill=True)

    def test_finish_after_tempo_edit_and_confirmation_completes_in_one_click(self):
        app = self.app
        app.stats.add_success()
        app.save_practice_session()
        app.stats.add_fail()
        app.session_tempo_entry.set("90")
        with patch("guitar_practice_app.gui.ask_unsaved_attempts", return_value="save") as prompt:
            app.finish_exercise()
        prompt.assert_called_once()
        self.assertEqual(app.journal.sessions[0].status, "completed")
        self.assertIsNone(app.practice.session)
        self.assertEqual(len(app.journal.logs), 2)
        self.assertEqual([log.tempo for log in app.journal.logs], [80, 80])
        self.assertEqual([(log.success, log.fail) for log in app.journal.logs], [(1, 0), (0, 1)])
        self.assertNotIn("Гамма", [item.exercise for item in app.journal.practice_plan(as_of=date(2026, 11, 11))])
        app.refresh_practice_plan.assert_called_with(prefill=True)

    def test_save_after_tempo_edit_does_not_save_twice_or_show_empty_counter_error(self):
        app = self.app
        app.stats.add_success()
        app.session_tempo_entry.set("90")
        with patch("guitar_practice_app.gui.ask_unsaved_attempts", return_value="save"), \
                patch("guitar_practice_app.gui.messagebox.showerror") as error:
            app.save_practice_session()
        self.assertEqual(len(app.journal.logs), 1)
        self.assertEqual(app.journal.logs[0].tempo, 80)
        self.assertEqual(app.session_tempo_entry.get(), "90")
        error.assert_not_called()

    def test_cancel_tempo_confirmation_does_not_finish(self):
        app = self.app
        app.stats.add_success()
        app.session_tempo_entry.set("90")
        with patch("guitar_practice_app.gui.ask_unsaved_attempts", return_value=None):
            app.finish_exercise()
        self.assertEqual(app.stats.total(), 1)
        self.assertEqual(app.journal.sessions, [])
        app.refresh_practice_plan.assert_not_called()

    def test_counter_fields_have_no_focus_out_dialog_binding(self):
        app = self.app
        app.counter_tab = Mock()
        app.durations = ["восьмые"]
        app.create_practice_plan_panel = Mock()
        tempo, log_date = Mock(), Mock()
        with patch.multiple("guitar_practice_app.gui.ttk", Frame=Mock(), LabelFrame=Mock(),
                            Label=Mock(), Combobox=Mock(), Button=Mock(), Entry=Mock(side_effect=[tempo, log_date])), \
                patch.multiple("guitar_practice_app.gui.tk", Label=Mock(), Frame=Mock(), Button=Mock()):
            app.create_counter_tab()
        for field in (tempo, log_date):
            self.assertNotIn("<FocusOut>", [call.args[0] for call in field.bind.call_args_list])
            field.bind.assert_any_call("<Return>", app.on_session_parameters_changed)

    def test_empty_finish_shows_error_and_does_not_advance(self):
        app = self.app
        with patch("guitar_practice_app.gui.messagebox.showerror") as error:
            app.finish_exercise()
        error.assert_called_once()
        app.refresh_practice_plan.assert_not_called()

    def test_close_save_preserves_result_but_does_not_complete(self):
        app = self.app
        app.stats.add_success()
        with patch("guitar_practice_app.gui.ask_unsaved_attempts", return_value="save"):
            app.close_app()
        self.assertEqual(len(app.journal.logs), 1)
        self.assertEqual(app.journal.sessions[0].status, "interrupted")
        app.root.destroy.assert_called_once()

    def test_close_cancel_keeps_window_and_attempts(self):
        app = self.app
        app.stats.add_success()
        with patch("guitar_practice_app.gui.ask_unsaved_attempts", return_value=None):
            app.close_app()
        app.root.destroy.assert_not_called()
        self.assertEqual(app.stats.total(), 1)

    def test_close_discard_keeps_previous_results_without_completion(self):
        app = self.app
        app.stats.add_success()
        app.save_practice_session()
        app.stats.add_fail()
        with patch("guitar_practice_app.gui.ask_unsaved_attempts", return_value="discard"):
            app.close_app()
        self.assertEqual(len(app.journal.logs), 1)
        self.assertEqual(app.journal.sessions[0].status, "interrupted")
        app.root.destroy.assert_called_once()

    def test_close_failure_keeps_window_and_attempts(self):
        app = self.app
        app.stats.add_success()
        app.save_journal.side_effect = OSError("Ошибка")
        with patch("guitar_practice_app.gui.ask_unsaved_attempts", return_value="save"), \
                patch("guitar_practice_app.gui.messagebox.showerror"):
            app.close_app()
        app.root.destroy.assert_not_called()
        self.assertEqual(app.stats.total(), 1)

    def test_failed_history_change_restores_session_metadata(self):
        from guitar_practice_app.history_ui import ExerciseHistoryWindow

        app = self.app
        app.stats.add_success()
        app.save_practice_session()
        original_sessions = list(app.journal.sessions)
        history = ExerciseHistoryWindow.__new__(ExerciseHistoryWindow)
        history.journal = app.journal
        history.window = Mock()
        history.on_change = Mock(side_effect=OSError("Ошибка"))
        history.refresh = Mock()
        with patch("guitar_practice_app.history_ui.messagebox.showerror"):
            history.apply_change(lambda: app.journal.delete_tempo_log(0))
        self.assertEqual(app.journal.sessions, original_sessions)
        self.assertEqual(len(app.journal.logs), 1)

    def test_failed_load_cannot_overwrite_journal(self):
        app = self.app
        app._storage_load_failed = True
        app.storage = Mock()
        with self.assertRaises(OSError):
            GuitarPracticeApp.save_journal(app)
        app.storage.save.assert_not_called()
