import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock, patch

from guitar_practice_app.models import Attempt, Exercise, TempoLog
from guitar_practice_app.practice import PracticeController
from guitar_practice_app.services import AttemptStats, Journal
from guitar_practice_app.stability import StabilityResult
from guitar_practice_app.stability_ui import StabilityWindow, export_stability
from guitar_practice_app.storage import JournalStorage


NOW = datetime.fromisoformat("2026-11-21T20:00:00+03:00")


class StabilityTest(unittest.TestCase):
    def setUp(self):
        self.journal = Journal([Exercise("Этюд"), Exercise("Гамма")])
        self.stats = AttemptStats()
        self.save = Mock()
        self.practice = PracticeController(self.journal, self.save, self.stats)

    def add(self, outcomes, tempo=110, duration="восьмые", scope="", exercise="Этюд",
            timestamp="2026-11-21T12:00:00+03:00", session_date="2026-11-21"):
        self.practice.approach_id = None
        return [self.practice.record_attempt(exercise, tempo, duration, session_date, success, scope, timestamp)
                for success in outcomes]

    def result(self, tempo=110, duration="восьмые", scope=""):
        return self.journal.stability("Этюд", tempo, duration, scope, self.practice.session_id, NOW)

    def test_acceptance_five_of_five_is_not_enough(self):
        self.add([True] * 5)
        result = self.result()
        self.assertEqual(result.percent, 100)
        self.assertEqual(result.total, 5)
        self.assertEqual(result.status, "Недостаточно данных")

    def test_acceptance_seven_of_ten(self):
        self.add([True] * 7 + [False] * 3)
        self.assertEqual(self.result().percent, 70)
        self.assertEqual(self.result().status, "Повышение разрешено")

    def test_acceptance_six_of_ten(self):
        self.add([True] * 6 + [False] * 4)
        self.assertEqual(self.result().percent, 60)
        self.assertEqual(self.result().status, "Порог повышения не достигнут")

    def test_acceptance_sessions_are_pooled_not_percentages_averaged(self):
        self.add([True] * 5)
        self.practice.finish()
        self.add([True] * 2 + [False] * 3)
        result = self.result()
        self.assertEqual((result.successes, result.total), (7, 10))
        self.assertEqual(result.status, "Повышение разрешено")
        self.assertEqual(len(result.current_attempts), 5)

    def test_sessions_of_different_sizes_are_not_averaged(self):
        self.add([True])
        self.practice.finish()
        self.add([False] * 9)
        self.assertEqual(self.result().percent, 10)

    def test_acceptance_31st_excludes_first(self):
        attempts = self.add([True] + [False] * 29 + [True])
        result = self.result()
        self.assertEqual(result.total, 30)
        self.assertEqual(result.attempts[0].id, attempts[1].id)
        self.assertEqual(result.successes, 1)
        self.assertEqual(len(result.current_attempts), 31)
        self.assertEqual(len(self.journal.attempts), 31)

    def test_acceptance_bpm_and_durations_remain_distinct(self):
        self.add([True] * 10, tempo=110)
        self.add([False] * 10, tempo=112)
        self.add([False] * 10, tempo=220, duration="четверти")
        self.assertEqual(self.result(110).percent, 100)
        self.assertEqual(self.result(112).percent, 0)
        self.assertEqual(self.result(220, "четверти").percent, 0)
        self.assertEqual(len(self.journal.stability_groups("Этюд")), 3)

    def test_acceptance_fragment_does_not_influence_whole(self):
        fragment = self.journal.save_fragment("Этюд", "Переход")
        self.add([True] * 10, scope=fragment.id)
        self.assertEqual(self.result().status, "Нет данных")
        self.assertEqual(self.result(scope=fragment.id).status, "Повышение разрешено")

    def test_acceptance_correction_recalculates_immediately_in_both_directions(self):
        attempts = self.add([True] * 6 + [False] * 4)
        self.journal.correct_attempt(attempts[-1].id, True)
        self.assertEqual(self.result().status, "Повышение разрешено")
        self.assertEqual(self.journal.attempt_by_id(attempts[-1].id).sequence, attempts[-1].sequence)
        self.journal.correct_attempt(attempts[-1].id, False)
        self.assertEqual(self.result().status, "Порог повышения не достигнут")

    def test_acceptance_historical_aggregates_never_create_attempts(self):
        self.journal.add_tempo_log("Этюд", 110, "восьмые", "2026-11-21", 100, 0)
        self.assertEqual(self.result().status, "Нет данных")
        self.assertEqual(self.journal.stability_groups("Этюд"), [(110, "восьмые")])
        self.assertEqual(self.journal.attempts, [])
        self.add([False])
        self.assertEqual(self.result().percent, 0)
        self.assertEqual(self.journal.stability_export("Этюд", as_of=NOW)["historical_aggregates"][0]["success"], 100)

    def test_historical_estimate_includes_all_since_14th_and_weights_by_counts(self):
        for log_date, successes, failures in (
            ("2026-11-13", 100, 0), ("2026-11-14", 5, 0),
            ("2026-11-20", 2, 3), ("2026-11-21", 0, 10), ("2026-11-22", 100, 0),
        ):
            self.journal.add_tempo_log("Этюд", 110, "восьмые", log_date, successes, failures)
        estimate = self.journal.historical_estimate("Этюд", 110, "восьмые", as_of=NOW)
        self.assertEqual((estimate["successes"], estimate["total"]), (7, 20))
        self.assertEqual(estimate["percent"], 35)
        self.assertEqual(estimate["aggregate_count"], 3)
        self.assertFalse(estimate["used_for_status"])
        self.assertFalse(estimate["exact_order_known"])
        self.assertEqual(self.result().status, "Нет данных")

    def test_historical_estimate_never_merges_exact_counts_other_tempos_or_scopes(self):
        self.journal.add_tempo_log("Этюд", 110, "восьмые", "2026-11-14", 7, 3)
        self.journal.add_tempo_log("Этюд", 112, "восьмые", "2026-11-14", 10, 0)
        self.journal.add_tempo_log("Этюд", 220, "четверти", "2026-11-14", 10, 0)
        self.add([False] * 10)
        fragment = self.journal.save_fragment("Этюд", "Фрагмент")
        before = self.journal.snapshot()
        estimate = self.journal.historical_estimate("Этюд", 110, "восьмые", as_of=NOW)
        self.assertEqual(estimate["percent"], 70)
        self.assertEqual(self.result().percent, 0)
        self.assertEqual(self.result().status, "Порог повышения не достигнут")
        self.assertIsNone(self.journal.historical_estimate("Этюд", 110, "восьмые", fragment.id, NOW)["percent"])
        self.assertEqual(self.journal.snapshot(), before)

    def test_empty_historical_estimate_and_export(self):
        self.journal.add_tempo_log("Этюд", 110, "восьмые", "2026-11-14", 0, 0)
        estimate = self.journal.historical_estimate("Этюд", 110, "восьмые", as_of=NOW)
        self.assertIsNone(estimate["percent"])
        exported = self.journal.stability_export("Этюд", as_of=NOW)
        self.assertEqual(exported["groups"][0]["historical_estimate"], estimate)
        self.assertIsNone(estimate["window_size"])

    def test_cutoff_is_inclusive_and_uses_event_date_not_session_date(self):
        self.add([True], timestamp="2026-11-13T23:59:59+03:00", session_date="2026-11-01")
        included = self.add([False], timestamp="2026-11-14T00:00:00+03:00", session_date="2026-11-01")
        result = self.result()
        self.assertEqual(result.total, 1)
        self.assertEqual(result.attempts[0].id, included[0].id)
        self.assertEqual(result.percent, 0)
        self.assertEqual(len(result.current_attempts), 2)

    def test_future_events_not_in_as_of_snapshot(self):
        self.add([True], timestamp="2026-11-22T12:00:00+03:00")
        self.assertEqual(self.result().status, "Нет данных")

    def test_clock_reversal_does_not_reorder_events(self):
        first = self.add([True], timestamp="2026-11-21T13:00:00+03:00")[0]
        second = self.add([False], timestamp="2026-11-21T12:00:00+03:00")[0]
        self.assertEqual([a.id for a in self.result().attempts], [first.id, second.id])

    def test_threshold_checked_before_rounding(self):
        self.journal.set_window_size(1000)
        prototype = self.add([True])[0]
        events = tuple(replace(prototype, id=str(i), sequence=i + 1, success=i < 699) for i in range(999))
        result = StabilityResult(events, 1000)
        self.assertEqual(f"{result.percent:.1f}", "70.0")
        self.assertEqual(result.status, "Порог повышения не достигнут")

    def test_changing_window_changes_calculation_without_deleting_events(self):
        self.add([True] * 20 + [False] * 10)
        self.journal.set_window_size(10)
        self.assertEqual(self.result().percent, 0)
        self.journal.set_window_size("30")
        self.assertEqual(self.result().total, 30)
        self.assertEqual(len(self.journal.attempts), 30)
        for invalid in (9, 1001, 1.5, True, "bad"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.journal.set_window_size(invalid)

    def test_deletion_refills_window_from_previous_events(self):
        events = self.add([True] + [False] * 30)
        self.journal.delete_attempt(events[-1].id)
        self.assertEqual(self.result().total, 30)
        self.assertEqual(self.result().successes, 1)
        sequence = self.add([True])[0].sequence
        self.assertEqual(sequence, 32)

    def test_fragment_does_not_change_maximum_goal_or_plan_start(self):
        self.journal.add_tempo_log("Этюд", 80, "восьмые", "2026-11-20")
        self.journal.set_exercise_goal("Этюд", 100, "восьмые", as_of=date(2026, 11, 21))
        scope = self.journal.save_fragment("Этюд", "Финал").id
        self.add([True], tempo=200, scope=scope)
        self.assertEqual(self.journal.max_normalized_tempo("Этюд"), 160)
        self.assertFalse(self.journal.goal_progress("Этюд", as_of=date(2026, 11, 21)).reached)
        self.assertEqual(self.journal.last_log("Этюд").tempo, 80)
        plan = self.journal.practice_plan(as_of=date(2026, 11, 21), active_session_id=self.practice.session_id)
        self.assertEqual(next(p for p in plan if p.exercise == "Этюд").start_tempo, 72)
        self.practice.finish()
        self.assertNotIn("Этюд", [p.exercise for p in self.journal.practice_plan(as_of=date(2026, 11, 21))])

    def test_fragment_names_are_unique_within_exercise_and_id_survives_rename(self):
        fragment = self.journal.save_fragment("Этюд", "Переход")
        with self.assertRaises(ValueError):
            self.journal.save_fragment("Этюд", " переход ")
        other = self.journal.save_fragment("Гамма", "Переход")
        self.assertNotEqual(fragment.id, other.id)
        self.add([True], scope=fragment.id)
        self.journal.save_fragment("Этюд", "Начало", fragment.id)
        self.assertEqual(self.result(scope=fragment.id).total, 1)
        self.assertEqual(self.journal.scope_name("Этюд", fragment.id), "Начало")
        with self.assertRaises(ValueError):
            self.add([True], scope=other.id)

    def test_exact_log_counts_and_parameters_cannot_be_manually_changed(self):
        self.add([True, False])
        original = self.journal.logs[0]
        with self.assertRaises(ValueError):
            self.journal.update_tempo_log(0, 110, "восьмые", original.date, 2, 0)
        with self.assertRaises(ValueError):
            self.journal.update_tempo_log(0, 112, "восьмые", original.date, 1, 1)
        with self.assertRaises(ValueError):
            self.journal.delete_tempo_log(0)
        self.assertEqual(self.journal.logs[0], original)

    def test_invalid_event_cannot_be_persisted(self):
        event = self.add([True])[0]
        for changes in ({"sequence": 0}, {"success": 1}, {"recorded_at": "2026-11-21T12:00:00"},
                        {"tempo": 0}, {"duration": "unknown"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(event, **changes)

    def test_export_contains_source_events_and_exact_window_composition(self):
        self.add([True] * 7 + [False] * 3)
        exported = self.journal.stability_export("Этюд", self.practice.session_id, NOW)
        self.assertEqual(exported["metadata"]["calculated_at"], NOW.isoformat())
        self.assertEqual(exported["metadata"]["window_size"], 30)
        self.assertEqual(exported["metadata"]["cutoff"], "2026-11-14")
        self.assertEqual(exported["metadata"]["minimum_attempts"], 10)
        self.assertEqual(exported["metadata"]["success_threshold_percent"], 70)
        self.assertEqual(exported["groups"][0]["percent"], 70)
        self.assertEqual(exported["groups"][0]["window_attempt_ids"], [a.id for a in self.journal.attempts])
        self.assertEqual(len(exported["attempts"]), 10)
        json.dumps(exported)

    def test_archive_does_not_remove_attempts(self):
        self.add([True] * 10)
        self.practice.interrupt()
        self.journal.archive_exercise("Этюд")
        self.assertEqual(self.result().total, 10)
        self.journal.restore_exercise("Этюд")
        self.assertEqual(self.result().status, "Повышение разрешено")


class StabilityStorageTest(unittest.TestCase):
    def test_roundtrip_retains_events_fragments_settings_and_sequence_high_watermark(self):
        journal = Journal([Exercise("Этюд")])
        fragment = journal.save_fragment("Этюд", "Финал")
        practice = PracticeController(journal, Mock(), AttemptStats())
        for outcome in (True, False):
            practice.record_attempt("Этюд", 100, "восьмые", "2026-11-21", outcome, fragment.id)
        journal.set_window_size(50)
        journal.delete_attempt(journal.attempts[-1].id)
        with tempfile.TemporaryDirectory() as folder:
            storage = JournalStorage(Path(folder) / "journal.json")
            storage.save_journal(journal)
            loaded = storage.load_journal()
        self.assertEqual(loaded.attempts, journal.attempts)
        self.assertEqual(loaded.fragments, journal.fragments)
        self.assertEqual(loaded.settings["stability_window"], 50)
        self.assertEqual(loaded.settings["next_attempt_sequence"], 3)
        self.assertEqual(loaded.sessions[0].status, "interrupted")
        next_practice = PracticeController(loaded, Mock(), AttemptStats())
        event = next_practice.record_attempt("Этюд", 100, "восьмые", "2026-11-21", True)
        self.assertEqual(event.sequence, 3)

    def test_loading_v2_preserves_historical_counts_without_creating_attempts(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "journal.json"
            path.write_text(json.dumps({
                "version": 2, "exercises": [{"name": "Этюд"}],
                "logs": [{"exercise": "Этюд", "tempo": 110, "duration": "восьмые",
                          "date": "2026-11-20", "success": 10, "fail": 2}],
            }), encoding="utf-8")
            original = path.read_bytes()
            loaded = JournalStorage(path).load_journal()
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(loaded.attempts, [])
            self.assertEqual((loaded.logs[0].success, loaded.logs[0].fail), (10, 2))

    def test_newer_schema_is_rejected_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "journal.json"
            path.write_text('{"version":999}', encoding="utf-8")
            with self.assertRaises(ValueError):
                JournalStorage(path).load_journal()

    def test_export_writes_json_but_cannot_replace_journal(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "journal.json"
            export = Path(folder) / "export.json"
            source.write_text("original", encoding="utf-8")
            journal = Journal([Exercise("Этюд")])
            with self.assertRaises(ValueError):
                export_stability(source, journal, "Этюд", protected_path=source)
            export_stability(export, journal, "Этюд", protected_path=source)
            self.assertEqual(source.read_text(), "original")
            self.assertIn("metadata", json.loads(export.read_text()))

    def test_failed_setting_or_attempt_correction_is_rolled_back_in_ui(self):
        journal = Journal([Exercise("Этюд")])
        practice = PracticeController(journal, Mock(), AttemptStats())
        attempt = practice.record_attempt("Этюд", 110, "восьмые", "2026-11-21", True)
        window = StabilityWindow.__new__(StabilityWindow)
        window.journal = journal
        window.window = Mock()
        window.save = Mock(side_effect=OSError("Нет места"))
        window.on_change = Mock()
        window.refresh = Mock()
        with patch("guitar_practice_app.stability_ui.messagebox.showerror"):
            self.assertFalse(window.apply_change(lambda: journal.correct_attempt(attempt.id, False)))
            self.assertFalse(window.apply_change(lambda: journal.set_window_size(50)))
        self.assertTrue(journal.attempts[0].success)
        self.assertEqual(journal.settings["stability_window"], 30)
        window.on_change.assert_not_called()
