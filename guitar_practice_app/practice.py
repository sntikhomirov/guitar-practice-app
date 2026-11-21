"""Autosaved individual attempts; ending an approach never records events twice."""

from datetime import datetime
from uuid import uuid4

from guitar_practice_app.models import Attempt, PracticeSession


class PracticeController:
    def __init__(self, journal, save, stats):
        self.journal = journal
        self.save = save
        self.stats = stats
        self.session_id = None
        self.approach_id = None
        self.visible_after_sequence = 0

    @property
    def session(self):
        session = self.journal.session_by_id(self.session_id)
        return session if session and session.status == "in_progress" else None

    def transaction(self, change):
        snapshot = self.journal.snapshot()
        state = self.session_id, self.approach_id, self.visible_after_sequence
        try:
            result = change()
            self.save()
            return result
        except Exception:
            self.journal.restore(snapshot)
            self.session_id, self.approach_id, self.visible_after_sequence = state
            raise

    def record_attempt(self, exercise, tempo, duration, log_date, success, scope_id="", recorded_at=None):
        def change():
            selected = self.journal.exercise_by_name(exercise)
            if selected.archived:
                raise ValueError("Упражнение в архиве.")
            values = self.journal._make_tempo_log(exercise, tempo, duration, log_date)
            self.journal.validate_scope(exercise, scope_id)
            if self.session is None:
                session = PracticeSession(str(uuid4()), exercise, values.date)
                self.journal.sessions.append(session)
                self.session_id = session.id
            elif self.session.exercise != exercise or self.session.date != values.date:
                raise ValueError("Сначала завершите или прервите текущую отработку.")
            if self.approach_id is None:
                self.approach_id = str(uuid4())
            existing = [a for a in self.journal.attempts if a.approach_id == self.approach_id]
            if existing and (existing[0].tempo, existing[0].duration, existing[0].scope_id) != (
                    values.tempo, values.duration, scope_id):
                raise ValueError("Закройте текущий подход перед сменой параметров.")
            sequence = self.journal.settings["next_attempt_sequence"]
            attempt = Attempt(str(uuid4()), sequence, exercise, values.tempo, values.duration, success,
                              recorded_at or datetime.now().astimezone().isoformat(),
                              self.session_id, self.approach_id, scope_id)
            self.journal.attempts.append(attempt)
            self.journal.settings["next_attempt_sequence"] = sequence + 1
            self.journal.rebuild_exact_logs()
            return attempt
        attempt = self.transaction(change)
        self.sync_stats()
        return attempt

    def sync_stats(self):
        self.stats.reset()
        for attempt in sorted(self.journal.attempts, key=lambda a: a.sequence):
            if attempt.approach_id == self.approach_id and attempt.sequence > self.visible_after_sequence:
                if attempt.success:
                    self.stats.add_success()
                else:
                    self.stats.add_fail()

    def save_result(self, *parameters):
        if not self.approach_id or not any(a.approach_id == self.approach_id for a in self.journal.attempts):
            raise ValueError("В текущем подходе нет попыток. Каждая попытка сохраняется автоматически.")
        self.approach_id = None
        self.stats.reset()

    def reset_counter(self):
        self.visible_after_sequence = self.journal.settings["next_attempt_sequence"] - 1
        self.stats.reset()

    def finish(self, *parameters):
        if self.session is None:
            raise ValueError("Сначала выполните хотя бы одну попытку.")
        self.transaction(lambda: self.journal.set_session_status(self.session_id, "completed"))
        self.session_id = None
        self.approach_id = None
        self.stats.reset()

    def interrupt(self):
        if self.session is not None:
            self.transaction(lambda: self.journal.set_session_status(self.session_id, "interrupted"))
        self.session_id = None
        self.approach_id = None
        self.stats.reset()

    def change_parameters(self, old, new):
        # Fields are exercise, BPM, duration, date, scope ID.
        exercise, tempo, duration, log_date, scope = new
        self.journal.validate_scope(exercise, scope)
        if exercise and self.journal.exercise_by_name(exercise).archived:
            raise ValueError("Упражнение в архиве.")
        if old[0] != exercise:
            self.interrupt()
        else:
            if self.session is not None and self.session.date != log_date:
                raise ValueError("Дата отработки зафиксирована.")
            self.approach_id = None
            self.stats.reset()
