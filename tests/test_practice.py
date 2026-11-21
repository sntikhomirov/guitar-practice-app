"""Practice workflow regressions for immediately persisted individual attempts."""

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from guitar_practice_app.gui import GuitarPracticeApp
from guitar_practice_app.practice import PracticeController
from guitar_practice_app.models import Exercise, TempoLog
from guitar_practice_app.services import AttemptStats, Journal
from guitar_practice_app.storage import JournalStorage


class LivePracticeTest(unittest.TestCase):
    def setUp(self):
        self.journal = Journal([Exercise("Гамма"), Exercise("Легато")])
        self.stats = AttemptStats()
        self.save = Mock()
        self.practice = PracticeController(self.journal, self.save, self.stats)
        self.params = ("Гамма", "80", "восьмые", "2026-11-21", "")

    def record(self, success=True, **kwargs):
        return self.practice.record_attempt(*self.params[:4], success, self.params[4],
                                            recorded_at="2026-11-21T12:00:00+03:00", **kwargs)

    def test_first_attempt_creates_session_and_exact_log(self):
        attempt = self.record()
        self.save.assert_called_once()
        self.assertEqual(self.practice.session.id, attempt.session_id)
        self.assertEqual(self.stats.total(), 1)
        self.assertEqual(self.journal.logs[0].success, 1)
        self.assertTrue(self.journal.logs[0].exact)

    def test_attempt_order_is_preserved_not_aggregated_away(self):
        for success in (True, False, True):
            self.record(success)
        self.assertEqual([a.success for a in self.journal.attempts], [True, False, True])
        self.assertEqual([a.sequence for a in self.journal.attempts], [1, 2, 3])
        self.assertEqual(len(self.journal.sessions), 1)
        self.assertEqual((self.journal.logs[0].success, self.journal.logs[0].fail), (2, 1))

    def test_close_approach_never_records_twice(self):
        self.record()
        self.practice.save_result()
        self.assertEqual(len(self.journal.attempts), 1)
        self.assertEqual(len(self.journal.logs), 1)
        self.assertEqual(self.stats.total(), 0)
        self.assertEqual(self.practice.session.status, "in_progress")
        self.record(False)
        self.assertEqual(len(self.journal.logs), 2)
        self.assertEqual(len(self.journal.sessions), 1)

    def test_reset_does_not_remove_attempts_or_close_approach(self):
        self.record()
        approach = self.practice.approach_id
        self.practice.reset_counter()
        self.assertEqual(self.stats.total(), 0)
        self.assertEqual(len(self.journal.attempts), 1)
        self.assertEqual(self.practice.approach_id, approach)
        self.record(False)
        self.assertEqual(self.stats.total(), 1)
        self.assertEqual(self.stats.fail, 1)
        self.assertEqual(len(self.journal.attempts), 2)
        self.assertEqual(len(self.journal.logs), 1)

    def test_finish_requires_results_and_is_single_write(self):
        with self.assertRaises(ValueError):
            self.practice.finish()
        self.record()
        self.save.reset_mock()
        self.practice.finish()
        self.save.assert_called_once()
        self.assertEqual(len(self.journal.attempts), 1)
        self.assertEqual(self.journal.sessions[0].status, "completed")
        self.assertNotIn("Гамма", [p.exercise for p in self.journal.practice_plan(as_of=date(2026, 11, 21))])

    def test_failed_attempt_leaves_no_session_log_or_sequence_gap(self):
        self.save.side_effect = OSError("Диск заполнен")
        with self.assertRaises(OSError):
            self.record()
        self.assertEqual(self.journal.attempts, [])
        self.assertEqual(self.journal.logs, [])
        self.assertEqual(self.journal.sessions, [])
        self.assertEqual(self.stats.total(), 0)
        self.assertIsNone(self.practice.session_id)
        self.assertEqual(self.journal.settings["next_attempt_sequence"], 1)
        self.save.side_effect = None
        self.assertEqual(self.record().sequence, 1)

    def test_failed_later_attempt_preserves_previous_events_and_counter(self):
        self.record()
        snapshot = self.journal.snapshot()
        self.save.side_effect = OSError("Ошибка")
        with self.assertRaises(OSError):
            self.record(False)
        self.assertEqual(self.journal.snapshot(), snapshot)
        self.assertEqual(self.stats.total(), 1)

    def test_failed_finish_does_not_mark_complete_or_duplicate_events(self):
        self.record()
        self.save.side_effect = OSError("Ошибка")
        with self.assertRaises(OSError):
            self.practice.finish()
        self.assertEqual(self.practice.session.status, "in_progress")
        self.assertEqual(len(self.journal.attempts), 1)
        self.assertEqual(self.stats.total(), 1)

    def test_invalid_fields_are_rejected_before_counting(self):
        for tempo, duration in (("", "восьмые"), ("x", "восьмые"), ("0", "восьмые"), ("80", "bad")):
            with self.subTest(tempo=tempo), self.assertRaises(ValueError):
                self.practice.record_attempt("Гамма", tempo, duration, "2026-11-21", True)
        self.assertEqual(self.stats.total(), 0)
        self.assertEqual(self.journal.attempts, [])

    def test_change_tempo_closes_approach_but_retains_session_and_events(self):
        self.record()
        session = self.practice.session_id
        new = ("Гамма", "90", "восьмые", "2026-11-21", "")
        self.practice.change_parameters(self.params, new)
        self.assertEqual(self.stats.total(), 0)
        self.assertEqual(self.practice.session_id, session)
        self.assertEqual(len(self.journal.attempts), 1)
        self.practice.record_attempt(*new[:4], False)
        self.assertEqual([log.tempo for log in self.journal.logs], [80, 90])

    def test_direct_parameter_change_without_closing_approach_is_rejected(self):
        self.record()
        with self.assertRaises(ValueError):
            self.practice.record_attempt("Гамма", 90, "восьмые", "2026-11-21", True)
        self.assertEqual(len(self.journal.attempts), 1)

    def test_switch_exercise_interrupts_does_not_complete(self):
        self.record()
        self.practice.change_parameters(self.params, ("Легато", "80", "восьмые", "2026-11-21", ""))
        self.assertEqual(self.journal.sessions[0].status, "interrupted")
        self.assertIsNone(self.practice.session)
        self.assertEqual(self.stats.total(), 0)

    def test_failed_switch_preserves_session_counter_and_parameters(self):
        self.record()
        session = self.practice.session_id
        self.save.side_effect = OSError("Ошибка")
        with self.assertRaises(OSError):
            self.practice.change_parameters(self.params, ("Легато", "80", "восьмые", "2026-11-21", ""))
        self.assertEqual(self.practice.session_id, session)
        self.assertEqual(self.stats.total(), 1)

    def test_date_locked_after_first_click_not_after_save(self):
        self.record()
        with self.assertRaises(ValueError):
            self.practice.change_parameters(self.params, ("Гамма", "80", "восьмые", "2026-11-22", ""))
        self.assertEqual(self.practice.session.date, "2026-11-21")

    def test_goal_cannot_hide_active_session(self):
        self.journal.set_exercise_goal("Гамма", 80, "восьмые", as_of=date(2026, 11, 21))
        self.record()
        plan = self.journal.practice_plan(as_of=date(2026, 11, 21), active_session_id=self.practice.session_id)
        self.assertIn("Гамма", [p.exercise for p in plan])

    def test_restart_keeps_events_but_does_not_resume_session(self):
        self.record()
        with tempfile.TemporaryDirectory() as folder:
            storage = JournalStorage(Path(folder) / "journal.json")
            storage.save_journal(self.journal)
            loaded = storage.load_journal()
        self.assertEqual(loaded.attempts, self.journal.attempts)
        self.assertEqual(loaded.sessions[0].status, "interrupted")
        self.assertEqual(len(loaded.logs), 1)
        self.assertIsNone(PracticeController(loaded, Mock(), AttemptStats()).session)

    def test_history_date_move_keeps_real_timestamps(self):
        event = self.record()
        self.journal.update_tempo_log(0, 80, "восьмые", "2026-11-20", 1, 0)
        self.assertEqual(self.journal.attempts[0].recorded_at, event.recorded_at)
        self.assertEqual(self.journal.sessions[0].date, "2026-11-20")
        self.journal.rebuild_exact_logs()
        self.assertEqual(self.journal.logs[0].date, "2026-11-20")

    def test_correction_updates_current_counter_and_series(self):
        first = self.record()
        self.record(False)
        self.journal.correct_attempt(first.id, False)
        self.practice.sync_stats()
        self.assertEqual((self.stats.success, self.stats.fail, self.stats.fail_streak), (0, 2, 2))

    def test_deleting_last_attempt_removes_session_and_allows_new_attempt(self):
        event = self.record()
        self.journal.delete_attempt(event.id)
        self.practice.sync_stats()
        self.assertEqual(self.journal.logs, [])
        self.assertIsNone(self.practice.session)
        self.record()
        self.assertEqual(self.journal.attempts[0].sequence, 2)


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
        app._session_parameters = ("Гамма", "80", "восьмые", "2026-11-21", "")
        app.session_exercise_combobox, app.session_tempo_entry, app.session_duration_combobox, app.session_date_entry = (
            Field(value) for value in app._session_parameters[:4])
        self.scope = ""
        app.current_scope_id = lambda: self.scope
        def scopes(exercise, scope_id=""):
            self.scope = scope_id
        app.refresh_scopes = scopes
        app.session_status = Mock()
        app.update_stats = Mock()
        app.refresh_journal_table = Mock()
        app.refresh_practice_plan = Mock()

    def test_plus_is_saved_immediately_and_locks_date(self):
        app = self.app
        app.add_success()
        self.assertEqual(len(app.journal.attempts), 1)
        self.assertEqual(app.session_date_entry.state, "readonly")
        app.save_journal.assert_called_once()

    def test_repeated_save_never_duplicates_individual_attempts(self):
        app = self.app
        app.add_success()
        app.save_practice_session()
        app.add_fail()
        app.save_practice_session()
        self.assertEqual([a.tempo for a in app.journal.attempts], [80, 80])
        self.assertEqual(len(app.journal.logs), 2)
        self.assertEqual(len(app.journal.sessions), 1)

    def test_save_keeps_form_and_does_not_advance(self):
        app = self.app
        app.add_success()
        params = app.read_session_parameters()
        app.save_practice_session()
        self.assertEqual(app.read_session_parameters(), params)
        self.assertEqual(app.stats.total(), 0)
        app.refresh_practice_plan.assert_called_with(prefill=False)

    def test_change_tempo_without_dialog_keeps_previous_attempts(self):
        app = self.app
        app.add_success()
        app.session_tempo_entry.set("100")
        app.add_fail()
        self.assertEqual([a.tempo for a in app.journal.attempts], [80, 100])
        self.assertEqual((app.stats.success, app.stats.fail), (0, 1))

    def test_history_refresh_does_not_reassign_previous_tempo(self):
        app = self.app
        app.add_success()
        app.session_tempo_entry.set("100")
        app.on_history_changed()
        self.assertEqual(app._session_parameters[1], "80")
        self.assertEqual(app.journal.attempts[0].tempo, 80)
        app.add_fail()
        self.assertEqual([a.tempo for a in app.journal.attempts], [80, 100])

    def test_date_sync_preserves_scope_and_other_unconfirmed_fields(self):
        app = self.app
        app.add_success()
        app.session_tempo_entry.set("100")
        app.journal.update_tempo_log(0, 80, "восьмые", "2026-11-20", 1, 0)
        app.sync_session_date()
        self.assertEqual(app._session_parameters, ("Гамма", "80", "восьмые", "2026-11-20", ""))
        self.assertEqual(app.session_tempo_entry.get(), "100")

    def test_finish_after_tempo_edit_needs_one_click_and_never_reassigns_attempt(self):
        app = self.app
        app.add_success()
        app.save_practice_session()
        app.add_fail()
        app.session_tempo_entry.set("100")
        app.finish_exercise()
        self.assertEqual([a.tempo for a in app.journal.attempts], [80, 80])
        self.assertEqual(app.journal.sessions[0].status, "completed")
        app.refresh_practice_plan.assert_called_with(prefill=True)

    def test_reset_only_resets_display(self):
        app = self.app
        app.add_success()
        app.reset()
        self.assertEqual(app.stats.total(), 0)
        self.assertEqual(len(app.journal.attempts), 1)

    def test_close_needs_no_save_prompt_and_preserves_events(self):
        app = self.app
        app.add_success()
        app.close_app()
        app.root.destroy.assert_called_once()
        self.assertEqual(app.journal.sessions[0].status, "interrupted")
        self.assertEqual(len(app.journal.attempts), 1)

    def test_close_failure_keeps_window_open(self):
        app = self.app
        app.add_success()
        app.save_journal.side_effect = OSError("Ошибка")
        with patch("guitar_practice_app.gui.messagebox.showerror"):
            app.close_app()
        app.root.destroy.assert_not_called()
        self.assertEqual(app.practice.session.status, "in_progress")

    def test_failed_click_does_not_increment_or_create_event(self):
        app = self.app
        app.save_journal.side_effect = OSError("Ошибка")
        with patch("guitar_practice_app.gui.messagebox.showerror") as error:
            app.add_success()
        error.assert_called_once()
        self.assertEqual(app.stats.total(), 0)
        self.assertEqual(app.journal.attempts, [])

    def test_invalid_tempo_rejected_before_click(self):
        app = self.app
        app.session_tempo_entry.set("bad")
        with patch("guitar_practice_app.gui.messagebox.showerror"):
            app.add_success()
        self.assertEqual(app.stats.total(), 0)
        self.assertEqual(app.journal.attempts, [])

    def test_finish_failure_does_not_advance(self):
        app = self.app
        app.add_success()
        app.refresh_practice_plan.reset_mock()
        app.save_journal.side_effect = OSError("Ошибка")
        with patch("guitar_practice_app.gui.messagebox.showerror"):
            app.finish_exercise()
        self.assertEqual(app.practice.session.status, "in_progress")
        app.refresh_practice_plan.assert_not_called()

    def test_empty_finish_shows_error(self):
        with patch("guitar_practice_app.gui.messagebox.showerror") as error:
            self.app.finish_exercise()
        error.assert_called_once()

    def test_failed_load_cannot_overwrite_source_file(self):
        self.app._storage_load_failed = True
        self.app.storage = Mock()
        with self.assertRaises(OSError):
            GuitarPracticeApp.save_journal(self.app)
        self.app.storage.save_journal.assert_not_called()


class SessionCompatibilityTest(unittest.TestCase):
    def test_legacy_migration_does_not_invent_attempts_or_modify_counts(self):
        journal = Journal([Exercise("Гамма")], [
            TempoLog("Гамма", 80, "восьмые", "2026-11-21", 5, 2),
            TempoLog("Гамма", 90, "восьмые", "2026-11-21", 3, 4),
        ])
        self.assertEqual(len(journal.sessions), 1)
        self.assertEqual(journal.attempts, [])
        self.assertEqual([(log.success, log.fail) for log in journal.logs], [(5, 2), (3, 4)])
        self.assertEqual(journal.sessions[0].status, "completed")
